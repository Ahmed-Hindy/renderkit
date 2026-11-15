"""Slate card generation using OpenImageIO."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Protocol

import OpenImageIO as oiio

if TYPE_CHECKING:
    from renderkit.core.config import SlateConfig

logger = logging.getLogger(__name__)

_DEFAULT_SLATE_BACKGROUND: tuple[float, float, float, float] = (0.06, 0.06, 0.08, 1.0)
_ACCENT_RULE_COLOR: tuple[float, float, float, float] = (0.28, 0.56, 0.96, 1.0)
_TITLE_COLOR: tuple[float, float, float, float] = (0.96, 0.97, 0.99, 1.0)
_LABEL_COLOR: tuple[float, float, float, float] = (0.62, 0.67, 0.76, 1.0)
_VALUE_COLOR: tuple[float, float, float, float] = (0.92, 0.94, 0.97, 1.0)
_NOTES_COLOR: tuple[float, float, float, float] = (0.82, 0.85, 0.90, 1.0)


class SlateConfigProtocol(Protocol):
    """Protocol matching ``SlateConfig`` fields for decoupled imports."""

    enabled: bool
    title: str
    show: str
    shot: str
    artist: str
    notes: str
    background_color: tuple[float, float, float, float]


class SlateGenerator:
    """Generates a 4-channel float slate ImageBuf using OpenImageIO."""

    def __init__(self, config: SlateConfig | SlateConfigProtocol) -> None:
        """Initialize the slate generator.

        Args:
            config: Slate configuration or compatible protocol object.
        """
        self.config = config

    def generate_slate_buf(
        self,
        width: int,
        height: int,
        metadata: dict[str, Any],
    ) -> oiio.ImageBuf:
        """Generate a slate frame buffer at the requested resolution.

        Args:
            width: Output slate width in pixels.
            height: Output slate height in pixels.
            metadata: Metadata dictionary providing fallback/dynamic fields such as
                ``title``, ``show``, ``shot``, ``artist``, ``date``, ``frame_range``,
                ``fps``, ``resolution``, ``colorspace``, ``codec``, and ``notes``.

        Returns:
            4-channel float ``oiio.ImageBuf`` containing the rendered slate.
        """
        if width <= 0 or height <= 0:
            raise ValueError(f"Slate dimensions must be positive, got {width}x{height}")

        spec = oiio.ImageSpec(width, height, 4, oiio.FLOAT)
        buf = oiio.ImageBuf(spec)

        bg_color = self._normalize_rgba(getattr(self.config, "background_color", None))
        if not oiio.ImageBufAlgo.fill(buf, bg_color):
            raise RuntimeError(f"Failed to fill slate background: {oiio.geterror()}")

        margin_x = max(16, int(width * 0.07))
        margin_y = max(16, int(height * 0.10))
        title_font_size = max(14, min(64, int(height * 0.055)))
        body_font_size = max(10, min(32, int(height * 0.028)))
        row_step = body_font_size + max(6, int(body_font_size * 0.55))

        title = (
            self._resolve_text("title", metadata) or self._resolve_text("shot", metadata) or "SLATE"
        )
        show = self._resolve_text("show", metadata)
        shot = self._resolve_text("shot", metadata)
        artist = self._resolve_text("artist", metadata)
        date_val = str(metadata.get("date") or datetime.now().strftime("%Y-%m-%d"))
        frame_range = str(metadata.get("frame_range") or "")
        fps_raw = metadata.get("fps")
        fps_val = f"{fps_raw:g}" if isinstance(fps_raw, (int, float)) else str(fps_raw or "")
        resolution = str(metadata.get("resolution") or f"{width}x{height}")
        colorspace = str(metadata.get("colorspace") or "")
        codec = str(metadata.get("codec") or "")
        notes = self._resolve_text("notes", metadata)

        cursor_y = min(max(1, height - 1), margin_y + title_font_size)
        self._render_text(
            buf,
            margin_x,
            cursor_y,
            title,
            fontsize=title_font_size,
            textcolor=_TITLE_COLOR,
        )

        rule_top = min(max(1, height - 2), cursor_y + max(8, int(title_font_size * 0.35)))
        rule_height = max(2, int(height * 0.004))
        rule_bottom = min(height, rule_top + rule_height)
        rule_right = max(margin_x + 1, width - margin_x)
        if rule_top < rule_bottom and margin_x < rule_right:
            rule_roi = oiio.ROI(margin_x, rule_right, rule_top, rule_bottom, 0, 1, 0, 4)
            if not oiio.ImageBufAlgo.fill(buf, _ACCENT_RULE_COLOR, rule_roi):
                raise RuntimeError(f"Failed to draw slate accent rule: {oiio.geterror()}")

        cursor_y = rule_bottom + row_step + max(8, int(body_font_size * 0.5))
        label_col_x = margin_x
        value_col_x = min(
            width - margin_x,
            margin_x + max(90, int(width * 0.16)),
        )

        rows: list[tuple[str, str]] = [
            ("SHOW", show),
            ("SHOT", shot),
            ("ARTIST", artist),
            ("DATE", date_val),
            ("FRAMES", frame_range),
            ("FPS", fps_val),
            ("RESOLUTION", resolution),
            ("COLORSPACE", colorspace),
            ("CODEC", codec),
        ]

        for label, value in rows:
            if not value:
                continue
            if cursor_y >= height - margin_y:
                break
            self._render_text(
                buf,
                label_col_x,
                cursor_y,
                label,
                fontsize=body_font_size,
                textcolor=_LABEL_COLOR,
            )
            self._render_text(
                buf,
                value_col_x,
                cursor_y,
                value,
                fontsize=body_font_size,
                textcolor=_VALUE_COLOR,
            )
            cursor_y += row_step

        if notes and cursor_y < height - margin_y:
            cursor_y = min(height - 1, cursor_y + max(4, int(body_font_size * 0.35)))
            if cursor_y < height - margin_y:
                self._render_text(
                    buf,
                    label_col_x,
                    cursor_y,
                    "NOTES",
                    fontsize=body_font_size,
                    textcolor=_LABEL_COLOR,
                )
                for line in notes.splitlines() or [notes]:
                    if cursor_y >= height - margin_y:
                        break
                    self._render_text(
                        buf,
                        value_col_x,
                        cursor_y,
                        line,
                        fontsize=body_font_size,
                        textcolor=_NOTES_COLOR,
                    )
                    cursor_y += row_step

        return buf

    def _resolve_text(self, key: str, metadata: dict[str, Any]) -> str:
        config_val = getattr(self.config, key, "")
        if config_val:
            return str(config_val)
        meta_val = metadata.get(key)
        return str(meta_val) if meta_val else ""

    @staticmethod
    def _normalize_rgba(color: Any) -> tuple[float, float, float, float]:
        if color is None:
            return _DEFAULT_SLATE_BACKGROUND
        channels = tuple(float(c) for c in color)
        if len(channels) == 3:
            return (channels[0], channels[1], channels[2], 1.0)
        if len(channels) == 4:
            return (channels[0], channels[1], channels[2], channels[3])
        return _DEFAULT_SLATE_BACKGROUND

    @staticmethod
    def _render_text(
        buf: oiio.ImageBuf,
        x: int,
        y: int,
        text: str,
        *,
        fontsize: int,
        textcolor: tuple[float, float, float, float],
    ) -> None:
        if not oiio.ImageBufAlgo.render_text(
            buf,
            x,
            y,
            text,
            fontsize=fontsize,
            textcolor=textcolor,
        ):
            raise RuntimeError(f"Failed to render slate text '{text}': {oiio.geterror()}")
