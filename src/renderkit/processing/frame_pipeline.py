"""Shared ImageBuf frame preparation for rendering and previews."""

import getpass
import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, cast

import OpenImageIO as oiio

from renderkit.core.config import BurnInConfig, ContactSheetConfig, WatermarkConfig
from renderkit.core.sequence_names import split_numbered_frame_name
from renderkit.exceptions import ColorSpaceError, ImageReadError, VideoEncodingError
from renderkit.io.file_info import FileInfo
from renderkit.io.image_reader import ImageReader, ImageReaderFactory, LayerMapEntry
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.burnin import BurnInProcessor
from renderkit.processing.color_space import ColorSpaceConverter
from renderkit.processing.contact_sheet import ContactSheetGenerator
from renderkit.processing.scaler import ImageScaler
from renderkit.processing.watermark import WatermarkProcessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedFrameBuffer:
    """Prepared frame ImageBuf and the scale applied during preparation."""

    buf: Any
    applied_scale: float = 1.0


@dataclass(frozen=True)
class FramePreparationOptions:
    """Options for shared ImageBuf frame preparation."""

    frame_path: Path
    frame_num: int
    output_width: Optional[int]
    output_height: Optional[int]
    source_width: Optional[int]
    source_height: Optional[int]
    scaler: ImageScaler
    input_space: Optional[str]
    color_converter: ColorSpaceConverter
    reader: Optional[ImageReader] = None
    layer: Optional[str] = None
    layer_map: Optional[dict[str, LayerMapEntry]] = None
    fps: Optional[float] = None
    burnin_processor: Optional[BurnInProcessor] = None
    burnin_config: Optional[BurnInConfig] = None
    burnin_metadata: Optional[dict[str, Any]] = None
    burnin_config_adapter: Optional["BurnInConfigAdapter"] = None
    contact_sheet_generator: Optional[ContactSheetGenerator] = None
    contact_sheet_config: Optional[ContactSheetConfig] = None
    output_scale: float = 1.0
    file_info: Optional[FileInfo] = None
    contact_sheet_enabled: Optional[bool] = None
    watermark_processor: Optional[WatermarkProcessor] = None
    watermark_config: Optional[WatermarkConfig] = None


BurnInConfigAdapter = Callable[[BurnInConfig, float, int], BurnInConfig]


def expand_data_channels_to_rgb(buf: oiio.ImageBuf) -> oiio.ImageBuf:
    """Return a grayscale RGB buffer from the first channel of a data buffer."""
    display_buf = oiio.ImageBufAlgo.channels(buf, (0, 0, 0), ("R", "G", "B"))
    if display_buf.has_error:
        raise ValueError(f"Failed to prepare data-channel frame: {display_buf.geterror()}")
    return display_buf


def prepare_frame_buffer(options: FramePreparationOptions) -> PreparedFrameBuffer:
    """Read and prepare a single frame ImageBuf using the shared pipeline.

    Args:
        options: Frame preparation options.

    Returns:
        Prepared frame buffer and applied scale.
    """
    reader = _resolve_reader(options)

    if _contact_sheet_enabled(options):
        generator = _resolve_contact_sheet_generator(options, reader)
        buf = _build_contact_sheet_buffer(options, generator)
        spec = buf.spec()
        source_width, source_height = _resolve_source_size(options, spec)
        buf = _apply_color_or_data_channel_policy(options, buf)
        if isinstance(generator, ContactSheetGenerator):
            try:
                buf = generator.render_layer_labels(buf)
            except (RuntimeError, TypeError, ValueError) as e:
                raise VideoEncodingError(
                    f"Failed to build contact sheet for frame {options.frame_num}: {e}"
                ) from e
        target_width, target_height = _resolve_target_size(options, spec)
        buf, applied_scale = _apply_scaling(
            options,
            buf,
            source_width,
            source_height,
            target_width,
            target_height,
        )
        buf = _apply_burnins(options, buf, applied_scale)
        buf = _apply_watermark(options, buf)
        return PreparedFrameBuffer(buf=buf, applied_scale=applied_scale)

    buf = _read_source_buffer(options, reader)
    spec = buf.spec()
    source_width, source_height = _resolve_source_size(options, spec)
    target_width, target_height = _resolve_target_size(options, spec)
    buf, applied_scale = _apply_scaling(
        options,
        buf,
        source_width,
        source_height,
        target_width,
        target_height,
    )
    buf = _apply_color_or_data_channel_policy(options, buf)
    buf = _apply_burnins(options, buf, applied_scale)
    buf = _apply_watermark(options, buf)

    return PreparedFrameBuffer(buf=buf, applied_scale=applied_scale)


def _resolve_reader(options: FramePreparationOptions) -> ImageReader:
    if options.reader is not None:
        return options.reader
    return ImageReaderFactory.create_reader(
        options.frame_path, image_cache=get_shared_image_cache()
    )


def _resolve_contact_sheet_generator(
    options: FramePreparationOptions,
    reader: ImageReader,
) -> ContactSheetGenerator:
    if options.contact_sheet_generator is not None:
        return options.contact_sheet_generator
    return ContactSheetGenerator(
        options.contact_sheet_config or ContactSheetConfig(),
        reader=reader,
        layer_map=options.layer_map,
    )


def _build_contact_sheet_buffer(
    options: FramePreparationOptions,
    generator: Any,
) -> oiio.ImageBuf:
    try:
        if isinstance(generator, ContactSheetGenerator):
            return generator.composite_layers(options.frame_path, render_labels=False)
        return cast(oiio.ImageBuf, generator.composite_layers(options.frame_path))
    except ImageReadError as e:
        raise ImageReadError(
            f"Failed to build contact sheet for frame {options.frame_num}: {e}"
        ) from e
    except (RuntimeError, TypeError, ValueError) as e:
        raise VideoEncodingError(
            f"Failed to build contact sheet for frame {options.frame_num}: {e}"
        ) from e


def _read_source_buffer(
    options: FramePreparationOptions,
    reader: ImageReader,
) -> oiio.ImageBuf:
    if _contact_sheet_enabled(options):
        generator = _resolve_contact_sheet_generator(options, reader)
        return _build_contact_sheet_buffer(options, generator)

    try:
        return cast(
            oiio.ImageBuf,
            reader.read_imagebuf(
                options.frame_path,
                layer=options.layer,
                layer_map=options.layer_map,
            ),
        )
    except ImageReadError as e:
        raise ImageReadError(f"Failed to read frame {options.frame_num}: {e}") from e


def _contact_sheet_enabled(options: FramePreparationOptions) -> bool:
    if options.contact_sheet_enabled is not None:
        return options.contact_sheet_enabled
    return options.contact_sheet_generator is not None or options.contact_sheet_config is not None


def _resolve_source_size(
    options: FramePreparationOptions,
    spec: oiio.ImageSpec,
) -> tuple[int, int]:
    if _contact_sheet_enabled(options):
        return spec.width, spec.height
    return options.source_width or spec.width, options.source_height or spec.height


def _apply_color_or_data_channel_policy(
    options: FramePreparationOptions,
    buf: oiio.ImageBuf,
) -> oiio.ImageBuf:
    spec = buf.spec()

    if getattr(spec, "nchannels", 3) in (3, 4):
        try:
            return cast(
                oiio.ImageBuf,
                options.color_converter.convert_buf(buf, input_space=options.input_space),
            )
        except ColorSpaceError as e:
            raise ColorSpaceError(
                f"Color space conversion failed for frame {options.frame_num}: {e}"
            ) from e

    logger.debug(
        "Skipping color conversion for non-RGB frame buffer. frame=%s channels=%s",
        options.frame_num,
        spec.nchannels,
    )
    try:
        return expand_data_channels_to_rgb(buf)
    except (RuntimeError, TypeError, ValueError) as e:
        raise VideoEncodingError(
            f"Failed to prepare data-channel frame {options.frame_num}: {e}"
        ) from e


def _resolve_target_size(
    options: FramePreparationOptions,
    spec: oiio.ImageSpec,
) -> tuple[int, int]:
    target_width = options.output_width
    target_height = options.output_height
    if target_width is None or target_height is None:
        scale = min(1.0, max(0.0, options.output_scale))
        target_width = max(1, int(spec.width * scale))
        target_height = max(1, int(spec.height * scale))
    return target_width, target_height


def _apply_scaling(
    options: FramePreparationOptions,
    buf: oiio.ImageBuf,
    source_width: int,
    source_height: int,
    target_width: int,
    target_height: int,
) -> tuple[oiio.ImageBuf, float]:
    applied_scale = 1.0
    if target_width != source_width or target_height != source_height:
        try:
            buf = options.scaler.scale_buf(buf, target_width, target_height)
        except (RuntimeError, TypeError, ValueError) as e:
            raise VideoEncodingError(f"Failed to scale frame {options.frame_num}: {e}") from e
        scaled_spec = buf.spec()
        applied_scale = min(
            scaled_spec.width / float(source_width),
            scaled_spec.height / float(source_height),
        )
    return buf, applied_scale


def _apply_burnins(
    options: FramePreparationOptions,
    buf: oiio.ImageBuf,
    applied_scale: float,
) -> oiio.ImageBuf:
    if not options.burnin_config or not options.burnin_processor:
        return buf

    try:
        active_config = _resolve_burnin_config(options, buf, applied_scale)
        metadata = _resolve_burnin_metadata(options, buf=buf)
        return cast(
            oiio.ImageBuf,
            options.burnin_processor.apply_burnins(
                buf,
                metadata,
                active_config,
            ),
        )
    except (RuntimeError, TypeError, ValueError) as e:
        raise VideoEncodingError(
            f"Failed to apply burn-ins for frame {options.frame_num}: {e}"
        ) from e


def _apply_watermark(
    options: FramePreparationOptions,
    buf: oiio.ImageBuf,
) -> oiio.ImageBuf:
    if not options.watermark_config:
        return buf

    processor = options.watermark_processor or WatermarkProcessor()
    try:
        metadata = _resolve_burnin_metadata(options, buf=buf)
        return processor.apply_watermark(buf, options.watermark_config, metadata)
    except (RuntimeError, TypeError, ValueError) as e:
        raise VideoEncodingError(
            f"Failed to apply watermark for frame {options.frame_num}: {e}"
        ) from e


def _resolve_burnin_config(
    options: FramePreparationOptions,
    buf: oiio.ImageBuf,
    applied_scale: float,
) -> BurnInConfig:
    if options.burnin_config_adapter is None:
        assert options.burnin_config is not None
        return options.burnin_config

    assert options.burnin_config is not None
    return options.burnin_config_adapter(
        options.burnin_config,
        applied_scale,
        buf.spec().width,
    )


def _resolve_current_user() -> str:
    """Return the active OS username, falling back to ``'unknown'`` on error."""
    try:
        user = getpass.getuser()
        return user or "unknown"
    except Exception:
        return "unknown"


def _resolve_burnin_metadata(
    options: FramePreparationOptions,
    buf: Optional[oiio.ImageBuf] = None,
) -> dict[str, Any]:
    """Build default burn-in metadata merged with any caller-provided overrides."""
    metadata = _default_burnin_metadata(options, buf=buf)
    if isinstance(options.burnin_metadata, Mapping):
        for key, value in options.burnin_metadata.items():
            if key != "exr":
                metadata[key] = value
    return metadata


def _default_burnin_metadata(
    options: FramePreparationOptions,
    buf: Optional[oiio.ImageBuf] = None,
) -> dict[str, Any]:
    """Build default token replacement metadata for burn-in rendering."""
    if buf is not None:
        spec = buf.spec()
        width, height = spec.width, spec.height
    elif options.output_width is not None and options.output_height is not None:
        width, height = options.output_width, options.output_height
    elif options.file_info is not None:
        width, height = options.file_info.width, options.file_info.height
    elif options.source_width is not None and options.source_height is not None:
        width, height = options.source_width, options.source_height
    else:
        width, height = 0, 0

    stem = options.frame_path.stem
    split = split_numbered_frame_name(options.frame_path)
    if split is not None:
        shot = split[0].rstrip("._- ") or stem
    else:
        shot = stem.rstrip("._- ") or stem

    caller_meta = options.burnin_metadata if isinstance(options.burnin_metadata, Mapping) else None
    frame_range = (
        str(caller_meta["frame_range"])
        if caller_meta is not None and caller_meta.get("frame_range") is not None
        else str(options.frame_num)
    )

    extra_attrs = getattr(options.file_info, "attributes", None)
    exr_attrs: dict[str, Any] = dict(extra_attrs) if isinstance(extra_attrs, Mapping) else {}
    if caller_meta is not None and isinstance(caller_meta.get("exr"), Mapping):
        exr_attrs.update(caller_meta["exr"])

    core_metadata: dict[str, Any] = {
        "frame": options.frame_num,
        "frame_range": frame_range,
        "file": options.frame_path.name,
        "filename": options.frame_path.name,
        "stem": stem,
        "shot": shot,
        "fps": options.fps,
        "layer": options.layer or "RGBA",
        "colorspace": options.input_space or "Unknown",
        "resolution": f"{width}x{height}",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "user": _resolve_current_user(),
        "exr": exr_attrs,
    }

    metadata: dict[str, Any] = {}
    if isinstance(extra_attrs, Mapping):
        for key, value in extra_attrs.items():
            if key not in core_metadata:
                metadata[key] = value
    metadata.update(core_metadata)
    return metadata
