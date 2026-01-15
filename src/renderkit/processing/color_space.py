"""Color space conversion using Strategy pattern."""

import logging
import re
from enum import Enum
from typing import Any, Optional, Protocol

from renderkit import constants
from renderkit.exceptions import ColorSpaceError

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
_OIIO_COLOR_SPACE_CACHE: Optional[dict[str, str]] = None


def _get_oiio_color_space_map(oiio) -> dict[str, str]:
    global _OIIO_COLOR_SPACE_CACHE
    if _OIIO_COLOR_SPACE_CACHE is not None:
        return _OIIO_COLOR_SPACE_CACHE
    try:
        config = oiio.ColorConfig()
        names = config.getColorSpaceNames()
        if not names:
            raise ColorSpaceError("OCIO config does not define any color spaces.")
        _OIIO_COLOR_SPACE_CACHE = {name.lower(): name for name in names}
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
                _OIIO_COLOR_SPACE_CACHE[role.lower()] = role_name
    except Exception as e:
        raise ColorSpaceError(f"Failed to load OCIO config from OIIO: {e}") from e
    return _OIIO_COLOR_SPACE_CACHE


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


def _ensure_float_buf(oiio, buf):
    spec = buf.spec()
    if spec.format == oiio.FLOAT:
        return buf
    float_spec = oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
    float_buf = oiio.ImageBuf(float_spec)
    if not oiio.ImageBufAlgo.copy(float_buf, buf):
        raise ColorSpaceError(f"OIIO failed to convert to float: {oiio.geterror()}")
    return float_buf


def _oiio_clamp_buf(oiio, buf, min_val: float, max_val: float):
    spec = buf.spec()
    dst = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.clamp(dst, buf, min_val, max_val):
        raise ColorSpaceError(f"OIIO clamp failed: {oiio.geterror()}")
    return dst


def _oiio_tone_map_reinhard(oiio, buf):
    src = _ensure_float_buf(oiio, buf)
    spec = src.spec()
    denom = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.add(denom, src, 1.0):
        raise ColorSpaceError(f"OIIO tone map add failed: {oiio.geterror()}")
    tone = oiio.ImageBuf(oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT))
    if not oiio.ImageBufAlgo.div(tone, src, denom):
        raise ColorSpaceError(f"OIIO tone map div failed: {oiio.geterror()}")
    return _oiio_clamp_buf(oiio, tone, 0.0, 1.0)


def _oiio_colorconvert_buf(oiio, src_buf, from_spaces: list[str], to_spaces: list[str]):
    src_buf = _ensure_float_buf(oiio, src_buf)
    spec = src_buf.spec()
    channels = spec.nchannels
    if channels not in (3, 4):
        raise ColorSpaceError("Color conversion expects 3 or 4 channel images.")

    space_map = _get_oiio_color_space_map(oiio)
    from_candidates = _resolve_oiio_spaces(from_spaces, space_map)
    to_candidates = _resolve_oiio_spaces(to_spaces, space_map)

    errors: list[str] = []
    for from_space in from_candidates:
        for to_space in to_candidates:
            dst_buf = oiio.ImageBuf(
                oiio.ImageSpec(spec.width, spec.height, spec.nchannels, oiio.FLOAT)
            )
            if oiio.ImageBufAlgo.colorconvert(dst_buf, src_buf, from_space, to_space):
                return dst_buf
            err = dst_buf.geterror()
            if err:
                errors.append(err)
    if errors:
        message = " ".join(errors)
        raise ColorSpaceError(message.strip())

    raise ColorSpaceError(f"OIIO color conversion failed for '{from_spaces}' -> '{to_spaces}'.")


def _normalize_colorspace_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def get_ocio_role_space_map() -> dict[str, str]:
    try:
        import PyOpenColorIO as OCIO
    except Exception:
        return {}

    try:
        config = OCIO.GetCurrentConfig()
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
        config = OCIO.GetCurrentConfig()
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

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        """Convert an OIIO ImageBuf to a new ImageBuf."""
        ...


class OCIOColorSpaceStrategy:
    """Strategy for converting using OpenColorIO."""

    def __init__(self) -> None:
        self._output_space: Optional[str] = None
        self.config = None
        try:
            import PyOpenColorIO as OCIO
        except ImportError as e:
            raise ColorSpaceError("PyOpenColorIO not available.") from e

        try:
            self.config = OCIO.GetCurrentConfig()
        except Exception as e:
            raise ColorSpaceError(f"Failed to get OCIO config: {e}") from e

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
                return match

        # Resolve role names (e.g., "scene_linear") to their colorspace.
        try:
            if hasattr(self.config, "hasRole") and self.config.hasRole(input_space):
                resolved = self.config.getRoleColorSpace(input_space)
                if resolved:
                    return resolved
            if hasattr(self.config, "getRoleNames"):
                for role in self.config.getRoleNames():
                    if role.lower() == input_space.lower():
                        resolved = self.config.getRoleColorSpace(role)
                        if resolved:
                            return resolved
        except Exception:
            pass

        try:
            if hasattr(self.config, "getColorSpaceNameByRole"):
                resolved = self.config.getColorSpaceNameByRole(input_space)
                if resolved:
                    return resolved
        except Exception:
            pass

        return input_space

    def _resolve_output_space(self) -> str:
        if self._output_space:
            return self._output_space

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

        self._output_space = output_space
        return output_space

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        if not self.config:
            raise ColorSpaceError("OCIO config not available.")
        if not input_space:
            raise ColorSpaceError("OCIO input color space is required.")

        try:
            import OpenImageIO as oiio
        except ImportError as err:
            raise ColorSpaceError("OpenImageIO not available for color conversion.") from err

        try:
            input_space = self._resolve_input_space(input_space)
            output_space = self._resolve_output_space()
            logger.debug(f"OCIO Conversion (ImageBuf): '{input_space}' -> '{output_space}'")
            return _oiio_colorconvert_buf(oiio, buf, [input_space], [output_space])
        except Exception as e:
            raise ColorSpaceError(f"OCIO conversion error: {e}") from e


class LinearToSRGBStrategy:
    """Strategy for converting linear to sRGB color space."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        try:
            import OpenImageIO as oiio
        except ImportError as err:
            raise ColorSpaceError("OpenImageIO not available for color conversion.") from err

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

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        try:
            import OpenImageIO as oiio
        except ImportError as err:
            raise ColorSpaceError("OpenImageIO not available for color conversion.") from err

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

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        try:
            import OpenImageIO as oiio
        except ImportError as err:
            raise ColorSpaceError("OpenImageIO not available for color conversion.") from err

        srgb = _oiio_clamp_buf(oiio, buf, 0.0, 1.0)
        return _oiio_colorconvert_buf(
            oiio,
            srgb,
            _OIIO_SRGB_CANDIDATES,
            _OIIO_LINEAR_CANDIDATES,
        )


class NoConversionStrategy:
    """Strategy for no color space conversion (passthrough)."""

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        try:
            import OpenImageIO as oiio
        except ImportError as err:
            raise ColorSpaceError("OpenImageIO not available for color conversion.") from err
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

    def __init__(self, preset: ColorSpacePreset = ColorSpacePreset.LINEAR_TO_SRGB):
        """Initialize color space converter.

        Args:
            preset: Color space conversion preset
        """
        strategy_class = self._strategies.get(preset)
        if strategy_class is None:
            raise ColorSpaceError(f"Unknown color space preset: {preset}")

        self._strategy = strategy_class()

    def convert_buf(self, buf: Any, input_space: Optional[str] = None):
        """Convert an OIIO ImageBuf without round-tripping through NumPy."""
        return self._strategy.convert_buf(buf, input_space=input_space)

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
