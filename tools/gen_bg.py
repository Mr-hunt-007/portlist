#!/usr/bin/env python3
"""Generate the site's background textures.

Written rather than downloaded, for the same reason as the social card: the
repository carries no third-party image and nothing anybody has to take on
trust. Pure standard library.

    python3 tools/gen_bg.py

Two files, both deliberately faint. They are texture, not decoration you are
meant to look at:

    docs/bg-grid.png    a 320px tile: terminal cell grid plus a little noise
    docs/bg-ports.png   a wide field of ports and the links between them
"""
import math
import os
import random
import struct
import zlib

INK = (0x0B, 0x10, 0x17)


def png(path, w, h, px, alpha=False):
    raw = bytearray()
    mode = 6 if alpha else 2
    for y in range(h):
        raw.append(0)
        for x in range(w):
            raw += bytes(px[y][x])
    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, mode, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)
    return len(body)


def grid_tile(path, size=320, cell=40):
    """A terminal cell grid. Transparent, so one file works on both themes."""
    rnd = random.Random(7)                     # fixed seed: the file is reproducible
    px = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            a = 0
            if x % cell == 0 or y % cell == 0:
                a = 16
            if x % (cell * 4) == 0 or y % (cell * 4) == 0:
                a = 26
            n = rnd.random()
            if n > 0.9985:                      # a sparse dust of brighter cells
                a = max(a, 40)
            if a:
                px[y][x] = (0x7F, 0x9A, 0xB8, a)
    return png(path, size, size, px, alpha=True)


def port_field(path, w=1600, h=900):
    """Ports scattered on a field, with the short links drawn between them.

    The layout is seeded, not random per run, so the file does not churn in git
    every time this is run.
    """
    rnd = random.Random(1337)
    px = [[(0, 0, 0, 0) for _ in range(w)] for _ in range(h)]
    nodes = []
    for _ in range(90):
        nodes.append((rnd.randrange(40, w - 40), rnd.randrange(40, h - 40),
                      rnd.choice([1, 1, 1, 2])))

    def blend(x, y, colour, a):
        if 0 <= x < w and 0 <= y < h:
            r, g, b, old = px[y][x]
            if a > old:
                px[y][x] = (colour[0], colour[1], colour[2], a)

    # links first, so nodes sit on top
    for i, (x1, y1, _s) in enumerate(nodes):
        for x2, y2, _t in nodes[i + 1:]:
            d = math.hypot(x2 - x1, y2 - y1)
            if d > 190:
                continue
            steps = int(d)
            for k in range(steps):
                t = k / float(steps)
                blend(int(x1 + (x2 - x1) * t), int(y1 + (y2 - y1) * t),
                      (0x3F, 0xA7, 0xA0), 11)

    for x, y, s in nodes:
        for dy in range(-s, s + 1):
            for dx in range(-s, s + 1):
                if dx * dx + dy * dy <= s * s:
                    blend(x + dx, y + dy, (0xE8, 0xA3, 0x3D) if s > 1 else (0x8F, 0xB6, 0xD8),
                          70 if s > 1 else 42)
    return png(path, w, h, px, alpha=True)


def paper(path, size=400):
    """Warm paper grain. Barely there: it should read as a surface, not as noise.

    Two frequencies, because one looks like television static. A coarse fibre
    laid under a fine speck, both at very low contrast.
    """
    rnd = random.Random(21)
    base = (0xF2, 0xEF, 0xE7)
    px = [[base for _ in range(size)] for _ in range(size)]
    for y in range(size):
        for x in range(size):
            fibre = math.sin((x * 0.7 + y * 0.3) * 0.35) * 1.4
            speck = (rnd.random() - 0.5) * 5.0
            d = fibre + speck
            px[y][x] = tuple(max(0, min(255, int(c + d))) for c in base)
    return png(path, size, size, px)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    docs = os.path.join(root, "docs")
    a = grid_tile(os.path.join(docs, "bg-grid.png"))
    b = port_field(os.path.join(docs, "bg-ports.png"))
    c = paper(os.path.join(docs, "bg-paper.png"))
    print("wrote docs/bg-grid.png  (%d bytes)" % a)
    print("wrote docs/bg-ports.png (%d bytes)" % b)
    print("wrote docs/bg-paper.png (%d bytes)" % c)


if __name__ == "__main__":
    main()
