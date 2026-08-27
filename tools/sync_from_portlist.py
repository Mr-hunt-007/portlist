#!/usr/bin/env python3
"""Regenerate Portboard's copies of the shared terminal files from portlist's.

`tui.py` and `vibe.py` are one source of truth living in two trees. Hand-editing
both is how the splash screen in portlist ended up spelling PORTBOARD, so the
copy is generated and the differences are declared here, in one table, rather
than remembered.

    python3 tools/sync_from_portlist.py [--check]
"""
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BOARD = os.path.join(os.path.dirname(HERE), "portboard")

# portlist text -> portboard text. Every difference between the two copies.
SUBS = [
    ("This file is shared with `portboard`, the project this is a standalone copy of.\n"
     "Keep it free of anything that assumes the web server exists.",
     "This file is shared with `portlist`, a standalone copy of just this view. Keep it\n"
     "free of anything that assumes the web server exists."),
    ('"PORTLIST", C_HEAD, True', '"PORTBOARD", C_HEAD, True'),
    ('["PORTLIST"]', '["PORTBOARD"]'),
    ('"P O R T L I S T" if w >= 40 else "PORTLIST"',
     '"P O R T B O A R D" if w >= 44 else "PORTBOARD"'),
    ("`V`, or by itself after thirty seconds of no keys.",
     "`V`, or by itself after thirty seconds of no keys."),
    ("portlist", "portboard"),
    ("Portlist", "Portboard"),
]

ART = ('''SPLASH = [
    r"  ___    __    ___   ____         _   ___   ____ ",
    r" | _ \\  /  \\  | _ \\ |_  _| | |   | | / __| |_  _|",
    r" |  _/ | () | |   /   | |  | |_  | | \\__ \\   | | ",
    r" |_|    \\__/  |_|_\\   |_|  |___| |_| |___/   |_| ",
    r"",
    r"      every port, and where it came from          ",
]''', '''SPLASH = [
    r"  ___   __  ___  ____  ____  ___    __    __   ___  ___   ",
    r" | _ \\ /  \\| _ \\|_  _||  _ \\/ _ \\  /  \\  |  \\ | _ \\| _ \\  ",
    r" |  _/| () |   / | |  | _ <| (_) || () | | | )|   /| |) | ",
    r" |_|   \\__/|_|\\_\\|_|  |____/\\___/  \\__/  |__/ |_|\\_\\|___/ ",
    r"",
    r"        every port, and where it came from                 ",
]''')


def convert(text):
    if ART[0] in text:
        text = text.replace(ART[0], ART[1], 1)
    for old, new in SUBS:
        text = text.replace(old, new)
    return text.replace("plcore", "pbcore")


def main():
    check = "--check" in sys.argv
    bad = 0
    for name in ("tui.py", "vibe.py"):
        src = os.path.join(HERE, "plcore", name)
        dst = os.path.join(BOARD, "pbcore", name)
        want = convert(open(src).read())
        have = open(dst).read() if os.path.exists(dst) else None
        if want == have:
            print("  %-8s already in sync" % name)
            continue
        if check:
            print("  %-8s OUT OF SYNC" % name); bad += 1
            continue
        open(dst, "w").write(want)
        print("  %-8s written (%d bytes)" % (name, len(want)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
