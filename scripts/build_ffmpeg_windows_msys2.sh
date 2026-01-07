#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "${script_dir}/.." && pwd)"
build_root="${repo_root}/_ffmpeg_build"
vendor_dir="${repo_root}/vendor/ffmpeg"

rm -rf "${build_root}"
mkdir -p "${build_root}"
cd "${build_root}"

git clone --depth 1 https://git.ffmpeg.org/ffmpeg.git
cd ffmpeg

./configure \
  --prefix="${build_root}/ffmpeg/build" \
  --target-os=mingw32 --arch=x86_64 \
  --enable-gpl \
  --disable-doc --disable-debug --enable-small \
  --disable-programs --enable-ffmpeg \
  --disable-ffplay --disable-ffprobe \
  --disable-everything \
  --enable-protocol=file,pipe \
  --enable-demuxer=rawvideo \
  --enable-decoder=rawvideo \
  --enable-muxer=mov,mp4 \
  --enable-filter=scale,format \
  --enable-swscale \
  --enable-libx265 --enable-libaom \
  --enable-encoder=libx265,libaom-av1 \
  --enable-parser=hevc,av1

make -j"$(nproc)"
make install

mkdir -p "${vendor_dir}"
cp -f "${build_root}/ffmpeg/build/bin/ffmpeg.exe" "${vendor_dir}/ffmpeg.exe"
strip "${vendor_dir}/ffmpeg.exe"

if ldd "${vendor_dir}/ffmpeg.exe" | grep -q "not found"; then
  echo "Missing DLL dependencies for ffmpeg.exe" >&2
  exit 1
fi

deps=$(ldd "${vendor_dir}/ffmpeg.exe" \
  | awk '/=>/ {print $3}' \
  | grep -i 'ucrt64/bin/.*\.dll$' \
  | sort -u)

for dep in ${deps}; do
  cp -f "${dep}" "${vendor_dir}/"
done

echo "Bundled ffmpeg written to ${vendor_dir}"
