"""Build Mochi's agent-session scene from the canonical coffee frames.

While a coding agent works, Mochi sips from his mug and keeps a little monitor
company while it scrolls code. Every frame is an untouched coffee frame plus
one authored prop: the monitor below, drawn on Mochi's 4 px grid (64-cell art
shown x4) and placed at his bottom-right. Mochi himself is never redrawn, so
the scene cannot drift off-model.

The monitor was drafted with PixelEngine (oai_gpt25_high, style-referenced to
``terminal/terminal_05.png``; jobs 17c83bfe-ec0e-478c-8350-520f5ea133b2 and
c829ff79-ef57-48ad-a17f-6f9ca90a4f55), keyed off its magenta matte and fringe,
cropped, and transcribed below as palette art.

The committed PNGs are the source of truth: once frames are hand-cleaned in
Pixelorama, this script is only a record of the draft. It refuses to overwrite
existing frames unless given ``--force``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
COFFEE_DIR = ROOT / "assets" / "mochi" / "coffee"
TARGET_DIR = ROOT / "assets" / "mochi" / "agent"
CANVAS = 256
SCALE = 4
BOTTOM_MARGIN_PX = 4

PALETTE = {
    "o": (2, 29, 10, 255),  # outline and screen
    "a": (161, 167, 198, 255),  # casing shade
    "b": (204, 206, 238, 255),  # casing
    "w": (239, 241, 250, 255),  # casing highlight
    "g": (103, 247, 96, 255),  # code
}

MONITOR = (
    "  oooooooooooooooooooo  ",
    " oowbbbbbbbbbbbbbbbbwoo ",
    "oowbaaaaaaaaaaaaaaaaaboo",
    "owbaooooooooooooooooaaao",
    "owbaooooooooooooooooaaao",
    "owbaooggggggooooooooaabo",
    "owbaooooooooooooooooaabo",
    "owbaooggggggggggooooaabo",
    "owbaooooooooooooooooaabo",
    "owbaoogggggggoooooooaabo",
    "owbaooooooooooooooooaabo",
    "owbaooggooooooooooooaabo",
    "obbaooooooooooooooooaaao",
    "obbabbbbbbbbbbbbbbbwaaao",
    "oobaaaaaaaaaaaaaaaaaaaoo",
    " oobaaaaaaaaaaaaaaaaaoo ",
    "  oooooooooooooooooooo  ",
    "         obaaaao        ",
    "     ooooowaaaaoooo     ",
    "    oowwbbaaaaabbboo    ",
    "    owbbbbbbbbbbbbbo    ",
    "     oooooooooooooo     ",
)
MONITOR_WIDTH = len(MONITOR[0])
MONITOR_HEIGHT = len(MONITOR)

# Screen interior (grid px, inclusive) and where code is typed.
SCREEN_ROWS = range(3, 13)
SCREEN_COLS = range(4, 20)
CODE_ROWS = (5, 7, 9, 11)
CODE_COL = 6
CODE_MAX_COL = 18
# The code cycle: (indent, length). Nine lines over an 18-frame loop scroll one
# line every two frames, so the screen loops seamlessly.
LINES = ((0, 6), (0, 10), (2, 7), (2, 9), (4, 5), (2, 8), (0, 3), (0, 11), (2, 6))

HIDDEN = MONITOR_HEIGHT + 2  # grid px below rest: fully under the bottom edge
INTRO_DROPS = (HIDDEN, HIDDEN, 16, 9, 4, 1, 0)
OUTRO_DROPS = (0, 2, 6, 13, HIDDEN)
LOOP_FRAMES = 18


def _with_screen(lines: list[tuple[int, int, int, bool]]) -> list[str]:
    """The monitor with its screen cleared, then (row, indent, length, cursor) drawn."""
    rows = [list(row) for row in MONITOR]
    for y in SCREEN_ROWS:
        for x in SCREEN_COLS:
            rows[y][x] = "o"
    for row, indent, length, cursor in lines:
        start = CODE_COL + indent
        for x in range(start, min(start + length, CODE_MAX_COL + 1)):
            rows[row][x] = "g"
        if cursor:
            rows[row][min(start + length + 1, CODE_MAX_COL)] = "g"
    return ["".join(row) for row in rows]


def screen_off() -> list[str]:
    return _with_screen([])


def loop_screen(frame: int) -> list[str]:
    """Scroll one line every two frames; the bottom line types in with a cursor."""
    line, phase = divmod(frame % LOOP_FRAMES, 2)
    drawn = []
    for slot, row in enumerate(CODE_ROWS):
        indent, length = LINES[(line + slot) % len(LINES)]
        typing = slot == len(CODE_ROWS) - 1
        if typing and not phase:
            length = max(1, length // 2)
        drawn.append((row, indent, length, typing))
    return _with_screen(drawn)


def _coffee(index: int) -> Image.Image:
    with Image.open(COFFEE_DIR / f"mochi_coffee_{index:04d}.png") as image:
        return image.convert("RGBA")


def compose(coffee_index: int, monitor: list[str], drop: int) -> Image.Image:
    """An untouched coffee frame with the monitor sunk ``drop`` grid px below rest."""
    frame = _coffee(coffee_index)
    pixels = frame.load()
    left = CANVAS - MONITOR_WIDTH * SCALE
    top = CANVAS - MONITOR_HEIGHT * SCALE - BOTTOM_MARGIN_PX + drop * SCALE
    for row, line in enumerate(monitor):
        for col, cell in enumerate(line):
            if cell == " ":
                continue
            colour = PALETTE[cell]
            for dy in range(SCALE):
                y = top + row * SCALE + dy
                if y >= CANVAS:
                    break  # sunk below the bottom edge
                for dx in range(SCALE):
                    pixels[left + col * SCALE + dx, y] = colour
    return frame


def frames() -> dict[str, list[Image.Image]]:
    intro = [
        compose(index, loop_screen(0) if index == len(INTRO_DROPS) else screen_off(), drop)
        for index, drop in enumerate(INTRO_DROPS, start=1)
    ]
    loop = [compose(8 + frame % 9, loop_screen(frame), 0) for frame in range(LOOP_FRAMES)]
    outro = [compose(17 + index, screen_off(), drop) for index, drop in enumerate(OUTRO_DROPS)]
    return {"agent_intro": intro, "agent_loop": loop, "agent_outro": outro}


def build(out_dir: Path = TARGET_DIR, *, force: bool = False) -> dict[str, list[Path]]:
    out_dir = Path(out_dir)
    scene = frames()
    targets = {
        name: [out_dir / f"{name}_{index:02d}.png" for index in range(1, len(images) + 1)]
        for name, images in scene.items()
    }
    existing = [path for paths in targets.values() for path in paths if path.exists()]
    if existing and not force:
        raise FileExistsError(
            f"frames exist in {out_dir}; they may be hand-cleaned — pass --force to overwrite"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, images in scene.items():
        for image, path in zip(images, targets[name], strict=True):
            image.save(path, format="PNG")
    return targets


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=TARGET_DIR)
    parser.add_argument("--force", action="store_true", help="overwrite existing frames")
    args = parser.parse_args(argv)
    try:
        written = build(args.out, force=args.force)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 1
    for name, paths in written.items():
        print(f"{name}: {len(paths)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
