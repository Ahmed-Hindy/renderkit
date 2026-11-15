"""Tests for JSON conversion presets and intro slate frame generation."""

import json
from pathlib import Path

import OpenImageIO as oiio
import pytest

from renderkit.core.config import (
    BurnInConfig,
    BurnInElement,
    ContactSheetConfig,
    ConversionConfig,
    SlateConfig,
    WatermarkConfig,
)
from renderkit.core.converter import SequenceConverter
from renderkit.core.presets import (
    PRESET_SCHEMA_VERSION,
    load_preset,
    resolve_preset_path,
    save_preset,
)
from renderkit.exceptions import ConfigurationError
from renderkit.io.file_info import FileInfo
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.processing.slate import SlateGenerator


class TestPresets:
    """Tests for saving and loading conversion presets."""

    def test_save_and_load_preset_round_trip(self, tmp_path: Path) -> None:
        """All non-path ConversionConfig fields should round-trip cleanly through JSON."""
        burnin = BurnInConfig(
            elements=[
                BurnInElement(
                    text_template="Frame {frame}",
                    x=20,
                    y=20,
                    font_size=18,
                    color=(0.9, 0.8, 0.7),
                    alignment="left",
                    zone="top_left",
                ),
                BurnInElement(
                    text_template="{shot}",
                    alignment="right",
                    zone="bottom_right",
                ),
            ],
            use_background=True,
            background_opacity=45,
        )
        contact_sheet = ContactSheetConfig(
            columns=3,
            thumbnail_width=320,
            padding=6,
            background_color=(0.05, 0.05, 0.05),
            show_labels=False,
            font_size=14,
            layer_width=320,
            layer_height=180,
        )
        slate = SlateConfig(
            enabled=True,
            title="Lookdev Turnaround",
            show="DEMO",
            shot="sh010",
            artist="Alex",
            notes="Check specular lobes",
            background_color=(0.08, 0.09, 0.12, 1.0),
        )
        watermark = WatermarkConfig(
            text="CONFIDENTIAL - {user}",
            opacity=30,
            font_size=42,
            tiled=True,
            spacing=180,
        )
        config = ConversionConfig(
            input_pattern="C:/work/render.%04d.exr",
            output_path="C:/work/out.mp4",
            prefetch_workers=4,
            fps=23.976,
            color_space_preset=ColorSpacePreset.OCIO_CONVERSION,
            width=1920,
            height=1080,
            codec="prores_hq",
            bitrate=50_000_000,
            quality=9,
            layer="beauty",
            start_frame=1001,
            end_frame=1048,
            explicit_input_color_space="ACEScg",
            burnin_config=burnin,
            contact_sheet_mode=True,
            contact_sheet_config=contact_sheet,
            ocio_config_path="/studio/ocio/config.ocio",
            ocio_display="sRGB",
            ocio_view="ACES 1.0 - SDR Video",
            ocio_output_space="Output - sRGB",
            exposure=0.5,
            gamma=2.2,
            slate_config=slate,
            watermark_config=watermark,
        )

        preset_path = tmp_path / "nested" / "lookdev.json"
        save_preset(config, preset_path)

        raw = json.loads(preset_path.read_text(encoding="utf-8"))
        assert raw["schema_version"] == PRESET_SCHEMA_VERSION
        assert "input_pattern" not in raw
        assert "output_path" not in raw

        loaded = load_preset(preset_path)
        rebuilt = ConversionConfig(
            input_pattern="D:/other/render.%04d.exr",
            output_path="D:/other/out.mp4",
            **loaded,
        )

        assert rebuilt.prefetch_workers == config.prefetch_workers
        assert rebuilt.fps == config.fps
        assert rebuilt.color_space_preset == config.color_space_preset
        assert rebuilt.width == config.width
        assert rebuilt.height == config.height
        assert rebuilt.codec == config.codec
        assert rebuilt.bitrate == config.bitrate
        assert rebuilt.quality == config.quality
        assert rebuilt.layer == config.layer
        assert rebuilt.start_frame == config.start_frame
        assert rebuilt.end_frame == config.end_frame
        assert rebuilt.explicit_input_color_space == config.explicit_input_color_space
        assert rebuilt.burnin_config == config.burnin_config
        assert rebuilt.contact_sheet_mode == config.contact_sheet_mode
        assert rebuilt.contact_sheet_config == config.contact_sheet_config
        assert rebuilt.ocio_config_path == config.ocio_config_path
        assert rebuilt.ocio_display == config.ocio_display
        assert rebuilt.ocio_view == config.ocio_view
        assert rebuilt.ocio_output_space == config.ocio_output_space
        assert rebuilt.exposure == config.exposure
        assert rebuilt.gamma == config.gamma
        assert rebuilt.slate_config == config.slate_config
        assert rebuilt.watermark_config == config.watermark_config

    def test_load_preset_missing_file_raises_configuration_error(self, tmp_path: Path) -> None:
        """Missing preset files should raise ConfigurationError."""
        with pytest.raises(ConfigurationError, match="Failed to read preset file"):
            load_preset(tmp_path / "missing.json")

    def test_load_preset_invalid_json_raises_configuration_error(self, tmp_path: Path) -> None:
        """Malformed JSON preset files should raise ConfigurationError."""
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{not valid json", encoding="utf-8")

        with pytest.raises(ConfigurationError, match="Invalid JSON"):
            load_preset(bad_file)

    @pytest.mark.parametrize(
        "payload",
        [
            [],
            {},
            {"schema_version": 2},
            {"schema_version": True},
            {"schema_version": 1, "color_space_preset": "unknown_preset"},
            {"schema_version": 1, "burnin_config": "bad"},
            {"schema_version": 1, "slate_config": {"background_color": [1.0, 2.0]}},
        ],
    )
    def test_load_preset_invalid_schema_or_fields_raises(
        self, tmp_path: Path, payload: object
    ) -> None:
        """Invalid schema version or malformed payload sections should raise ConfigurationError."""
        preset_file = tmp_path / "invalid.json"
        preset_file.write_text(json.dumps(payload), encoding="utf-8")

        with pytest.raises(ConfigurationError):
            load_preset(preset_file)

    def test_resolve_preset_path_direct_and_env_search(self, tmp_path: Path, monkeypatch) -> None:
        """resolve_preset_path should check direct paths then RENDERKIT_PRESET_PATH."""
        import os

        direct_file = tmp_path / "direct.json"
        direct_file.write_text('{"schema_version": 1}', encoding="utf-8")
        assert resolve_preset_path(direct_file) == direct_file

        dir_one = tmp_path / "presets_one"
        dir_two = tmp_path / "presets_two"
        dir_one.mkdir()
        dir_two.mkdir()

        first_match = dir_one / "dailies.json"
        first_match.write_text('{"schema_version": 1}', encoding="utf-8")
        second_match = dir_two / "dailies.json"
        second_match.write_text('{"schema_version": 1}', encoding="utf-8")
        studio_only = dir_two / "studio_hdr.json"
        studio_only.write_text('{"schema_version": 1}', encoding="utf-8")

        monkeypatch.setenv("RENDERKIT_PRESET_PATH", f"{dir_one}{os.pathsep}{dir_two}")
        assert resolve_preset_path("dailies") == first_match
        assert resolve_preset_path("dailies.json") == first_match
        assert resolve_preset_path("studio_hdr") == studio_only

        with pytest.raises(ConfigurationError, match="Preset file not found"):
            resolve_preset_path("nonexistent_preset")


class TestSlateGenerationAndPrepend:
    """Tests for SlateGenerator and SequenceConverter slate prepending."""

    def test_slate_generator_produces_expected_imagebuf(self) -> None:
        """SlateGenerator should render a 4-channel float ImageBuf at requested resolution."""
        slate_cfg = SlateConfig(
            enabled=True,
            title="Shot Review",
            show="DEMO",
            shot="sh010",
            artist="Alex",
            notes="Initial pass",
        )
        buf = SlateGenerator(slate_cfg).generate_slate_buf(
            320,
            180,
            {
                "frame_range": "1001-1010",
                "fps": "24.00",
                "resolution": "320x180",
                "colorspace": "ACEScg",
                "codec": "libx264",
                "date": "2026-11-15",
            },
        )
        spec = buf.spec()
        assert spec.width == 320
        assert spec.height == 180
        assert spec.nchannels == 4
        assert spec.format == oiio.FLOAT

    def test_sequence_converter_prepends_slate_frame_before_sequence_frames(self) -> None:
        """SequenceConverter._process_frames should write slate frame before frame 1001."""

        class FakeSequence:
            def get_file_path(self, frame_num: int) -> Path:
                return Path(f"render.{frame_num:04d}.exr")

        class RecordingEncoder:
            def __init__(self) -> None:
                self.written: list[tuple[int, int, int]] = []
                self.closed = False

            def write_frame(self, buf: oiio.ImageBuf) -> None:
                spec = buf.spec()
                self.written.append((spec.width, spec.height, spec.nchannels))

            def close(self) -> None:
                self.closed = True

            def abort(self) -> None:
                pass

        encoder = RecordingEncoder()
        converter = SequenceConverter(
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="out.mp4",
                fps=24.0,
                slate_config=SlateConfig(
                    enabled=True,
                    title="Review",
                    show="SHOW",
                    shot="sh010",
                    artist="Sam",
                ),
            )
        )
        converter.sequence = FakeSequence()
        converter.encoder = encoder

        def fake_process_single_frame_buf(frame_num, output_width, output_height, *_args, **_kw):
            seq_buf = oiio.ImageBuf(oiio.ImageSpec(output_width, output_height, 3, oiio.FLOAT))
            converter._write_frame_buf(frame_num, seq_buf)
            return seq_buf

        converter._process_single_frame_buf = fake_process_single_frame_buf

        converter._process_frames(
            frame_numbers=[1001, 1002],
            output_width=160,
            output_height=90,
            width=160,
            height=90,
            input_space="ACEScg",
            file_info=FileInfo(width=160, height=90, channels=3, layers=[]),
            progress_callback=None,
            show_progress=False,
        )

        assert encoder.closed is True
        # First written frame is 4-channel float slate; next two are 3-channel sequence frames.
        assert encoder.written == [
            (160, 90, 4),
            (160, 90, 3),
            (160, 90, 3),
        ]

    def test_sequence_converter_skips_disabled_slate(self) -> None:
        """Disabled SlateConfig should not prepend a slate frame."""

        class FakeSequence:
            def get_file_path(self, frame_num: int) -> Path:
                return Path(f"render.{frame_num:04d}.exr")

        class RecordingEncoder:
            def __init__(self) -> None:
                self.written: list[int] = []
                self.closed = False

            def write_frame(self, buf: oiio.ImageBuf) -> None:
                self.written.append(buf.spec().nchannels)

            def close(self) -> None:
                self.closed = True

            def abort(self) -> None:
                pass

        encoder = RecordingEncoder()
        converter = SequenceConverter(
            ConversionConfig(
                input_pattern="render.%04d.exr",
                output_path="out.mp4",
                fps=24.0,
                slate_config=SlateConfig(enabled=False, title="Hidden"),
            )
        )
        converter.sequence = FakeSequence()
        converter.encoder = encoder

        def fake_process_single_frame_buf(frame_num, output_width, output_height, *_args, **_kw):
            seq_buf = oiio.ImageBuf(oiio.ImageSpec(output_width, output_height, 3, oiio.FLOAT))
            converter._write_frame_buf(frame_num, seq_buf)
            return seq_buf

        converter._process_single_frame_buf = fake_process_single_frame_buf

        converter._process_frames(
            frame_numbers=[1001],
            output_width=160,
            output_height=90,
            width=160,
            height=90,
            input_space=None,
            file_info=FileInfo(width=160, height=90, channels=3, layers=[]),
            progress_callback=None,
            show_progress=False,
        )

        assert encoder.closed is True
        assert encoder.written == [3]
