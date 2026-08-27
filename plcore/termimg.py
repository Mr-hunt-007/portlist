# -*- coding: utf-8 -*-
"""Put a real picture on the terminal, where the terminal can take one.

Most terminals cannot. They draw characters, so a picture has to become
characters, which is what `imgmap.py` is for and what vibe mode has always
done. A few terminals speak a graphics protocol and can show the file itself.

Only **kitty's protocol** is used here, and for one reason: it has a z-index.
`z=-1` puts the image behind the text and in front of the cell background,
which is the only arrangement where a background is a background. iTerm2's
inline images and sixel both occupy cells, so a picture drawn that way covers
the readings rather than sitting behind them, and a screen whose numbers are
hidden by decoration is worse than one with no decoration. Those terminals get
the character rendering, which is not a consolation prize: it is the thing this
program was already doing well.

Nothing here writes a byte unless the terminal has said it speaks the protocol.
On a terminal that does not, every function is a no-op, so the failure mode of
being wrong about support is a blank background rather than escape codes
sprayed across somebody's screen.
"""
import base64
import os

# One id for the whole program. Re-transmitting under the same id replaces the
# image rather than accumulating copies in the terminal's memory.
IMAGE_ID = 7331
CHUNK = 4096          # the protocol's limit on one escape's payload


def protocol(env=None):
    """-> "kitty" if this terminal speaks the graphics protocol, else None.

    Read from the environment, which is what these terminals set for exactly
    this purpose. A runtime probe would be more certain, but it means writing
    an escape and reading the reply, and doing that inside a curses session
    risks the answer landing in the key queue and being acted on as input.
    """
    env = os.environ if env is None else env
    if env.get("PORTLIST_NO_GRAPHICS"):
        return None
    if env.get("KITTY_WINDOW_ID") or "kitty" in (env.get("TERM") or ""):
        return "kitty"
    # Ghostty and WezTerm implement kitty's protocol. Konsole announces itself
    # only through TERM, which the branch above already covers.
    if (env.get("TERM_PROGRAM") or "").lower() in ("ghostty", "wezterm"):
        return "kitty"
    return None


def available(env=None):
    return protocol(env) is not None


def _escape(payload):
    return b"\x1b_G" + payload + b"\x1b\\"


def transmit(path, cols, rows, env=None):
    """-> the bytes that put `path` behind the text, or b"" if unsupported.

    The file is sent as-is: the protocol decodes PNG itself, so nothing here
    needs to understand the format a second time.
    """
    if not available(env):
        return b""
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return b""
    if not raw[:8] == b"\x89PNG\r\n\x1a\n":
        return b""
    data = base64.standard_b64encode(raw)
    # a=T transmit and display, f=100 the payload is a PNG, t=d it is in this
    # escape rather than in a file the terminal should open, c/r the cell box
    # to fit it into, z=-1 behind the text, q=2 answer nothing back.
    head = (b"a=T,f=100,t=d,i=%d,c=%d,r=%d,z=-1,q=2"
            % (IMAGE_ID, max(1, cols), max(1, rows)))
    out = []
    chunks = [data[i:i + CHUNK] for i in range(0, len(data), CHUNK)] or [b""]
    for n, chunk in enumerate(chunks):
        more = b"1" if n < len(chunks) - 1 else b"0"
        prefix = head if n == 0 else b"q=2,i=%d" % IMAGE_ID
        out.append(_escape(prefix + b",m=" + more + b";" + chunk))
    return b"".join(out)


def place(cols, rows, env=None):
    """-> bytes that redraw the already-sent image, without resending it."""
    if not available(env):
        return b""
    return _escape(b"a=p,i=%d,c=%d,r=%d,z=-1,q=2"
                   % (IMAGE_ID, max(1, cols), max(1, rows)))


def clear(env=None):
    """-> bytes that remove it. Leaving a picture behind on exit is rude."""
    if not available(env):
        return b""
    return _escape(b"a=d,d=i,i=%d,q=2" % IMAGE_ID)


def describe(env=None):
    """One line for the UI about what this terminal can and cannot do."""
    if available(env):
        return "this terminal can show the picture itself"
    name = (os.environ if env is None else env).get("TERM_PROGRAM") or \
           (os.environ if env is None else env).get("TERM") or "this terminal"
    return "%s draws characters, not pictures, so the picture is drawn as characters" % name
