"""Confidential and tiled text watermark overlay processor using OpenImageIO."""

from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from typing import Any, Optional, cast

import OpenImageIO as oiio

from renderkit.core.config import WatermarkConfig
from renderkit.io.oiio_utils import require_oiio

logger = logging.getLogger(__name__)

_TOKEN_PATTERN = re.compile(r"\{([a-zA-Z0-9_.:/-]+)\}")


class WatermarkProcessor:
    """Processor for applying centered or tiled text watermarks to OIIO ImageBuf frames."""

    def __init__(self) -> None:
        """Initialize the watermark processor."""
        self.oiio = require_oiio()

    def apply_watermark(
        self,
        buf: oiio.ImageBuf,
        config: Optional[WatermarkConfig],
        metadata: Optional[dict[str, Any]] = None,
    ) -> oiio.ImageBuf:
        """Apply a centered or tiled watermark overlay to an ImageBuf.

        Renders subtle grey-white text onto a 4-channel premultiplied overlay and
        alpha-composites it over ``buf`` so opacity blends accurately on both
        3-channel RGB and 4-channel RGBA buffers.

        Args:
            buf: Input OIIO ImageBuf.
            config: Watermark configuration. When ``None``, returns ``buf`` unchanged.
            metadata: Optional metadata dictionary for safe ``{token}`` substitution
                in ``config.text``. Missing tokens are left literal.

        Returns:
            Modified ``oiio.ImageBuf`` with the watermark applied, or ``buf`` unchanged
            when ``config`` is ``None`` or opacity is 0.
        """
        if config is None:
            return buf

        alpha = max(0.0, min(1.0, config.opacity / 100.0))
        if alpha == 0.0:
            return buf

        spec = buf.spec()
        width = int(spec.width)
        height = int(spec.height)
        if width <= 0 or height <= 0:
            return buf

        text = self._resolve_text(config.text, metadata)
        if not text.strip():
            return buf

        overlay = self._create_overlay(spec)
        font_size = max(1, int(config.font_size))

        if config.tiled:
            self._render_tiled(overlay, spec, text, font_size, max(1, int(config.spacing)))
        else:
            self._render_centered(overlay, spec, text, font_size)

        if alpha < 1.0:
            if not self.oiio.ImageBufAlgo.mul(overlay, overlay, (alpha, alpha, alpha, alpha)):
                raise RuntimeError(f"Failed to scale watermark opacity: {self.oiio.geterror()}")

        return self._composite_overlay(buf, overlay, spec)

    def _create_overlay(self, spec: Any) -> oiio.ImageBuf:
        """Create a transparent 4-channel float overlay matching ``spec`` bounds."""
        overlay_spec = self.oiio.ImageSpec(spec.width, spec.height, 4, self.oiio.FLOAT)
        overlay_spec.x = spec.x
        overlay_spec.y = spec.y
        overlay_spec.full_x = spec.full_x
        overlay_spec.full_y = spec.full_y
        overlay_spec.full_width = spec.full_width
        overlay_spec.full_height = spec.full_height
        overlay = self.oiio.ImageBuf(overlay_spec)
        if not self.oiio.ImageBufAlgo.fill(overlay, (0.0, 0.0, 0.0, 0.0)):
            raise RuntimeError(f"Failed to initialize watermark overlay: {self.oiio.geterror()}")
        return cast(oiio.ImageBuf, overlay)

    def _render_centered(
        self,
        overlay: oiio.ImageBuf,
        spec: Any,
        text: str,
        font_size: int,
    ) -> None:
        """Render a single centered watermark onto ``overlay``."""
        cx = int(spec.x) + int(spec.width) // 2
        cy = int(spec.y) + int(spec.height) // 2
        self._draw_text(overlay, cx, cy, text, font_size)

    def _render_tiled(
        self,
        overlay: oiio.ImageBuf,
        spec: Any,
        text: str,
        font_size: int,
        spacing: int,
    ) -> None:
        """Render a staggered grid of watermarks across ``overlay``."""
        width = int(spec.width)
        height = int(spec.height)
        origin_x = int(spec.x)
        origin_y = int(spec.y)
        half_step = spacing // 2

        y_start = min(half_step, height // 2)
        y_positions = list(range(y_start, height, spacing))
        if not y_positions:
            y_positions = [height // 2]

        x_even_start = min(half_step, width // 2)
        even_xs = list(range(x_even_start, width, spacing)) or [width // 2]

        odd_start = (x_even_start + half_step) % spacing
        odd_xs = list(range(odd_start, width, spacing))
        if not odd_xs:
            odd_xs = [min(width - 1, max(0, (width // 2) + (half_step // 2)))]

        for row_idx, rel_y in enumerate(y_positions):
            clamped_y = max(0, min(height - 1, rel_y))
            row_xs = odd_xs if (row_idx % 2 == 1) else even_xs
            for rel_x in row_xs:
                clamped_x = max(0, min(width - 1, rel_x))
                self._draw_text(
                    overlay, origin_x + clamped_x, origin_y + clamped_y, text, font_size
                )

    def _draw_text(
        self,
        overlay: oiio.ImageBuf,
        x: int,
        y: int,
        text: str,
        font_size: int,
    ) -> None:
        """Render white full-coverage text centered at ``(x, y)`` onto ``overlay``."""
        if not self.oiio.ImageBufAlgo.render_text(
            overlay,
            x,
            y,
            text,
            fontsize=font_size,
            textcolor=(1.0, 1.0, 1.0, 1.0),
            alignx="center",
            aligny="center",
        ):
            raise RuntimeError(f"Failed to render watermark text '{text}': {self.oiio.geterror()}")

    def _composite_overlay(
        self,
        buf: oiio.ImageBuf,
        overlay: oiio.ImageBuf,
        spec: Any,
    ) -> oiio.ImageBuf:
        """Composite 4-channel premultiplied ``overlay`` over ``buf`` preserving channel count."""
        nchannels = int(spec.nchannels)
        if nchannels == 4:
            result = self.oiio.ImageBufAlgo.over(overlay, buf)
            if result.has_error:
                raise RuntimeError(f"Failed to composite watermark: {result.geterror()}")
            return cast(oiio.ImageBuf, result)

        if nchannels == 3:
            bg_rgba = self.oiio.ImageBufAlgo.channels(buf, (0, 1, 2, 1.0), ("R", "G", "B", "A"))
            if bg_rgba.has_error:
                raise RuntimeError(
                    f"Failed to expand RGB buffer for watermark: {bg_rgba.geterror()}"
                )
            composited = self.oiio.ImageBufAlgo.over(overlay, bg_rgba)
            if composited.has_error:
                raise RuntimeError(f"Failed to composite watermark: {composited.geterror()}")
            ch_names = (
                tuple(spec.channelnames[:3]) if len(spec.channelnames) >= 3 else ("R", "G", "B")
            )
            result = self.oiio.ImageBufAlgo.channels(composited, (0, 1, 2), ch_names)
            if result.has_error:
                raise RuntimeError(f"Failed to restore RGB channels: {result.geterror()}")
            return cast(oiio.ImageBuf, result)

        bg_rgba = self.oiio.ImageBufAlgo.channels(buf, (0, 0, 0, 1.0), ("R", "G", "B", "A"))
        if bg_rgba.has_error:
            raise RuntimeError(f"Failed to prepare buffer for watermark: {bg_rgba.geterror()}")
        composited = self.oiio.ImageBufAlgo.over(overlay, bg_rgba)
        if composited.has_error:
            raise RuntimeError(f"Failed to composite watermark: {composited.geterror()}")
        indices = tuple(range(nchannels))
        result = self.oiio.ImageBufAlgo.channels(
            composited,
            indices,
            tuple(spec.channelnames[:nchannels]),
        )
        if result.has_error:
            raise RuntimeError(f"Failed to restore watermark channels: {result.geterror()}")
        return cast(oiio.ImageBuf, result)

    @staticmethod
    def _resolve_text(template: str, metadata: Optional[dict[str, Any]]) -> str:
        """Safely substitute known ``{token}`` placeholders, leaving unknown ones literal."""
        if not metadata:
            return template

        def _substitute(match: re.Match[str]) -> str:
            key = match.group(1)
            if key.startswith("exr:"):
                attr_name = key[4:]
                exr_meta = metadata.get("exr")
                if isinstance(exr_meta, Mapping) and attr_name in exr_meta:
                    val = exr_meta[attr_name]
                    if val is not None:
                        return str(val)
                if attr_name in metadata and metadata[attr_name] is not None:
                    return str(metadata[attr_name])
                return match.group(0)

            if ":" in key:
                field_name, fmt_spec = key.split(":", 1)
            else:
                field_name, fmt_spec = key, None

            if field_name not in metadata or metadata[field_name] is None:
                return match.group(0)

            value = metadata[field_name]
            if fmt_spec is not None:
                try:
                    return format(value, fmt_spec)
                except (ValueError, TypeError):
                    return str(value)
            return str(value)

        return _TOKEN_PATTERN.sub(_substitute, template)
