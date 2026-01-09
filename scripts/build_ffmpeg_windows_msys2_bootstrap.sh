#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"

export PATH=/ucrt64/bin:/usr/bin:/bin
export PKG_CONFIG=/ucrt64/bin/pkgconf
export PKG_CONFIG_PATH=/ucrt64/lib/pkgconfig

pacman -Sy --noconfirm

install_pkg() {
  pacman -S --needed --noconfirm "$1"
}

install_first_available() {
  for pkg in "$@"; do
    if pacman -Si "$pkg" >/dev/null 2>&1; then
      install_pkg "$pkg"
      return 0
    fi
  done
  echo "Missing package: $*" >&2
  return 1
}

install_pkg base-devel
install_pkg mingw-w64-ucrt-x86_64-toolchain
install_pkg mingw-w64-ucrt-x86_64-nasm
install_pkg mingw-w64-ucrt-x86_64-yasm
install_pkg mingw-w64-ucrt-x86_64-pkgconf
install_first_available mingw-w64-ucrt-x86_64-x264 mingw-w64-ucrt-x86_64-libx264
install_first_available mingw-w64-ucrt-x86_64-x265 mingw-w64-ucrt-x86_64-libx265
install_first_available mingw-w64-ucrt-x86_64-aom mingw-w64-ucrt-x86_64-libaom

if [ -x /c/Windows/System32/curl.exe ]; then
  curl() { /c/Windows/System32/curl.exe --ssl-no-revoke "$@"; }
  export -f curl
fi

cd "${repo_root}"
bash scripts/build_ffmpeg_windows_msys2.sh
