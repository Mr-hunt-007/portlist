#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bake the room plate down to something small enough to ship.

The plate on the site is 1400x788 and 186 KB, which is the right size for a
web page and the wrong size for a wheel: vibe mode only ever samples it down
to a few hundred terminal cells, so every pixel past that is weight nobody
sees. This writes a small 8-bit greyscale PNG with `zlib` and `struct`, the
same two modules the decoder uses, so nothing new is added to install.

    python3 tools/gen_vibe_bg.py docs/plate-terminal.png plcore/data/room.png
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import imgmap                                        # noqa: E402

OUT_W = 420          # ~2x the widest terminal anyone runs vibe mode on


def _box(src, sw, sh, dw, dh):
    """Average each destination pixel over the source box it covers.

    Nearest-neighbour turns a dithered plate into moire, because the dither is
    already a high-frequency pattern and point-sampling it aliases badly. The
    average is what makes the stipple read as tone again.
    """
    out = bytearray(dw * dh)
    for y in range(dh):
        y0, y1 = y * sh // dh, max(y * sh // dh + 1, (y + 1) * sh // dh)
        for x in range(dw):
            x0, x1 = x * sw // dw, max(x * sw // dw + 1, (x + 1) * sw // dw)
            total = n = 0
            for yy in range(y0, y1):
                row = yy * sw
                for xx in range(x0, x1):
                    total += src[row + xx]; n += 1
            out[y * dw + x] = total // n
    return out


def _png(width, height, grey):
    raw = bytearray()
    for y in range(height):
        raw.append(0)                                   # filter 0: none
        raw += grey[y * width:(y + 1) * width]

    def chunk(tag, body):
        return (struct.pack(">I", len(body)) + tag + body
                + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF))

    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main(argv):
    src_path = argv[1] if len(argv) > 1 else "docs/plate-terminal.png"
    dst_path = argv[2] if len(argv) > 2 else "plcore/data/room.png"
    sw, sh, lum = imgmap.load(src_path)
    dw = min(OUT_W, sw)
    dh = max(1, sh * dw // sw)
    small = _box(lum, sw, sh, dw, dh)

    lo, hi = min(small), max(small)
    if hi > lo:
        # The plate is a dark room: almost everything sits in the bottom of the
        # range, so the density map would be nearly empty. Stretching to the
        # full range is what makes the monitors and the window read on screen.
        span = float(hi - lo)
        small = bytearray(int((v - lo) * 255 / span) for v in small)

    folder = os.path.dirname(dst_path)
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(dst_path, "wb") as f:
        f.write(_png(dw, dh, small))
    print("%s  %dx%d  %.1f KB  (from %dx%d, %.1f KB)"
          % (dst_path, dw, dh, os.path.getsize(dst_path) / 1024.0,
             sw, sh, os.path.getsize(src_path) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
