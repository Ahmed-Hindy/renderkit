"""Tests for the public RenderKit API."""

import pytest

from renderkit.api import processor as processor_module
from renderkit.api.processor import RenderKit


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
