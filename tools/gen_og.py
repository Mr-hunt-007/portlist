#!/usr/bin/env python3
"""Generate docs/og.png, the social card.

Written rather than downloaded, so the repository carries no third-party image
and no binary anybody has to take on trust. Pure standard library: zlib and
struct are a PNG encoder if you are willing to write the chunks yourself.

    python3 tools/gen_og.py
"""
import os
import struct
import zlib

W, H = 1200, 630
BG = (0x0B, 0x10, 0x17)
GRID = (0x14, 0x1D, 0x28)
AMBER = (0xE8, 0xA3, 0x3D)
TEAL = (0x3F, 0xA7, 0xA0)
SLATE = (0x6B, 0x7C, 0x90)
RED = (0xD9, 0x54, 0x4D)

# A 5x7 pixel font, written out here so the card needs no font file and no
# rasteriser. The splash screen's ASCII letterforms were tried first and turned
# to mush at block scale: thin diagonal strokes do not survive being a rectangle.
FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["111", "010", "010", "010", "010", "010", "111"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    ",": ["000", "000", "000", "000", "000", "010", "100"],
    ".": ["00", "00", "00", "00", "00", "00", "11"],
    " ": ["000", "000", "000", "000", "000", "000", "000"],
}


def canvas():
    return [[BG for _ in range(W)] for _ in range(H)]


def rect(px, x, y, w, h, colour):
    for yy in range(max(0, y), min(H, y + h)):
        row = px[yy]
        for xx in range(max(0, x), min(W, x + w)):
            row[xx] = colour


def measure(word, scale, gap):
    return sum((len(FONT[ch][0]) + gap) * scale for ch in word) - gap * scale


def text(px, word, x0, y0, scale, colour, gap=1):
    """Draw with the pixel font. -> width drawn."""
    x = x0
    for ch in word:
        glyph = FONT[ch]
        for r, line in enumerate(glyph):
            for c, bit in enumerate(line):
                if bit == "1":
                    rect(px, x + c * scale, y0 + r * scale, scale, scale, colour)
        x += (len(glyph[0]) + gap) * scale
    return x - x0


def png(path, px):
    raw = bytearray()
    for row in px:
        raw.append(0)                       # filter type 0 for every scanline
        for r, g, b in row:
            raw += bytes((r, g, b))

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)
    return len(body)


def main():
    px = canvas()
    for x in range(0, W, 40):               # a faint grid, like a terminal cell map
        rect(px, x, 0, 1, H, GRID)
    for y in range(0, H, 40):
        rect(px, 0, y, W, 1, GRID)
    rect(px, 0, 0, W, 6, AMBER)             # a signal line across the top

    scale = 16
    word = "PORTLIST"
    text(px, word, (W - measure(word, scale, 1)) // 2, 150, scale, AMBER)

    tag = "EVERY PORT, AND WHERE IT CAME FROM."
    tscale = 5
    text(px, tag, (W - measure(tag, tscale, 1)) // 2, 300, tscale, SLATE)

    # A suggestion of the table underneath: port, service, scope, risk.
    y = 390
    for i, (port_c, svc_w, scope_c, risk_c) in enumerate([
            (TEAL, 210, SLATE, TEAL), (TEAL, 260, SLATE, TEAL),
            (AMBER, 180, AMBER, RED), (TEAL, 240, SLATE, TEAL),
            (TEAL, 150, SLATE, TEAL)]):
        rect(px, 250, y, 62, 12, port_c)
        rect(px, 340, y, svc_w, 12, SLATE)
        rect(px, 640, y, 130, 12, scope_c)
        rect(px, 820, y, 70, 12, risk_c)
        rect(px, 930, y, 20, 12, AMBER if i in (0, 3) else GRID)
        y += 34

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "docs", "og.png")
    size = png(out, px)
    print("wrote %s (%d bytes, %dx%d)" % (out, size, W, H))


if __name__ == "__main__":
    main()
