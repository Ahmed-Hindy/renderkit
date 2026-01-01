import sys

try:
    import PyOpenColorIO as OCIO

    print(f"OCIO Version: {OCIO.__version__ if hasattr(OCIO, '__version__') else 'Unknown'}")

    config = OCIO.GetCurrentConfig()
    print(f"Config object type: {type(config)}")

    methods = [m for m in dir(config) if not m.startswith("_")]
    print("\nAvailable methods on Config:")
    for m in sorted(methods):
        print(f"  - {m}")

    # Check specifically for color space related methods
    print("\nColor space related methods:")
    for m in sorted(methods):
        if "ColorSpace" in m or "space" in m.lower():
            print(f"  - {m}")

except ImportError:
    print("PyOpenColorIO not found")
except Exception as e:
    print(f"Error inspecting OCIO: {e}")
