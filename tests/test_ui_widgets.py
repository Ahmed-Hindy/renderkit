"""Tests for shared UI widget helpers."""

from pathlib import Path

import numpy as np
import pytest

from renderkit.core.config import BurnInConfig, BurnInElement
from renderkit.processing.color_space import ColorSpacePreset
from renderkit.processing.frame_pipeline import (
    FramePreparationOptions,
    PreparedFrameBuffer,
    prepare_frame_buffer,
)
from renderkit.ui.preview_image import (
    PreviewImageData,
    imagebuf_to_preview_image,
    preview_image_to_pixmap,
    preview_image_to_qimage,
)
from renderkit.ui.qt_compat import QPixmap
from renderkit.ui.widgets import (
    PreviewWorker,
    _prepare_buf_for_preview_display,
    _scaled_burnin_config_for_preview,
)

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


def test_imagebuf_to_preview_image_converts_rgb_float_to_uint8() -> None:
    """RGB float preview buffers should become contiguous uint8 payloads."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    pixels = np.array(
        [
            [[0.0, 0.5, 1.0], [1.5, -0.5, 0.25]],
            [[0.2, 0.4, 0.6], [0.8, 1.0, 0.0]],
        ],
        dtype=np.float32,
    )
    spec = oiio.ImageSpec(2, 2, 3, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), pixels)

    result = imagebuf_to_preview_image(buf)

    assert result.width == 2
    assert result.height == 2
    assert result.channels == 3
    assert result.pixels.dtype == np.uint8
    assert result.pixels.flags.c_contiguous
    np.testing.assert_array_equal(
        result.pixels,
        np.array(
            [
                [[0, 127, 255], [255, 0, 63]],
                [[51, 102, 153], [204, 255, 0]],
            ],
            dtype=np.uint8,
        ),
    )


def test_imagebuf_to_preview_image_preserves_rgba_channels() -> None:
    """RGBA preview buffers should preserve the alpha channel."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    pixels = np.array([[[0.0, 0.25, 0.5, 1.0]]], dtype=np.float32)
    spec = oiio.ImageSpec(1, 1, 4, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), pixels)

    result = imagebuf_to_preview_image(buf)

    assert result.channels == 4
    np.testing.assert_array_equal(
        result.pixels,
        np.array([[[0, 63, 127, 255]]], dtype=np.uint8),
    )


def test_imagebuf_to_preview_image_rejects_empty_pixels() -> None:
    """Empty OIIO pixel extraction should fail clearly."""

    class EmptyBuf:
        def get_pixels(self, pixel_type):
            return None

    with pytest.raises(ValueError, match="Failed to extract preview pixels"):
        imagebuf_to_preview_image(EmptyBuf())


def test_imagebuf_to_preview_image_rejects_unsupported_channels() -> None:
    """Only RGB/RGBA buffers should reach Qt preview marshaling."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    pixels = np.ones((1, 1, 5), dtype=np.float32)
    spec = oiio.ImageSpec(1, 1, 5, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), pixels)

    with pytest.raises(ValueError, match="Unsupported image channels: 5"):
        imagebuf_to_preview_image(buf)


def test_preview_image_to_pixmap_returns_pixmap(qapp) -> None:
    """Preview image data should become a valid GUI-thread pixmap."""
    data = PreviewImageData(
        pixels=np.full((1, 1, 3), 255, dtype=np.uint8),
        width=1,
        height=1,
        channels=3,
    )

    pixmap = preview_image_to_pixmap(data)

    assert isinstance(pixmap, QPixmap)
    assert not pixmap.isNull()


def test_preview_image_to_qimage_rejects_non_uint8_dtype() -> None:
    """Reject pixels with non-uint8 dtypes to prevent memory layout corruption."""
    data = PreviewImageData(
        pixels=np.full((2, 2, 3), 1.0, dtype=np.float32),
        width=2,
        height=2,
        channels=3,
    )
    with pytest.raises(ValueError, match="Preview image pixels must be uint8"):
        preview_image_to_qimage(data)


def test_preview_image_to_qimage_handles_non_contiguous_array(qapp) -> None:
    """Automatically convert non-contiguous NumPy arrays to C-contiguous for QImage safety."""
    # 1. Fortran-contiguous array
    f_pixels = np.asfortranarray(np.full((2, 2, 3), 128, dtype=np.uint8))
    assert not f_pixels.flags.c_contiguous

    data_f = PreviewImageData(
        pixels=f_pixels,
        width=2,
        height=2,
        channels=3,
    )
    qimage_f = preview_image_to_qimage(data_f)
    assert qimage_f.width() == 2
    assert qimage_f.height() == 2

    # 2. Sliced/strided array view
    large_pixels = np.zeros((4, 4, 3), dtype=np.uint8)
    large_pixels[::2, ::2] = 255
    sliced_pixels = large_pixels[::2, ::2]
    assert not sliced_pixels.flags.c_contiguous

    data_sliced = PreviewImageData(
        pixels=sliced_pixels,
        width=2,
        height=2,
        channels=3,
    )
    qimage_sliced = preview_image_to_qimage(data_sliced)
    assert qimage_sliced.width() == 2
    assert qimage_sliced.height() == 2


def test_prepare_frame_buffer_expands_data_channels_without_color_conversion() -> None:
    """Shared frame prep should keep data-channel buffers preview/render safe."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    pixels = np.array(
        [
            [[0.1, 0.8], [0.2, 0.7]],
            [[0.3, 0.6], [0.4, 0.5]],
        ],
        dtype=np.float32,
    )
    spec = oiio.ImageSpec(2, 2, 2, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), pixels)

    class Reader:
        def read_imagebuf(self, path, layer=None, layer_map=None):
            return buf

    class FailingColorConverter:
        def convert_buf(self, buf, input_space=None):
            raise AssertionError("data-channel buffers should not be color converted")

    prepared = prepare_frame_buffer(
        FramePreparationOptions(
            frame_path=Path("render.0001.exr"),
            frame_num=1,
            output_width=2,
            output_height=2,
            source_width=2,
            source_height=2,
            scaler=object(),
            input_space="rendering",
            color_converter=FailingColorConverter(),
            reader=Reader(),
        )
    )

    result_spec = prepared.buf.spec()
    assert result_spec.nchannels == 3
    result_pixels = prepared.buf.get_pixels(oiio.FLOAT)
    np.testing.assert_allclose(result_pixels[:, :, 0], pixels[:, :, 0])
    np.testing.assert_allclose(result_pixels[:, :, 1], pixels[:, :, 0])
    np.testing.assert_allclose(result_pixels[:, :, 2], pixels[:, :, 0])


def test_preview_worker_delegates_imagebuf_processing(monkeypatch, qapp) -> None:
    """Preview worker should keep shared processing separate from Qt image creation."""
    if oiio is None:
        pytest.skip("OpenImageIO not available")

    spec = oiio.ImageSpec(1, 1, 3, oiio.FLOAT)
    buf = oiio.ImageBuf(spec)
    assert buf.set_pixels(oiio.ROI(), np.ones((1, 1, 3), dtype=np.float32))

    calls = []

    def fake_prepare_frame_buffer(options):
        calls.append(options)
        return PreparedFrameBuffer(buf=buf, applied_scale=0.5)

    monkeypatch.setattr("renderkit.ui.widgets.prepare_frame_buffer", fake_prepare_frame_buffer)

    emitted = []
    worker = PreviewWorker(
        file_path="render.0001.exr",
        color_space=ColorSpacePreset.LINEAR_TO_SRGB,
        input_space="rendering",
        layer="beauty",
        preview_scale=0.5,
    )
    worker.preview_ready.connect(emitted.append)

    worker.run()

    assert emitted
    assert isinstance(emitted[0], PreviewImageData)
    assert not isinstance(emitted[0], QPixmap)
    assert calls
    call = calls[0]
    assert call.frame_path == "render.0001.exr"
    assert call.layer == "beauty"
    assert call.input_space == "rendering"
    assert call.output_scale == pytest.approx(0.5)
    assert call.contact_sheet_config is None


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
