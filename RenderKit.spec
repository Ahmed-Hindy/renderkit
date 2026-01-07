# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = [('src/renderkit/ui/icons', 'renderkit/ui/icons'), ('src/renderkit/ui/stylesheets', 'renderkit/ui/stylesheets')]
binaries = []
hiddenimports = []
# Rely on PyInstaller's built-in PySide6 hook to avoid duplicate Qt frameworks on macOS.
tmp_ret = collect_all('OpenImageIO')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('opencolorio')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('imageio_ffmpeg')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# Ensure importlib.metadata can resolve package versions at runtime.
datas += copy_metadata('imageio')
datas += copy_metadata('imageio-ffmpeg')

qt_excludes = [
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

def _prune_qt_plugins(datas_list):
    pruned = []
    for entry in datas_list:
        if len(entry) == 2:
            src, dest = entry
            entry_type = None
        else:
            src, dest, entry_type = entry
        dest_parts = Path(dest).parts
        if len(dest_parts) >= 4 and dest_parts[:3] == ("PySide6", "Qt", "plugins"):
            plugin_dir = dest_parts[3]
            if plugin_dir not in allowed_qt_plugin_dirs:
                continue
        if len(dest_parts) >= 3 and dest_parts[:3] == ("PySide6", "Qt", "qml"):
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
a.datas = _prune_qt_plugins(a.datas)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RenderKit',
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
