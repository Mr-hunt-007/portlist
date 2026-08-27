# -*- coding: utf-8 -*-
"""Turn a PNG into a density map a terminal can draw.

`zlib` and `struct` are a PNG decoder if you are willing to write the filters
out, which is the whole reason this can exist in a program with no dependencies.

**PNG only, and that is a real limit, not an oversight.** JPEG needs a DCT and a
Huffman decoder; writing one here would be several hundred lines of the wrong
kind of code for a port tool. A JPEG is reported as unsupported rather than
half-read, and the message says to convert it.

What comes back is not an image. It is one number per terminal cell, 0.0 to 1.0,
sampled with the 1:2 aspect of a character cell already accounted for, so a
circle in the file is still a circle on the screen.
"""
import os
import struct
import zlib

PALETTE, GREY, RGB, GREY_A, RGBA = 3, 0, 2, 4, 6
CHANNELS = {GREY: 1, RGB: 3, PALETTE: 1, GREY_A: 2, RGBA: 4}


class Unsupported(Exception):
    """The file is a picture this decoder will not pretend to understand."""


def _chunks(data):
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise Unsupported("not a PNG file")
    i = 8
    while i + 8 <= len(data):
        (length,) = struct.unpack(">I", data[i:i + 4])
        tag = data[i + 4:i + 8]
        body = data[i + 8:i + 8 + length]
        yield tag, body
        i += 12 + length


def _unfilter(raw, width, height, bpp, stride):
    """Undo the five PNG line filters. Every row refers to the one above it."""
    out = bytearray(height * stride)
    pos = 0
    for y in range(height):
        ft = raw[pos]; pos += 1
        line = bytearray(raw[pos:pos + stride]); pos += stride
        up = out[(y - 1) * stride:y * stride] if y else bytearray(stride)
        if ft == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 0xFF
        elif ft == 2:
            for x in range(stride):
                line[x] = (line[x] + up[x]) & 0xFF
        elif ft == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + up[x]) >> 1)) & 0xFF
        elif ft == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = up[x]
                c = up[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pr) & 0xFF
        elif ft != 0:
            raise Unsupported("unknown row filter %d" % ft)
        out[y * stride:(y + 1) * stride] = line
    return out


def load(path):
    """-> (width, height, luminance bytes) or raises Unsupported."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:3] == b"\xff\xd8\xff":
        raise Unsupported("JPEG is not supported: save it as a PNG")
    width = height = depth = colour = None
    idat, palette, trns = bytearray(), None, None
    for tag, body in _chunks(data):
        if tag == b"IHDR":
            width, height, depth, colour, comp, filt, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8:
                raise Unsupported("only 8 bits per channel, this file is %d" % depth)
            if interlace:
                raise Unsupported("interlaced PNGs are not supported")
            if colour not in CHANNELS:
                raise Unsupported("colour type %d is not supported" % colour)
        elif tag == b"PLTE":
            palette = body
        elif tag == b"tRNS":
            trns = body
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    if width is None:
        raise Unsupported("no header chunk")

    ch = CHANNELS[colour]
    stride = width * ch
    raw = zlib.decompress(bytes(idat))
    flat = _unfilter(raw, width, height, ch, stride)

    lum = bytearray(width * height)
    for y in range(height):
        row = y * stride
        for x in range(width):
            i = row + x * ch
            if colour == GREY:
                v, a = flat[i], 255
            elif colour == GREY_A:
                v, a = flat[i], flat[i + 1]
            elif colour == RGB:
                v = (flat[i] * 299 + flat[i + 1] * 587 + flat[i + 2] * 114) // 1000
                a = 255
            elif colour == RGBA:
                v = (flat[i] * 299 + flat[i + 1] * 587 + flat[i + 2] * 114) // 1000
                a = flat[i + 3]
            else:                                   # palette
                idx = flat[i] * 3
                if palette is None or idx + 2 >= len(palette):
                    v, a = 0, 255
                else:
                    v = (palette[idx] * 299 + palette[idx + 1] * 587
                         + palette[idx + 2] * 114) // 1000
                    a = trns[flat[i]] if (trns and flat[i] < len(trns)) else 255
            # transparent pixels read as empty, not as black: a cut-out PNG
            # should leave the terminal background showing through.
            lum[y * width + x] = v * a // 255
    return width, height, lum


def cells(path, cols, rows, cell_aspect=2.1, invert="auto"):
    """-> [[0.0..1.0]] with one value per terminal cell.

    A character cell is about twice as tall as it is wide, so the source is
    sampled with that ratio built in. Without it every picture comes out
    squashed and nobody can tell what it is.

    `invert` decides which end of the image becomes ink on screen. A terminal
    draws light characters on a dark ground, so a photograph maps naturally:
    bright areas become dense. A drawing on white paper maps backwards, and the
    first time a paper-white plate was used as a background the terminal filled
    with a solid wall of characters where the paper was and left the drawing
    blank. On "auto" an image whose average is bright is flipped, so what gets
    drawn is the ink somebody actually drew.
    """
    w, h, lum = load(path)
    if invert == "auto":
        flip = (sum(lum) / float(len(lum) or 1)) > 140
    else:
        flip = bool(invert)
    if flip:
        lum = bytearray(255 - v for v in lum)
    if not w or not h or cols < 1 or rows < 1:
        return []
    # fit the picture inside the grid, keeping its shape
    src_ratio = (w / float(h)) * cell_aspect
    box_ratio = cols / float(rows)
    if src_ratio > box_ratio:
        use_c, use_r = cols, max(1, int(round(cols / src_ratio)))
    else:
        use_r, use_c = rows, max(1, int(round(rows * src_ratio)))
    off_c, off_r = (cols - use_c) // 2, (rows - use_r) // 2

    grid = [[0.0] * cols for _ in range(rows)]
    for gy in range(use_r):
        sy0 = gy * h // use_r
        sy1 = max(sy0 + 1, (gy + 1) * h // use_r)
        for gx in range(use_c):
            sx0 = gx * w // use_c
            sx1 = max(sx0 + 1, (gx + 1) * w // use_c)
            total = n = 0
            for sy in range(sy0, sy1):
                base = sy * w
                for sx in range(sx0, sx1):
                    total += lum[base + sx]; n += 1
            grid[off_r + gy][off_c + gx] = (total / float(n)) / 255.0 if n else 0.0
    return grid


def describe(path):
    """A one-line answer for the UI, whether it worked or not."""
    try:
        w, h, _ = load(path)
        return "%s  %dx%d" % (os.path.basename(path), w, h)
    except Unsupported as e:
        return "%s  (%s)" % (os.path.basename(path), e)
    except OSError as e:
        return "%s  (%s)" % (os.path.basename(path), e.strerror or "unreadable")
