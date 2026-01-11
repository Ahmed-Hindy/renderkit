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

    @patch(
        "renderkit.ui.main_window.ModernMainWindow._setup_ui"
    )  # Mock UI setup to assume headless
    @patch("renderkit.ui.main_window.ModernMainWindow._apply_theme")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_logging")
    @patch("renderkit.ui.main_window.ModernMainWindow._load_settings")
    @patch("renderkit.ui.main_window.ModernMainWindow._setup_connections")
    @patch("renderkit.ui.main_window.QMainWindow.__init__")  # Mock QMainWindow
    def test_ensure_ocio_env_dev_mode(self, mock_init, *args):
        # We need to mock QMainWindow because we can't create QApplication here easily without segfaults sometimes

        # Manually invoke the method since we mocked __init__
        window = ModernMainWindow.__new__(ModernMainWindow)
        window._ensure_ocio_env()

        self.assertIn("OCIO", os.environ)
        self.assertTrue(os.environ["OCIO"].endswith("config.ocio"))
        self.assertIn("ocio", os.environ["OCIO"])
        print(f"Verified OCIO detected at: {os.environ['OCIO']}")

    @patch("sys.frozen", True, create=True)
    @patch(
        "sys._MEIPASS", str(Path(__file__).parent.parent / "src"), create=True
    )  # Mock pointing to src root for test
    # logic expects sys._MEIPASS / renderkit / data / minimal_config.ocio
    # so we need to mock _MEIPASS such that that path exists.
    # We constructed the file at src/renderkit/data/minimal_config.ocio
    # So if we set _MEIPASS to 'src', then 'src/renderkit/data/...' works?
    # No, PyInstaller flattens or specific structure.
    # In my code: Path(sys._MEIPASS) / "renderkit" / "data" / "minimal_config.ocio"
    # So I need to set _MEIPASS to a dir containing 'renderkit/data/minimal_config.ocio'.
    # That is 'src'.
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
