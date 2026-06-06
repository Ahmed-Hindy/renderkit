"""Tests for UI stylesheet expectations."""

from importlib import resources


def _active_theme_qss() -> str:
    return (
        resources.files("renderkit.ui")
        .joinpath("stylesheets", "matcha.qss")
        .read_text(encoding="utf-8")
    )


def test_combo_boxes_have_hover_highlights() -> None:
    """Ensure dropdown widgets visibly respond to hover in the active theme."""
    qss = _active_theme_qss()

    assert '[theme="light"] QComboBox:hover' in qss
    assert "background-color: #f6f8fa;" in qss
    assert '[theme="dark"] QComboBox:hover' in qss
    assert "background-color: #161b22;" in qss
    assert '[theme="light"] QComboBox QAbstractItemView::item:hover' in qss
    assert '[theme="light"] QListView#ComboBoxPopup::item:hover' in qss
    assert '[theme="light"] QAbstractItemView#ComboBoxPopup::item:hover' in qss
    assert "background-color: #0969da;" in qss
    assert '[theme="dark"] QComboBox QAbstractItemView::item:hover' in qss
    assert '[theme="dark"] QListView#ComboBoxPopup::item:hover' in qss
    assert '[theme="dark"] QAbstractItemView#ComboBoxPopup::item:hover' in qss
    assert "background-color: #4493f8;" in qss

    for line in qss.splitlines():
        stripped_line = line.strip().rstrip(",")
        if "ComboBoxPopup" in stripped_line:
            assert stripped_line.startswith(('[theme="light"] ', '[theme="dark"] '))
