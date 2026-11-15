"""Tests for Houdini 21.0 and Nuke DCC integration helpers."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from renderkit.core.config import VALID_BURNIN_ZONES, ConversionConfig, ConversionConfigBuilder
from renderkit.core.presets import load_preset, resolve_preset_path, save_preset
from renderkit.exceptions import ConfigurationError
from renderkit.integrations import houdini, nuke
from renderkit.processing.color_space import ColorSpacePreset


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


_REPO_ROOT = Path(__file__).resolve().parent.parent
_PRESETS_DIR = _REPO_ROOT / "presets"


def test_repo_presets_load_and_resolve_via_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """All JSON presets in presets/ pass load_preset, build ConversionConfig, and resolve via env."""
    preset_files = sorted(_PRESETS_DIR.glob("*.json"))
    expected_names = {
        "studio_dailies.json",
        "client_review_watermarked.json",
        "editorial_prores422.json",
    }
    assert expected_names.issubset({path.name for path in preset_files})

    monkeypatch.setenv("RENDERKIT_PRESET_PATH", str(_PRESETS_DIR))

    loaded_by_name: dict[str, dict[str, Any]] = {}
    for preset_file in preset_files:
        assert resolve_preset_path(preset_file.stem) == preset_file
        assert resolve_preset_path(preset_file.name) == preset_file
        loaded = load_preset(preset_file)
        cfg = ConversionConfig(
            input_pattern="render.%04d.exr",
            output_path="output.mov",
            **loaded,
        )
        assert cfg.color_space_preset == ColorSpacePreset.OCIO_CONVERSION
        loaded_by_name[preset_file.stem] = loaded

    studio = loaded_by_name["studio_dailies"]
    assert studio["codec"] == "libx264"
    assert studio["quality"] == 8
    assert studio["explicit_input_color_space"] == "ACES - ACEScg"
    assert studio["burnin_config"] is not None
    assert {el.zone for el in studio["burnin_config"].elements} == set(VALID_BURNIN_ZONES)

    client = loaded_by_name["client_review_watermarked"]
    assert client["codec"] == "libx264"
    assert client["quality"] == 7
    assert client["slate_config"] is not None
    assert client["slate_config"].enabled is True
    assert client["watermark_config"] is not None
    assert client["watermark_config"].text == "CONFIDENTIAL - {user}"
    assert client["watermark_config"].opacity == 25
    assert client["watermark_config"].tiled is True
    assert client["burnin_config"] is not None

    editorial = loaded_by_name["editorial_prores422"]
    assert editorial["codec"] == "prores_422"
    assert editorial["quality"] == 10


def test_houdini_wrapper_scripts_with_fake_nodes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Drop-in Houdini post-render and shelf scripts import cleanly and run with fake nodes."""
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    monkeypatch.delitem(sys.modules, "hou", raising=False)

    post_render_mod = importlib.import_module("integrations.houdini.post_render_dailies")
    shelf_mod = importlib.import_module("integrations.houdini.launch_renderkit_shelf")

    assert post_render_mod.main(None) is None
    assert shelf_mod.launch_selected_node_in_renderkit(None) is None

    captured_configs: list[ConversionConfig] = []

    class FakeConverter:
        def __init__(self, config: ConversionConfig) -> None:
            self.config = config

        def convert(self) -> None:
            captured_configs.append(self.config)

    monkeypatch.setattr(houdini, "SequenceConverter", FakeConverter)
    monkeypatch.setenv("OCIO", "/studio/config.ocio")

    rop_node = _FakeHoudiniNode({"lopoutput": str(tmp_path / "shot010.$F4.exr")})
    out_video = post_render_mod.main(
        rop_node,
        preset=_PRESETS_DIR / "studio_dailies.json",
        contact_sheet=True,
    )
    assert out_video == tmp_path / "shot010.mp4"
    assert len(captured_configs) == 1
    assert captured_configs[0].ocio_config_path == "/studio/config.ocio"
    assert captured_configs[0].contact_sheet_mode is True

    fake_hou = SimpleNamespace(
        pwd=lambda: rop_node,
        selectedNodes=lambda: (rop_node,),
        fps=lambda: 25.0,
        playbar=SimpleNamespace(frameRange=lambda: (1001, 1020)),
    )
    monkeypatch.setitem(sys.modules, "hou", fake_hou)

    spawned: list[list[str]] = []
    fake_proc = SimpleNamespace(pid=4321)

    def fake_popen(args: list[str], **_kwargs: Any) -> Any:
        spawned.append(args)
        return fake_proc

    monkeypatch.setattr(houdini.subprocess, "Popen", fake_popen)

    proc = shelf_mod.launch_selected_node_in_renderkit(preset="studio_dailies", layer="beauty")
    assert proc is fake_proc
    assert len(spawned) == 1
    assert "--open" in spawned[0]
    assert str(tmp_path / "shot010.$F4.exr") in spawned[0]
    assert "--layer" in spawned[0]
    assert "beauty" in spawned[0]
    assert "--preset" in spawned[0]
    assert "studio_dailies" in spawned[0]
    assert "--ocio" in spawned[0]
    assert "/studio/config.ocio" in spawned[0]


def test_nuke_menu_wrapper_outside_and_inside_fake_nuke(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Drop-in Nuke menu.py is safe outside Nuke and registers working menu callbacks."""
    monkeypatch.syspath_prepend(str(_REPO_ROOT))
    monkeypatch.delitem(sys.modules, "nuke", raising=False)

    nuke_menu_mod = importlib.import_module("integrations.nuke.menu")
    assert nuke_menu_mod._get_nuke() is None
    assert nuke_menu_mod.create_dailies_menu() is None

    class FakeMenu:
        def __init__(self, name: str = "Nuke") -> None:
            self.name = name
            self.commands: dict[str, Any] = {}
            self.submenus: dict[str, FakeMenu] = {}

        def addMenu(self, name: str) -> FakeMenu:  # noqa: N802
            submenu = FakeMenu(name)
            self.submenus[name] = submenu
            return submenu

        def addCommand(self, label: str, callback: Any) -> None:  # noqa: N802
            self.commands[label] = callback

    write_node = _FakeNukeNode(
        {
            "file": _FakeKnob(str(tmp_path / "comp.%04d.exr")),
            "colorspace": _FakeKnob("ACES - ACEScg"),
        },
        first_frame=1001,
        last_frame=1010,
    )
    root_menu = FakeMenu("Nuke")
    fake_nuke = SimpleNamespace(
        menu=lambda name: root_menu if name == "Nuke" else None,
        selectedNode=lambda: write_node,
        selectedNodes=lambda: [write_node],
    )
    monkeypatch.setitem(sys.modules, "nuke", fake_nuke)

    created = nuke_menu_mod.create_dailies_menu()
    assert created is root_menu.submenus["RenderKit"]
    assert "Generate Dailies (RenderKit)" in created.commands
    assert "Open in RenderKit UI" in created.commands

    captured_configs: list[ConversionConfig] = []

    class FakeConverter:
        def __init__(self, config: ConversionConfig) -> None:
            self.config = config

        def convert(self) -> None:
            captured_configs.append(self.config)

    monkeypatch.setattr(nuke, "SequenceConverter", FakeConverter)
    out_mov = created.commands["Generate Dailies (RenderKit)"]()
    assert out_mov == tmp_path / "comp.mov"
    assert len(captured_configs) == 1
    assert captured_configs[0].codec == "prores_422"

    spawned: list[list[str]] = []
    fake_proc = SimpleNamespace(pid=9876)

    def fake_popen(args: list[str], **_kwargs: Any) -> Any:
        spawned.append(args)
        return fake_proc

    monkeypatch.setattr(nuke_menu_mod.subprocess, "Popen", fake_popen)
    proc = created.commands["Open in RenderKit UI"]()
    assert proc is fake_proc
    assert len(spawned) == 1
    assert "--open" in spawned[0]
    assert str(tmp_path / "comp.%04d.exr") in spawned[0]
