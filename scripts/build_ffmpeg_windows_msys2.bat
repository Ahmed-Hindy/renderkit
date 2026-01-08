@echo off
setlocal

set "MSYS2_ROOT=C:\msys64"
set "REPO=%~dp0.."

if not exist "%MSYS2_ROOT%\msys2_shell.cmd" (
  echo MSYS2 not found at "%MSYS2_ROOT%".
  echo Please set MSYS2_ROOT to your MSYS2 install path.
  exit /b 1
)

pushd "%REPO%" >nul
"%MSYS2_ROOT%\msys2_shell.cmd" -defterm -here -ucrt64 -no-start -c ^
"bash scripts/build_ffmpeg_windows_msys2_bootstrap.sh"
popd >nul

endlocal
