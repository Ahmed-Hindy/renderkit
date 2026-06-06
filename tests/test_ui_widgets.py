"""Tests for shared UI widget helpers."""

from renderkit.core.config import BurnInConfig, BurnInElement
from renderkit.ui.widgets import _scaled_burnin_config_for_preview


def test_scaled_burnin_config_for_preview_scales_font_and_positions() -> None:
    """Preview burn-ins should stay proportional to reduced preview buffers."""
    config = BurnInConfig(
        elements=[
            BurnInElement("Frame: {frame}", x=0, y=10, font_size=20, alignment="left"),
            BurnInElement("Layer: {layer}", x=0, y=10, font_size=20, alignment="center"),
            BurnInElement("FPS: {fps}", x=0, y=10, font_size=20, alignment="right"),
            BurnInElement("Shot", x=100, y=40, font_size=24, alignment="left"),
        ],
        background_opacity=45,
    )

    scaled = _scaled_burnin_config_for_preview(config, scale=0.25, image_width=480)

    assert scaled is not config
    assert scaled.background_opacity == 45
    assert [element.font_size for element in scaled.elements] == [5, 5, 5, 6]
    assert [(element.x, element.y) for element in scaled.elements] == [
        (5, 2),
        (240, 2),
        (475, 2),
        (25, 10),
    ]


def test_scaled_burnin_config_for_preview_does_not_mutate_original() -> None:
    """Preview scaling should not change final-render burn-in settings."""
    original = BurnInElement("Frame: {frame}", x=0, y=10, font_size=20, alignment="left")
    config = BurnInConfig(elements=[original])

    _scaled_burnin_config_for_preview(config, scale=0.5, image_width=960)

    assert original.x == 0
    assert original.y == 10
    assert original.font_size == 20
