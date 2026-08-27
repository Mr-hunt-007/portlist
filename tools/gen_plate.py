#!/usr/bin/env python3
"""Downsample the observatory plate for the web, with nothing but the stdlib.

The source is a 1536x1024 PNG at about 2.4 MB, which is more than a landing page
should ask anyone to download for one picture. This box-filters it to a sensible
width and re-encodes, reusing the PNG reader in plcore/imgmap.py so the project
still carries no image library.

    python3 tools/gen_plate.py [width]
"""
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from plcore import imgmap                                   # noqa: E402

CHANNELS = imgmap.CHANNELS


def read_rgb(path):
    """-> (w, h, bytearray of RGB triples). Same decoder, colour kept."""
    with open(path, "rb") as f:
        data = f.read()
    w = h = depth = colour = None
    idat, palette = bytearray(), None
    for tag, body in imgmap._chunks(data):
        if tag == b"IHDR":
            w, h, depth, colour, _c, _f, interlace = struct.unpack(">IIBBBBB", body)
            if depth != 8 or interlace:
                raise imgmap.Unsupported("need 8-bit, non-interlaced")
        elif tag == b"PLTE":
            palette = body
        elif tag == b"IDAT":
            idat += body
        elif tag == b"IEND":
            break
    ch = CHANNELS[colour]
    flat = imgmap._unfilter(zlib.decompress(bytes(idat)), w, h, ch, w * ch)
    rgb = bytearray(w * h * 3)
    for i in range(w * h):
        j = i * ch
        if colour == imgmap.RGB or colour == imgmap.RGBA:
            r, g, b = flat[j], flat[j + 1], flat[j + 2]
        elif colour == imgmap.GREY or colour == imgmap.GREY_A:
            r = g = b = flat[j]
        else:
            k = flat[j] * 3
            r, g, b = palette[k], palette[k + 1], palette[k + 2]
        rgb[i * 3:i * 3 + 3] = bytes((r, g, b))
    return w, h, rgb


def resize(w, h, rgb, out_w):
    """Box filter. Slow and obvious, which is the right trade for a build step."""
    out_h = max(1, round(h * out_w / float(w)))
    out = bytearray(out_w * out_h * 3)
    for y in range(out_h):
        y0, y1 = y * h // out_h, max(y * h // out_h + 1, (y + 1) * h // out_h)
        for x in range(out_w):
            x0, x1 = x * w // out_w, max(x * w // out_w + 1, (x + 1) * w // out_w)
            r = g = b = n = 0
            for sy in range(y0, y1):
                base = sy * w
                for sx in range(x0, x1):
                    i = (base + sx) * 3
                    r += rgb[i]; g += rgb[i + 1]; b += rgb[i + 2]; n += 1
            i = (y * out_w + x) * 3
            out[i], out[i + 1], out[i + 2] = r // n, g // n, b // n
    return out_w, out_h, out


def quantise(w, h, rgb, colours=64):
    """Popularity palette plus Floyd-Steinberg dithering.

    The plate is flat paper, fine black linework and a few vermilion seals, so a
    handful of colours carries it. Truecolour PNG of that is 1.5 MB; indexed is a
    quarter of it. Dithering matters here: without it the paper bands into
    visible steps, which is worse than the file size.
    """
    bins = {}
    for i in range(0, len(rgb), 3):
        key = (rgb[i] >> 3, rgb[i + 1] >> 3, rgb[i + 2] >> 3)
        bins[key] = bins.get(key, 0) + 1
    # Popularity alone loses the accent: the vermilion seals are a fraction of a
    # per cent of the pixels, so they never win a slot, and the plate comes back
    # in black and white. Reserve a few places for the most saturated bins that
    # actually occur, then fill the rest by count.
    def sat(key):
        r, g, b = key
        return max(r, g, b) - min(r, g, b)

    accents = sorted((k for k in bins if sat(k) >= 4),
                     key=lambda k: -(sat(k) * (bins[k] ** 0.5)))[:8]
    rest = sorted((k for k in bins if k not in set(accents)),
                  key=lambda k: -bins[k])[:max(0, colours - len(accents))]
    top = [(k, bins[k]) for k in accents + rest]
    pal = [((r << 3) | 4, (g << 3) | 4, (b << 3) | 4) for (r, g, b), _n in top]
    while len(pal) < colours:
        pal.append((0, 0, 0))

    cache = {}

    def nearest(r, g, b):
        key = (r >> 2, g >> 2, b >> 2)
        hit = cache.get(key)
        if hit is not None:
            return hit
        best, bd = 0, 1 << 30
        for i, (pr, pg, pb) in enumerate(pal):
            d = (pr - r) ** 2 + (pg - g) ** 2 + (pb - b) ** 2
            if d < bd:
                best, bd = i, d
        cache[key] = best
        return best

    work = [float(v) for v in rgb]
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 3
            r = min(255, max(0, work[i])); g = min(255, max(0, work[i + 1]))
            b = min(255, max(0, work[i + 2]))
            idx = nearest(int(r), int(g), int(b))
            pr, pg, pb = pal[idx]
            out[y * w + x] = idx
            er, eg, eb = r - pr, g - pg, b - pb
            for dx, dy, f in ((1, 0, 7 / 16.0), (-1, 1, 3 / 16.0),
                              (0, 1, 5 / 16.0), (1, 1, 1 / 16.0)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and ny < h:
                    j = (ny * w + nx) * 3
                    work[j] += er * f; work[j + 1] += eg * f; work[j + 2] += eb * f
    return pal, out


def write_indexed(path, w, h, pal, idx):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += idx[y * w:(y + 1) * w]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    plte = bytearray()
    for r, g, b in pal:
        plte += bytes((r, g, b))
    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 3, 0, 0, 0))
            + chunk(b"PLTE", bytes(plte))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)
    return len(body)


def write_png(path, w, h, rgb):
    raw = bytearray()
    for y in range(h):
        raw.append(0)
        raw += rgb[y * w * 3:(y + 1) * w * 3]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        return out + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    body = (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(body)
    return len(body)


PLATES = [("plate-observatory", 1280), ("plate-terminal", 1400)]


def main():
    """Usage: gen_plate.py [name] [width]. With no arguments, does them all."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    jobs = PLATES
    if len(sys.argv) > 1:
        jobs = [(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 1280)]
    for name, width in jobs:
        one(root, name, width)


def one(root, name, width):
    src = os.path.join(root, "docs", name + "-source.png")
    dst = os.path.join(root, "docs", name + ".png")
    if not os.path.exists(src):                 # first run: keep the original aside
        os.rename(dst, src)
    w, h, rgb = read_rgb(src)
    ow, oh, small = resize(w, h, rgb, width)
    pal, idx = quantise(ow, oh, small)
    size = write_indexed(dst, ow, oh, pal, idx)
    print("%-18s %dx%d (%d KB)  ->  %dx%d indexed, %d colours (%d KB)"
          % (name, w, h, os.path.getsize(src) // 1024, ow, oh, len(pal), size // 1024))


if __name__ == "__main__":
    main()
