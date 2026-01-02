import logging
from typing import Any

logger = logging.getLogger(__name__)


class BurnInProcessor:
    """Processor for applying text burn-ins to images using OIIO."""

    def __init__(self) -> None:
        """Initialize the processor."""
        try:
            import OpenImageIO as oiio

            self.oiio = oiio
        except ImportError as e:
            raise RuntimeError("OpenImageIO library not available.") from e

    def apply_burnins(
        self,
        buf: Any,  # oiio.ImageBuf
        frame_metadata: dict[str, Any],
        burnin_config: Any,  # BurnInConfig
    ) -> Any:
        """Apply burn-ins to an OIIO ImageBuf.

        Args:
            buf: OIIO ImageBuf to apply burn-ins to
            frame_metadata: Metadata for token replacement
            burnin_config: Configuration for burn-ins

        Returns:
            Modified OIIO ImageBuf
        """
        if not burnin_config or not burnin_config.elements:
            return buf

        spec = buf.spec()
        width = spec.width

        # Draw background bar if requested
        if getattr(burnin_config, "use_background", False):
            # Bar height based on max font size (roughly)
            max_font_size = max([e.font_size for e in burnin_config.elements])
            bar_height = int(max_font_size * 2.0)

            # Darken the area by multiplying
            # background_opacity 30 means 30% darkening -> multiplier 0.7
            opacity = getattr(burnin_config, "background_opacity", 30)
            multiplier = 1.0 - (max(0, min(100, opacity)) / 100.0)

            roi = self.oiio.ROI(0, width, 0, bar_height)
            self.oiio.ImageBufAlgo.mul(buf, buf, (multiplier, multiplier, multiplier, 1.0), roi)

        for element in burnin_config.elements:
            # Replace tokens in template
            text = self._replace_tokens(element.text_template, frame_metadata)

            # Calculate x-position based on alignment if it's 0 (meaning "auto")
            x_pos = element.x
            if x_pos == 0:
                if element.alignment == "center":
                    x_pos = width // 2
                elif element.alignment == "right":
                    x_pos = width - 20
                elif element.alignment == "left":
                    x_pos = 20

            # Apply burn-in
            # Adjust Y to be within the bar if background is used
            y_pos = element.y
            if getattr(burnin_config, "use_background", False) and y_pos < bar_height:
                # Center vertically in bar (render_text base is baseline)
                y_pos = int(bar_height * 0.7)

            if not self.oiio.ImageBufAlgo.render_text(
                buf,
                x_pos,
                y_pos,
                text,
                fontsize=element.font_size,
                fontname=element.font,
                textcolor=element.color,
                alignx=element.alignment,
            ):
                logger.error(f"Failed to render burn-in text '{text}': {self.oiio.geterror()}")

        return buf

    def _replace_tokens(self, template: str, metadata: dict[str, Any]) -> str:
        """Replace tokens in the template with metadata values.

        Supported tokens:
        - {frame}: Frame number
        - {file}: Filename
        - {fps}: Frame rate
        - {layer}: Layer name
        - {colorspace}: Color space
        """
        try:
            return template.format(**metadata)
        except KeyError as e:
            logger.warning(f"KeyError during token replacement: {e}")
            return template
        except Exception as e:
            logger.error(f"Error during token replacement: {e}")
            return template
