"""FFmpeg-based video reader for plate ingest and transcoding."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any, Optional

import numpy as np

from renderkit.core.ffmpeg_utils import get_ffmpeg_exe, get_ffprobe_exe, popen_kwargs
from renderkit.exceptions import RenderKitError
from renderkit.io.oiio_utils import require_oiio

logger = logging.getLogger(__name__)


class VideoReadError(RenderKitError, RuntimeError):
    """Raised when probing or decoding a video file fails."""


@dataclass(frozen=True)
class VideoInfo:
    """Metadata describing a probed video stream."""

    width: int
    height: int
    fps: float
    frame_count: Optional[int] = None
    pixel_aspect: float = 1.0
    codec_name: Optional[str] = None
    pix_fmt: Optional[str] = None


def _parse_rational_float(raw: object) -> Optional[float]:
    """Parse an FFprobe rational string (e.g. ``'24000/1001'``) or number into a positive float."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val > 0 else None
    text = str(raw).strip()
    if not text or text.upper() == "N/A":
        return None
    for sep in ("/", ":"):
        if sep in text:
            parts = text.split(sep, 1)
            try:
                num = float(parts[0])
                den = float(parts[1])
            except ValueError:
                return None
            if den <= 0 or num <= 0:
                return None
            return num / den
    try:
        val = float(text)
    except ValueError:
        return None
    return val if val > 0 else None


def _parse_int_positive(raw: object) -> Optional[int]:
    """Parse a positive integer field from FFprobe output."""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw > 0 else None
    text = str(raw).strip()
    if not text or text.upper() == "N/A":
        return None
    try:
        val = int(text)
    except ValueError:
        return None
    return val if val > 0 else None


def _resolve_executable(exe: str, fallback_name: str) -> str:
    """Verify an FFmpeg/FFprobe executable exists on disk or PATH."""
    exe_path = Path(exe)
    if exe_path.is_file():
        return str(exe_path)
    which_exe = shutil.which(exe) or shutil.which(fallback_name)
    if which_exe:
        return which_exe
    raise VideoReadError(f"{fallback_name} executable not found: {exe}")


def _read_exact(stream: IO[bytes], num_bytes: int) -> bytes:
    """Read up to ``num_bytes`` from ``stream``, handling short reads until EOF."""
    chunks: list[bytes] = []
    remaining = num_bytes
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


class FFmpegVideoReader:
    """Stream video metadata and decoded RGB frames via FFprobe and FFmpeg."""

    def probe_video(self, path: Path) -> VideoInfo:
        """Probe video stream dimensions, frame rate, and pixel aspect ratio.

        Args:
            path: Path to the source video file.

        Returns:
            Populated :class:`VideoInfo` describing the primary video stream.

        Raises:
            FileNotFoundError: If ``path`` does not exist.
            VideoReadError: If ``ffprobe`` is unavailable, fails, or reports no valid video stream.
        """
        video_path = Path(path)
        if not video_path.is_file():
            raise FileNotFoundError(f"Video file not found: {video_path}")

        ffprobe_exe = _resolve_executable(get_ffprobe_exe(), "ffprobe")
        cmd = [
            ffprobe_exe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,nb_frames,sample_aspect_ratio,codec_name,pix_fmt",
            "-of",
            "json",
            str(video_path),
        ]
        try:
            result = subprocess.run(  # NOSONAR
                cmd,
                capture_output=True,
                text=True,
                check=False,
                shell=False,
                **popen_kwargs(),
            )
        except OSError as exc:
            raise VideoReadError(f"Failed to execute ffprobe for '{video_path}': {exc}") from exc

        if result.returncode != 0:
            details = (
                result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
            )
            raise VideoReadError(f"ffprobe failed for '{video_path}': {details}")

        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise VideoReadError(f"Invalid JSON from ffprobe for '{video_path}': {exc}") from exc

        if not isinstance(payload, dict):
            raise VideoReadError(f"Unexpected ffprobe output format for '{video_path}'.")

        streams = payload.get("streams")
        if not isinstance(streams, list) or not streams or not isinstance(streams[0], dict):
            raise VideoReadError(f"No video stream found in '{video_path}'.")

        stream = streams[0]
        width = _parse_int_positive(stream.get("width"))
        height = _parse_int_positive(stream.get("height"))
        if width is None or height is None:
            raise VideoReadError(f"Invalid video dimensions in '{video_path}'.")

        fps = _parse_rational_float(stream.get("r_frame_rate")) or _parse_rational_float(
            stream.get("avg_frame_rate")
        )
        if fps is None:
            raise VideoReadError(f"Could not determine frame rate for '{video_path}'.")

        frame_count = _parse_int_positive(stream.get("nb_frames"))
        pixel_aspect = _parse_rational_float(stream.get("sample_aspect_ratio")) or 1.0

        raw_codec = stream.get("codec_name")
        codec_name = str(raw_codec) if isinstance(raw_codec, str) and raw_codec else None
        raw_pix_fmt = stream.get("pix_fmt")
        pix_fmt = str(raw_pix_fmt) if isinstance(raw_pix_fmt, str) and raw_pix_fmt else None

        return VideoInfo(
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            pixel_aspect=pixel_aspect,
            codec_name=codec_name,
            pix_fmt=pix_fmt,
        )

    def iter_frames(
        self,
        path: Path,
        *,
        start_frame: Optional[int] = None,
        end_frame: Optional[int] = None,
        bit_depth: int = 16,
    ) -> Iterator[tuple[int, Any]]:
        """Yield decoded video frames as float32 ``oiio.ImageBuf`` instances.

        Args:
            path: Path to the source video file.
            start_frame: Optional 0-based inclusive start frame index.
            end_frame: Optional 0-based inclusive end frame index.
            bit_depth: Intermediate pipe bit depth (``8`` or ``16``).

        Yields:
            Tuples of ``(source_frame_index, oiio.ImageBuf)``.

        Raises:
            ValueError: If ``bit_depth`` is not 8 or 16, or the frame range is invalid.
            FileNotFoundError: If ``path`` does not exist.
            VideoReadError: If FFmpeg fails or outputs a truncated frame.
        """
        if bit_depth not in (8, 16):
            raise ValueError(f"Unsupported bit_depth {bit_depth}; expected 8 or 16.")
        if start_frame is not None and start_frame < 0:
            raise ValueError("start_frame must be >= 0.")
        if end_frame is not None and end_frame < 0:
            raise ValueError("end_frame must be >= 0.")
        if start_frame is not None and end_frame is not None and start_frame > end_frame:
            raise ValueError("start_frame must be <= end_frame.")

        oiio = require_oiio(VideoReadError, "OpenImageIO is required to decode video frames.")
        video_path = Path(path)
        info = self.probe_video(video_path)
        ffmpeg_exe = _resolve_executable(get_ffmpeg_exe(), "ffmpeg")

        pix_fmt = "rgb48le" if bit_depth == 16 else "rgb24"
        cmd = [ffmpeg_exe, "-v", "error", "-i", str(video_path)]

        first_frame_idx = 0
        if start_frame is not None or end_frame is not None:
            s_idx = start_frame if start_frame is not None else 0
            first_frame_idx = s_idx
            if end_frame is not None:
                vf = f"select=between(n\\,{s_idx}\\,{end_frame}),setpts=PTS-STARTPTS"
                cmd.extend(["-vf", vf, "-vsync", "0", "-frames:v", str(end_frame - s_idx + 1)])
            else:
                vf = f"select=gte(n\\,{s_idx}),setpts=PTS-STARTPTS"
                cmd.extend(["-vf", vf, "-vsync", "0"])

        cmd.extend(["-f", "rawvideo", "-pix_fmt", pix_fmt, "pipe:1"])

        bytes_per_channel = 2 if bit_depth == 16 else 1
        frame_byte_count = info.width * info.height * 3 * bytes_per_channel

        try:
            proc = subprocess.Popen(  # NOSONAR
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,
                **popen_kwargs(),
            )
        except OSError as exc:
            raise VideoReadError(f"Failed to start ffmpeg for '{video_path}': {exc}") from exc

        if proc.stdout is None:
            proc.terminate()
            proc.wait()
            raise VideoReadError(f"FFmpeg stdout pipe unavailable for '{video_path}'.")

        frame_index = first_frame_idx
        dtype = np.dtype("<u2") if bit_depth == 16 else np.uint8
        scale = np.float32(65535.0 if bit_depth == 16 else 255.0)
        eof_reached = False

        try:
            while True:
                chunk = _read_exact(proc.stdout, frame_byte_count)
                if not chunk:
                    eof_reached = True
                    break
                if len(chunk) < frame_byte_count:
                    raise VideoReadError(
                        f"Truncated video frame at index {frame_index} in '{video_path}': "
                        f"expected {frame_byte_count} bytes, got {len(chunk)}."
                    )

                arr = (
                    np.frombuffer(chunk, dtype=dtype)
                    .reshape((info.height, info.width, 3))
                    .astype(np.float32)
                    / scale
                )
                arr = np.ascontiguousarray(arr)

                spec = oiio.ImageSpec(info.width, info.height, 3, oiio.FLOAT)
                if abs(info.pixel_aspect - 1.0) > 1e-4:
                    spec.attribute("PixelAspectRatio", float(info.pixel_aspect))
                buf = oiio.ImageBuf(spec)
                if not buf.set_pixels(oiio.ROI.All, arr):
                    raise VideoReadError(
                        f"Failed to populate ImageBuf for frame {frame_index}: {buf.geterror()}"
                    )

                yield frame_index, buf
                frame_index += 1

            if eof_reached:
                stderr_output = ""
                if proc.stderr is not None:
                    stderr_output = proc.stderr.read().decode("utf-8", errors="replace").strip()
                returncode = proc.wait()
                if returncode != 0:
                    details = stderr_output or f"exit code {returncode}"
                    raise VideoReadError(f"FFmpeg decode failed for '{video_path}': {details}")
        finally:
            for stream in (proc.stdout, proc.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        proc.kill()
                        proc.wait(timeout=2)
                    except (OSError, subprocess.TimeoutExpired):
                        pass
