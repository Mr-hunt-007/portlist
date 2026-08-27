"""The command line. `portlist`, or `python3 -m plcore`.

The CLI lives in the package rather than in the top-level script so that a
packaged install (pipx, Homebrew, pip) has a real entry point to point at, while
`python3 portlist.py` keeps working from a clone.
"""
import argparse
import os
import sys

VERSION = "1.1"

KEYS = """\
views
  0  dashboard           everything at once: machine, exposure, agents, the
                         listening table, the selected service and the activity
  1  services            everything listening, with who started it
  2  exposed             reachable from beyond this machine
  3  attention           critical, high and medium risk
  4  leftovers           looks abandoned, with the measurements behind the guess
  5  agents              grouped by the agent, editor or terminal that started it
  6  containers          by compose project, and the host ports they hold
  7  sessions            coding-agent sessions, what they were about, context used
  8  system              this machine: load, memory, disks, network, exposure
  9  graph               who started what, where it runs, what it exposes

keys
  j / k, arrows          move, inside whichever section has focus
  tab, shift-tab         the next view, the same order as the number keys
  h / l, left, right     move between the dashboard's panes
  enter, o               detail pane
  O                      open the port in a browser (shift+enter and ctrl+enter
                         too, where the terminal sends them)
  /                      search
  f                      a port that is free now and not spoken for later
  a                      animation on the system view, off for good if you like
  b                      inside vibe mode: how strongly the background shows
  V                      vibe mode: the ambient screen. Any key comes back, and
                         it drifts in on its own after 30 idle seconds
  r                      rescan now
  ?                      this list
  q                      quit
"""


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="portlist",
        description="Every port on this machine, and where it came from.",
        epilog=KEYS, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="portlist " + VERSION)
    p.add_argument("--data-dir", default=None,
                   help="where the launch ledger and use history live "
                        "(default: ~/.portlist)")
    p.add_argument("--keys", action="store_true", help="print the keys and exit")
    p.add_argument("--vibe-bg", metavar="PNG", default=None,
                   help="draw this picture behind the vibe scenes (PNG only). "
                        "Pass an empty string to clear it. Off until you set it, "
                        "and `b` inside vibe mode tunes how strongly it shows.")
    args = p.parse_args(argv)

    if args.keys:
        print(KEYS)
        return 0
    if args.vibe_bg is not None:
        from . import imgmap, vibe
        path = os.path.abspath(os.path.expanduser(args.vibe_bg)) if args.vibe_bg else ""
        if path:
            try:
                imgmap.load(path)                 # fail here, not three screens later
            except imgmap.Unsupported as e:
                print("cannot use that picture: %s" % e, file=sys.stderr)
                return 2
            except OSError as e:
                print("cannot read %s: %s" % (path, e.strerror or "unreadable"),
                      file=sys.stderr)
                return 2
        cfg = vibe.load()
        cfg["bg"] = path
        if path and not cfg.get("bg_opacity"):
            cfg["bg_opacity"] = 30                # a visible starting point
        vibe.save(cfg)
        print("vibe background: %s" % (imgmap.describe(path) if path else "cleared"))
        if path:
            print("showing at %d%%. Press b inside vibe mode to change it." % cfg["bg_opacity"])
        return 0
    if args.data_dir:
        os.environ["PORTLIST_DATA"] = args.data_dir

    try:
        from . import tui
    except ImportError as e:
        print("portlist needs curses, which this Python build does not have: %s" % e,
              file=sys.stderr)
        return 2
    return tui.main()


if __name__ == "__main__":
    sys.exit(main())
