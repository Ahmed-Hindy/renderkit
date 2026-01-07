"""Icon system for RenderKit UI."""

from pathlib import Path
from typing import Optional

from renderkit.ui.qt_compat import QColor, QIcon, QPainter, QPixmap, Qt

# Icon directory
ICONS_DIR = Path(__file__).parent


class IconManager:
    """Manages icons for the application."""

    def __init__(self):
        self._icon_cache: dict[str, QIcon] = {}
        self._default_color: Optional[str] = None
        self._icon_paths = {
            # File type icons
            "file_image": "file-image.svg",
            "file_video": "file-video-camera.svg",
            "file_folder": "folder-open.svg",
            # Action icons
            "play": "play.svg",
            "pause": "pause.svg",
            "stop": "square-pause.svg",
            "convert": "wrench.svg",
            "browse": "folder-open.svg",
            "preview": "eye.svg",
            "settings": "settings.svg",
            "help": "info.svg",
            "detect": "search.svg",
            "scan": "scan.svg",
            # UI icons
            "close": "x.svg",
            "warning": "triangle-alert.svg",
            "error": "circle-alert.svg",
            "info": "info.svg",
            "ban": "ban.svg",
        }

    def get_icon(self, name: str, color: Optional[str] = None, size: int = 16) -> QIcon:
        """Get icon by name, optionally with custom color."""
        color_to_use = color if color is not None else self._default_color
        cache_key = f"{name}_{color_to_use}_{size}"

        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        icon_path = ICONS_DIR / self._icon_paths.get(name, "info.svg")

        if icon_path.exists():
            icon = QIcon(str(icon_path))
            if color_to_use:
                icon = self._tint_icon(icon, color_to_use, size)
        else:
            # Create a simple colored square as fallback
            icon = self._create_fallback_icon(color_to_use or "#FFFFFF", size)

        self._icon_cache[cache_key] = icon
        return icon

    def set_default_color(self, color: Optional[str]) -> None:
        """Set default icon tint color for icons that don't specify one."""
        if color == self._default_color:
            return
        self._default_color = color
        self._icon_cache.clear()

    def _create_fallback_icon(self, color: str, size: int) -> QIcon:
        """Create a simple fallback icon."""
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor(color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 2, 2)
        painter.end()

        return QIcon(pixmap)

    def _tint_icon(self, icon: QIcon, color: str, size: int) -> QIcon:
        """Tint an icon to a specific color."""
        pixmap = icon.pixmap(size, size)
        if pixmap.isNull():
            return icon

        tinted = QPixmap(pixmap.size())
        tinted.fill(Qt.GlobalColor.transparent)

        painter = QPainter(tinted)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        source_mode = getattr(QPainter, "CompositionMode_Source", None)
        source_in_mode = getattr(QPainter, "CompositionMode_SourceIn", None)
        if source_mode is None or source_in_mode is None:
            source_mode = QPainter.CompositionMode.CompositionMode_Source
            source_in_mode = QPainter.CompositionMode.CompositionMode_SourceIn
        painter.setCompositionMode(source_mode)
        painter.drawPixmap(0, 0, pixmap)
        painter.setCompositionMode(source_in_mode)
        painter.fillRect(tinted.rect(), QColor(color))
        painter.end()

        return QIcon(tinted)

    def has_icon(self, name: str) -> bool:
        """Check if icon exists."""
        return name in self._icon_paths


# Global icon manager instance
icon_manager = IconManager()
