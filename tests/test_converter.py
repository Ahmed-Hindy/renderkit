"""Tests for converter (integration tests would require actual EXR files)."""

import builtins
from pathlib import Path

import pytest

from renderkit.core import converter as converter_module
from renderkit.core.config import (
    VALID_BURNIN_ZONES,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfig,
    ConversionConfigBuilder,
    SlateConfig,
)
from renderkit.core.converter import SequenceConverter
from renderkit.exceptions import (
    ColorSpaceError,
    ConfigurationError,
    ConversionCancelledError,
    ImageReadError,
    VideoEncodingError,
)
from renderkit.io.file_info import FileInfo
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.processing.contact_sheet import compute_contact_sheet_label_metrics
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

    @pytest.mark.parametrize("gamma", [0.0, -0.5])
    def test_config_validation_gamma_positive(self, gamma: float) -> None:
        """Test gamma validation requires values > 0."""
        with pytest.raises(ConfigurationError, match="Gamma must be greater than 0"):
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                gamma=gamma,
            )

    @pytest.mark.parametrize("zone", sorted(VALID_BURNIN_ZONES))
    def test_burnin_element_accepts_valid_zones(self, zone: str) -> None:
        """Valid HUD zone names should be accepted on BurnInElement."""
        element = BurnInElement(text_template="{frame}", zone=zone)
        assert element.zone == zone

    def test_burnin_element_rejects_invalid_zone(self) -> None:
        """Invalid HUD zone names should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Invalid burn-in zone"):
            BurnInElement(text_template="{frame}", zone="middle_nowhere")


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

    def test_builder_with_ocio_grade_and_slate(self) -> None:
        """Test builder OCIO, grade, and slate methods."""
        slate = SlateConfig(
            enabled=True,
            title="Shot Review",
            show="DEMO",
            shot="sh010",
            artist="Alex",
            notes="Final",
        )
        config = (
            ConversionConfigBuilder()
            .with_input_pattern("render.%04d.exr")
            .with_output_path("output.mp4")
            .with_ocio(
                config_path="/studio/config.ocio",
                input_space="ACEScg",
                display="sRGB",
                view="ACES 1.0 - SDR Video",
                output_space="Output - sRGB",
            )
            .with_grade(exposure=1.25, gamma=2.2)
            .with_slate(slate)
            .build()
        )

        assert config.color_space_preset == ColorSpacePreset.OCIO_CONVERSION
        assert config.ocio_config_path == "/studio/config.ocio"
        assert config.explicit_input_color_space == "ACEScg"
        assert config.ocio_display == "sRGB"
        assert config.ocio_view == "ACES 1.0 - SDR Video"
        assert config.ocio_output_space == "Output - sRGB"
        assert config.exposure == 1.25
        assert config.gamma == 2.2
        assert config.slate_config == slate

    def test_builder_with_grade_rejects_non_positive_gamma(self) -> None:
        """Builder with_grade should validate gamma > 0."""
        with pytest.raises(ConfigurationError, match="Gamma must be greater than 0"):
            ConversionConfigBuilder().with_grade(exposure=0.0, gamma=0.0)


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


class TestSequenceConverterLayout:
    """Tests for converter output layout calculations."""

    def test_contact_sheet_resolution_uses_shared_label_metrics(self) -> None:
        """Contact sheet output dimensions should match renderer label metrics."""
        cs_config = ContactSheetConfig(
            columns=2,
            thumbnail_width=40,
            padding=5,
            show_labels=True,
            font_size=8,
        )
        converter = SequenceConverter.__new__(SequenceConverter)
        converter.config = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path="output.mp4",
            contact_sheet_mode=True,
            contact_sheet_config=cs_config,
        )
        converter.contact_sheet_generator = object()
        file_info = FileInfo(width=100, height=50, channels=3, layers=["beauty", "diffuse", "z"])

        output_width, output_height = converter._resolve_output_resolution(file_info, 100, 50)

        _, label_h = compute_contact_sheet_label_metrics(cs_config)
        assert output_width == (40 + (5 * 2)) * 2
        assert output_height == (20 + (5 * 2) + label_h) * 2


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

    def test_process_sequential_frame_plan_uses_freeze_frame_policy(self) -> None:
        """Sequential frame-plan processing should write missing frames from the last valid frame."""

        class RecordingEncoder:
            def __init__(self) -> None:
                self.frames = []

            def write_frame(self, buf) -> None:
                self.frames.append(buf.name)

        class NamedBuf:
            def __init__(self, name: str) -> None:
                self.name = name

        converter = self._converter()
        converter.encoder = RecordingEncoder()
        plan = converter._build_frame_processing_plan([1, 3])

        def process_frame(frame_num, *args, **kwargs):
            buf = NamedBuf(str(frame_num))
            converter._write_frame_buf(frame_num, buf)
            return buf

        converter._process_single_frame_buf = process_frame

        success_count = converter._process_sequential_frame_plan(
            plan,
            output_width=100,
            output_height=100,
            width=100,
            height=100,
            scaler=object(),
            input_space=None,
            contact_sheet_generator=None,
            tick_progress=lambda _index: None,
        )

        assert success_count == 3
        assert converter.encoder.frames == ["1", "1", "3"]

    def test_process_frames_calls_encoder_abort_on_frame_error(self) -> None:
        """Frame failures should call encoder.abort() instead of close() when available."""

        class AbortableEncoder:
            def __init__(self) -> None:
                self.aborted = False
                self.closed = False

            def abort(self) -> None:
                self.aborted = True

            def close(self) -> None:
                self.closed = True

        encoder = AbortableEncoder()
        converter = self._converter()
        converter.encoder = encoder

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

        assert encoder.aborted is True
        assert encoder.closed is False

    def test_process_frames_calls_encoder_abort_on_cancellation(self) -> None:
        """Progress callback cancellation should call encoder.abort() instead of close()."""

        class AbortableEncoder:
            def __init__(self) -> None:
                self.aborted = False
                self.closed = False

            def abort(self) -> None:
                self.aborted = True

            def close(self) -> None:
                self.closed = True

        encoder = AbortableEncoder()
        converter = self._converter()
        converter.encoder = encoder
        converter._process_single_frame_buf = lambda *args, **kwargs: _FakeBuf()

        with pytest.raises(ConversionCancelledError, match="cancelled"):
            converter._process_frames(
                frame_numbers=[1, 2],
                output_width=100,
                output_height=100,
                width=100,
                height=100,
                input_space=None,
                file_info=FileInfo(width=100, height=100, channels=4, layers=[]),
                progress_callback=lambda _cur, _tot: False,
                show_progress=False,
            )

        assert encoder.aborted is True
        assert encoder.closed is False

    def test_initialize_encoder_passes_non_unit_pixel_aspect_only(self, monkeypatch) -> None:
        """_initialize_encoder should omit pixel_aspect=1.0 and pass non-unit pixel_aspect."""
        calls: list[tuple[tuple, dict]] = []

        class SpyEncoder:
            def __init__(self, *args, **kwargs) -> None:
                calls.append((args, kwargs))

            def initialize(self, _w: int, _h: int) -> None:
                pass

        monkeypatch.setattr(converter_module, "VideoEncoder", SpyEncoder)

        converter = self._converter()
        converter._initialize_encoder(1920, 1080, pixel_aspect=1.0)
        converter._initialize_encoder(1920, 1080, pixel_aspect=2.0)

        assert calls[0][1] == {}
        assert calls[1][1] == {"pixel_aspect": 2.0}

    def test_configure_color_converter_wires_ocio_and_grade(self, monkeypatch) -> None:
        """_configure_color_converter should promote to OCIO and pass grade parameters."""
        captured: list[tuple[tuple, dict]] = []

        class SpyColorConverter:
            def __init__(self, *args, **kwargs) -> None:
                captured.append((args, kwargs))

        monkeypatch.setattr(converter_module, "ColorSpaceConverter", SpyColorConverter)

        converter = SequenceConverter(
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="output.mp4",
                fps=24.0,
                ocio_config_path="/studio/config.ocio",
                ocio_display="sRGB",
                ocio_view="ACES 1.0 - SDR Video",
                ocio_output_space="Output - sRGB",
                explicit_input_color_space="ACEScg",
                exposure=1.5,
                gamma=2.2,
            )
        )

        input_space = converter._configure_color_converter(None)

        assert input_space == "ACEScg"
        assert len(captured) == 1
        args, kwargs = captured[0]
        assert args == (ColorSpacePreset.OCIO_CONVERSION,)
        assert kwargs == {
            "ocio_config_path": "/studio/config.ocio",
            "ocio_display": "sRGB",
            "ocio_view": "ACES 1.0 - SDR Video",
            "ocio_output_space": "Output - sRGB",
            "exposure": 1.5,
            "gamma": 2.2,
        }


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
