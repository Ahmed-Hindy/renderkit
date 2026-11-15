"""Text burn-in overlay processor using OpenImageIO."""

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from renderkit.io.oiio_utils import require_oiio

_BURNIN_EDGE_MARGIN = 20
_BURNIN_BAR_HEIGHT_MULTIPLIER = 2.0
_BURNIN_VERTICAL_CENTER_FACTOR = 0.7
_TOP_ZONES = frozenset({"top_left", "top_center", "top_right"})
_BOTTOM_ZONES = frozenset({"bottom_left", "bottom_center", "bottom_right"})
_VALID_ZONES = _TOP_ZONES | _BOTTOM_ZONES
_TOKEN_PATTERN = re.compile(r"\{([a-zA-Z0-9_.:/-]+)\}")
_TEMPLATE_SCAN_PATTERN = re.compile(r"\{\{|\}\}|" + _TOKEN_PATTERN.pattern)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _PlannedBurnIn:
    """Resolved placement and styling for a single burn-in element."""

    text: str
    x: int
    y: int
    align: str
    font_size: int
    font: str
    color: tuple[float, ...]
    is_top: bool
    is_bottom: bool


class BurnInProcessor:
    """Processor for applying text burn-ins to images using OIIO."""

    def __init__(self) -> None:
        """Initialize the processor."""
        self.oiio = require_oiio()

    def apply_burnins(
        self,
        buf: Any,  # oiio.ImageBuf
        frame_metadata: dict[str, Any],
        burnin_config: Any,  # BurnInConfig
    ) -> Any:
        """Apply burn-ins to an OIIO ImageBuf.

        Args:
            buf: OIIO ImageBuf to apply burn-ins to.
            frame_metadata: Metadata for token replacement.
            burnin_config: Configuration for burn-ins.

        Returns:
            Modified OIIO ImageBuf.
        """
        if not burnin_config or not burnin_config.elements:
            return buf

        spec = buf.spec()
        width = spec.width
        height = spec.height
        padding = max(12, int(width * 0.015))
        use_background = getattr(burnin_config, "use_background", True)
        opacity = getattr(burnin_config, "background_opacity", 30)
        draw_bars = bool(use_background and opacity > 0)

        max_font_size = max(max(1, int(e.font_size)) for e in burnin_config.elements)
        legacy_bar_height = int(max_font_size * _BURNIN_BAR_HEIGHT_MULTIPLIER)

        planned: list[_PlannedBurnIn] = []
        zone_offsets: dict[str, int] = {}

        for element in burnin_config.elements:
            text = self._replace_tokens(element.text_template, frame_metadata)
            scaled_font_size = max(1, int(element.font_size))
            zone = getattr(element, "zone", None)

            if zone is not None:
                x_pos, y_pos, align, is_top, is_bottom = self._resolve_zone_placement(
                    zone=zone,
                    width=width,
                    height=height,
                    padding=padding,
                    font_size=scaled_font_size,
                    zone_offsets=zone_offsets,
                )
            else:
                align = element.alignment
                x_pos = element.x
                if x_pos == 0:
                    if align == "center":
                        x_pos = width // 2
                    elif align == "right":
                        x_pos = width - _BURNIN_EDGE_MARGIN
                    elif align == "left":
                        x_pos = _BURNIN_EDGE_MARGIN

                y_pos = element.y
                if draw_bars and y_pos < legacy_bar_height:
                    y_pos = int(legacy_bar_height * _BURNIN_VERTICAL_CENTER_FACTOR)
                is_top = y_pos < height // 2
                is_bottom = y_pos >= height // 2

            planned.append(
                _PlannedBurnIn(
                    text=text,
                    x=x_pos,
                    y=y_pos,
                    align=align,
                    font_size=scaled_font_size,
                    font=element.font,
                    color=element.color,
                    is_top=is_top,
                    is_bottom=is_bottom,
                )
            )

        if draw_bars:
            multiplier = 1.0 - (max(0, min(100, opacity)) / 100.0)
            top_items = [item for item in planned if item.is_top]
            if top_items:
                max_top_font = max(item.font_size for item in top_items)
                max_top_y = max(item.y for item in top_items)
                top_bar_height = min(
                    height,
                    max(
                        int(max_top_font * _BURNIN_BAR_HEIGHT_MULTIPLIER),
                        max_top_y + max(6, int(max_top_font * 0.35)) + padding // 2,
                    ),
                )
                top_roi = self.oiio.ROI(0, width, 0, top_bar_height)
                self.oiio.ImageBufAlgo.mul(
                    buf, buf, (multiplier, multiplier, multiplier, 1.0), top_roi
                )

            bottom_items = [item for item in planned if item.is_bottom]
            if bottom_items:
                max_bottom_font = max(item.font_size for item in bottom_items)
                min_bottom_y = min(item.y for item in bottom_items)
                bottom_bar_top = max(
                    0,
                    min(
                        height - int(max_bottom_font * _BURNIN_BAR_HEIGHT_MULTIPLIER),
                        min_bottom_y - max_bottom_font - padding // 2,
                    ),
                )
                bottom_roi = self.oiio.ROI(0, width, bottom_bar_top, height)
                self.oiio.ImageBufAlgo.mul(
                    buf, buf, (multiplier, multiplier, multiplier, 1.0), bottom_roi
                )

        for item in planned:
            if not self.oiio.ImageBufAlgo.render_text(
                buf,
                item.x,
                item.y,
                item.text,
                fontsize=item.font_size,
                fontname=item.font,
                textcolor=item.color,
                alignx=item.align,
            ):
                raise RuntimeError(
                    f"Failed to render burn-in text '{item.text}': {self.oiio.geterror()}"
                )

        return buf

    @staticmethod
    def _resolve_zone_placement(
        *,
        zone: str,
        width: int,
        height: int,
        padding: int,
        font_size: int,
        zone_offsets: dict[str, int],
    ) -> tuple[int, int, str, bool, bool]:
        """Compute ``(x, y, align, is_top, is_bottom)`` for a named HUD zone."""
        if zone not in _VALID_ZONES:
            raise ValueError(f"Invalid burn-in zone: '{zone}'")

        if zone.endswith("_left"):
            x_pos = padding
            align = "left"
        elif zone.endswith("_center"):
            x_pos = width // 2
            align = "center"
        else:
            x_pos = max(padding, width - padding)
            align = "right"

        offset = zone_offsets.get(zone, 0)
        line_step = font_size + max(6, int(font_size * 0.35))
        if zone in _TOP_ZONES:
            y_pos = min(max(1, height - 1), padding + font_size + offset)
            is_top = True
            is_bottom = False
        else:
            descender = max(4, int(font_size * 0.2))
            y_pos = max(1, min(height - 1, height - padding - descender - offset))
            is_top = False
            is_bottom = True

        zone_offsets[zone] = offset + line_step
        return x_pos, y_pos, align, is_top, is_bottom

    def _replace_tokens(self, template: str, metadata: dict[str, Any]) -> str:
        """Replace tokens in the template with metadata values.

        Supports standard tokens (e.g. ``{frame}``, ``{fps:.1f}``, ``{user}``,
        ``{frame_range}``) as well as EXR attribute tokens prefixed with
        ``exr:`` (e.g. ``{exr:compression}``, ``{exr:karma/renderTime}``).
        """
        remainder = _TEMPLATE_SCAN_PATTERN.sub("", template)
        if "{" in remainder or "}" in remainder:
            raise ValueError(f"Invalid burn-in template '{template}': unmatched or empty braces")

        def _substitute(match: re.Match[str]) -> str:
            raw = match.group(0)
            if raw == "{{":
                return "{"
            if raw == "}}":
                return "}"

            key = match.group(1)
            if key.startswith("exr:"):
                return self._resolve_exr_token(key, metadata, template)

            if ":" in key:
                field_name, fmt_spec = key.split(":", 1)
            else:
                field_name, fmt_spec = key, None

            if field_name not in metadata:
                raise ValueError(f"Missing burn-in metadata token: '{field_name}'")

            value = metadata[field_name]
            if fmt_spec is not None:
                try:
                    return format(value, fmt_spec)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid burn-in template '{template}': {e}") from e
            return str(value)

        return _TEMPLATE_SCAN_PATTERN.sub(_substitute, template)

    @staticmethod
    def _resolve_exr_token(key: str, metadata: dict[str, Any], template: str) -> str:
        """Resolve an ``{exr:<attr>}`` token from ``metadata['exr']`` or top-level metadata."""
        attr_name = key[4:]
        exr_meta = metadata.get("exr")

        if isinstance(exr_meta, Mapping) and attr_name in exr_meta:
            val = exr_meta[attr_name]
            if val is not None:
                return str(val)

        if attr_name in metadata:
            val = metadata[attr_name]
            if val is not None:
                return str(val)

        if ":" in attr_name:
            sub_attr, fmt_spec = attr_name.rsplit(":", 1)
            candidate: Any = None
            has_candidate = False
            if isinstance(exr_meta, Mapping) and sub_attr in exr_meta:
                candidate = exr_meta[sub_attr]
                has_candidate = candidate is not None
            elif sub_attr in metadata:
                candidate = metadata[sub_attr]
                has_candidate = candidate is not None
            if has_candidate:
                try:
                    return format(candidate, fmt_spec)
                except (ValueError, TypeError) as e:
                    raise ValueError(f"Invalid burn-in template '{template}': {e}") from e

        raise ValueError(f"Missing burn-in metadata token: '{key}'")
