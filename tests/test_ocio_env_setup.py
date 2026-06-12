import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.append(str(src_path))

import renderkit.processing.color_space as color_space  # noqa: E402
from renderkit.processing.color_space import (  # noqa: E402
    OCIOColorSpaceStrategy,
    get_bundled_ocio_config_path,
)
from renderkit.ui.main_window import ModernMainWindow  # noqa: E402


class TestOCIOConfigSetup(unittest.TestCase):
    def setUp(self):
        self.original_ocio = os.environ.get("OCIO")
        color_space._BUNDLED_OCIO_CONFIG_CACHE = None

    def tearDown(self):
        if self.original_ocio:
            os.environ["OCIO"] = self.original_ocio
        else:
            os.environ.pop("OCIO", None)
        color_space._BUNDLED_OCIO_CONFIG_CACHE = None

    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ensure_bundled_ocio_config_does_not_create_env_var(self, mock_init, *args):
        os.environ.pop("OCIO", None)

        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_bundled_ocio_config()

        self.assertNotIn("OCIO", os.environ)
        self.assertTrue(get_bundled_ocio_config_path().name == "config.ocio")

    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ensure_bundled_ocio_config_does_not_overwrite_env_var(self, mock_init, *args):
        existing_ocio = "C:/some/system/path/config.ocio"
        os.environ["OCIO"] = existing_ocio

        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_bundled_ocio_config()

        self.assertEqual(os.environ["OCIO"], existing_ocio)
        self.assertTrue(get_bundled_ocio_config_path().name == "config.ocio")

    @patch("sys.frozen", True, create=True)
    @patch("sys._MEIPASS", str(Path(__file__).parent.parent / "src"), create=True)
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ensure_bundled_ocio_config_frozen_mode(self, mock_init, *args):
        os.environ.pop("OCIO", None)

        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_bundled_ocio_config()

        self.assertNotIn("OCIO", os.environ)
        self.assertTrue(str(get_bundled_ocio_config_path()).endswith("config.ocio"))

    def test_ocio_strategy_loads_bundled_config_when_env_var_is_invalid(self):
        os.environ["OCIO"] = "C:/does/not/exist/config.ocio"

        strategy = OCIOColorSpaceStrategy()

        self.assertEqual(strategy.config_path, get_bundled_ocio_config_path())
        self.assertIn("ACES - ACEScg", list(strategy.config.getColorSpaceNames()))
        self.assertEqual(os.environ["OCIO"], "C:/does/not/exist/config.ocio")


if __name__ == "__main__":
    unittest.main()
