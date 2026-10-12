"""Draw the MZ app icon (src/megazword/mz.ico) with the standard library only.

Same mark as the dashboard's app header: a green rounded square with a dark "MZ"
stroke (dashboard.html, 32x32 viewBox). Run: python scripts/make_icon.py
"""

import math
import struct
import zlib
from pathlib import Path

GREEN = (0x72, 0xF0, 0xA5)
INK = (0x09, 0x21, 0x15)
# The header SVG paths, in its 32x32 viewBox.
STROKES = [[(5, 22), (5, 10), (10, 16), (15, 10), (15, 22)],
           [(18, 10), (27, 10), (18, 22), (27, 22)]]
STROKE_WIDTH = 2.5
RADIUS = 8
SIZES = (16, 24, 32, 48, 64, 128, 256)
SAMPLES = 4  # per axis, for antialiasing


def _seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - ax - t * dx, py - ay - t * dy)


def _in_rounded_square(x, y):
    cx = min(max(x, RADIUS), 32 - RADIUS)
    cy = min(max(y, RADIUS), 32 - RADIUS)
    return 0 <= x <= 32 and 0 <= y <= 32 and math.hypot(x - cx, y - cy) <= RADIUS


def _on_stroke(x, y):
    half = STROKE_WIDTH / 2
    return any(_seg_dist(x, y, *a, *b) <= half
               for line in STROKES for a, b in zip(line, line[1:]))


def pixels(size):
    """RGBA rows for one icon size."""
    rows = []
    scale = 32 / size
    for j in range(size):
        row = bytearray()
        for i in range(size):
            bg = ink = 0
            for sj in range(SAMPLES):
                for si in range(SAMPLES):
                    x = (i + (si + 0.5) / SAMPLES) * scale
                    y = (j + (sj + 0.5) / SAMPLES) * scale
                    if _in_rounded_square(x, y):
                        bg += 1
                        ink += _on_stroke(x, y)
            n = SAMPLES * SAMPLES
            if not bg:
                row += bytes(4)
                continue
            mix = ink / bg
            rgb = [round(g * (1 - mix) + k * mix) for g, k in zip(GREEN, INK)]
            row += bytes([*rgb, round(255 * bg / n)])
        rows.append(bytes(row))
    return rows


def png(size):
    raw = b"".join(b"\x00" + r for r in pixels(size))

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def ico(sizes=SIZES):
    images = [png(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = b""
    for size, data in zip(sizes, images):
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    return header + entries + b"".join(images)


if __name__ == "__main__":
    out = Path(__file__).resolve().parents[1] / "src" / "megazword" / "mz.ico"
    out.write_bytes(ico())
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")
