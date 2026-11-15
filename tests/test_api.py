"""Tests for the public RenderKit API."""

import pytest

from renderkit.api import processor as processor_module
from renderkit.api.processor import RenderKit
from renderkit.core.config import BurnInConfig, BurnInElement, SlateConfig, WatermarkConfig
from renderkit.processing.color_space import ColorSpacePreset


def test_api_rejects_one_sided_resolution() -> None:
    """The public API should not silently ignore one resize dimension."""
    processor = RenderKit.__new__(RenderKit)

    with pytest.raises(ValueError, match="width and height must be used together"):
        processor.convert_exr_sequence_to_mp4(
            "render.%04d.exr",
            "output.mp4",
            width=1920,
        )


def test_api_preserves_one_sided_frame_range(monkeypatch) -> None:
    """A single API range bound should remain open-ended."""
    captured_configs = []

    class FakeSequenceConverter:
        def __init__(self, config) -> None:
            captured_configs.append(config)

        def convert(self, show_progress=None) -> None:
            pass

    monkeypatch.setattr(processor_module, "SequenceConverter", FakeSequenceConverter)
    processor = RenderKit.__new__(RenderKit)

    processor.convert_exr_sequence_to_mp4(
        "render.%04d.exr",
        "output.mp4",
        start_frame=1001,
    )

    assert len(captured_configs) == 1
    assert captured_configs[0].start_frame == 1001
    assert captured_configs[0].end_frame is None


def test_api_wires_ocio_grade_burnin_slate_and_watermark(monkeypatch) -> None:
    """New optional kwargs on convert_exr_sequence_to_mp4 should populate ConversionConfig."""
    captured_configs = []

    class FakeSequenceConverter:
        def __init__(self, config) -> None:
            captured_configs.append(config)

        def convert(self, show_progress=None) -> None:
            pass

    monkeypatch.setattr(processor_module, "SequenceConverter", FakeSequenceConverter)
    processor = RenderKit.__new__(RenderKit)

    burnin = BurnInConfig(elements=[BurnInElement(text_template="{frame}", zone="top_left")])
    slate = SlateConfig(title="Review", show="DEMO", shot="sh010")
    watermark = WatermarkConfig(text="CONFIDENTIAL", opacity=35, tiled=True)

    processor.convert_exr_sequence_to_mp4(
        "render.%04d.exr",
        "output.mp4",
        fps=24.0,
        ocio_config_path="/studio/config.ocio",
        input_space="ACEScg",
        display="sRGB",
        view="ACES 1.0 - SDR Video",
        exposure=1.25,
        gamma=2.2,
        burnin_config=burnin,
        slate_config=slate,
        watermark_config=watermark,
    )

    assert len(captured_configs) == 1
    cfg = captured_configs[0]
    assert cfg.color_space_preset == ColorSpacePreset.OCIO_CONVERSION
    assert cfg.ocio_config_path == "/studio/config.ocio"
    assert cfg.explicit_input_color_space == "ACEScg"
    assert cfg.ocio_display == "sRGB"
    assert cfg.ocio_view == "ACES 1.0 - SDR Video"
    assert cfg.exposure == 1.25
    assert cfg.gamma == 2.2
    assert cfg.burnin_config == burnin
    assert cfg.slate_config == slate
    assert cfg.watermark_config == watermark
