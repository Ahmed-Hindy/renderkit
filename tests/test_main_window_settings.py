"""Tests for main-window settings persistence helpers."""

from renderkit.ui.main_window_settings import load_settings, reset_settings, save_settings


class _Settings:
    def __init__(self) -> None:
        self.values = {}
        self.setValue = self.set_value

    def set_value(self, key, value) -> None:
        self.values[key] = value

    def value(self, key, default, type=None):
        value = self.values.get(key, default)
        if type is None:
            return value
        return type(value)


class _ValueWidget:
    def __init__(self, value) -> None:
        self._value = value
        self.setValue = self.set_value

    def value(self):
        return self._value

    def set_value(self, value) -> None:
        self._value = value


class _CheckWidget:
    def __init__(self, checked: bool) -> None:
        self._checked = checked
        self.isChecked = self.is_checked
        self.setChecked = self.set_checked

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, checked: bool) -> None:
        self._checked = checked


class _ComboWidget:
    def __init__(self, text: str) -> None:
        self._text = text
        self._index = 1
        self.currentText = self.current_text
        self.currentIndex = self.current_index
        self.setCurrentText = self.set_current_text
        self.setCurrentIndex = self.set_current_index

    def current_text(self) -> str:
        return self._text

    def set_current_text(self, text: str) -> None:
        self._text = text

    def set_current_index(self, index: int) -> None:
        self._index = index
        if index == 0:
            self._text = "H.264"

    def current_index(self) -> int:
        return self._index


class _DummyWindow:
    def __init__(self) -> None:
        self.settings = _Settings()
        self.fps_spin = _ValueWidget(48)
        self.keep_source_fps_check = _CheckWidget(False)
        self.keep_source_frame_range_check = _CheckWidget(False)
        self.width_spin = _ValueWidget(2048)
        self.height_spin = _ValueWidget(858)
        self.codec_combo = _ComboWidget("H.265")
        self.keep_resolution_check = _CheckWidget(False)
        self.aspect_link_btn = _CheckWidget(False)
        self.quality_slider = _ValueWidget(7)
        self.prefetch_workers_spin = _ValueWidget(5)
        self.burnin_enable_check = _CheckWidget(False)
        self.burnin_frame_check = _CheckWidget(False)
        self.burnin_layer_check = _CheckWidget(False)
        self.burnin_fps_check = _CheckWidget(False)
        self.burnin_font_size_spin = _ValueWidget(32)
        self.burnin_opacity_spin = _ValueWidget(80)
        self.cs_enable_check = _CheckWidget(True)
        self.cs_columns_spin = _ValueWidget(3)
        self.cs_padding_spin = _ValueWidget(9)
        self.preview_scale_spin = _ValueWidget(50)


def test_save_settings_persists_available_widget_values() -> None:
    """Saved settings should use the UI's current values."""
    window = _DummyWindow()

    save_settings(window)

    assert window.settings.values["fps"] == 48
    assert window.settings.values["codec_text"] == "H.265"
    assert window.settings.values["cs_enable"] is True
    assert window.settings.values["preview_scale"] == 50


def test_load_settings_restores_typed_values() -> None:
    """Stored values should be restored through the setting schema."""
    window = _DummyWindow()
    window.settings.values.update(
        {
            "fps": "30",
            "keep_resolution": "True",
            "codec_text": "H.264",
            "preview_scale": "25",
        }
    )

    load_settings(window)

    assert window.fps_spin.value() == 30
    assert window.keep_resolution_check.isChecked() is True
    assert window.codec_combo.currentText() == "H.264"
    assert window.preview_scale_spin.value() == 25


def test_reset_settings_restores_defaults_and_codec_index() -> None:
    """Reset should centralize defaults without changing codec reset behavior."""
    window = _DummyWindow()

    reset_settings(window)

    assert window.fps_spin.value() == 24
    assert window.keep_source_fps_check.isChecked() is True
    assert window.width_spin.value() == 1920
    assert window.height_spin.value() == 1080
    assert window.codec_combo.currentIndex() == 0
    assert window.quality_slider.value() == 10
    assert window.cs_enable_check.isChecked() is False
    assert window.preview_scale_spin.value() == 75
