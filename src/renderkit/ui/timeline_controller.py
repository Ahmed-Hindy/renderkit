"""Timeline scrubber controller for preview navigation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Optional

from renderkit.core.sequence import FrameSequence
from renderkit.ui.qt_compat import QLabel, QSlider, QTimer, QWidget

PreviewLoader = Callable[[Path, bool], None]


class TimelineController:
    """Manage timeline scrubber state and preview updates."""

    def __init__(
        self,
        slider: QSlider,
        start_label: QLabel,
        end_label: QLabel,
        current_label: QLabel,
        container: QWidget,
        load_preview: PreviewLoader,
        parent: Optional[QWidget] = None,
    ) -> None:
        self._slider = slider
        self._start_label = start_label
        self._end_label = end_label
        self._current_label = current_label
        self._container = container
        self._load_preview = load_preview

        self._sequence: Optional[FrameSequence] = None
        self._frames: list[int] = []
        self._pending_frame: Optional[int] = None
        self._last_frame: Optional[int] = None
        self._is_scrubbing = False
        self._sync_guard = False

        self._timer = QTimer(parent or container)
        self._timer.setSingleShot(True)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self._apply_scrub)

        self._slider.valueChanged.connect(self._on_slider_changed)
        self._slider.sliderPressed.connect(self._on_scrub_started)
        self._slider.sliderReleased.connect(self._on_scrub_finished)

        self.reset()

    def reset(self) -> None:
        """Hide and reset the timeline UI and state."""
        self._sequence = None
        self._frames = []
        self._pending_frame = None
        self._last_frame = None
        self._is_scrubbing = False
        self._sync_guard = False
        self._timer.stop()

        self._container.setVisible(False)
        self._slider.setEnabled(False)
        self._slider.setMinimum(0)
        self._slider.setMaximum(0)
        self._slider.setValue(0)
        self._start_label.setText("--")
        self._end_label.setText("--")
        self._current_label.setText("Frame: -")

    def set_sequence(self, sequence: FrameSequence) -> None:
        """Configure timeline for a detected sequence."""
        frame_numbers = list(sequence.frame_numbers)
        if not frame_numbers:
            self.reset()
            return

        self._sequence = sequence
        self._frames = frame_numbers
        first_frame = frame_numbers[0]
        last_frame = frame_numbers[-1]
        max_index = len(frame_numbers) - 1

        self._sync_guard = True
        self._slider.blockSignals(True)
        self._slider.setMinimum(0)
        self._slider.setMaximum(max_index)
        self._slider.setValue(0)
        self._slider.setEnabled(True)
        self._slider.blockSignals(False)
        self._sync_guard = False

        self._start_label.setText(str(first_frame))
        self._end_label.setText(str(last_frame))
        self._current_label.setText(f"Frame: {first_frame}")
        self._container.setVisible(True)

        self._pending_frame = None
        self._last_frame = None

    def _frame_from_index(self, index: int) -> Optional[int]:
        if not self._frames:
            return None
        if index <= 0:
            return self._frames[0]
        if index >= len(self._frames):
            return self._frames[-1]
        return self._frames[index]

    def _on_slider_changed(self, value: int) -> None:
        if self._sync_guard or not self._sequence:
            return
        frame = self._frame_from_index(value)
        if frame is None:
            return
        self._current_label.setText(f"Frame: {frame}")
        self._pending_frame = frame
        self._timer.start()

    def _on_scrub_started(self) -> None:
        self._is_scrubbing = True

    def _on_scrub_finished(self) -> None:
        self._is_scrubbing = False
        if not self._sequence:
            return
        self._timer.stop()
        frame = self._frame_from_index(self._slider.value())
        if frame is None:
            return
        self._pending_frame = None
        self._last_frame = None
        path = self._sequence.get_file_path(frame)
        self._load_preview(path, False)

    def _apply_scrub(self) -> None:
        if not self._sequence or self._pending_frame is None:
            return
        frame = self._pending_frame
        self._pending_frame = None
        if self._last_frame == frame:
            return
        self._last_frame = frame
        path = self._sequence.get_file_path(frame)
        self._load_preview(path, self._is_scrubbing)
