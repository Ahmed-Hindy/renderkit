"""Tests for main window file info discovery wiring."""

from pathlib import Path

from renderkit.ui import main_window_logic


class _DummySignal:
    def __init__(self) -> None:
        self.connected = []

    def connect(self, func) -> None:
        self.connected.append(func)


class _DummyWorker:
    def __init__(self, file_path: Path, parent=None) -> None:
        self.file_path = file_path
        self.parent = parent
        self.file_info_ready = _DummySignal()
        self.error_occurred = _DummySignal()
        self.started = False
        self._running = False

    def isRunning(self) -> bool:
        return self._running

    def start(self) -> None:
        self.started = True


class _DummyWindow(main_window_logic.MainWindowLogicMixin):
    def __init__(self) -> None:
        self._file_info_worker = None
        self.ready_calls = []
        self.error_calls = []

    def _on_file_info_ready(
        self, path_str, file_info, sample_path, sequence, frame_count, frame_range, pattern
    ) -> None:
        self.ready_calls.append(
            (path_str, file_info, sample_path, sequence, frame_count, frame_range, pattern)
        )

    def _on_file_info_error(
        self, path_str, error, sample_path, sequence, frame_count, frame_range, pattern
    ) -> None:
        self.error_calls.append(
            (path_str, error, sample_path, sequence, frame_count, frame_range, pattern)
        )


def test_start_file_info_discovery_wires_worker(monkeypatch, tmp_path: Path) -> None:
    """Ensure FileInfoWorker is created and signals are wired with context."""
    monkeypatch.setattr(main_window_logic, "FileInfoWorker", _DummyWorker)
    window = _DummyWindow()

    sample_path = tmp_path / "render.0001.exr"
    sequence = [1, 2]
    frame_range = "1 - 2"
    pattern = str(tmp_path / "render.####.exr")

    window._start_file_info_discovery(sample_path, sequence, len(sequence), frame_range, pattern)

    worker = window._file_info_worker
    assert isinstance(worker, _DummyWorker)
    assert worker.file_path == sample_path
    assert worker.parent is window
    assert worker.started is True
    assert len(worker.file_info_ready.connected) == 1
    assert len(worker.error_occurred.connected) == 1

    file_info = object()
    worker.file_info_ready.connected[0]("path", file_info)
    assert window.ready_calls == [
        ("path", file_info, sample_path, sequence, len(sequence), frame_range, pattern)
    ]

    error = object()
    worker.error_occurred.connected[0]("path", error)
    assert window.error_calls == [
        ("path", error, sample_path, sequence, len(sequence), frame_range, pattern)
    ]
