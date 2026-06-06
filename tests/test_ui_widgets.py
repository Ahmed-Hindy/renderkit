"""Tests for shared UI widget helpers."""

import numpy as np
import pytest

from renderkit.core.config import BurnInConfig, BurnInElement
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.ui.widgets import _prepare_buf_for_preview_display, _scaled_burnin_config_for_preview

try:
    import OpenImageIO as oiio
except ImportError:
    oiio = None


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


@pytest.mark.parametrize("channels", [1, 2])
def test_prepare_buf_for_preview_display_expands_data_channels(channels: int) -> None:
    """Data-channel AOV previews should display as grayscale RGB without OCIO."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    pixels = np.array(
        [
            [[0.1, 0.8], [0.2, 0.7]],
            [[0.3, 0.6], [0.4, 0.5]],
        ],
        dtype=np.float32,
    )[:, :, :channels]
    spec = oiio.ImageSpec(2, 2, channels, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), pixels)

    result = _prepare_buf_for_preview_display(
        buf,
        ColorSpacePreset.OCIO_CONVERSION,
        input_space="rendering",
    )

    result_spec = result.spec()
    assert result_spec.nchannels == 3
    result_pixels = result.get_pixels(oiio.FLOAT)
    np.testing.assert_allclose(result_pixels[:, :, 0], pixels[:, :, 0])
    np.testing.assert_allclose(result_pixels[:, :, 1], pixels[:, :, 0])
    np.testing.assert_allclose(result_pixels[:, :, 2], pixels[:, :, 0])


def test_no_wheel_combo_popup_tracks_hover(qtbot, qapp) -> None:
    """Ensure combo popup rows can receive hover styling."""
    from renderkit.ui.main_window_widgets import (
        COMBO_POPUP_OBJECT_NAME,
        NoWheelComboBox,
    )

    combo = NoWheelComboBox()
    qtbot.addWidget(combo)

    view = combo.view()
    assert view.objectName() == COMBO_POPUP_OBJECT_NAME
    assert view.hasMouseTracking() is True
    assert view.viewport().hasMouseTracking() is True
    assert view.styleSheet() == ""


def test_no_wheel_combo_popup_hover_updates_current_row(qtbot, qapp) -> None:
    """Ensure hovering a popup item moves the highlighted row."""
    from renderkit.ui.main_window_widgets import NoWheelComboBox
    from renderkit.ui.qt_compat import QApplication, QEvent, QMouseEvent, Qt

    combo = NoWheelComboBox()
    combo.addItems(["first", "second", "third"])
    qtbot.addWidget(combo)
    combo.show()
    combo.showPopup()
    qtbot.wait(10)

    view = combo.view()
    target = view.model().index(1, 0)
    target_position = view.visualRect(target).center()
    event = QMouseEvent(
        QEvent.Type.MouseMove,
        target_position,
        target_position,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(view.viewport(), event)

    qtbot.waitUntil(lambda: view.currentIndex().row() == 1, timeout=1000)
    combo.hidePopup()
