# Native rewrite (in progress)

The `rewrite/cpp-qt` branch contains an experimental C++20 and Qt 6 implementation alongside the existing Python application. The Python package remains the supported implementation until feature parity, cross-platform tests, and packaging have been verified.

The native build uses a pinned vcpkg baseline. The Qt overlay disables the optional Windows Vista/11 style plugin because it requires a newer Windows SDK; RenderKit uses Qt's Fusion style. OpenImageIO is built with FreeType and OpenColorIO support.

On Windows, start an x64 Visual Studio developer shell with a recent MSVC toolset, then set `VCPKG_ROOT` **after** entering that shell. For example, if vcpkg is installed at `C:\vcpkg`:

```powershell
$env:VCPKG_ROOT = 'C:\vcpkg'
cmake --preset debug
cmake --build --preset debug --parallel
ctest --preset debug --output-on-failure
```

Visual Studio's developer environment may set `VCPKG_ROOT` to its own bundled copy; use the pinned checkout instead. CMake stages the bundled OCIO configuration and, when present, `vendor/ffmpeg/windows` next to the executable. The first vcpkg build can take substantial time and disk space; configure a vcpkg binary cache to reuse compiled dependencies.

The native executable is `build/cpp-debug/RenderKit.exe`. It is a development build, not yet a release package. Full GUI and pipeline parity and cross-platform deployment still require validation before the Python implementation is removed.

On Linux, use the `linux` configure, build, and test presets. They use a dynamic vcpkg triplet so the application can be packaged with shared libraries. For an installed package, launch `./renderkit` from the package directory; the launcher sets the library path needed by Qt's desktop plugin. A system font such as DejaVu Sans is needed for burn-ins and contact-sheet labels.

## Verification and remaining work

- The Windows release preset builds and its native tests cover sequence detection, settings, logging, EXR metadata and layers, color conversion, contact sheets, burn-ins, Qt widgets, and FFmpeg encoding. A staged Windows application has also been smoke-tested with its bundled FFmpeg.
- The Linux native build passed all eight test targets in Debian. The installed bundle started in a separate network-isolated Debian container, and also stayed running under Xvfb with the XCB platform plugin. Interactive desktop use and compatibility with older Linux distributions remain unverified. The reusable source archive cache is under `build/vcpkg-downloads`; the build container and volume are named `renderkit-cpp-linux-20261112`.
- The native CI workflow and package staging are experimental and have not yet run on GitHub. Manual desktop interaction, remaining GUI and processing parity, release automation, and the full planned test matrix are outstanding. Keep the Python application and existing release workflows until those checks pass.
