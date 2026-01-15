import re
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all

def get_version():
    init_path = Path("src") / "renderkit" / "__init__.py"
    if init_path.exists():
        content = init_path.read_text()
        match = re.search(r'__version__\s*=\s*[\'"]([^\'"]+)[\'"]', content)
        if match:
            return match.group(1)
    return "0.0.0"

version = get_version()
app_name = f'RenderKit_{version}'

datas = [('src/renderkit/ui/icons', 'renderkit/ui/icons'), ('src/renderkit/ui/stylesheets', 'renderkit/ui/stylesheets'), ('src/renderkit/data/ocio', 'renderkit/data/ocio')]
binaries = []
hiddenimports = []
# Rely on PyInstaller's built-in PySide6 hook to avoid duplicate Qt frameworks on macOS.
tmp_ret = collect_all('OpenImageIO')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('opencolorio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# qt_compat uses dynamic imports; include minimal PySide6 modules explicitly.
hiddenimports += ["PySide6", "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets"]

vendor_ffmpeg_root = Path("vendor") / "ffmpeg"
platform_dir_map = {
    "win32": "windows",
    "linux": "linux",
    "darwin": "macos",
}
platform_dir = platform_dir_map.get(sys.platform)
vendor_ffmpeg_dir = None
if platform_dir:
    candidate_dir = vendor_ffmpeg_root / platform_dir
    if candidate_dir.exists():
        vendor_ffmpeg_dir = candidate_dir

def _should_include_ffmpeg_path(path: Path) -> bool:
    if sys.platform == "win32":
        return path.suffix.lower() in {".exe", ".dll"}
    if path.name == "ffmpeg":
        return True
    return path.suffix.lower() in {".so", ".dylib"}

if vendor_ffmpeg_dir and vendor_ffmpeg_dir.exists():
    for ffmpeg_path in vendor_ffmpeg_dir.iterdir():
        if not ffmpeg_path.is_file():
            continue
        if _should_include_ffmpeg_path(ffmpeg_path):
            binaries.append((str(ffmpeg_path), "ffmpeg"))

qt_excludes = [
    "tkinter",
    "_tkinter",
    "tk",
    "tcl",
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtConcurrent",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtPrintSupport",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
    "PySide6.QtXml",
]

allowed_qt_plugin_dirs = {
    "platforms",
    "imageformats",
    "styles",
    "iconengines",
    "platformthemes",
}

qt_excluded_tokens = {name.split(".")[-1] for name in qt_excludes}
qt_excluded_tokens.add("QtWebEngineProcess")
qt_excluded_tokens.update(
    {
        f"Qt6{token[2:]}"
        for token in qt_excluded_tokens
        if token.startswith("Qt") and not token.startswith("Qt6")
    }
)

def _should_drop_qt_lib(dest_parts, dest):
    if len(dest_parts) >= 4 and dest_parts[:3] in {
        ("PySide6", "Qt", "lib"),
        ("PySide6", "Qt", "bin"),
        ("PySide6", "Qt6", "lib"),
        ("PySide6", "Qt6", "bin"),
    }:
        dest_str = str(dest)
        for token in qt_excluded_tokens:
            if token in dest_str:
                return True
    return False

def _prune_qt_payload(entries):
    pruned = []
    for entry in entries:
        if len(entry) == 2:
            src, dest = entry
            entry_type = None
        else:
            src, dest, entry_type = entry
        dest_parts = Path(dest).parts
        if len(dest_parts) >= 4 and dest_parts[:3] in {
            ("PySide6", "Qt", "plugins"),
            ("PySide6", "Qt6", "plugins"),
        }:
            plugin_dir = dest_parts[3]
            if plugin_dir not in allowed_qt_plugin_dirs:
                continue
        if len(dest_parts) >= 3 and dest_parts[:3] in {
            ("PySide6", "Qt", "qml"),
            ("PySide6", "Qt6", "qml"),
        }:
            continue
        if _should_drop_qt_lib(dest_parts, dest):
            continue
        if entry_type is None:
            pruned.append((src, dest))
        else:
            pruned.append((src, dest, entry_type))
    return pruned

strip_binaries = sys.platform != "win32"


entry_script = Path("src") / "renderkit" / "ui" / "main_window.py"

a = Analysis(
    [str(entry_script)],
    pathex=[str(Path("src"))],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=qt_excludes,
    noarchive=False,
    optimize=0,
)
a.datas = _prune_qt_payload(a.datas)
a.binaries = _prune_qt_payload(a.binaries)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=app_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=strip_binaries,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=strip_binaries,
    upx=True,
    upx_exclude=[],
    name='RenderKit',
)
