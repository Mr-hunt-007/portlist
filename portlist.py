#!/usr/bin/env python3
"""portlist - every port on this machine, and where it came from.

A terminal program. There is no web UI, no dashboard and no server: it draws a
full screen, reads the machine, and gets out of the way. Standard library only,
no dependencies, and it opens no listening socket of its own - a tool for
watching what is listening should not add to the list.

    portlist                what is listening, and who started it
    portlist --version
    portlist --help

This file is the clone-and-run entry point; the CLI itself is `plcore/app.py`,
so that a packaged install has something to point at.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from plcore.app import main          # noqa: E402  (after the path insert)

if __name__ == "__main__":
    sys.exit(main())
