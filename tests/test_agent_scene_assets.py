"""The agent scene ships as three manifest animations with clean idle seams."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import cairo

from mochi.sprites import ANIMATIONS

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets" / "mochi"
MANIFEST = ASSETS / "manifest.json"


def _animations() -> dict:
    return json.loads(MANIFEST.read_text())["animations"]


def _silhouette(relative_path: str) -> bytes:
    surface = cairo.ImageSurface.create_from_png(str(ASSETS / relative_path))
    # ARGB32 is stored little-endian as BGRA; keep only alpha.
    return bytes(surface.get_data())[3::4]


def test_agent_scene_manifest_entries() -> None:
    animations = _animations()

    for name, count, loop in (
        ("agent_intro", 7, False),
        ("agent_loop", 18, True),
        ("agent_outro", 5, False),
    ):
        assert animations[name] == {
            "frames": [f"agent/{name}_{index:02d}.png" for index in range(1, count + 1)],
            "frame_count": count,
            "fps": 8.333333333333334,
            "loop": loop,
        }, name


def test_agent_scene_frames_are_canonical_256px_rgba() -> None:
    animations = _animations()

    for name in ("agent_intro", "agent_loop", "agent_outro"):
        for relative_path in animations[name]["frames"]:
            surface = cairo.ImageSurface.create_from_png(str(ASSETS / relative_path))
            assert (surface.get_width(), surface.get_height()) == (256, 256), relative_path
            assert surface.get_format() == cairo.FORMAT_ARGB32, relative_path


def test_agent_scene_enters_and_leaves_through_the_idle_silhouette() -> None:
    animations = _animations()
    idle = _silhouette(animations["idle"]["frames"][0])

    assert _silhouette(animations["agent_intro"]["frames"][0]) == idle
    assert _silhouette(animations["agent_outro"]["frames"][-1]) == idle


def test_agent_scene_is_packaged() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["tool"]["setuptools"]["data-files"]["share/mochi/agent"] == [
        "assets/mochi/agent/*.png"
    ]


def test_agent_scene_loads_at_runtime() -> None:
    assert ANIMATIONS["agent_intro"].looping is False
    assert ANIMATIONS["agent_loop"].looping is True
    assert ANIMATIONS["agent_outro"].looping is False
    assert len(ANIMATIONS["agent_loop"].frames) == 18
