"""The agent scene builder composes canonical coffee frames with one prop."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytest.importorskip("PIL")
from PIL import Image  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
COFFEE = ROOT / "assets" / "mochi" / "coffee"


def _builder():
    spec = importlib.util.spec_from_file_location(
        "build_agent_scene", ROOT / "tools" / "build_agent_scene.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def builder():
    return _builder()


@pytest.fixture(scope="module")
def built(builder, tmp_path_factory):
    out = tmp_path_factory.mktemp("agent")
    return builder, builder.build(out)


def _coffee(index: int) -> Image.Image:
    return Image.open(COFFEE / f"mochi_coffee_{index:04d}.png").convert("RGBA")


def _source_coffee_indices():
    return {
        "agent_intro": list(range(1, 8)),
        "agent_loop": [8 + frame % 9 for frame in range(18)],
        "agent_outro": list(range(17, 22)),
    }


def test_monitor_palette_art_is_a_clean_rectangle(builder) -> None:
    assert len(builder.MONITOR) == builder.MONITOR_HEIGHT == 22
    assert {len(row) for row in builder.MONITOR} == {builder.MONITOR_WIDTH} == {24}
    assert set("".join(builder.MONITOR)) <= set(builder.PALETTE) | {" "}


def test_builds_the_three_animations(built) -> None:
    _builder_module, frames = built

    assert {name: len(paths) for name, paths in frames.items()} == {
        "agent_intro": 7,
        "agent_loop": 18,
        "agent_outro": 5,
    }
    for paths in frames.values():
        for path in paths:
            with Image.open(path) as image:
                assert image.size == (256, 256)
                assert image.mode == "RGBA"


def test_build_is_deterministic(builder, built, tmp_path) -> None:
    _builder_module, first = built
    second = builder.build(tmp_path)

    for name in first:
        assert [p.read_bytes() for p in first[name]] == [p.read_bytes() for p in second[name]]


def test_refuses_to_overwrite_hand_cleaned_frames(builder, tmp_path) -> None:
    builder.build(tmp_path)

    with pytest.raises(FileExistsError, match="--force"):
        builder.build(tmp_path)
    builder.build(tmp_path, force=True)


def test_mochi_is_untouched_outside_the_monitor(builder, built) -> None:
    _builder_module, frames = built
    left = 256 - builder.MONITOR_WIDTH * builder.SCALE
    top = 256 - builder.MONITOR_HEIGHT * builder.SCALE - builder.BOTTOM_MARGIN_PX

    for name, indices in _source_coffee_indices().items():
        for path, index in zip(frames[name], indices, strict=True):
            built_pixels = Image.open(path).convert("RGBA").load()
            source_pixels = _coffee(index).load()
            for y in range(256):
                for x in range(256):
                    if x >= left and y >= top:
                        continue  # the monitor's rectangle
                    assert built_pixels[x, y] == source_pixels[x, y], (path.name, x, y)


def test_scene_starts_and_ends_on_the_untouched_idle_pose(built) -> None:
    _builder_module, frames = built

    assert Image.open(frames["agent_intro"][0]).convert("RGBA").tobytes() == _coffee(1).tobytes()
    assert Image.open(frames["agent_outro"][-1]).convert("RGBA").tobytes() == _coffee(21).tobytes()


def test_resting_monitor_uses_only_its_palette(builder, built) -> None:
    _builder_module, frames = built
    palette = {tuple(rgba) for rgba in builder.PALETTE.values()}
    left = 256 - builder.MONITOR_WIDTH * builder.SCALE
    top = 256 - builder.MONITOR_HEIGHT * builder.SCALE - builder.BOTTOM_MARGIN_PX

    for path in frames["agent_loop"]:
        pixels = Image.open(path).convert("RGBA").load()
        for row, line in enumerate(builder.MONITOR):
            for col, cell in enumerate(line):
                if cell == " ":
                    continue
                x, y = left + col * builder.SCALE, top + row * builder.SCALE
                assert pixels[x, y] in palette, (path.name, x, y)


def test_screen_scrolls_and_loops_seamlessly(builder) -> None:
    screens = [builder.loop_screen(frame) for frame in range(18)]

    assert len({tuple(screen) for screen in screens}) == 18  # it moves every frame
    # Frame 17 → frame 0 continues the same progression as any other pair.
    assert builder.loop_screen(18) == screens[0]
