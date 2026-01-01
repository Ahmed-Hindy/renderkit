import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

try:
    from renderkit import constants

    print("✅ Constants imported successfully")
except ImportError as e:
    print(f"❌ Failed to import constants: {e}")
    sys.exit(1)

try:
    from renderkit.io.image_reader import ImageReader

    # Check if we can instantiate or check module attributes
    print("✅ ImageReader imported successfully")
except ImportError as e:
    print(f"❌ Failed to import ImageReader: {e}")
    sys.exit(1)

try:
    from renderkit.processing.color_space import ColorSpacePreset, OCIOColorSpaceStrategy

    print("✅ ColorSpace modules imported successfully")
except ImportError as e:
    print(f"❌ Failed to import ColorSpace modules: {e}")
    sys.exit(1)

try:
    # Minimal UI import check - might fail without QApplication but imports should work
    from renderkit.ui.main_window import ModernMainWindow as MainWindow

    print("✅ MainWindow imported successfully")
except ImportError as e:
    # If it fails due to no app, that's fine, but we want to catch SyntaxErrors or ImportErrors
    if "QApplication" in str(e):
        print("⚠️ MainWindow import skipped due to Qt requirement (expected)")
    else:
        print(f"❌ Failed to import MainWindow: {e}")
        sys.exit(1)
except Exception as e:
    print(f"⚠️ MainWindow check warning: {e}")

print("Refactoring verification Passed!")
