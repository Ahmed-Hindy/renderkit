"""Contact sheet generation logic for multi-AOV per-frame composites."""

import logging
from pathlib import Path

import numpy as np
import OpenImageIO as oiio

from renderkit.core.config import ContactSheetConfig
from renderkit.io.image_reader import ImageReaderFactory
from renderkit.processing.scaler import ImageScaler

logger = logging.getLogger(__name__)


class ContactSheetGenerator:
    """Generates a composite grid of all AOVs (layers) for a single image frame."""

    def __init__(self, config: ContactSheetConfig) -> None:
        """Initialize generator.

        Args:
            config: Contact sheet layout configuration
        """
        self.config = config

    def composite_layers(self, frame_path: Path) -> oiio.ImageBuf:
        """Composite all layers of a frame into a grid.

        Args:
            frame_path: Path to the image file (e.g. EXR)

        Returns:
            ImageBuf containing the composited grid
        """
        reader = ImageReaderFactory.create_reader(frame_path)
        layers = reader.get_layers(frame_path)

        if not layers:
            # Fallback to just reading the image if no layers detected
            return oiio.ImageBuf(str(frame_path))

        # Calculate grid dimensions
        num_layers = len(layers)
        cols = self.config.columns
        rows = (num_layers + cols - 1) // cols

        thumb_w = self.config.thumbnail_width
        padding = self.config.padding

        # We'll calculate thumb_h based on the first layer's aspect ratio
        first_pixels = reader.read(frame_path, layer=layers[0])
        h, w = first_pixels.shape[:2]
        aspect = h / w
        thumb_h = int(thumb_w * aspect)

        # Label height
        label_h = 0
        if self.config.show_labels:
            label_h = int(self.config.font_size * 2.5)

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
                # Read layer
                layer_pixels = reader.read(frame_path, layer=layer_name)

                # Resize to thumbnail
                scaled_buf = self._scale_to_thumbnail(layer_pixels, thumb_w, thumb_h)

                # Paste onto canvas
                oiio.ImageBufAlgo.paste(canvas, x_offset, y_offset, 0, 0, scaled_buf)

                # Add label
                if self.config.show_labels:
                    label_x = x_offset
                    label_y = y_offset + thumb_h + 5
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

    def _scale_to_thumbnail(self, pixels: np.ndarray, width: int, height: int) -> oiio.ImageBuf:
        """Scale pixel data to thumbnail dimensions and return as ImageBuf."""
        scaled_pixels = ImageScaler.scale_image(pixels, width=width, height=height)

        # Convert back to ImageBuf
        channels = scaled_pixels.shape[2] if scaled_pixels.ndim == 3 else 1
        spec = oiio.ImageSpec(width, height, channels, oiio.FLOAT)
        scaled_buf = oiio.ImageBuf(spec)
        scaled_buf.set_pixels(oiio.ROI(), scaled_pixels.astype(np.float32))
        return scaled_buf
