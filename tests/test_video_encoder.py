"""Tests for FFmpeg video encoder probing and initialization."""

import logging
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import OpenImageIO as oiio
import pytest

from renderkit.exceptions import ConfigurationError, VideoEncodingError
from renderkit.processing import video_encoder
from renderkit.processing.pixels import float_pixels_to_uint16
from renderkit.processing.video_encoder import (
    CODEC_PROFILES,
    EncoderProbeResult,
    VideoEncoder,
    _RawFfmpegPipeWriter,
)


def test_probe_available_encoders_reports_subprocess_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """FFmpeg probe failures should be distinguishable from successful empty probes."""

    def raise_os_error(*args, **kwargs):
        raise OSError("ffmpeg missing")

    monkeypatch.setattr(video_encoder, "get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(video_encoder.subprocess, "run", raise_os_error)

    with caplog.at_level(logging.WARNING, logger="renderkit.processing.video_encoder"):
        result = video_encoder._probe_available_encoders()

    assert result.failed
    assert result.error == "ffmpeg missing"
    assert result.encoders == frozenset()
    assert "Unable to query FFmpeg encoders: ffmpeg missing" in caplog.text


def test_probe_available_encoders_success_can_be_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful probe with no parsed encoders is not a probe failure."""

    def run_empty_probe(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(video_encoder, "get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(video_encoder.subprocess, "run", run_empty_probe)

    result = video_encoder._probe_available_encoders()

    assert result.succeeded
    assert result.encoders == frozenset()
    assert result.error is None


def test_initialize_rejects_successful_empty_encoder_probe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A successful empty encoder list should not be treated as an unknown capability state."""

    def fail_if_writer_starts(*args, **kwargs):
        raise AssertionError("writer should not start when encoder absence is confirmed")

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset()),
    )
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", fail_if_writer_starts)

    encoder = VideoEncoder(output_path=tmp_path / "out.mp4", fps=24.0)

    with pytest.raises(VideoEncodingError, match="Available encoders: none"):
        encoder.initialize(1920, 1080)


def test_initialize_attempts_requested_codec_when_probe_fails(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Probe failures remain warning-only but are explicit in logs."""

    captured: dict[str, str] = {}

    class FakeWriter:
        def __init__(
            self,
            output_path,
            width,
            height,
            fps,
            codec,
            pix_fmt_in,
            pix_fmt_out,
            ffmpeg_params,
            ffmpeg_log_level,
            bitrate,
        ) -> None:
            captured["codec"] = codec

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset(), error="probe exploded"),
    )
    monkeypatch.setattr(video_encoder.VideoEncoder, "_configure_ffmpeg_report", lambda self: None)
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", FakeWriter)

    encoder = VideoEncoder(output_path=tmp_path / "out.mp4", fps=24.0, codec="libx264")

    with caplog.at_level(logging.WARNING, logger="renderkit.processing.video_encoder"):
        encoder.initialize(1920, 1080)

    assert captured == {"codec": "libx264"}
    assert encoder.is_initialized()
    assert "Skipping FFmpeg encoder availability validation because probing failed" in caplog.text
    assert "probe exploded" in caplog.text


def test_read_ffmpeg_report_tail_ignores_os_read_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Report tails are best-effort diagnostics and should not mask encoding errors."""

    report_path = tmp_path / "ffmpeg.log"
    report_path.write_text("ffmpeg output", encoding="utf-8")
    encoder = VideoEncoder(output_path=tmp_path / "out.mp4", fps=24.0)
    encoder._ffmpeg_report_path = report_path

    def raise_os_error(self, *args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "read_text", raise_os_error)

    with caplog.at_level(logging.DEBUG, logger="renderkit.processing.video_encoder"):
        assert encoder._read_ffmpeg_report_tail() is None

    assert "Unable to read FFmpeg report tail" in caplog.text
    assert "permission denied" in caplog.text


def test_raw_ffmpeg_pipe_writer_close_raises_on_nonzero_returncode() -> None:
    """FFmpeg finalization failures should be reported after the process exits."""

    class FakeStdin:
        def __init__(self) -> None:
            self.closed = False

        def close(self) -> None:
            self.closed = True

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.returncode = None

        def poll(self):
            return None

        def wait(self) -> None:
            self.returncode = 42

    process = FakeProcess()
    writer = _RawFfmpegPipeWriter.__new__(_RawFfmpegPipeWriter)
    writer._process = process
    writer._cmd_str = "ffmpeg -i pipe:0 out.mp4"

    with pytest.raises(RuntimeError, match="FFmpeg exited with code 42"):
        writer.close()

    assert process.stdin.closed


def test_video_encoder_close_raises_finalization_failures(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Writer close exceptions should propagate as VideoEncodingError."""

    class FailingWriter:
        def close(self) -> None:
            raise RuntimeError("simulated ffmpeg finalization failure")

    restored = False

    def restore_env(self) -> None:
        nonlocal restored
        restored = True

    monkeypatch.setattr(VideoEncoder, "_restore_ffmpeg_report_env", restore_env)

    encoder = VideoEncoder(output_path=tmp_path / "out.mp4", fps=24.0)
    encoder._writer = FailingWriter()

    with pytest.raises(VideoEncodingError, match="Failed to finalize video encoding"):
        encoder.close()

    assert encoder._writer is None
    assert restored


def test_video_encoder_partial_output_promotion_on_close(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Partial output file is promoted to final output_path on successful close."""
    output_path = tmp_path / "render.mp4"
    captured: dict[str, object] = {}

    class FakeWriter:
        def __init__(
            self,
            partial_path,
            width,
            height,
            fps,
            codec,
            pix_fmt_in,
            pix_fmt_out,
            ffmpeg_params,
            ffmpeg_log_level,
            bitrate,
        ) -> None:
            captured["partial_path"] = partial_path
            partial_path.write_bytes(b"encoded-bytes")

        def close(self) -> None:
            return None

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx264"})),
    )
    monkeypatch.setattr(video_encoder.VideoEncoder, "_configure_ffmpeg_report", lambda self: None)
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", FakeWriter)

    encoder = VideoEncoder(output_path=output_path, fps=24.0, codec="libx264")
    encoder.initialize(64, 64)
    assert captured["partial_path"] == encoder._partial_output_path
    assert encoder._partial_output_path.exists()
    assert not output_path.exists()

    encoder.close()
    assert not encoder._partial_output_path.exists()
    assert output_path.exists()
    assert output_path.read_bytes() == b"encoded-bytes"


def test_video_encoder_partial_cleanup_on_close_failure_and_abort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Partial output file is removed on close failure and on abort()."""
    monkeypatch.setattr(VideoEncoder, "_restore_ffmpeg_report_env", lambda self: None)

    # Case 1: close() failure removes partial file
    output_fail = tmp_path / "fail.mp4"

    class FailingWriter:
        def close(self) -> None:
            raise RuntimeError("boom")

    encoder_fail = VideoEncoder(output_path=output_fail, fps=24.0)
    encoder_fail._partial_output_path.write_bytes(b"partial")
    encoder_fail._writer = FailingWriter()

    with pytest.raises(VideoEncodingError, match="Failed to finalize video encoding"):
        encoder_fail.close()

    assert not encoder_fail._partial_output_path.exists()
    assert not output_fail.exists()

    # Case 2: abort() calls writer.abort() and removes partial file
    output_abort = tmp_path / "abort.mp4"
    aborted = False

    class AbortableWriter:
        def abort(self) -> None:
            nonlocal aborted
            aborted = True

    encoder_abort = VideoEncoder(output_path=output_abort, fps=24.0)
    encoder_abort._partial_output_path.write_bytes(b"partial")
    encoder_abort._writer = AbortableWriter()
    encoder_abort.abort()

    assert aborted is True
    assert encoder_abort._writer is None
    assert not encoder_abort._partial_output_path.exists()
    assert not output_abort.exists()


def test_video_encoder_pixel_aspect_setsar_filter(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """pixel_aspect != 1.0 appends -vf setsar=... and non-positive values fail validation."""
    with pytest.raises(ConfigurationError, match="Pixel aspect ratio must be positive"):
        VideoEncoder(output_path=tmp_path / "bad.mp4", fps=24.0, pixel_aspect=0.0)

    captured_params: list[str] = []

    class FakeWriter:
        def __init__(
            self,
            output_path,
            width,
            height,
            fps,
            codec,
            pix_fmt_in,
            pix_fmt_out,
            ffmpeg_params,
            ffmpeg_log_level,
            bitrate,
        ) -> None:
            captured_params.extend(ffmpeg_params)

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx264"})),
    )
    monkeypatch.setattr(video_encoder.VideoEncoder, "_configure_ffmpeg_report", lambda self: None)
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", FakeWriter)

    encoder = VideoEncoder(output_path=tmp_path / "anamorphic.mp4", fps=24.0, pixel_aspect=2.0)
    encoder.initialize(128, 64)

    assert "-vf" in captured_params
    vf_idx = captured_params.index("-vf")
    assert captured_params[vf_idx + 1] == "setsar=2.000000"


@pytest.mark.parametrize(
    (
        "codec_name",
        "expected_ffmpeg",
        "expected_in",
        "expected_out",
        "expected_bits",
        "expected_mb",
    ),
    [
        ("hevc_10bit", "libx265", "rgb48le", "yuv420p10le", 10, 16),
        ("prores_hq", "prores_ks", "rgb48le", "yuv422p10le", 10, 2),
        ("prores_4444", "prores_ks", "rgba64le", "yuva444p12le", 12, 2),
        ("dnxhr_hqx", "dnxhd", "rgb48le", "yuv422p10le", 10, 2),
    ],
)
def test_video_encoder_high_bitdepth_and_prores_profiles_write_uint16(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    codec_name: str,
    expected_ffmpeg: str,
    expected_in: str,
    expected_out: str,
    expected_bits: int,
    expected_mb: int,
) -> None:
    """10-bit/12-bit/ProRes/DNxHR profiles configure FFmpeg pix_fmts and pipe uint16 frames."""
    captured: dict[str, object] = {}
    written_bytes: list[bytes] = []

    class FakeWriter:
        def __init__(
            self,
            output_path,
            width,
            height,
            fps,
            codec,
            pix_fmt_in,
            pix_fmt_out,
            ffmpeg_params,
            ffmpeg_log_level,
            bitrate,
        ) -> None:
            captured["codec"] = codec
            captured["width"] = width
            captured["height"] = height
            captured["pix_fmt_in"] = pix_fmt_in
            captured["pix_fmt_out"] = pix_fmt_out
            captured["ffmpeg_params"] = list(ffmpeg_params)

        def append_data(self, frame: np.ndarray) -> None:
            captured["frame_dtype"] = frame.dtype
            captured["frame_shape"] = frame.shape
            written_bytes.append(frame.tobytes())

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx265", "prores_ks", "dnxhd"})),
    )
    monkeypatch.setattr(video_encoder.VideoEncoder, "_configure_ffmpeg_report", lambda self: None)
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", FakeWriter)

    ext = ".mov" if "prores" in codec_name or "dnxhr" in codec_name else ".mp4"
    encoder = VideoEncoder(output_path=tmp_path / f"out{ext}", fps=24.0, codec=codec_name)
    assert encoder.macro_block_size == expected_mb
    assert CODEC_PROFILES[codec_name].bit_depth == expected_bits

    encoder.initialize(16, 16)

    assert captured["codec"] == expected_ffmpeg
    assert captured["pix_fmt_in"] == expected_in
    assert captured["pix_fmt_out"] == expected_out
    for param in CODEC_PROFILES[codec_name].extra_params:
        assert param in captured["ffmpeg_params"]

    # Create a 4-channel float ImageBuf (16x16) with out-of-range edge values
    spec = oiio.ImageSpec(16, 16, 4, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    arr = np.full((16, 16, 4), 0.5, dtype=np.float32)
    arr[0, 0] = [0.0, 1.0, 2.0, 0.25]
    buf.set_pixels(buf.roi, arr)

    encoder.write_frame(buf)

    expected_channels = 4 if CODEC_PROFILES[codec_name].needs_alpha else 3
    assert captured["frame_dtype"] == np.uint16
    assert captured["frame_shape"] == (16, 16, expected_channels)
    decoded = np.frombuffer(written_bytes[0], dtype=np.uint16).reshape(16, 16, expected_channels)
    assert decoded[0, 0, 0] == 0
    assert decoded[0, 0, 1] == 65535
    assert decoded[0, 0, 2] == 65535


def test_float_pixels_to_uint16_clamps_and_handles_nonfinite() -> None:
    """float_pixels_to_uint16 handles NaN/Inf, rounds accurately, and returns contiguous uint16."""
    arr = np.array([[[-0.5, 0.0, 0.5, 1.0, 1.5, np.nan, np.inf, -np.inf]]], dtype=np.float32)
    out = float_pixels_to_uint16(arr)

    assert out.dtype == np.uint16
    assert out.flags["C_CONTIGUOUS"]
    assert out[0, 0, 0] == 0
    assert out[0, 0, 1] == 0
    assert out[0, 0, 2] == 32768
    assert out[0, 0, 3] == 65535
    assert out[0, 0, 4] == 65535
    assert out[0, 0, 5] == 0
    assert out[0, 0, 6] == 65535
    assert out[0, 0, 7] == 0


@pytest.mark.parametrize(
    "codec_name",
    [
        "h264_nvenc",
        "hevc_nvenc",
        "h264_qsv",
        "hevc_qsv",
        "h264_videotoolbox",
        "hevc_videotoolbox",
        "h264_vaapi",
    ],
)
def test_hardware_encoder_profiles_defined(codec_name: str) -> None:
    """Hardware encoder profiles use identical ffmpeg_codec, yuv420p, rgb24, and .mp4."""
    profile = CODEC_PROFILES[codec_name]
    assert profile.ffmpeg_codec == codec_name
    assert profile.pix_fmt_in == "rgb24"
    assert profile.pix_fmt_out == "yuv420p"
    assert profile.bit_depth == 8
    assert profile.container_ext == ".mp4"


def test_get_codec_profile_container_extensions() -> None:
    """ProRes/DNxHR resolve to .mov while H.264/HEVC resolve to .mp4."""
    assert video_encoder.get_codec_profile("prores_422").container_ext == ".mov"
    assert video_encoder.get_codec_profile("dnxhr_hqx").container_ext == ".mov"
    assert video_encoder.get_codec_profile("libx264").container_ext == ".mp4"
    assert video_encoder.get_codec_profile("h264_nvenc").container_ext == ".mp4"


@pytest.mark.parametrize(
    ("requested", "expected_fallback"),
    [
        ("h264_nvenc", "libx264"),
        ("h264_qsv", "libx264"),
        ("h264_videotoolbox", "libx264"),
        ("h264_vaapi", "libx264"),
        ("hevc_nvenc", "libx265"),
        ("hevc_qsv", "libx265"),
        ("hevc_videotoolbox", "libx265"),
    ],
)
def test_select_available_encoder_hardware_fallback_warns(
    requested: str,
    expected_fallback: str,
) -> None:
    """Unavailable hardware encoders fall back to libx264/libx265 and warn via logger."""
    warnings: list[str] = []

    class FakeLogger:
        def warning(self, msg: str, *args: object) -> None:
            warnings.append(msg % args if args else msg)

    selected, warning_msg = video_encoder.select_available_encoder(
        requested,
        {"libx264", "libx265", "mpeg4"},
        logger=FakeLogger(),
    )

    assert selected == expected_fallback
    assert warning_msg is not None
    assert requested in warning_msg
    assert expected_fallback in warning_msg
    assert warnings == [warning_msg]


def test_select_available_encoder_uses_hardware_when_present() -> None:
    """Available hardware encoder is returned without fallback warning."""
    selected, warning_msg = video_encoder.select_available_encoder(
        "h264_nvenc",
        {"h264_nvenc", "libx264"},
    )
    assert selected == "h264_nvenc"
    assert warning_msg is None


def test_video_encoder_initializes_with_hardware_fallback_and_direct_nvenc(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """VideoEncoder falls back from unavailable NVENC to libx264 and uses NVENC when present."""
    captured: list[tuple[str, list[str]]] = []

    class FakeWriter:
        def __init__(
            self,
            output_path,
            width,
            height,
            fps,
            codec,
            pix_fmt_in,
            pix_fmt_out,
            ffmpeg_params,
            ffmpeg_log_level,
            bitrate,
        ) -> None:
            captured.append((codec, list(ffmpeg_params)))

    monkeypatch.setattr(video_encoder.VideoEncoder, "_configure_ffmpeg_report", lambda self: None)
    monkeypatch.setattr(video_encoder, "_RawFfmpegPipeWriter", FakeWriter)

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx264"})),
    )
    fallback_encoder = VideoEncoder(
        output_path=tmp_path / "fallback.mp4", fps=24.0, codec="h264_nvenc"
    )
    with caplog.at_level(logging.WARNING, logger="renderkit.processing.video_encoder"):
        fallback_encoder.initialize(64, 64)
    assert captured[-1][0] == "libx264"
    assert "-crf" in captured[-1][1]
    assert "falling back to 'libx264'" in caplog.text

    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"h264_nvenc", "libx264"})),
    )
    hw_encoder = VideoEncoder(output_path=tmp_path / "nvenc.mp4", fps=24.0, codec="h264_nvenc")
    hw_encoder.initialize(64, 64)
    assert captured[-1][0] == "h264_nvenc"
    assert "-preset" in captured[-1][1]
    assert "-cq" in captured[-1][1]


def test_video_encoder_ffreport_isolated_to_subprocess_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """RENDERKIT_FFMPEG_LOG=1 passes FFREPORT via Popen env without mutating os.environ."""
    popen_calls: list[dict[str, object]] = []

    class FakeStdin:
        def close(self) -> None:
            return None

    class FakeProcess:
        def __init__(self) -> None:
            self.stdin = FakeStdin()
            self.returncode = None

        def poll(self):
            return None

        def wait(self) -> None:
            self.returncode = 0

    def fake_popen(cmd, **kwargs):
        popen_calls.append({"cmd": cmd, "kwargs": kwargs})
        return FakeProcess()

    monkeypatch.setenv("RENDERKIT_FFMPEG_LOG", "1")
    monkeypatch.setenv("FFREPORT", "sentinel=1")
    monkeypatch.setattr(
        video_encoder,
        "get_encoder_probe_result",
        lambda: EncoderProbeResult(frozenset({"libx264"})),
    )
    monkeypatch.setattr(video_encoder, "get_ffmpeg_exe", lambda: "ffmpeg")
    monkeypatch.setattr(video_encoder.subprocess, "Popen", fake_popen)

    encoder = VideoEncoder(output_path=tmp_path / "out.mp4", fps=24.0, codec="libx264")
    encoder.initialize(64, 64)

    assert os.environ.get("FFREPORT") == "sentinel=1"
    assert len(popen_calls) == 1
    popen_env = popen_calls[0]["kwargs"]["env"]
    assert isinstance(popen_env, dict)
    assert popen_env["FFREPORT"].startswith("file=")
    assert popen_env["FFREPORT"].endswith(":level=48")
    assert popen_env["FFREPORT"] != "sentinel=1"

    encoder.close()
    assert os.environ.get("FFREPORT") == "sentinel=1"
    assert encoder._ffmpeg_env is None
