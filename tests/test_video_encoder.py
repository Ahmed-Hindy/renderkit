"""Tests for FFmpeg video encoder probing and initialization."""

import logging
from pathlib import Path
from types import SimpleNamespace

import pytest

from renderkit.exceptions import VideoEncodingError
from renderkit.processing import video_encoder
from renderkit.processing.video_encoder import (
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
