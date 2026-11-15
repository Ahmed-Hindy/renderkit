#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_ffmpeg="${1:-$(command -v ffmpeg || true)}"
target_dir="${2:-${repo_root}/vendor/ffmpeg/linux}"

if [[ -z "${source_ffmpeg}" || ! -f "${source_ffmpeg}" ]]; then
  echo "A system FFmpeg executable is required." >&2
  exit 1
fi

encoders="$("${source_ffmpeg}" -hide_banner -encoders 2>&1)"
for encoder in libx264 libx265 libaom-av1; do
  if [[ "${encoders}" != *"${encoder}"* ]]; then
    echo "FFmpeg is missing the required encoder: ${encoder}" >&2
    exit 1
  fi
done

if ! command -v ldd >/dev/null 2>&1; then
  echo "ldd is required to discover FFmpeg's shared libraries." >&2
  exit 1
fi
if ldd_output="$(ldd "${source_ffmpeg}" 2>&1)"; then
  :
elif [[ "${ldd_output}" != *"not a dynamic executable"* &&
        "${ldd_output}" != *"statically linked"* ]]; then
  echo "Could not inspect FFmpeg's shared libraries: ${ldd_output}" >&2
  exit 1
fi
if [[ "${ldd_output}" == *"not found"* ]]; then
  echo "FFmpeg has missing shared libraries:" >&2
  echo "${ldd_output}" >&2
  exit 1
fi
mkdir -p "${target_dir}/lib"
cp -L -- "${source_ffmpeg}" "${target_dir}/ffmpeg.bin"
chmod +x "${target_dir}/ffmpeg.bin"
while read -r soname library; do
  case "${soname}" in
    libc.so.*|libm.so.*|libpthread.so.*|libdl.so.*|librt.so.*|ld-linux*) continue ;;
  esac
  cp -L -- "${library}" "${target_dir}/lib/${soname}"
done < <(printf '%s\n' "${ldd_output}" | awk '$2 == "=>" && $3 ~ /^\// {print $1, $3}')

cat > "${target_dir}/ffmpeg" <<'EOF'
#!/usr/bin/env sh
set -eu
here="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
export LD_LIBRARY_PATH="${here}/lib${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"
exec "${here}/ffmpeg.bin" "$@"
EOF
chmod +x "${target_dir}/ffmpeg"
version="$("${target_dir}/ffmpeg" -version)"
printf '%s\n' "${version%%$'\n'*}"
echo "Staged FFmpeg in ${target_dir}"
