"""Tests for converter (integration tests would require actual EXR files)."""

import builtins
from pathlib import Path

import pytest

from renderkit.core import converter as converter_module
from renderkit.core.config import ConversionConfig, ConversionConfigBuilder
from renderkit.core.converter import SequenceConverter
from renderkit.exceptions import (
    ColorSpaceError,
    ConfigurationError,
    ImageReadError,
    VideoEncodingError,
)
from renderkit.io.file_info import FileInfo
from renderkit.processing.video_encoder import VideoEncoder


class TestConversionConfig:
    """Tests for ConversionConfig."""

    def test_config_creation(self) -> None:
        """Test creating a valid configuration."""
        config = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path="output.mp4",
            fps=24.0,
        )

        assert config.input_pattern == "render.%04d.exr"
        assert config.output_path == "output.mp4"
        assert config.fps == 24.0

    def test_config_validation_fps(self) -> None:
        """Test FPS validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                fps=-1.0,
            )

    def test_config_validation_frame_range(self) -> None:
        """Test frame range validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                start_frame=10,
                end_frame=5,  # Invalid: start > end
            )

    def test_config_validation_prefetch_workers(self) -> None:
        """Test prefetch workers validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                prefetch_workers=0,
            )

    def test_config_validation_quality_range(self) -> None:
        """Test quality validation."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                quality=11,
            )

    @pytest.mark.parametrize("quality", [-1, 11])
    def test_video_encoder_validation_quality_range(self, quality: int, tmp_path: Path) -> None:
        """Test video encoder quality validation."""
        with pytest.raises(ConfigurationError, match="Quality must be between 0 and 10"):
            VideoEncoder(
                output_path=tmp_path / "output.mp4",
                fps=24.0,
                quality=quality,
            )

    def test_config_validation_contact_sheet_requires_config(self) -> None:
        """Test contact sheet mode requires explicit layout configuration."""
        with pytest.raises(ConfigurationError):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                contact_sheet_mode=True,
            )


class TestConversionConfigBuilder:
    """Tests for ConversionConfigBuilder."""

    def test_builder_pattern(self) -> None:
        """Test building configuration with builder pattern."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_fps(24.0)
            .build()
        )

        assert config.input_pattern == "render.%04d.exr"
        assert config.output_path == "output.mp4"
        assert config.fps == 24.0

    def test_builder_missing_required(self) -> None:
        """Test builder error when required fields are missing."""
        with pytest.raises(ConfigurationError):
            ConversionConfigBuilder().with_output_path("output.mp4").build()

        with pytest.raises(ConfigurationError):
            ConversionConfigBuilder().with_input_pattern("render.%04d.exr").build()

    def test_builder_with_resolution(self) -> None:
        """Test builder with resolution."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_resolution(1920, 1080)
            .build()
        )

        assert config.width == 1920
        assert config.height == 1080

    def test_builder_with_frame_range(self) -> None:
        """Test builder with frame range."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_frame_range(100, 200)
            .build()
        )

        assert config.start_frame == 100
        assert config.end_frame == 200

    def test_builder_with_open_ended_frame_range(self) -> None:
        """Test builder with an open-ended frame range."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_frame_range(100, None)
            .build()
        )

        assert config.start_frame == 100
        assert config.end_frame is None

    def test_builder_with_prefetch_workers(self) -> None:
        """Test builder with prefetch workers."""
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_prefetch_workers(4)
            .build()
        )

        assert config.prefetch_workers == 4


class _FakeSequence:
    def get_file_path(self, frame_num: int) -> Path:
        return Path(f"render.{frame_num:04d}.exr")


class _FakeBuf:
    class _Spec:
        width = 100
        height = 100

    def spec(self):
        return self._Spec()


class _PassThroughColorConverter:
    def convert_buf(self, buf, input_space=None):
        return buf


class TestSequenceConverterFailures:
    """Tests for strict frame failure behavior."""

    def _converter(self) -> SequenceConverter:
        converter = SequenceConverter.__new__(SequenceConverter)
        converter.sequence = _FakeSequence()
        converter.config = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path="output.mp4",
            fps=24.0,
        )
        converter._layer_map = None
        return converter

    def test_prepare_frame_raises_on_read_failure(self) -> None:
        """Existing-frame read failures should abort instead of returning None."""

        class FailingReader:
            def read_imagebuf(self, path, layer=None, layer_map=None):
                raise ImageReadError("read failed")

        converter = self._converter()

        with pytest.raises(ImageReadError, match="Failed to read frame 1"):
            converter._prepare_frame_buf(
                1,
                100,
                100,
                100,
                100,
                scaler=object(),
                input_space=None,
                reader=FailingReader(),
                color_converter=_PassThroughColorConverter(),
                burnin_processor=None,
            )

    def test_prepare_frame_raises_on_color_failure(self) -> None:
        """Color conversion failures should abort instead of skipping frames."""

        class Reader:
            def read_imagebuf(self, path, layer=None, layer_map=None):
                return _FakeBuf()

        class FailingColorConverter:
            def convert_buf(self, buf, input_space=None):
                raise ColorSpaceError("bad transform")

        converter = self._converter()

        with pytest.raises(ColorSpaceError, match="Color space conversion failed for frame 2"):
            converter._prepare_frame_buf(
                2,
                100,
                100,
                100,
                100,
                scaler=object(),
                input_space=None,
                reader=Reader(),
                color_converter=FailingColorConverter(),
                burnin_processor=None,
            )

    def test_prepare_frame_wraps_contact_sheet_render_failure(self) -> None:
        """Contact sheet render failures should include frame context."""

        class FailingContactSheetGenerator:
            def composite_layers(self, path):
                raise RuntimeError("label render failed")

        converter = self._converter()

        with pytest.raises(VideoEncodingError, match="Failed to build contact sheet for frame 3"):
            converter._prepare_frame_buf(
                3,
                100,
                100,
                100,
                100,
                scaler=object(),
                input_space=None,
                reader=object(),
                color_converter=_PassThroughColorConverter(),
                burnin_processor=None,
                contact_sheet_generator=FailingContactSheetGenerator(),
            )

    def test_process_frames_raises_encoder_finalization_failure(self) -> None:
        """Close-time encoder failures should fail an otherwise successful conversion."""

        class FailingCloseEncoder:
            def write_frame(self, _buf) -> None:
                # This test isolates encoder finalization; frame writing is stubbed out.
                pass

            def close(self) -> None:
                raise VideoEncodingError("final mp4 flush failed")

        converter = self._converter()
        converter.encoder = FailingCloseEncoder()
        converter._process_single_frame_buf = lambda *args, **kwargs: _FakeBuf()

        with pytest.raises(VideoEncodingError, match="final mp4 flush failed"):
            converter._process_frames(
                frame_numbers=[1],
                output_width=100,
                output_height=100,
                width=100,
                height=100,
                input_space=None,
                file_info=FileInfo(width=100, height=100, channels=4, layers=[]),
                progress_callback=None,
                show_progress=False,
            )

    def test_process_frames_preserves_frame_failure_over_cleanup_failure(self) -> None:
        """Cleanup failures should not hide the frame-processing error already in flight."""

        class FailingCloseEncoder:
            def close(self) -> None:
                raise VideoEncodingError("final mp4 flush failed")

        converter = self._converter()
        converter.encoder = FailingCloseEncoder()

        def raise_frame_failure(*args, **kwargs):
            raise VideoEncodingError("frame preparation failed")

        converter._process_single_frame_buf = raise_frame_failure

        with pytest.raises(VideoEncodingError, match="frame preparation failed"):
            converter._process_frames(
                frame_numbers=[1],
                output_width=100,
                output_height=100,
                width=100,
                height=100,
                input_space=None,
                file_info=FileInfo(width=100, height=100, channels=4, layers=[]),
                progress_callback=None,
                show_progress=False,
            )

    def test_process_frames_finalizes_after_successful_frame_writes(self) -> None:
        """Successful frame writes should still reach encoder finalization."""

        class ClosingEncoder:
            def __init__(self) -> None:
                self.closed = False

            def write_frame(self, _buf) -> None:
                # This test only asserts finalization after successful frame processing.
                pass

            def close(self) -> None:
                self.closed = True

        encoder = ClosingEncoder()
        converter = self._converter()
        converter.encoder = encoder
        converter._process_single_frame_buf = lambda *args, **kwargs: _FakeBuf()

        converter._process_frames(
            frame_numbers=[1],
            output_width=100,
            output_height=100,
            width=100,
            height=100,
            input_space=None,
            file_info=FileInfo(width=100, height=100, channels=4, layers=[]),
            progress_callback=None,
            show_progress=False,
        )

        assert encoder.closed


class TestSequenceConverterProgress:
    """Tests for CLI progress-bar behavior."""

    def test_non_interactive_stderr_disables_tqdm_by_default(self, monkeypatch) -> None:
        """Captured stderr should not create a tqdm progress bar."""

        class FakeStderr:
            def isatty(self) -> bool:
                return False

        class FakeEncoder:
            def close(self) -> None:
                # The progress test only verifies close() is called safely.
                pass

        real_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "tqdm":
                raise AssertionError("tqdm should not be imported for captured stderr")
            return real_import(name, *args, **kwargs)

        converter = SequenceConverter(
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                fps=24.0,
            )
        )
        converter.sequence = _FakeSequence()
        converter.encoder = FakeEncoder()

        monkeypatch.setattr(converter_module.sys, "stderr", FakeStderr())
        monkeypatch.setattr(builtins, "__import__", guarded_import)
        monkeypatch.setattr(
            converter,
            "_process_single_frame_buf",
            lambda *args, **kwargs: _FakeBuf(),
        )

        converter._process_frames(
            frame_numbers=[1],
            output_width=100,
            output_height=100,
            width=100,
            height=100,
            input_space=None,
            file_info=FileInfo(width=100, height=100, channels=4, layers=[]),
            progress_callback=None,
            show_progress=None,
        )
