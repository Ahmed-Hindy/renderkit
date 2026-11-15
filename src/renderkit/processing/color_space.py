"""Color space conversion using Strategy pattern."""

import logging
import os
import re
import sys
from enum import Enum
from pathlib import Path
from typing import Any, Optional, Protocol

import numpy as np

from renderkit import constants
from renderkit.exceptions import ColorSpaceError
from renderkit.io.oiio_utils import require_oiio

logger = logging.getLogger(__name__)

_OIIO_LINEAR_CANDIDATES = ["linear", "Linear", "scene_linear", "scene-linear"]
_OIIO_SRGB_CANDIDATES = ["sRGB", "srgb", "Output - sRGB", "srgb_display", "out_srgb"]
_OIIO_REC709_CANDIDATES = [
    "Rec709",
    "Rec.709",
    "rec709",
    "BT.709",
    "bt709",
    "Output - Rec.709",
    "Output - Rec709",
]
_OIIO_COLOR_SPACE_MAP_CACHE: dict[str, dict[str, str]] = {}
_BUNDLED_OCIO_CONFIG_CACHE: Optional[Path] = None
_OIIO_COLOR_CONVERSION_ERROR = "OpenImageIO not available for color conversion."


def _require_oiio_for_color_conversion() -> Any:
    return require_oiio(ColorSpaceError, _OIIO_COLOR_CONVERSION_ERROR)


def get_bundled_ocio_config_path() -> Path:
    """Return RenderKit's bundled OCIO config path."""
    global _BUNDLED_OCIO_CONFIG_CACHE
    if _BUNDLED_OCIO_CONFIG_CACHE is not None:
        return _BUNDLED_OCIO_CONFIG_CACHE

    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        candidates.append(Path(sys._MEIPASS) / "renderkit" / "data" / "ocio" / "config.ocio")

    candidates.append(Path(__file__).resolve().parent.parent / "data" / "ocio" / "config.ocio")

    for candidate in candidates:
        if candidate.exists():
            _BUNDLED_OCIO_CONFIG_CACHE = candidate.resolve()
            return _BUNDLED_OCIO_CONFIG_CACHE

    raise ColorSpaceError("Bundled OCIO config not found.")


def resolve_ocio_config_path(explicit_path: Optional[str | Path] = None) -> Path:
    """Resolve the OCIO config path from an explicit path, ``OCIO`` env var, or bundled config.

    Args:
        explicit_path: Optional explicit path to an OCIO configuration file.

    Returns:
        Resolved Path to a valid OCIO configuration file.

    Raises:
        ColorSpaceError: If ``explicit_path`` is provided but missing or cannot be loaded.
    """
    if explicit_path is not None:
        candidate = Path(explicit_path).expanduser()
        if not candidate.is_file():
            raise ColorSpaceError(f"OCIO config file not found: {candidate}")
        try:
            import PyOpenColorIO as ocio
        except ImportError as exc:
            raise ColorSpaceError("PyOpenColorIO not available.") from exc
        try:
            ocio.Config.CreateFromFile(str(candidate))
        except Exception as exc:
            raise ColorSpaceError(f"Failed to load OCIO config '{candidate}': {exc}") from exc
        return candidate.resolve()

    env_ocio = os.environ.get("OCIO")
    if env_ocio:
        env_candidate = Path(env_ocio).expanduser()
        if env_candidate.is_file():
            try:
                import PyOpenColorIO as ocio

                ocio.Config.CreateFromFile(str(env_candidate))
                return env_candidate.resolve()
            except Exception as exc:
                logger.warning(
                    "Invalid OCIO config at OCIO='%s' (%s); falling back to bundled config.",
                    env_ocio,
                    exc,
                )
        else:
            logger.warning(
                "OCIO environment variable points to non-existent file '%s'; "
                "falling back to bundled config.",
                env_ocio,
            )

    return get_bundled_ocio_config_path()


def get_ocio_displays(config_path: Optional[str | Path] = None) -> list[str]:
    """Return available OCIO display names for the resolved configuration.

    Args:
        config_path: Optional explicit OCIO config path.

    Returns:
        List of display names defined in the OCIO configuration.

    Raises:
        ColorSpaceError: If PyOpenColorIO is unavailable or the config cannot be loaded.
    """
    resolved_path = resolve_ocio_config_path(config_path)
    try:
        import PyOpenColorIO as ocio
    except ImportError as exc:
        raise ColorSpaceError("PyOpenColorIO not available.") from exc
    try:
        cfg = ocio.Config.CreateFromFile(str(resolved_path))
        return list(cfg.getDisplays())
    except Exception as exc:
        raise ColorSpaceError(
            f"Failed to read OCIO displays from '{resolved_path}': {exc}"
        ) from exc


def get_ocio_views(display: str, config_path: Optional[str | Path] = None) -> list[str]:
    """Return available OCIO view names for a display in the resolved configuration.

    Args:
        display: Target OCIO display name.
        config_path: Optional explicit OCIO config path.

    Returns:
        List of view names registered for ``display``.

    Raises:
        ColorSpaceError: If PyOpenColorIO is unavailable or the config cannot be loaded.
    """
    resolved_path = resolve_ocio_config_path(config_path)
    try:
        import PyOpenColorIO as ocio
    except ImportError as exc:
        raise ColorSpaceError("PyOpenColorIO not available.") from exc
    try:
        cfg = ocio.Config.CreateFromFile(str(resolved_path))
        return list(cfg.getViews(display))
    except Exception as exc:
        raise ColorSpaceError(
            f"Failed to read OCIO views for display '{display}' from '{resolved_path}': {exc}"
        ) from exc


def _summarize_list(values: list[str], max_items: int = 20) -> str:
    if not values:
        return "[]"
    if len(values) <= max_items:
        return str(values)
    shown = values[:max_items]
    return f"{shown} ... (+{len(values) - max_items} more)"


def _count_crlf_pairs(data: bytes) -> int:
    return data.count(b"\r\n")


def _get_oiio_color_space_map(
    oiio: Any, config_path: Optional[str | Path] = None
) -> dict[str, str]:
    resolved_config_path = str(
        config_path if config_path is not None else get_bundled_ocio_config_path()
    )
    cached = _OIIO_COLOR_SPACE_MAP_CACHE.get(resolved_config_path)
    if cached is not None:
        return cached
    try:
        config = oiio.ColorConfig(resolved_config_path)
        names = config.getColorSpaceNames()
        if not names:
            raise ColorSpaceError("OCIO config does not define any color spaces.")
        space_map: dict[str, str] = {name.lower(): name for name in names}
        role_candidates = [
            "scene_linear",
            "reference",
            "default",
            "data",
            "color_picking",
            "interchange_display",
            "interchange_scene",
            "compositing_log",
            "texture_paint",
            "matte_paint",
            "rendering",
        ]
        for role in role_candidates:
            try:
                role_name = config.getColorSpaceNameByRole(role)
            except Exception:
                role_name = None
            if role_name:
                space_map[role.lower()] = role_name
    except Exception as e:
        raise ColorSpaceError(f"Failed to load OCIO config from OIIO: {e}") from e
    _OIIO_COLOR_SPACE_MAP_CACHE[resolved_config_path] = space_map
    return space_map


def _resolve_oiio_spaces(candidates: list[str], space_map: dict[str, str]) -> list[str]:
    if not space_map:
        return candidates
    resolved = []
    for name in candidates:
        key = name.lower()
        actual = space_map.get(key)
        if actual:
            resolved.append(actual)
            continue
        normalized = key.replace("-", "_").replace(" ", "_")
        actual = space_map.get(normalized)
        if actual:
            resolved.append(actual)
    return resolved or candidates


def _ensure_float_buf(oiio: Any, buf: Any) -> Any:
    spec = buf.spec()
    if spec.format == oiio.FLOAT:
        return buf
    float_spec = oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
    float_buf = oiio.ImageBuf(float_spec)
    if not oiio.ImageBufAlgo.copy(float_buf, buf):
        raise ColorSpaceError(f"OIIO failed to convert to float: {oiio.geterror()}")
    return float_buf


def _apply_exposure_buf(buf: Any, exposure: float) -> Any:
    """Scale scene-linear RGB channels by ``2 ** exposure`` while preserving alpha.

    Args:
        buf: Source OIIO ImageBuf.
        exposure: Exposure adjustment in stops.

    Returns:
        Exposure-adjusted OIIO ImageBuf (or ``buf`` unchanged if ``abs(exposure) <= 1e-6``).
    """
    if abs(exposure) <= 1e-6:
        return buf
    oiio = _require_oiio_for_color_conversion()
    src = _ensure_float_buf(oiio, buf)
    spec = src.spec()
    mult = float(2.0**exposure)
    scale: Any = (mult, mult, mult, 1.0) if spec.nchannels >= 4 else mult
    dst = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.mul(dst, src, scale):
        raise ColorSpaceError(
            f"OIIO exposure adjustment failed: {dst.geterror() or oiio.geterror()}"
        )
    return dst


def _apply_gamma_buf(buf: Any, gamma: float) -> Any:
    """Apply display gamma ``pow(max(rgb, 0), 1 / gamma)`` while preserving alpha.

    Args:
        buf: Source OIIO ImageBuf.
        gamma: Display gamma exponent (must be greater than 0).

    Returns:
        Gamma-adjusted OIIO ImageBuf (or ``buf`` unchanged if ``abs(gamma - 1.0) <= 1e-6``).

    Raises:
        ColorSpaceError: If ``gamma <= 0`` or an OIIO operation fails.
    """
    if gamma <= 0:
        raise ColorSpaceError("Gamma must be greater than 0.")
    if abs(gamma - 1.0) <= 1e-6:
        return buf
    oiio = _require_oiio_for_color_conversion()
    src = _ensure_float_buf(oiio, buf)
    spec = src.spec()
    clamped = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.max(clamped, src, 0.0):
        raise ColorSpaceError(f"OIIO gamma clamp failed: {clamped.geterror() or oiio.geterror()}")
    inv_g = float(1.0 / gamma)
    exponent: Any = (inv_g, inv_g, inv_g, 1.0) if spec.nchannels >= 4 else inv_g
    dst = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.pow(dst, clamped, exponent):
        raise ColorSpaceError(f"OIIO gamma adjustment failed: {dst.geterror() or oiio.geterror()}")
    return dst


def _oiio_clamp_buf(oiio: Any, buf: Any, min_val: float, max_val: float) -> Any:
    spec = buf.spec()
    dst = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.clamp(dst, buf, min_val, max_val):
        raise ColorSpaceError(f"OIIO clamp failed: {oiio.geterror()}")
    return dst


def _oiio_tone_map_reinhard(oiio: Any, buf: Any) -> Any:
    src = _ensure_float_buf(oiio, buf)
    spec = src.spec()
    denom = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.add(denom, src, 1.0):
        raise ColorSpaceError(f"OIIO tone map add failed: {oiio.geterror()}")
    tone = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.div(tone, src, denom):
        raise ColorSpaceError(f"OIIO tone map div failed: {oiio.geterror()}")
    return _oiio_clamp_buf(oiio, tone, 0.0, 1.0)


def _oiio_colorconvert_buf(
    oiio: Any,
    src_buf: Any,
    from_spaces: list[str],
    to_spaces: list[str],
    config_path: Optional[str | Path] = None,
) -> Any:
    src_buf = _ensure_float_buf(oiio, src_buf)
    spec = src_buf.spec()
    channels = spec.nchannels
    if channels not in (3, 4):
        raise ColorSpaceError("Color conversion expects 3 or 4 channel images.")

    resolved_color_config_path = str(
        config_path if config_path is not None else get_bundled_ocio_config_path()
    )
    space_map = _get_oiio_color_space_map(oiio, resolved_color_config_path)
    from_candidates = _resolve_oiio_spaces(from_spaces, space_map)
    to_candidates = _resolve_oiio_spaces(to_spaces, space_map)

    errors: list[str] = []
    for from_space in from_candidates:
        for to_space in to_candidates:
            dst_buf = oiio.ImageBuf(
                oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
            )
            if oiio.ImageBufAlgo.colorconvert(
                dst_buf,
                src_buf,
                from_space,
                to_space,
                unpremult=True,
                colorconfig=resolved_color_config_path,
            ):
                return dst_buf
            err = dst_buf.geterror()
            if err:
                errors.append(err)
    if errors:
        available_spaces = sorted(set(space_map.values()))
        logger.error(
            "OIIO colorconvert failed after %s attempts. from_candidates=%s to_candidates=%s "
            "available_spaces_count=%s available_spaces_sample=%s errors=%s oiio_error=%s",
            len(from_candidates) * len(to_candidates),
            from_candidates,
            to_candidates,
            len(available_spaces),
            _summarize_list(available_spaces),
            _summarize_list(errors, max_items=10),
            oiio.geterror(),
        )
        message = " ".join(errors)
        raise ColorSpaceError(message.strip())

    available_spaces = sorted(set(space_map.values()))
    logger.error(
        "OIIO colorconvert failed with no detailed OIIO error. from_spaces=%s to_spaces=%s "
        "from_candidates=%s to_candidates=%s available_spaces_count=%s available_spaces_sample=%s",
        from_spaces,
        to_spaces,
        from_candidates,
        to_candidates,
        len(available_spaces),
        _summarize_list(available_spaces),
    )
    raise ColorSpaceError(f"OIIO color conversion failed for '{from_spaces}' -> '{to_spaces}'.")


def _normalize_colorspace_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def get_ocio_role_space_map() -> dict[str, str]:
    try:
        import PyOpenColorIO as OCIO
    except Exception:
        return {}

    try:
        config = OCIO.Config.CreateFromFile(str(get_bundled_ocio_config_path()))
        roles = list(config.getRoleNames())
    except Exception:
        return {}

    role_map: dict[str, str] = {}
    for role in roles:
        try:
            space = config.getRoleColorSpace(role)
        except Exception:
            space = None
        if space:
            role_map[role] = space

    return role_map


def get_ocio_role_display_options() -> list[tuple[str, str]]:
    role_map = get_ocio_role_space_map()
    if not role_map:
        return []

    options: list[tuple[str, str]] = []
    for role in sorted(role_map):
        options.append((f"{role} ({role_map[role]})", role))

    return options


def get_ocio_colorspace_label(name: str) -> Optional[str]:
    try:
        import PyOpenColorIO as OCIO
    except Exception:
        return None

    try:
        config = OCIO.Config.CreateFromFile(str(get_bundled_ocio_config_path()))
        spaces = set(config.getColorSpaceNames())
    except Exception:
        return None

    if name in spaces:
        return name

    lowered = {space.lower(): space for space in spaces}
    return lowered.get(name.lower())


def resolve_ocio_role_label_for_colorspace(
    colorspace_name: str,
    preferred_roles: Optional[list[str]] = None,
) -> Optional[str]:
    if not colorspace_name:
        return None

    role_map = get_ocio_role_space_map()
    if not role_map:
        return None

    target_key = _normalize_colorspace_key(colorspace_name)
    matching_roles = [
        role for role, space in role_map.items() if _normalize_colorspace_key(space) == target_key
    ]
    if not matching_roles:
        return None

    if preferred_roles:
        preferred_lower = [role.lower() for role in preferred_roles]
        for pref in preferred_lower:
            for role in matching_roles:
                if role.lower() == pref:
                    return f"{role} ({role_map[role]})"

    role = sorted(matching_roles)[0]
    return f"{role} ({role_map[role]})"


class ColorSpacePreset(Enum):
    """Color space conversion presets."""

    LINEAR_TO_SRGB = "linear_to_srgb"
    LINEAR_TO_REC709 = "linear_to_rec709"
    SRGB_TO_LINEAR = "srgb_to_linear"
    NO_CONVERSION = "no_conversion"
    OCIO_CONVERSION = "ocio_conversion"


class ColorSpaceStrategy(Protocol):
    """Protocol for color space conversion strategies."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        """Convert an OIIO ImageBuf to a new ImageBuf."""
        ...


class OCIOColorSpaceStrategy:
    """Strategy for converting using OpenColorIO."""

    def __init__(
        self,
        input_space: Optional[str] = None,
        output_space: Optional[str] = None,
        *,
        config_path: Optional[str | Path] = None,
        display: Optional[str] = None,
        view: Optional[str] = None,
        exposure: float = 0.0,
        gamma: float = 1.0,
    ) -> None:
        """Initialize the OpenColorIO color conversion strategy.

        Args:
            input_space: Optional default input color space name or role.
            output_space: Optional explicit output color space name or role.
            config_path: Optional explicit OCIO config file path.
            display: Optional OCIO display name (triggers display/view transform).
            view: Optional OCIO view name (triggers display/view transform).
            exposure: Scene-linear exposure adjustment in stops applied before OCIO.
            gamma: Display gamma exponent applied after OCIO (must be greater than 0).

        Raises:
            ColorSpaceError: If ``gamma <= 0``, PyOpenColorIO is unavailable, the config
                cannot be loaded, or the requested display/view is invalid.
        """
        if gamma <= 0:
            raise ColorSpaceError("Gamma must be greater than 0.")

        self.input_space = input_space
        self.output_space = output_space
        self._output_space: Optional[str] = output_space
        self.exposure = float(exposure)
        self.gamma = float(gamma)
        self.config: Optional[Any] = None
        self._resolved_display: Optional[str] = None
        self._resolved_view: Optional[str] = None

        try:
            import PyOpenColorIO as OCIO
        except ImportError as e:
            raise ColorSpaceError("PyOpenColorIO not available.") from e

        resolved_path = resolve_ocio_config_path(config_path)
        self.config_path = resolved_path
        self._config_path = resolved_path

        try:
            self.config = OCIO.Config.CreateFromFile(str(self._config_path))
        except Exception as e:
            raise ColorSpaceError(f"Failed to load OCIO config '{self._config_path}': {e}") from e

        if display is not None or view is not None:
            available_displays = list(self.config.getDisplays())
            resolved_display = display if display is not None else self.config.getDefaultDisplay()
            if not resolved_display or resolved_display not in available_displays:
                raise ColorSpaceError(
                    f"OCIO display '{resolved_display}' not found in config '{self._config_path}'. "
                    f"Available displays: {available_displays}"
                )
            available_views = list(self.config.getViews(resolved_display))
            resolved_view = (
                view if view is not None else self.config.getDefaultView(resolved_display)
            )
            if not resolved_view or resolved_view not in available_views:
                raise ColorSpaceError(
                    f"OCIO view '{resolved_view}' not found for display '{resolved_display}' "
                    f"in config '{self._config_path}'. Available views: {available_views}"
                )
            self._resolved_display = resolved_display
            self._resolved_view = resolved_view

    def _resolve_input_space(self, input_space: str) -> str:
        if not input_space or not self.config:
            return input_space

        try:
            spaces = set(self.config.getColorSpaceNames())
        except Exception:
            spaces = set()

        if input_space in spaces:
            return input_space

        if spaces:
            lowered = {name.lower(): name for name in spaces}
            match = lowered.get(input_space.lower())
            if match:
                return str(match)

        # Resolve role names (e.g., "scene_linear") to their colorspace.
        try:
            if hasattr(self.config, "hasRole") and self.config.hasRole(input_space):
                resolved = self.config.getRoleColorSpace(input_space)
                if resolved:
                    return str(resolved)
            if hasattr(self.config, "getRoleNames"):
                for role in self.config.getRoleNames():
                    if role.lower() == input_space.lower():
                        resolved = self.config.getRoleColorSpace(role)
                        if resolved:
                            return str(resolved)
        except Exception as exc:
            logger.debug("Failed to resolve OCIO input role '%s': %s", input_space, exc)

        try:
            if hasattr(self.config, "getColorSpaceNameByRole"):
                resolved = self.config.getColorSpaceNameByRole(input_space)
                if resolved:
                    return str(resolved)
        except Exception as exc:
            logger.debug("Failed to resolve OCIO role via OIIO API '%s': %s", input_space, exc)

        return input_space

    def _resolve_output_space(self) -> str:
        if self.output_space:
            return self._resolve_input_space(self.output_space)
        if self._output_space:
            return self._output_space
        if self.config is None:
            raise ColorSpaceError("OCIO config not available.")

        # Common display spaces in OCIO configs
        output_candidates = constants.OCIO_OUTPUT_CANDIDATES
        output_space = None

        all_spaces = self.config.getColorSpaceNames()
        for candidate in output_candidates:
            if candidate in all_spaces:
                output_space = candidate
                break

        if not output_space:
            # Try finding a display view
            display = self.config.getDefaultDisplay()
            view = self.config.getDefaultView(display)
            output_space = self.config.getDisplayViewColorSpaceName(display, view)

        if not output_space:
            raise ColorSpaceError("Could not find suitable OCIO output space.")

        resolved_output = str(output_space)
        self._output_space = resolved_output
        return resolved_output

    def _log_ocio_failure_diagnostics(
        self,
        requested_input_space: str,
        resolved_input_space: Optional[str],
        resolved_output_space: Optional[str],
        error: Exception,
    ) -> None:
        config_version = "unknown"
        search_path = "unknown"
        default_display = "unknown"
        default_view = "unknown"
        display_view_space = "unknown"
        colorspaces: list[str] = []
        roles: list[str] = []
        processor_status = "not-attempted"
        config_file_crlf = "unknown"
        lut_sources_count = 0
        lut_diagnostics: list[str] = []
        config_path: Optional[Path] = getattr(self, "config_path", None)
        config = self.config

        if config is not None:
            try:
                major = config.getMajorVersion()
                minor = config.getMinorVersion()
                config_version = f"{major}.{minor}"
            except Exception as exc:
                config_version = f"unavailable: {exc}"

            try:
                search_path = str(config.getSearchPath())
            except Exception as exc:
                search_path = f"unavailable: {exc}"

            try:
                colorspaces = sorted(config.getColorSpaceNames())
            except Exception as exc:
                colorspaces = [f"unavailable: {exc}"]

            try:
                role_names = sorted(config.getRoleNames())
                roles = [f"{role}={config.getRoleColorSpace(role)}" for role in role_names]
            except Exception as exc:
                roles = [f"unavailable: {exc}"]

            try:
                default_display = str(config.getDefaultDisplay())
                default_view = str(config.getDefaultView(default_display))
                display_view_space = str(
                    config.getDisplayViewColorSpaceName(default_display, default_view)
                )
            except Exception as exc:
                default_display = f"unavailable: {exc}"

            if resolved_input_space and resolved_output_space:
                try:
                    config.getProcessor(resolved_input_space, resolved_output_space)
                    processor_status = "ok"
                except Exception as proc_error:
                    processor_status = f"failed: {proc_error}"

        if config_path and config_path.exists():
            try:
                ocio_path = config_path
                config_bytes = ocio_path.read_bytes()
                config_file_crlf = str(_count_crlf_pairs(config_bytes))
                config_text = config_bytes.decode("utf-8", errors="replace")
                lut_sources = sorted(set(re.findall(r"src:\s*([^\s,}]+)", config_text)))
                lut_sources_count = len(lut_sources)
                for lut_source in lut_sources[:20]:
                    lut_path = ocio_path.parent / "luts" / lut_source
                    if not lut_path.exists():
                        lut_diagnostics.append(f"{lut_source}:missing")
                        continue
                    lut_bytes = lut_path.read_bytes()
                    lut_diagnostics.append(
                        f"{lut_source}:size={len(lut_bytes)}:crlf={_count_crlf_pairs(lut_bytes)}"
                    )
                if len(lut_sources) > 20:
                    lut_diagnostics.append(f"... (+{len(lut_sources) - 20} more LUT refs)")
            except Exception as io_error:
                lut_diagnostics.append(f"lut_diagnostics_failed={io_error}")

        logger.error(
            "OCIO diagnostics: error=%s requested_input=%s resolved_input=%s resolved_output=%s "
            "config_path=%s config_exists=%s config_version=%s search_path=%s "
            "default_display=%s default_view=%s display_view_space=%s processor_status=%s "
            "colorspaces_count=%s colorspaces_sample=%s roles=%s "
            "config_crlf=%s lut_sources_count=%s lut_diagnostics=%s",
            error,
            requested_input_space,
            resolved_input_space,
            resolved_output_space,
            config_path,
            bool(config_path and config_path.exists()),
            config_version,
            search_path,
            default_display,
            default_view,
            display_view_space,
            processor_status,
            len(colorspaces),
            _summarize_list(colorspaces),
            _summarize_list(roles, max_items=15),
            config_file_crlf,
            lut_sources_count,
            _summarize_list(lut_diagnostics, max_items=20),
        )

    def _apply_display_view_fallback(self, oiio: Any, work_buf: Any, canonical_in: str) -> Any:
        """Apply OCIO display/view transform via PyOpenColorIO CPUProcessor."""
        import PyOpenColorIO as ocio

        if self.config is None:
            raise ColorSpaceError("OCIO config not available.")

        spec = work_buf.spec()
        if spec.nchannels not in (3, 4):
            raise ColorSpaceError("Color conversion expects 3 or 4 channel images.")

        processor = self.config.getProcessor(
            canonical_in,
            self._resolved_display,
            self._resolved_view,
            ocio.TRANSFORM_DIR_FORWARD,
        )
        cpu = processor.getDefaultCPUProcessor()

        pixels = work_buf.get_pixels(oiio.FLOAT)
        if pixels.ndim == 1:
            pixels = pixels.reshape((spec.height, spec.width, spec.nchannels))
        pixels = np.ascontiguousarray(pixels, dtype=np.float32).copy()

        if spec.nchannels == 3:
            cpu.applyRGB(pixels)
        else:
            cpu.applyRGBA(pixels)

        dst = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
        dst.set_pixels(oiio.ROI(), pixels)
        return dst

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        """Convert an OIIO ImageBuf using OCIO colorspace or display/view transforms."""
        if not self.config:
            raise ColorSpaceError("OCIO config not available.")

        requested_input_space = input_space if input_space is not None else self.input_space
        if not requested_input_space:
            raise ColorSpaceError("OCIO input color space is required.")

        oiio = _require_oiio_for_color_conversion()

        resolved_input_space: Optional[str] = requested_input_space
        resolved_output_space: Optional[str] = None
        try:
            canonical_in = self._resolve_input_space(requested_input_space)
            resolved_input_space = canonical_in

            work_buf = _apply_exposure_buf(buf, self.exposure)

            if self._resolved_display is not None and self._resolved_view is not None:
                work_buf = _ensure_float_buf(oiio, work_buf)
                spec = work_buf.spec()
                if spec.nchannels not in (3, 4):
                    raise ColorSpaceError("Color conversion expects 3 or 4 channel images.")
                resolved_output_space = f"{self._resolved_display}/{self._resolved_view}"
                logger.debug(
                    "OCIO Display/View Conversion: requested_input='%s' resolved_input='%s' "
                    "display='%s' view='%s'",
                    requested_input_space,
                    canonical_in,
                    self._resolved_display,
                    self._resolved_view,
                )
                dst = oiio.ImageBuf(
                    oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
                )
                ociodisplay_ok = False
                ociodisplay_err: Optional[str] = None
                try:
                    ociodisplay_ok = bool(
                        oiio.ImageBufAlgo.ociodisplay(
                            dst,
                            work_buf,
                            self._resolved_display,
                            self._resolved_view,
                            fromspace=canonical_in,
                            colorconfig=str(self._config_path),
                        )
                    )
                    if not ociodisplay_ok:
                        ociodisplay_err = dst.geterror() or oiio.geterror() or "unknown error"
                except Exception as exc:
                    ociodisplay_err = str(exc)

                if ociodisplay_ok:
                    converted_buf = dst
                else:
                    logger.debug(
                        "OIIO ociodisplay failed (%s); falling back to PyOpenColorIO CPUProcessor.",
                        ociodisplay_err,
                    )
                    converted_buf = self._apply_display_view_fallback(oiio, work_buf, canonical_in)
            else:
                resolved_output_space = self._resolve_output_space()
                logger.debug(
                    "OCIO Conversion (ImageBuf): requested_input='%s' resolved_input='%s' "
                    "output='%s'",
                    requested_input_space,
                    canonical_in,
                    resolved_output_space,
                )
                converted_buf = _oiio_colorconvert_buf(
                    oiio,
                    work_buf,
                    [canonical_in],
                    [resolved_output_space],
                    config_path=self._config_path,
                )

            return _apply_gamma_buf(converted_buf, self.gamma)
        except Exception as e:
            self._log_ocio_failure_diagnostics(
                requested_input_space=requested_input_space,
                resolved_input_space=resolved_input_space,
                resolved_output_space=resolved_output_space,
                error=e,
            )
            raise ColorSpaceError(f"OCIO conversion error: {e}") from e


class LinearToSRGBStrategy:
    """Strategy for converting linear to sRGB color space."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        oiio = _require_oiio_for_color_conversion()

        tone_mapped = _oiio_tone_map_reinhard(oiio, buf)
        oiio_result = _oiio_colorconvert_buf(
            oiio,
            tone_mapped,
            _OIIO_LINEAR_CANDIDATES,
            _OIIO_SRGB_CANDIDATES,
        )
        return _oiio_clamp_buf(oiio, oiio_result, 0.0, 1.0)


class LinearToRec709Strategy:
    """Strategy for converting linear to Rec.709 color space."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        oiio = _require_oiio_for_color_conversion()

        tone_mapped = _oiio_tone_map_reinhard(oiio, buf)
        oiio_result = _oiio_colorconvert_buf(
            oiio,
            tone_mapped,
            _OIIO_LINEAR_CANDIDATES,
            _OIIO_REC709_CANDIDATES,
        )
        return _oiio_clamp_buf(oiio, oiio_result, 0.0, 1.0)


class SRGBToLinearStrategy:
    """Strategy for converting sRGB to linear color space."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        oiio = _require_oiio_for_color_conversion()

        srgb = _oiio_clamp_buf(oiio, buf, 0.0, 1.0)
        return _oiio_colorconvert_buf(
            oiio,
            srgb,
            _OIIO_SRGB_CANDIDATES,
            _OIIO_LINEAR_CANDIDATES,
        )


class NoConversionStrategy:
    """Strategy for no color space conversion (passthrough)."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        oiio = _require_oiio_for_color_conversion()
        return _ensure_float_buf(oiio, buf)


class ColorSpaceConverter:
    """Color space converter using Strategy pattern."""

    _strategies: dict[ColorSpacePreset, type[ColorSpaceStrategy]] = {
        ColorSpacePreset.LINEAR_TO_SRGB: LinearToSRGBStrategy,
        ColorSpacePreset.LINEAR_TO_REC709: LinearToRec709Strategy,
        ColorSpacePreset.SRGB_TO_LINEAR: SRGBToLinearStrategy,
        ColorSpacePreset.NO_CONVERSION: NoConversionStrategy,
        ColorSpacePreset.OCIO_CONVERSION: OCIOColorSpaceStrategy,
    }

    def __init__(
        self,
        preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB,
        *,
        ocio_config_path: Optional[str | Path] = None,
        ocio_display: Optional[str] = None,
        ocio_view: Optional[str] = None,
        ocio_output_space: Optional[str] = None,
        exposure: float = 0.0,
        gamma: float = 1.0,
    ) -> None:
        """Initialize color space converter.

        Args:
            preset: Color space conversion preset.
            ocio_config_path: Optional explicit OCIO config path (forces OCIO strategy).
            ocio_display: Optional OCIO display name (forces OCIO strategy).
            ocio_view: Optional OCIO view name (forces OCIO strategy).
            ocio_output_space: Optional OCIO output space (forces OCIO strategy).
            exposure: Scene-linear exposure adjustment in stops.
            gamma: Display gamma exponent (must be greater than 0).

        Raises:
            ColorSpaceError: If ``gamma <= 0`` or ``preset`` is unknown.
        """
        if gamma <= 0:
            raise ColorSpaceError("Gamma must be greater than 0.")

        self._exposure = float(exposure)
        self._gamma = float(gamma)

        use_ocio = any(
            opt is not None
            for opt in (ocio_config_path, ocio_display, ocio_view, ocio_output_space)
        )
        effective_preset = ColorSpacePreset.OCIO_CONVERSION if use_ocio else preset

        strategy_class = self._strategies.get(effective_preset)
        if strategy_class is None:
            raise ColorSpaceError(f"Unknown color space preset: {effective_preset}")

        if isinstance(strategy_class, type) and issubclass(strategy_class, OCIOColorSpaceStrategy):
            self._strategy: ColorSpaceStrategy = strategy_class(
                output_space=ocio_output_space,
                config_path=ocio_config_path,
                display=ocio_display,
                view=ocio_view,
                exposure=self._exposure,
                gamma=self._gamma,
            )
            self._apply_grade_in_converter = False
        else:
            self._strategy = strategy_class()
            self._apply_grade_in_converter = True

    @property
    def strategy(self) -> ColorSpaceStrategy:
        """Return the active color space conversion strategy."""
        return self._strategy

    def convert_buf(self, buf: Any, input_space: Optional[str] = None) -> Any:
        """Convert an OIIO ImageBuf without round-tripping through NumPy."""
        if self._apply_grade_in_converter:
            work_buf = _apply_exposure_buf(buf, self._exposure)
            converted = self.strategy.convert_buf(work_buf, input_space=input_space)
            return _apply_gamma_buf(converted, self._gamma)
        return self.strategy.convert_buf(buf, input_space=input_space)

    @classmethod
    def register_strategy(
        cls, preset: ColorSpacePreset, strategy_class: type[ColorSpaceStrategy]
    ) -> None:
        """Register a custom color space conversion strategy.

        Args:
            preset: Color space preset enum
            strategy_class: Strategy class to register
        """
        cls._strategies[preset] = strategy_class
