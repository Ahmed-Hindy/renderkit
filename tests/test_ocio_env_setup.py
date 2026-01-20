import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.append(str(src_path))

from renderkit.ui.main_window import ModernMainWindow  # noqa: E402


class TestOCIOEnvSetup(unittest.TestCase):
    def setUp(self):
        # Save original OCIO env
        self.original_ocio = os.environ.get("OCIO")
        if "OCIO" in os.environ:
            del os.environ["OCIO"]

    def tearDown(self):
        # Restore
        if self.original_ocio:
            os.environ["OCIO"] = self.original_ocio
        elif "OCIO" in os.environ:
            del os.environ["OCIO"]

    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ensure_ocio_env_dev_mode(self, mock_init, *args):
        # Ensure we have a dummy bundled config structure mocked or real
        # If we run in dev mode, logic looks at ../data/ocio/config.ocio relative to main_window logic
        # That path likely exists in this repo.

        # Scenario: OCIO is NOT set. Should pick up bundled.
        if "OCIO" in os.environ:
            del os.environ["OCIO"]

        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_ocio_env()

        self.assertIn("OCIO", os.environ)
        self.assertTrue(os.environ["OCIO"].endswith("config.ocio"))
        print(f"Verified OCIO detected at: {os.environ['OCIO']}")

    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ocio_env_overwrites_system_if_bundled_exists(self, mock_init, *args):
        # Scenario: OCIO IS set to something else.
        # Logic should overwrite it with bundled if bundled exists.

        # We need to ensure bundled path 'exists' for the logic to trigger the overwrite.
        # In this test environment (dev mode), the real file exists.

        os.environ["OCIO"] = "C:/some/system/path/config.ocio"

        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_ocio_env()

        self.assertNotEqual(os.environ["OCIO"], "C:/some/system/path/config.ocio")
        self.assertTrue(os.environ["OCIO"].endswith("config.ocio"))
        print(f"Verified system env was overridden by: {os.environ['OCIO']}")

    @patch("sys.frozen", True, create=True)
    @patch("sys._MEIPASS", str(Path(__file__).parent.parent / "src"), create=True)
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_ui")
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")
    def test_ensure_ocio_env_frozen_mode(self, mock_init, *args):
        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_ocio_env()

        self.assertIn("OCIO", os.environ)
        self.assertTrue(os.environ["OCIO"].endswith("config.ocio"))
        print(f"Frozen mode Verification: {os.environ['OCIO']}")


if __name__ == "__main__":
    unittest.main()
