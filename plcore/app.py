"""The command line. `portlist`, or `python3 -m plcore`.

The CLI lives in the package rather than in the top-level script so that a
packaged install (pipx, Homebrew, pip) has a real entry point to point at, while
`python3 portlist.py` keeps working from a clone.
"""
import argparse
import os
import sys

VERSION = "1.3"

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
  g                      inside vibe mode: the background picture. None, then
                         each PNG in ~/.portlist/backgrounds as the terminal's
                         own image and then as characters, then none again
  b                      inside vibe mode: how strongly a character background
                         shows, 0 to 100
  A                      inside vibe mode: whether the scene changes by itself
  V                      vibe mode: the ambient screen. Any key comes back, and
                         it drifts in on its own after 30 idle seconds
  W                      the living harbour in your browser (the same as
                         portlist --world, served from this session)
  r                      rescan now
  ?                      this list
  q                      quit
"""


COMMANDS = """\
commands
  portlist kill 3000     stop it, after showing what it is and who started it.
                         Stops a container, a Homebrew service or a launchd or
                         systemd job the right way, and checks it stayed stopped
  portlist cleanup       walk through what looks left over, with the evidence,
                         and stop what you say yes to
  portlist report        this machine's listeners as one HTML file to hand on
                         (--redact for one leaving your team)
  each takes --help
"""


def _command(name, argv):
    if name == "kill":
        from . import stop
        return stop.kill_main(argv)
    if name == "cleanup":
        from . import stop
        return stop.cleanup_main(argv)
    from . import report
    return report.report_main(argv)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    if argv and argv[0] in ("kill", "cleanup", "report"):
        try:
            return _command(argv[0], argv[1:])
        except KeyboardInterrupt:
            return 1
    p = argparse.ArgumentParser(
        prog="portlist",
        description="Every port on this machine, and where it came from.",
        epilog=COMMANDS + "\n" + KEYS, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="portlist " + VERSION)
    p.add_argument("--data-dir", default=None,
                   help="where the launch ledger and use history live "
                        "(default: ~/.portlist)")
    p.add_argument("--keys", action="store_true", help="print the keys and exit")
    p.add_argument("--vibe-bg", metavar="PNG", default=None,
                   help="draw this picture behind the vibe scenes (PNG only). "
                        "Pass an empty string to clear it. Off until you set it, "
                        "and `b` inside vibe mode tunes how strongly it shows.")
    p.add_argument("--world", "-world", action="store_true",
                   help="open the living harbour: every port as a building, in a "
                        "browser, full screen, for a second screen. Loopback only, "
                        "served until ctrl-c. It only reads, unless you switch "
                        "stopping on in its Play panel")
    p.add_argument("--world-port", type=int, default=0, metavar="N",
                   help="port for --world on 127.0.0.1 (default: any free one)")
    p.add_argument("--no-open", action="store_true",
                   help="with --world: print the address, open nothing")
    p.add_argument("--windowed", action="store_true",
                   help="with --world: a normal browser tab rather than full screen")
    q = p.add_argument_group(
        "one answer, then exit",
        "Name what you mean and portlist explains it instead of opening the views:\n"
        "  portlist 3000            why is :3000 running, who started it, can the network reach it\n"
        "  portlist node            every listener whose service, command or project matches\n"
        "  portlist --list --json   everything listening, for a script\n"
        "Exit codes: 0 fine, 1 warnings, 2 nothing matched, 3 another user's process "
        "(run with sudo), 4 unusable question, 5 internal error.")
    q.add_argument("targets", nargs="*", metavar="PORT|NAME",
                   help="a port (3000 or :3000) or a name to explain")
    q.add_argument("-o", "--port", type=int, action="append", default=[], metavar="N",
                   help="a port to explain (repeatable)")
    q.add_argument("-p", "--pid", type=int, action="append", default=[], metavar="PID",
                   help="a process to explain, by pid (repeatable)")
    q.add_argument("-x", "--exact", action="store_true", help="names must match exactly")
    q.add_argument("-s", "--short", action="store_true", help="only the chain that started it, on one line")
    q.add_argument("-t", "--tree", action="store_true", help="the chain that started it, as a tree")
    q.add_argument("--warnings", action="store_true", help="only what deserves a look")
    q.add_argument("--json", action="store_true", help="the answer as JSON")
    q.add_argument("-l", "--list", action="store_true", help="print everything listening, once")
    q.add_argument("--exposed", action="store_true", help="with --list: only what is bound beyond loopback")
    q.add_argument("--leftovers", action="store_true", help="with --list: only what looks left over")
    q.add_argument("--attention", action="store_true", help="with --list: only medium, high and critical risk")
    q.add_argument("--no-color", action="store_true", help="plain text, no colour (NO_COLOR works too)")
    q.add_argument("--completion", choices=("bash", "zsh", "fish"), metavar="SHELL",
                   help="print a shell completion script: bash, zsh or fish")
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
    if args.completion:
        from . import explain
        sys.stdout.write(explain.completion(args.completion))
        return 0
    only = "exposed" if args.exposed else "leftovers" if args.leftovers else "attention" if args.attention else None
    if args.targets or args.port or args.pid or args.list or only or args.json:
        from . import explain
        ports, names = explain.parse_targets(args.targets)
        mode = "short" if args.short else "tree" if args.tree else "warnings" if args.warnings else "full"
        return explain.run(ports=ports + args.port, pids=args.pid, names=names, exact=args.exact,
                           mode=mode, as_json=args.json, no_color=args.no_color,
                           list_mode=args.list or bool(only) or not (ports or names or args.port or args.pid),
                           only=only)
    if args.world:
        from . import worldserve
        return worldserve.run(port=args.world_port, open_it=not args.no_open,
                              fullscreen=not args.windowed)

    try:
        from . import tui
    except ImportError as e:
        print("portlist needs curses, which this Python build does not have: %s" % e,
              file=sys.stderr)
        return 2
    return tui.main()


if __name__ == "__main__":
    sys.exit(main())
