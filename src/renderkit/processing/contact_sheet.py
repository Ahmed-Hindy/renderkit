"""Contact sheet generation logic for multi-AOV per-frame composites."""

import logging
from pathlib import Path
from typing import Optional

import OpenImageIO as oiio

from renderkit.core.config import ContactSheetConfig
from renderkit.io.image_reader import ImageReader, ImageReaderFactory, LayerMapEntry
from renderkit.io.oiio_cache import get_shared_image_cache
from renderkit.processing.scaler import ImageScaler

logger = logging.getLogger(__name__)


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
            except Exception as e:
                logger.debug(f"Failed to precompute layer map for {frame_path}: {e}")

        if not layers:
            # Fallback to just reading the image if no layers detected
            return oiio.ImageBuf(str(frame_path))

        # Calculate grid dimensions
        num_layers = len(layers)
        cols = self.config.columns
        rows = (num_layers + cols - 1) // cols

        padding = self.config.padding

        subimage_buffers: dict[int, oiio.ImageBuf] = {}
        if layer_map:
            subimage_indices = set()
            for layer_name in layers:
                entry = layer_map.get(layer_name)
                if entry is not None and entry.subimage_index is not None:
                    subimage_indices.add(entry.subimage_index)
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
                except Exception as e:
                    logger.debug(f"Failed to cache subimage {subimage_index} for {frame_path}: {e}")
                    subimage_buffers = {}
                    break

        def resolve_layer_buf(layer_name: str) -> oiio.ImageBuf:
            if layer_map and subimage_buffers:
                entry = layer_map.get(layer_name)
                if entry is not None:
                    base_buf = subimage_buffers.get(entry.subimage_index)
                    if base_buf is not None:
                        if entry.channel_indices:
                            try:
                                return oiio.ImageBufAlgo.channels(base_buf, entry.channel_indices)
                            except Exception as e:
                                logger.debug(
                                    f"Failed to slice channels for {layer_name} in {frame_path}: {e}"
                                )
                        else:
                            return base_buf

            return reader.read_imagebuf(frame_path, layer=layer_name, layer_map=layer_map)

        # We'll calculate thumb_h based on the first layer's aspect ratio
        first_buf = resolve_layer_buf(layers[0])
        spec = first_buf.spec()
        h, w = spec.height, spec.width
        thumb_w, thumb_h = self.config.resolve_layer_size(w, h)

        # Label height
        label_h = 0
        label_gap = 0
        if self.config.show_labels:
            label_gap = max(4, int(self.config.font_size * 0.01))
            label_h = label_gap + int(self.config.font_size * 1.4)

        cell_w = thumb_w + (padding * 2)
        cell_h = thumb_h + (padding * 2) + label_h

        canvas_w = cell_w * cols
        canvas_h = cell_h * rows

        # Create canvas
        canvas_spec = oiio.ImageSpec(canvas_w, canvas_h, 3, oiio.FLOAT)
        canvas = oiio.ImageBuf(canvas_spec)
        oiio.ImageBufAlgo.fill(canvas, self.config.background_color)

        # Process each layer
        for i, layer_name in enumerate(layers):
            row = i // cols
            col = i % cols

            x_offset = col * cell_w + padding
            y_offset = row * cell_h + padding

            try:
                if layer_name == layers[0]:
                    layer_buf = first_buf
                else:
                    layer_buf = resolve_layer_buf(layer_name)

                if layer_buf.spec().width == thumb_w and layer_buf.spec().height == thumb_h:
                    scaled_buf = layer_buf
                else:
                    scaled_buf = self._scale_to_thumbnail(layer_buf, thumb_w, thumb_h)

                # Paste onto canvas
                oiio.ImageBufAlgo.paste(canvas, x_offset, y_offset, 0, 0, scaled_buf)

                # Add label
                if self.config.show_labels:
                    label_x = x_offset
                    label_y = (
                        y_offset
                        + thumb_h
                        + label_gap
                        + self.config.font_size
                        - max(2, int(self.config.font_size * 0.2))
                    )
                    oiio.ImageBufAlgo.render_text(
                        canvas,
                        label_x,
                        label_y,
                        layer_name,
                        fontsize=self.config.font_size,
                        textcolor=(1, 1, 1, 1),
                    )
            except Exception as e:
                logger.error(f"Failed to process layer {layer_name} for contact sheet: {e}")

        return canvas

    def _scale_to_thumbnail(self, buf: oiio.ImageBuf, width: int, height: int) -> oiio.ImageBuf:
        """Scale ImageBuf to thumbnail dimensions and return ImageBuf."""
        return ImageScaler.scale_buf(buf, width=width, height=height)
