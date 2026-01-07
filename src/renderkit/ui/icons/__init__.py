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
        cache_key = f"{name}_{color}_{size}"

        if cache_key in self._icon_cache:
            return self._icon_cache[cache_key]

        icon_path = ICONS_DIR / self._icon_paths.get(name, "info.svg")

        if icon_path.exists():
            icon = QIcon(str(icon_path))
        else:
            # Create a simple colored square as fallback
            icon = self._create_fallback_icon(color or "#FFFFFF", size)

        self._icon_cache[cache_key] = icon
        return icon

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

    def has_icon(self, name: str) -> bool:
        """Check if icon exists."""
        return name in self._icon_paths


# Global icon manager instance
icon_manager = IconManager()
