"""Unit tests for FFmpegVideoReader, VideoToExrConverter, transcoding, and converter wiring."""

from __future__ import annotations

import io
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import OpenImageIO as oiio
import pytest

from renderkit.core import converter as converter_module
from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ConversionConfig,
    WatermarkConfig,
)
from renderkit.core.converter import SequenceConverter
from renderkit.core.transcode import (
    VideoTranscodeConfig,
    generate_video_proxy,
    transcode_video,
)
from renderkit.core.video_ingest import (
    VideoToExrConfig,
    VideoToExrConverter,
    format_sequence_frame_path,
)
from renderkit.exceptions import ConfigurationError, ConversionCancelledError
from renderkit.io import video_reader as video_reader_module
from renderkit.io.file_info import FileInfo
from renderkit.io.video_reader import FFmpegVideoReader, VideoInfo, VideoReadError


def _make_solid_imagebuf(
    width: int,
    height: int,
    color: tuple[float, float, float] = (0.5, 0.25, 0.125),
    pixel_aspect: float = 1.0,
) -> oiio.ImageBuf:
    spec = oiio.ImageSpec(width, height, 3, oiio.FLOAT)
    if abs(pixel_aspect - 1.0) > 1e-4:
        spec.attribute("PixelAspectRatio", float(pixel_aspect))
    buf = oiio.ImageBuf(spec)
    arr = np.zeros((height, width, 3), dtype=np.float32)
    arr[:, :] = color
    assert buf.set_pixels(oiio.ROI.All, arr)
    return buf


class _FakeVideoReader:
    def __init__(
        self,
        info: VideoInfo,
        frames: list[tuple[int, oiio.ImageBuf]],
    ) -> None:
        self.info = info
        self.frames = frames
        self.iter_calls: list[dict[str, Any]] = []

    def probe_video(self, _path: Path) -> VideoInfo:
        return self.info

    def iter_frames(
        self,
        _path: Path,
        *,
        start_frame: int | None = None,
        end_frame: int | None = None,
        bit_depth: int = 16,
    ):
        self.iter_calls.append(
            {
                "start_frame": start_frame,
                "end_frame": end_frame,
                "bit_depth": bit_depth,
            }
        )
        yield from self.frames


class _SpyEncoder:
    def __init__(self, output_path: Path, fps: float, **kwargs: Any) -> None:
        self.output_path = output_path
        self.fps = fps
        self.kwargs = kwargs
        self.initialized_size: tuple[int, int] | None = None
        self.frames: list[oiio.ImageBuf] = []
        self.closed = False
        self.aborted = False
        self.fail_on_write_index: int | None = None

    def initialize(self, width: int, height: int) -> None:
        self.initialized_size = (width, height)

    def write_frame(self, buf: oiio.ImageBuf) -> None:
        if self.fail_on_write_index is not None and len(self.frames) == self.fail_on_write_index:
            raise RuntimeError("simulated write failure")
        self.frames.append(buf)

    def close(self) -> None:
        self.closed = True

    def abort(self) -> None:
        self.aborted = True


class TestFFmpegVideoReader:
    """Tests for FFmpegVideoReader probing and frame iteration."""

    def test_probe_video_missing_file_raises_file_not_found(self, tmp_path: Path) -> None:
        reader = FFmpegVideoReader()
        with pytest.raises(FileNotFoundError):
            reader.probe_video(tmp_path / "missing.mov")

    def test_probe_video_parses_stream_metadata(self, monkeypatch, tmp_path: Path) -> None:
        video_file = tmp_path / "plate.mov"
        video_file.write_bytes(b"stub")

        payload = {
            "streams": [
                {
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "24000/1001",
                    "avg_frame_rate": "24/1",
                    "nb_frames": "48",
                    "sample_aspect_ratio": "4:3",
                    "codec_name": "prores",
                    "pix_fmt": "yuv422p10le",
                }
            ]
        }

        monkeypatch.setattr(video_reader_module, "get_ffprobe_exe", lambda: "ffprobe")
        monkeypatch.setattr(video_reader_module.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(
            video_reader_module.subprocess,
            "run",
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps(payload), stderr=""
            ),
        )

        info = FFmpegVideoReader().probe_video(video_file)

        assert info.width == 1920
        assert info.height == 1080
        assert info.fps == pytest.approx(24000 / 1001)
        assert info.frame_count == 48
        assert info.pixel_aspect == pytest.approx(4 / 3)
        assert info.codec_name == "prores"
        assert info.pix_fmt == "yuv422p10le"

    def test_probe_video_raises_on_missing_stream(self, monkeypatch, tmp_path: Path) -> None:
        video_file = tmp_path / "audio_only.mov"
        video_file.write_bytes(b"stub")

        monkeypatch.setattr(video_reader_module, "get_ffprobe_exe", lambda: "ffprobe")
        monkeypatch.setattr(video_reader_module.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(
            video_reader_module.subprocess,
            "run",
            lambda *_args, **_kwargs: subprocess.CompletedProcess(
                args=[], returncode=0, stdout=json.dumps({"streams": []}), stderr=""
            ),
        )

        with pytest.raises(VideoReadError, match="No video stream"):
            FFmpegVideoReader().probe_video(video_file)

    @pytest.mark.parametrize("bit_depth", [8, 16])
    def test_iter_frames_decodes_pixels_and_cleans_up(
        self, monkeypatch, tmp_path: Path, bit_depth: int
    ) -> None:
        video_file = tmp_path / "plate.mp4"
        video_file.write_bytes(b"stub")

        if bit_depth == 16:
            frame0 = np.full((2, 3, 3), 65535, dtype="<u2").tobytes()
            frame1 = np.zeros((2, 3, 3), dtype="<u2").tobytes()
            expected_pix_fmt = "rgb48le"
        else:
            frame0 = np.full((2, 3, 3), 255, dtype=np.uint8).tobytes()
            frame1 = np.zeros((2, 3, 3), dtype=np.uint8).tobytes()
            expected_pix_fmt = "rgb24"

        class FakeProc:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(frame0 + frame1)
                self.stderr = io.BytesIO(b"")
                self.returncode = 0
                self.terminated = False
                self.waited = False

            def poll(self):
                return 0 if self.waited else None

            def wait(self, timeout=None):
                self.waited = True
                return self.returncode

            def terminate(self) -> None:
                self.terminated = True

            def kill(self) -> None:
                self.terminated = True

        captured_cmds: list[list[str]] = []
        proc = FakeProc()

        def fake_popen(cmd, **_kwargs):
            captured_cmds.append(cmd)
            return proc

        monkeypatch.setattr(video_reader_module, "get_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(video_reader_module.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(video_reader_module.subprocess, "Popen", fake_popen)

        reader = FFmpegVideoReader()
        monkeypatch.setattr(
            reader,
            "probe_video",
            lambda _p: VideoInfo(width=3, height=2, fps=24.0, pixel_aspect=2.0),
        )

        frames = list(
            reader.iter_frames(video_file, start_frame=5, end_frame=6, bit_depth=bit_depth)
        )

        assert len(frames) == 2
        assert frames[0][0] == 5
        assert frames[1][0] == 6
        assert np.allclose(frames[0][1].get_pixels(oiio.FLOAT), 1.0, atol=1e-4)
        assert np.allclose(frames[1][1].get_pixels(oiio.FLOAT), 0.0, atol=1e-4)
        assert frames[0][1].spec().get_float_attribute("PixelAspectRatio") == pytest.approx(2.0)
        assert proc.stdout.closed
        assert proc.stderr.closed
        assert proc.waited
        cmd = captured_cmds[0]
        assert expected_pix_fmt in cmd
        assert "-frames:v" in cmd
        assert "2" in cmd
        assert any("select=between(n\\,5\\,6)" in part for part in cmd)

    def test_iter_frames_early_close_terminates_process(self, monkeypatch, tmp_path: Path) -> None:
        video_file = tmp_path / "plate.mp4"
        video_file.write_bytes(b"stub")
        frame_bytes = np.zeros((2, 2, 3), dtype=np.uint8).tobytes()

        class HangingProc:
            def __init__(self) -> None:
                self.stdout = io.BytesIO(frame_bytes * 3)
                self.stderr = io.BytesIO(b"")
                self.returncode = None
                self.terminated = False
                self.waited = False

            def poll(self):
                return 0 if self.terminated else None

            def wait(self, timeout=None):
                self.waited = True
                self.returncode = 0
                return 0

            def terminate(self) -> None:
                self.terminated = True

            def kill(self) -> None:
                self.terminated = True

        proc = HangingProc()
        monkeypatch.setattr(video_reader_module, "get_ffmpeg_exe", lambda: "ffmpeg")
        monkeypatch.setattr(video_reader_module.shutil, "which", lambda name: f"/usr/bin/{name}")
        monkeypatch.setattr(video_reader_module.subprocess, "Popen", lambda *_a, **_k: proc)

        reader = FFmpegVideoReader()
        monkeypatch.setattr(
            reader, "probe_video", lambda _p: VideoInfo(width=2, height=2, fps=24.0)
        )

        gen = reader.iter_frames(video_file, bit_depth=8)
        idx, _buf = next(gen)
        assert idx == 0
        gen.close()

        assert proc.terminated
        assert proc.waited
        assert proc.stdout.closed
        assert proc.stderr.closed

    def test_iter_frames_validates_arguments(self, tmp_path: Path) -> None:
        reader = FFmpegVideoReader()
        video_file = tmp_path / "plate.mp4"
        with pytest.raises(ValueError, match="bit_depth"):
            list(reader.iter_frames(video_file, bit_depth=12))
        with pytest.raises(ValueError, match="start_frame"):
            list(reader.iter_frames(video_file, start_frame=10, end_frame=5))


class TestVideoToExrIngest:
    """Tests for pattern formatting and VideoToExrConverter."""

    @pytest.mark.parametrize(
        ("pattern", "frame", "expected"),
        [
            ("plates/shot.%04d.exr", 1001, Path("plates/shot.1001.exr")),
            ("plates/shot.%d.exr", 7, Path("plates/shot.7.exr")),
            ("plates/shot.####.exr", 42, Path("plates/shot.0042.exr")),
            ("shot#1/plate.###.exr", 5, Path("shot#1/plate.005.exr")),
        ],
    )
    def test_format_sequence_frame_path(self, pattern: str, frame: int, expected: Path) -> None:
        assert format_sequence_frame_path(pattern, frame) == expected

    def test_format_sequence_frame_path_requires_token(self) -> None:
        with pytest.raises(ValueError, match="frame token"):
            format_sequence_frame_path("plates/shot.exr", 1001)

    def test_config_rejects_invalid_compression(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="Invalid EXR compression"):
            VideoToExrConfig(
                input_path=tmp_path / "in.mov",
                output_pattern=str(tmp_path / "out.%04d.exr"),
                compression="jpeg2000",
            )

    def test_converter_writes_readable_exr_frames(self, tmp_path: Path) -> None:
        input_video = tmp_path / "in.mov"
        input_video.write_bytes(b"stub")
        out_dir = tmp_path / "plates"

        fake_reader = _FakeVideoReader(
            VideoInfo(width=8, height=6, fps=24.0, frame_count=2, pixel_aspect=2.0),
            [
                (0, _make_solid_imagebuf(8, 6, (0.5, 0.5, 0.5), pixel_aspect=2.0)),
                (1, _make_solid_imagebuf(8, 6, (0.25, 0.25, 0.25), pixel_aspect=2.0)),
            ],
        )

        config = VideoToExrConfig(
            input_path=input_video,
            output_pattern=str(out_dir / "plate.####.exr"),
            start_frame=1001,
            source_start_frame=0,
            source_end_frame=1,
            compression="zip",
            half_float=True,
            input_space="sRGB",
            output_space="Linear",
        )
        written = VideoToExrConverter(config, video_reader=fake_reader).convert()

        assert written == [out_dir / "plate.1001.exr", out_dir / "plate.1002.exr"]
        assert fake_reader.iter_calls == [{"start_frame": 0, "end_frame": 1, "bit_depth": 16}]

        inp = oiio.ImageInput.open(str(written[0]))
        assert inp is not None
        try:
            spec = inp.spec()
            assert spec.width == 8
            assert spec.height == 6
            assert spec.format == oiio.HALF
            assert spec.get_string_attribute("compression") == "zip"
            assert spec.get_float_attribute("PixelAspectRatio") == pytest.approx(2.0)
            pixels = inp.read_image(oiio.FLOAT)
            assert pixels is not None
            # sRGB 0.5 linearized should be below 0.5
            assert float(pixels[0, 0, 0]) < 0.45
        finally:
            inp.close()
        assert not any(out_dir.glob("*.partial.exr"))

    def test_converter_cancels_on_progress_callback(self, tmp_path: Path) -> None:
        input_video = tmp_path / "in.mov"
        input_video.write_bytes(b"stub")
        fake_reader = _FakeVideoReader(
            VideoInfo(width=4, height=4, fps=24.0, frame_count=2),
            [
                (0, _make_solid_imagebuf(4, 4)),
                (1, _make_solid_imagebuf(4, 4)),
            ],
        )
        config = VideoToExrConfig(
            input_path=input_video,
            output_pattern=str(tmp_path / "plate.%04d.exr"),
            input_space="Linear",
            output_space="Linear",
        )
        with pytest.raises(ConversionCancelledError):
            VideoToExrConverter(config, video_reader=fake_reader).convert(
                progress_callback=lambda _cur, _tot: False
            )


class TestVideoTranscodeAndProxy:
    """Tests for editorial video transcoding and proxy generation."""

    def test_transcode_config_validation(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="FPS"):
            VideoTranscodeConfig(tmp_path / "a.mov", tmp_path / "b.mp4", fps=0)
        with pytest.raises(ConfigurationError, match="Quality"):
            VideoTranscodeConfig(tmp_path / "a.mov", tmp_path / "b.mp4", quality=11)
        with pytest.raises(ConfigurationError, match="Gamma"):
            VideoTranscodeConfig(tmp_path / "a.mov", tmp_path / "b.mp4", gamma=0)

    def test_transcode_video_scales_applies_overlays_and_closes(self, tmp_path: Path) -> None:
        input_video = tmp_path / "edit.mov"
        input_video.write_bytes(b"stub")
        output_video = tmp_path / "review.mp4"

        fake_reader = _FakeVideoReader(
            VideoInfo(width=128, height=72, fps=24.0, frame_count=2, pixel_aspect=1.5),
            [
                (0, _make_solid_imagebuf(128, 72, (0.2, 0.2, 0.2), pixel_aspect=1.5)),
                (1, _make_solid_imagebuf(128, 72, (0.3, 0.3, 0.3), pixel_aspect=1.5)),
            ],
        )
        created_encoders: list[_SpyEncoder] = []

        def factory(out_path: Path, fps: float, **kwargs: Any) -> _SpyEncoder:
            enc = _SpyEncoder(out_path, fps, **kwargs)
            created_encoders.append(enc)
            return enc

        config = VideoTranscodeConfig(
            input_path=input_video,
            output_path=output_video,
            codec="libx264",
            quality=8,
            scale_width=64,
            burnin_config=BurnInConfig(
                elements=[BurnInElement(text_template="Frame {frame}", zone="top_left")]
            ),
            watermark_config=WatermarkConfig(text="REVIEW", opacity=20, font_size=16),
        )

        result = transcode_video(config, video_reader=fake_reader, encoder_factory=factory)

        assert result == output_video
        enc = created_encoders[0]
        assert enc.initialized_size == (64, 36)
        assert enc.fps == 24.0
        assert enc.kwargs["pixel_aspect"] == pytest.approx(1.5)
        assert len(enc.frames) == 2
        assert enc.frames[0].spec().width == 64
        assert enc.frames[0].spec().height == 36
        assert enc.closed is True
        assert enc.aborted is False

    def test_transcode_video_aborts_encoder_on_write_error(self, tmp_path: Path) -> None:
        input_video = tmp_path / "edit.mov"
        input_video.write_bytes(b"stub")
        fake_reader = _FakeVideoReader(
            VideoInfo(width=16, height=16, fps=24.0, frame_count=2),
            [(0, _make_solid_imagebuf(16, 16)), (1, _make_solid_imagebuf(16, 16))],
        )
        created_encoders: list[_SpyEncoder] = []

        def factory(out_path: Path, fps: float, **kwargs: Any) -> _SpyEncoder:
            enc = _SpyEncoder(out_path, fps, **kwargs)
            enc.fail_on_write_index = 1
            created_encoders.append(enc)
            return enc

        config = VideoTranscodeConfig(input_path=input_video, output_path=tmp_path / "out.mp4")
        with pytest.raises(RuntimeError, match="simulated write failure"):
            transcode_video(config, video_reader=fake_reader, encoder_factory=factory)

        assert created_encoders[0].aborted is True
        assert created_encoders[0].closed is False

    @pytest.mark.parametrize(
        ("codec", "expected_name"),
        [
            ("libx264", "shot_proxy.mp4"),
            ("prores_hq", "shot_proxy.mov"),
            ("dnxhr_hq", "shot_proxy.mov"),
        ],
    )
    def test_generate_video_proxy_defaults_and_scaling(
        self, tmp_path: Path, codec: str, expected_name: str
    ) -> None:
        input_video = tmp_path / "shot.mov"
        input_video.write_bytes(b"stub")
        fake_reader = _FakeVideoReader(
            VideoInfo(width=100, height=50, fps=24.0, frame_count=1),
            [(0, _make_solid_imagebuf(100, 50))],
        )
        created_encoders: list[_SpyEncoder] = []

        def factory(out_path: Path, fps: float, **kwargs: Any) -> _SpyEncoder:
            enc = _SpyEncoder(out_path, fps, **kwargs)
            created_encoders.append(enc)
            return enc

        result = generate_video_proxy(
            input_video,
            scale_factor=0.5,
            codec=codec,
            quality=7,
            video_reader=fake_reader,
            encoder_factory=factory,
        )

        assert result == tmp_path / "Proxy" / expected_name
        assert created_encoders[0].initialized_size == (50, 24)
        assert created_encoders[0].closed is True

    @pytest.mark.parametrize("scale_factor", [0.0, -0.5, 1.5])
    def test_generate_video_proxy_rejects_invalid_scale(
        self, tmp_path: Path, scale_factor: float
    ) -> None:
        with pytest.raises(ConfigurationError, match="scale_factor"):
            generate_video_proxy(tmp_path / "shot.mov", scale_factor=scale_factor)


class TestSequenceConverterWatermarkAndFrameRange:
    """Tests for SequenceConverter watermark and frame_range wiring."""

    @pytest.mark.parametrize("prefetch_workers", [1, 2])
    def test_sequence_converter_wires_watermark_and_frame_range(
        self, monkeypatch, tmp_path: Path, prefetch_workers: int
    ) -> None:
        captured_options: list[Any] = []

        class _Seq:
            def get_file_path(self, frame_num: int) -> Path:
                return tmp_path / f"plate.{frame_num:04d}.exr"

        class _Reader:
            def read_imagebuf(self, *_args, **_kwargs):
                return _make_solid_imagebuf(16, 16)

        class _Encoder:
            def write_frame(self, _buf) -> None:
                pass

            def close(self) -> None:
                pass

            def abort(self) -> None:
                pass

        def fake_prepare_frame_buffer(options):
            captured_options.append(options)

            class _Prepared:
                buf = _make_solid_imagebuf(16, 16)

            return _Prepared()

        monkeypatch.setattr(converter_module, "prepare_frame_buffer", fake_prepare_frame_buffer)
        monkeypatch.setattr(
            converter_module.ImageReaderFactory,
            "create_reader",
            staticmethod(lambda *_a, **_k: _Reader()),
        )

        wm = WatermarkConfig(text="INTERNAL", opacity=30, tiled=True)
        config = ConversionConfig(
            input_pattern=str(tmp_path / "plate.%04d.exr"),
            output_path=str(tmp_path / "out.mp4"),
            fps=24.0,
            prefetch_workers=prefetch_workers,
            watermark_config=wm,
        )
        converter = SequenceConverter(config)
        converter.sequence = _Seq()
        converter.reader = _Reader()
        converter.color_converter = converter._create_color_converter(config.color_space_preset)
        converter.encoder = _Encoder()

        assert converter.watermark_processor is not None

        converter._process_frames(
            frame_numbers=[1001, 1002],
            output_width=16,
            output_height=16,
            width=16,
            height=16,
            input_space=None,
            file_info=FileInfo(width=16, height=16, channels=3, layers=[]),
            progress_callback=None,
            show_progress=False,
        )

        assert len(captured_options) == 2
        for opts in captured_options:
            assert opts.watermark_config == wm
            assert opts.watermark_processor is not None
            assert opts.burnin_metadata == {"frame_range": "1001-1002"}


def test_ffmpeg_capability_fallback_skips_minimal_bundled_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When bundled FFmpeg lacks an encoder or container demuxer, system FFmpeg is selected."""
    from renderkit.core import ffmpeg_utils

    bundled = "C:/repo/vendor/ffmpeg/windows/ffmpeg.exe"
    system_full = "C:/msys64/ucrt64/bin/ffmpeg.exe"

    monkeypatch.setattr(ffmpeg_utils, "_AUTO_BUNDLED_FFMPEG", bundled)
    monkeypatch.setattr(ffmpeg_utils, "find_system_ffmpeg_executables", lambda: [system_full])
    monkeypatch.setattr(
        ffmpeg_utils,
        "ffmpeg_supports_encoder",
        lambda exe, enc: (enc == "libx264")
        if exe == bundled
        else (enc in {"libx264", "prores_ks"}),
    )
    monkeypatch.setattr(
        ffmpeg_utils,
        "ffmpeg_supports_video_decode",
        lambda exe: exe == system_full,
    )

    assert ffmpeg_utils.resolve_ffmpeg_for_encoder(bundled, "libx264") == bundled
    assert ffmpeg_utils.resolve_ffmpeg_for_encoder(bundled, "prores_ks") == system_full
    assert ffmpeg_utils.resolve_ffmpeg_for_decoding(bundled) == system_full
    # Explicit user override is never replaced even if it lacks capabilities
    assert ffmpeg_utils.resolve_ffmpeg_for_encoder("C:/custom/ffmpeg.exe", "prores_ks") == (
        "C:/custom/ffmpeg.exe"
    )
    assert ffmpeg_utils.resolve_ffmpeg_for_decoding("C:/custom/ffmpeg.exe") == (
        "C:/custom/ffmpeg.exe"
    )
