"""Contact sheet generation logic for multi-AOV per-frame composites."""

import logging
from pathlib import Path
from typing import Optional

import OpenImageIO as oiio

from renderkit.core.config import ContactSheetConfig
from renderkit.exceptions import ImageReadError
from renderkit.io.image_reader import ImageReader, ImageReaderFactory, LayerMapEntry
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.scaler import ImageScaler

_CS_LABEL_GAP_MULTIPLIER = 0.01
_CS_LABEL_MIN_GAP = 4
_CS_LINE_HEIGHT_MULTIPLIER = 1.4

logger = logging.getLogger(__name__)


def compute_contact_sheet_label_metrics(config: ContactSheetConfig) -> tuple[int, int]:
    """Return label gap and label height for a contact sheet config."""
    if not config.show_labels:
        return 0, 0
    label_gap = max(_CS_LABEL_MIN_GAP, int(config.font_size * _CS_LABEL_GAP_MULTIPLIER))
    label_h = label_gap + int(config.font_size * _CS_LINE_HEIGHT_MULTIPLIER)
    return label_gap, label_h


class ContactSheetGenerator:
    """Generates a composite grid of all AOVs (layers) for a single image frame."""

    def __init__(
        self,
        config: ContactSheetConfig,
        reader: Optional[ImageReader] = None,
        layers: Optional[list[str]] = None,
        layer_map: Optional[dict[str, LayerMapEntry]] = None,
    ) -> None:
        """Initialize generator.

        Args:
            config: Contact sheet layout configuration
            reader: Optional reader instance to reuse across frames
            layers: Optional layer list to reuse across frames
        """
        self.config = config
        self.reader = reader
        self.layers = layers
        self.layer_map = layer_map
        if layer_map is not None:
            logger.debug("Contact sheet layer map cached at init.")

    def composite_layers(self, frame_path: Path) -> oiio.ImageBuf:
        """Composite all layers of a frame into a grid.

        Args:
            frame_path: Path to the image file (e.g. EXR)

        Returns:
            ImageBuf containing the composited grid
        """
        reader = self.reader or ImageReaderFactory.create_reader(
            frame_path, image_cache=get_shared_image_cache()
        )
        layers = self.layers or reader.get_layers(frame_path)
        layer_map = self.layer_map
        if layer_map is None and hasattr(reader, "get_layer_map"):
            try:
                layer_map = reader.get_layer_map(frame_path)
                self.layer_map = layer_map
            except ImageReadError as e:
                logger.debug(f"Failed to precompute layer map for {frame_path}: {e}")

        if not layers:
            # Fallback to just reading the image if no layers detected
            return oiio.ImageBuf(str(frame_path))

        subimage_buffers = self._build_subimage_buffers(reader, frame_path, layers, layer_map)

        # We'll calculate thumb_h based on the first layer's aspect ratio
        first_buf = self._resolve_layer_buf(
            reader,
            frame_path,
            layers[0],
            layer_map,
            subimage_buffers,
        )
        spec = first_buf.spec()
        h, w = spec.height, spec.width
        layout = self._compute_layout(len(layers), w, h)
        thumb_w = layout["thumb_w"]
        thumb_h = layout["thumb_h"]
        cell_w = layout["cell_w"]
        cell_h = layout["cell_h"]
        canvas_w = layout["canvas_w"]
        canvas_h = layout["canvas_h"]
        label_gap = layout["label_gap"]
        padding = layout["padding"]
        cols = layout["cols"]

        # Create canvas
        canvas_spec = oiio.ImageSpec(canvas_w, canvas_h, 3, oiio.FLOAT)
        canvas = oiio.ImageBuf(canvas_spec)
        oiio.ImageBufAlgo.fill(canvas, self.config.background_color)

        for i, layer_name in enumerate(layers):
            row = i // cols
            col = i % cols

            x_offset = col * cell_w + padding
            y_offset = row * cell_h + padding

            try:
                layer_buf = (
                    first_buf
                    if layer_name == layers[0]
                    else self._resolve_layer_buf(
                        reader,
                        frame_path,
                        layer_name,
                        layer_map,
                        subimage_buffers,
                    )
                )
            except ImageReadError as e:
                raise ImageReadError(
                    f"Failed to read layer '{layer_name}' for contact sheet: {e}"
                ) from e

            if layer_buf.spec().width == thumb_w and layer_buf.spec().height == thumb_h:
                scaled_buf = layer_buf
            else:
                scaled_buf = self._scale_to_thumbnail(layer_buf, thumb_w, thumb_h)

            if not oiio.ImageBufAlgo.paste(canvas, x_offset, y_offset, 0, 0, scaled_buf):
                raise RuntimeError(
                    f"Failed to paste layer '{layer_name}' into contact sheet: {oiio.geterror()}"
                )

            if self.config.show_labels:
                label_x = x_offset
                label_y = (
                    y_offset
                    + thumb_h
                    + label_gap
                    + self.config.font_size
                    - max(2, int(self.config.font_size * 0.2))
                )
                if not oiio.ImageBufAlgo.render_text(
                    canvas,
                    label_x,
                    label_y,
                    layer_name,
                    fontsize=self.config.font_size,
                    textcolor=(1, 1, 1, 1),
                ):
                    raise RuntimeError(f"Failed to render label '{layer_name}': {oiio.geterror()}")

        return canvas

    def _compute_layout(self, num_layers: int, source_w: int, source_h: int) -> dict[str, int]:
        cols = self.config.columns
        rows = (num_layers + cols - 1) // cols
        padding = self.config.padding
        thumb_w, thumb_h = self.config.resolve_layer_size(source_w, source_h)
        label_gap, label_h = self._compute_label_metrics()
        cell_w = thumb_w + (padding * 2)
        cell_h = thumb_h + (padding * 2) + label_h
        canvas_w = cell_w * cols
        canvas_h = cell_h * rows
        return {
            "cols": cols,
            "rows": rows,
            "padding": padding,
            "thumb_w": thumb_w,
            "thumb_h": thumb_h,
            "cell_w": cell_w,
            "cell_h": cell_h,
            "canvas_w": canvas_w,
            "canvas_h": canvas_h,
            "label_gap": label_gap,
            "label_h": label_h,
        }

    def _compute_label_metrics(self) -> tuple[int, int]:
        return compute_contact_sheet_label_metrics(self.config)

    def _build_subimage_buffers(
        self,
        reader: ImageReader,
        frame_path: Path,
        layers: list[str],
        layer_map: Optional[dict[str, LayerMapEntry]],
    ) -> dict[int, oiio.ImageBuf]:
        if not layer_map or not layers:
            return {}

        subimage_indices = set()
        for layer_name in layers:
            entry = layer_map.get(layer_name)
            if entry is not None and entry.subimage_index is not None:
                subimage_indices.add(entry.subimage_index)

        subimage_buffers: dict[int, oiio.ImageBuf] = {}
        for subimage_index in subimage_indices:
            try:
                if hasattr(reader, "read_subimagebuf"):
                    subimage_buffers[subimage_index] = reader.read_subimagebuf(
                        frame_path, subimage_index
                    )
                else:
                    subimage_buffers[subimage_index] = oiio.ImageBuf(
                        str(frame_path), subimage_index, 0
                    )
            except ImageReadError as e:
                logger.debug(f"Failed to cache subimage {subimage_index} for {frame_path}: {e}")
                return {}

        return subimage_buffers

    def _resolve_layer_buf(
        self,
        reader: ImageReader,
        frame_path: Path,
        layer_name: str,
        layer_map: Optional[dict[str, LayerMapEntry]],
        subimage_buffers: dict[int, oiio.ImageBuf],
    ) -> oiio.ImageBuf:
        if layer_map and subimage_buffers:
            entry = layer_map.get(layer_name)
            if entry is not None:
                base_buf = subimage_buffers.get(entry.subimage_index)
                if base_buf is not None:
                    if entry.channel_indices:
                        layer_buf = oiio.ImageBufAlgo.channels(base_buf, entry.channel_indices)
                        if layer_buf.has_error:
                            logger.debug(
                                "Failed to slice channels for %s in %s: %s",
                                layer_name,
                                frame_path,
                                layer_buf.geterror(),
                            )
                        else:
                            return layer_buf
                    else:
                        return base_buf

        return reader.read_imagebuf(frame_path, layer=layer_name, layer_map=layer_map)

    def _scale_to_thumbnail(self, buf: oiio.ImageBuf, width: int, height: int) -> oiio.ImageBuf:
        """Scale ImageBuf to thumbnail dimensions and return ImageBuf."""
        return ImageScaler.scale_buf(buf, width=width, height=height)
