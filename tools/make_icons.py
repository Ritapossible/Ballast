"""Generate the favicon set from the Ballast mark.

No image library is available and none is wanted: the site ships with zero
dependencies, so the icons are rasterised here with `zlib` and `struct` alone and
committed as artifacts. Regenerate with `python3 tools/make_icons.py`.

The mark is a plumb line - a vertical rule through a weighted centre - which is
also what the product does: it holds a position steady rather than moving it.

At 16px the horizontal ticks collapse into mud, so they are drawn only at 32px and
above. An icon that is illegible in a tab is worse than a simpler one.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs"

BG = (0x07, 0x07, 0x08)
ACCENT = (0x00, 0xD9, 0xEC)
SAMPLES = 4                      # 4x4 supersampling per pixel


# --- geometry, in normalised 0..1 coordinates --------------------------------

def _rounded_rect(x: float, y: float, r: float = 0.22) -> bool:
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    return (x - cx) ** 2 + (y - cy) ** 2 <= r * r


def _capsule(x: float, y: float, x0: float, y0: float, x1: float, y1: float,
             half: float) -> bool:
    """Distance to a line segment, for round-capped bars."""
    dx, dy = x1 - x0, y1 - y0
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((x - x0) * dx + (y - y0) * dy) / length2))
    px, py = x0 + t * dx, y0 + t * dy
    return (x - px) ** 2 + (y - py) ** 2 <= half * half


def _mark_alpha(x: float, y: float, ticks: bool) -> float:
    if _capsule(x, y, 0.5, 0.14, 0.5, 0.86, 0.043):        # the plumb line
        return 1.0
    if (x - 0.5) ** 2 + (y - 0.5) ** 2 <= 0.178 ** 2:      # the weight
        return 1.0
    if ticks:
        for ty in (0.315, 0.685):
            if _capsule(x, y, 0.235, ty, 0.765, ty, 0.032):
                return 0.42
    return 0.0


def _pixels(size: int) -> bytes:
    ticks = size >= 32
    step = 1.0 / (size * SAMPLES)
    rows = bytearray()
    for py in range(size):
        rows.append(0)                                      # PNG filter: none
        for px in range(size):
            r = g = b = a = 0.0
            for sy in range(SAMPLES):
                for sx in range(SAMPLES):
                    x = (px * SAMPLES + sx + 0.5) * step
                    y = (py * SAMPLES + sy + 0.5) * step
                    if not _rounded_rect(x, y):
                        continue
                    m = _mark_alpha(x, y, ticks)
                    fr = BG[0] + (ACCENT[0] - BG[0]) * m
                    fg = BG[1] + (ACCENT[1] - BG[1]) * m
                    fb = BG[2] + (ACCENT[2] - BG[2]) * m
                    r, g, b, a = r + fr, g + fg, b + fb, a + 1.0
            n = SAMPLES * SAMPLES
            if a == 0:
                rows += bytes((0, 0, 0, 0))
            else:
                rows += bytes((round(r / a), round(g / a), round(b / a),
                               round(255 * a / n)))
    return bytes(rows)


# --- PNG ---------------------------------------------------------------------

def _chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


def png(size: int) -> bytes:
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)   # 8-bit RGBA
    return (b"\x89PNG\r\n\x1a\n"
            + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(_pixels(size), 9))
            + _chunk(b"IEND", b""))


def ico(sizes: list[int]) -> bytes:
    """ICO with embedded PNGs - supported everywhere that matters since Vista."""
    images = [png(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, blob = b"", b""
    for size, data in zip(sizes, images, strict=True):
        entries += struct.pack("<BBBBHHII", size if size < 256 else 0,
                               size if size < 256 else 0, 0, 0, 1, 32,
                               len(data), offset)
        blob += data
        offset += len(data)
    return header + entries + blob


SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="14" fill="#070708"/>
<g stroke="#00d9ec" stroke-linecap="round">
<path d="M15 20h34M15 44h34" stroke-width="4" opacity=".42"/>
<path d="M32 9v46" stroke-width="5.5"/>
</g>
<circle cx="32" cy="32" r="11.4" fill="#00d9ec"/>
</svg>"""


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    written = []
    for name, data in [
        ("favicon.svg", SVG.encode()),
        ("favicon.ico", ico([16, 32, 48])),
        ("apple-touch-icon.png", png(180)),
        ("icon-192.png", png(192)),
        ("icon-512.png", png(512)),
    ]:
        (OUT / name).write_bytes(data)
        written.append((name, len(data)))
    for name, n in written:
        print(f"  {name:22s} {n:>8,} bytes")


if __name__ == "__main__":
    main()
