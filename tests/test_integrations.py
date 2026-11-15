"""Tests for Houdini 21.0 and Nuke DCC integration helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from renderkit.core.config import ConversionConfig, ConversionConfigBuilder
from renderkit.core.presets import save_preset
from renderkit.exceptions import ConfigurationError
from renderkit.integrations import houdini, nuke


class _FakeParm:
    def __init__(self, value: Any) -> None:
        self._value = value

    def eval(self) -> Any:
        return self._value


class _FakeHoudiniNode:
    def __init__(self, parms: dict[str, Any]) -> None:
        self._parms = {key: _FakeParm(val) for key, val in parms.items()}

    def parm(self, name: str) -> Any:
        return self._parms.get(name)


class _FakeKnob:
    def __init__(self, value: Any, evaluated: Any = None) -> None:
        self._value = value
        self._evaluated = evaluated

    def value(self) -> Any:
        return self._value

    def evaluate(self) -> Any:
        return self._evaluated if self._evaluated is not None else self._value


class _FakeNukeNode:
    def __init__(
        self,
        knobs: dict[str, _FakeKnob],
        *,
        first_frame: int | None = None,
        last_frame: int | None = None,
    ) -> None:
        self._knobs = knobs
        self._first = first_frame
        self._last = last_frame

    def knob(self, name: str) -> Any:
        return self._knobs.get(name)

    def firstFrame(self) -> int | None:  # noqa: N802
        return self._first

    def lastFrame(self) -> int | None:  # noqa: N802
        return self._last


def test_extract_houdini_rop_context_reads_parms_env_and_hou_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Houdini ROP context extraction reads parms, $OCIO, and optional hou.fps()."""
    fake_hou = SimpleNamespace(
        fps=lambda: 25.0,
        playbar=SimpleNamespace(frameRange=lambda: (1001, 1048)),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    rop = _FakeHoudiniNode(
        {
            "lopoutput": "/shows/shot010/render.$F4.exr",
            "f1": 1001.0,
        }
    )
    ctx = houdini.extract_houdini_rop_context(rop, env={"OCIO": "/studio/config.ocio"})

    assert ctx == {
        "output_pattern": "/shows/shot010/render.$F4.exr",
        "first_frame": 1001,
        "last_frame": 1048,
        "fps": 25.0,
        "ocio_config_path": "/studio/config.ocio",
    }


def test_extract_houdini_rop_context_works_without_hou(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Houdini integration gracefully falls back to 24.0 fps when hou is not installed."""
    monkeypatch.delitem(sys.modules, "hou", raising=False)
    monkeypatch.setattr(houdini, "_get_hou", lambda: None)

    rop = _FakeHoudiniNode({"vm_picture": "/tmp/karma.$F4.exr", "f1": 1, "f2": 10})
    ctx = houdini.extract_houdini_rop_context(rop, env={})

    assert ctx == {
        "output_pattern": "/tmp/karma.$F4.exr",
        "first_frame": 1,
        "last_frame": 10,
        "fps": 24.0,
        "ocio_config_path": None,
    }


def test_run_houdini_post_render_inherits_ocio_preset_and_contact_sheet(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Post-render hook merges preset, $OCIO, contact sheet flag, and runs SequenceConverter."""
    preset_file = tmp_path / "houdini_dailies.json"
    preset_cfg = (
        ConversionConfigBuilder()
        .with_input_pattern("placeholder.%04d.exr")
        .with_output_path("placeholder.mov")
        .with_fps(24.0)
        .with_codec("prores_hq")
        .build()
    )
    save_preset(preset_cfg, preset_file)

    captured: list[ConversionConfig] = []

    class FakeConverter:
        def __init__(self, config: ConversionConfig) -> None:
            self.config = config

        def convert(self) -> None:
            captured.append(self.config)

    monkeypatch.setattr(houdini, "SequenceConverter", FakeConverter)
    monkeypatch.setattr(houdini, "_get_hou", lambda: None)

    out_path = houdini.run_houdini_post_render(
        tmp_path / "beauty.$F4.exr",
        preset=preset_file,
        contact_sheet=True,
        env={"OCIO": "/pipe/aces/config.ocio"},
    )

    assert out_path == tmp_path / "beauty.mov"
    assert len(captured) == 1
    cfg = captured[0]
    assert cfg.codec == "prores_hq"
    assert cfg.ocio_config_path == "/pipe/aces/config.ocio"
    assert cfg.contact_sheet_mode is True
    assert cfg.contact_sheet_config is not None


def test_build_and_launch_houdini_ui_command(monkeypatch: pytest.MonkeyPatch) -> None:
    """Houdini UI launcher constructs and spawns the renderkit ui --open command."""
    cmd = houdini.build_houdini_ui_command(
        "/renders/shot.%04d.exr",
        layer="diffuse",
        preset="dailies",
        ocio_config_path="/ocio/config.ocio",
        python_executable="/opt/hfs21.0/bin/hython",
    )
    assert cmd == [
        "/opt/hfs21.0/bin/hython",
        "-m",
        "renderkit.cli.main",
        "ui",
        "--open",
        "/renders/shot.%04d.exr",
        "--layer",
        "diffuse",
        "--preset",
        "dailies",
        "--ocio",
        "/ocio/config.ocio",
    ]

    spawned: list[list[str]] = []
    fake_proc = SimpleNamespace(pid=1234)

    def fake_popen(args: list[str], **_kwargs: Any) -> Any:
        spawned.append(args)
        return fake_proc

    monkeypatch.setattr(houdini.subprocess, "Popen", fake_popen)
    proc = houdini.launch_renderkit_ui_for_houdini(
        "/renders/shot.%04d.exr",
        layer="specular",
        python_executable="/usr/bin/python3",
    )
    assert proc is fake_proc
    assert spawned == [
        [
            "/usr/bin/python3",
            "-m",
            "renderkit.cli.main",
            "ui",
            "--open",
            "/renders/shot.%04d.exr",
            "--layer",
            "specular",
        ]
    ]


def test_extract_nuke_node_context_and_convert_dailies(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Nuke integration extracts Write node knobs and converts dailies with ProRes defaults."""
    with pytest.raises(ConfigurationError):
        nuke.extract_nuke_node_context(None)

    write_node = _FakeNukeNode(
        {
            "file": _FakeKnob("/comp/shot.%04d.exr", evaluated=str(tmp_path / "comp.####.exr")),
            "colorspace": _FakeKnob("ACEScg"),
        },
        first_frame=1001,
        last_frame=1024,
    )
    ctx = nuke.extract_nuke_node_context(write_node, env={"OCIO": "/nuke/config.ocio"})
    assert ctx == {
        "output_pattern": str(tmp_path / "comp.####.exr"),
        "first_frame": 1001,
        "last_frame": 1024,
        "colorspace": "ACEScg",
        "ocio_config_path": "/nuke/config.ocio",
    }

    captured: list[ConversionConfig] = []

    class FakeConverter:
        def __init__(self, config: ConversionConfig) -> None:
            self.config = config

        def convert(self) -> None:
            captured.append(self.config)

    monkeypatch.setattr(nuke, "SequenceConverter", FakeConverter)
    out_mov = nuke.convert_nuke_node_to_dailies(
        write_node,
        env={"OCIO": "/nuke/config.ocio"},
    )

    assert out_mov == tmp_path / "comp.mov"
    assert len(captured) == 1
    cfg = captured[0]
    assert cfg.codec == "prores_422"
    assert cfg.start_frame == 1001
    assert cfg.end_frame == 1024
    assert cfg.ocio_config_path == "/nuke/config.ocio"
    assert cfg.explicit_input_color_space == "ACEScg"


def test_build_nuke_ui_command(tmp_path: Path) -> None:
    """Nuke UI command forwards evaluated file path, preset, and $OCIO."""
    node = _FakeNukeNode(
        {"file": _FakeKnob(str(tmp_path / "plate.%04d.exr"))},
    )
    cmd = nuke.build_nuke_ui_command(
        node,
        preset="review",
        python_executable="/usr/bin/python",
        env={"OCIO": "/pipe/config.ocio"},
    )
    assert cmd == [
        "/usr/bin/python",
        "-m",
        "renderkit.cli.main",
        "ui",
        "--open",
        str(tmp_path / "plate.%04d.exr"),
        "--preset",
        "review",
        "--ocio",
        "/pipe/config.ocio",
    ]
