"""Build Mochi's reading loop from the canonical idle breathing frames.

Every frame is the untouched 64 × 64 idle body plus three authored overlays:
a small open book held in both nub hands, downcast eyes that scan along the
line being read, and a page that lifts, crosses the spine, and settles. The
body art is never redrawn, so reading cannot drift off-model from idle.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
IDLE_FRAMES = tuple(
    ROOT / "assets" / "mochi" / "idle" / f"idle_{index:02d}.png" for index in range(1, 7)
)
TARGET = ROOT / "assets" / "mochi" / "reading" / "reading.png"
CELL = 64
IDLE_SCALE = 4

PALETTE = {
    "o": (3, 48, 13, 255),  # Mochi outline
    ".": (174, 247, 173, 255),  # body light
    "w": (249, 251, 249, 255),  # highlight / paper
    "c": (217, 207, 184, 255),  # printed line / page shade
    "R": (192, 88, 60, 255),  # cover
    "r": (122, 50, 38, 255),  # cover shade and spine
    "h": (222, 123, 87, 255),  # cover highlight
}
EYE_DARK = {(2, 24, 16), (5, 31, 14)}
EYE_LIGHT = (249, 251, 249)

# Seen from the front, an open book held up to read shows its back cover with
# the two page blocks fanning above it.
BOOK = (
    "  oooo        oooo  ",
    " owwwwoo    oowwwwo ",
    "owcwcwwwoooowwwcwcwo",
    "owwwwwwwwrrwwwwwwwwo",
    "orhhRRRRRrrRRRRRRrro",
    "ohRRRRRRRrrRRRRRRRRo",
    "oRRRRRRRRrrRRRRRRRRo",
    "oRRRRRRRRrrRRRRRRRRo",
    "oRRRRRRRRrrRRRRRRRRo",
    "oRRRRRRRRrrRRRRRRRRo",
    "orrrrrrrrrrrrrrrrrro",
    " oooooooooooooooooo ",
)
BOOK_LEFT = 22
BOOK_TOP = 49

HAND = (
    " oo ",
    "o.wo",
    "o..o",
    " oo ",
)

# A turning page, drawn relative to BOOK_TOP: lifting off the right block,
# upright over the spine, then dropping onto the left block.
PAGE_TURN = {
    "lift": ((11, -2, "  ooooo "), (11, -1, " owwwwwo"), (11, 0, "owcwcwwo")),
    "upright": (
        (8, -5, " oooo "),
        (8, -4, "owwwwo"),
        (8, -3, "owcwwo"),
        (8, -2, "owwcwo"),
        (8, -1, "owcwwo"),
        (8, 0, "owwwwo"),
    ),
    "drop": ((1, -2, " ooooo  "), (1, -1, "owwwwwo "), (1, 0, "owcwcwwo")),
}

# (idle body frame, eye shift, page state, right hand lift). Twenty-four frames
# at 6 fps: four seconds of reading a line, turning a page, and starting again.
TIMELINE = (
    (0, -1, None, 0),
    (0, -1, None, 0),
    (1, -1, None, 0),
    (1, 0, None, 0),
    (2, 0, None, 0),
    (2, 0, None, 0),
    (3, 1, None, 0),
    (3, 1, None, 0),
    (4, 1, None, 0),
    (4, -1, None, 0),
    (5, -1, None, 0),
    (5, 0, None, 0),
    (0, 0, None, 0),
    (0, 1, None, 0),
    (1, 1, None, 0),
    (1, 1, "lift", 1),
    (2, 0, "upright", 1),
    (2, 0, "upright", 1),
    (3, -1, "drop", 0),
    (3, -1, None, 0),
    (4, -1, None, 0),
    (4, -1, None, 0),
    (5, -1, None, 0),
    (5, -1, None, 0),
)
FPS = 6


def _stamp(frame: Image.Image, rows: tuple[str, ...], left: int, top: int) -> None:
    for dy, row in enumerate(rows):
        for dx, key in enumerate(row):
            if key != " ":
                frame.putpixel((left + dx, top + dy), PALETTE[key])


def _eye_boxes(frame: Image.Image) -> list[tuple[int, int, int, int]]:
    """Return the two eye bounding boxes: the large dark blobs above the mouth."""
    seen: set[tuple[int, int]] = set()
    blobs: list[list[tuple[int, int]]] = []
    for y in range(CELL):
        for x in range(CELL):
            if (x, y) in seen or frame.getpixel((x, y))[:3] not in EYE_DARK:
                continue
            stack, blob = [(x, y)], []
            seen.add((x, y))
            while stack:
                px, py = stack.pop()
                blob.append((px, py))
                for nx, ny in ((px + 1, py), (px - 1, py), (px, py + 1), (px, py - 1)):
                    if (
                        0 <= nx < CELL
                        and 0 <= ny < CELL
                        and (nx, ny) not in seen
                        and frame.getpixel((nx, ny))[:3] in EYE_DARK | {EYE_LIGHT}
                    ):
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            blobs.append(blob)
    eyes = sorted(blobs, key=len, reverse=True)[:2]
    if len(eyes) != 2 or min(len(blob) for blob in eyes) < 20:
        raise RuntimeError("could not find both eyes in the idle frame")
    boxes = []
    for blob in eyes:
        xs = [x for x, _ in blob]
        ys = [y for _, y in blob]
        boxes.append((min(xs), min(ys), max(xs) + 1, max(ys) + 1))
    return sorted(boxes)


def _read_with_eyes(frame: Image.Image, shift: int) -> None:
    """Move the canonical eyes down toward the page and along the printed line."""
    # The eyes' rim shading reuses the outline green, so look one pixel past
    # the dark blob on each side to carry the whole eye.
    eye_colors = EYE_DARK | {EYE_LIGHT, PALETTE["o"][:3]}
    for left, top, right, bottom in _eye_boxes(frame):
        pixels = [
            (x, y, frame.getpixel((x, y)))
            for y in range(top, bottom)
            for x in range(left - 1, right + 1)
            if frame.getpixel((x, y))[:3] in eye_colors
        ]
        for x, y, _color in pixels:
            frame.putpixel((x, y), PALETTE["."])
        for x, y, color in pixels:
            frame.putpixel((x + shift, y + 1), color)


def build_frames() -> list[Image.Image]:
    bodies = []
    for path in IDLE_FRAMES:
        idle = Image.open(path).convert("RGBA")
        bodies.append(idle.resize((CELL, CELL), Image.Resampling.NEAREST))
        if bodies[-1].resize(idle.size, Image.Resampling.NEAREST).tobytes() != idle.tobytes():
            raise RuntimeError(f"{path.name} is not a clean {IDLE_SCALE}x idle frame")

    frames = []
    for body_index, eye_shift, page_state, hand_lift in TIMELINE:
        frame = bodies[body_index].copy()
        _read_with_eyes(frame, eye_shift)
        _stamp(frame, BOOK, BOOK_LEFT, BOOK_TOP)
        for left, offset, row in PAGE_TURN.get(page_state, ()):
            _stamp(frame, (row,), BOOK_LEFT + left, BOOK_TOP + offset)
        _stamp(frame, HAND, BOOK_LEFT - 2, BOOK_TOP + 5)
        _stamp(frame, HAND, BOOK_LEFT + len(BOOK[0]) - 2, BOOK_TOP + 5 - hand_lift)
        frames.append(frame)
    return frames


def main() -> None:
    frames = build_frames()
    sheet = Image.new("RGBA", (CELL * len(frames), CELL))
    for index, frame in enumerate(frames):
        sheet.alpha_composite(frame, (index * CELL, 0))
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(TARGET, optimize=True)
    print(f"wrote {TARGET.relative_to(ROOT)} ({len(frames)} frames at {FPS} fps)")


if __name__ == "__main__":
    main()
