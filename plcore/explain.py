"""One-shot answers: `portlist 3000`, `portlist node`, `portlist --pid 812`.

The terminal views answer "what is listening". This answers the question you
have when you already know which one you mean: why is it running, who started
it, can the network reach it, and should you worry. It reads the same scan the
views read and adds nothing to it, so an answer here never disagrees with the
table.

Output modes, all from one explanation:
  default       the full answer, one screen
  --short       the chain that started it, on one line
  --tree        the chain as a tree, with what the process started in turn
  --warnings    only what deserves a look
  --json        all of it, for scripts and agents

Exit codes, so a script can act on the answer:
  0  found, nothing to warn about
  1  found, with warnings
  2  nothing matched
  3  found, but owned by another user, so the details are hidden
  4  the question itself was not usable (a port out of range, no target)
  5  something inside portlist failed
"""
import json
import os
import re
import sys
import time

EXIT_OK, EXIT_WARN, EXIT_NOTFOUND, EXIT_PERM, EXIT_INPUT, EXIT_INTERNAL = 0, 1, 2, 3, 4, 5

INJECTION_VARS = ("LD_PRELOAD", "LD_AUDIT", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
                  "DYLD_FRAMEWORK_PATH")
BIG_RSS = 1 << 30                 # 1 GiB resident
LONG_UP = 90 * 86400              # 90 days


# ------------------------------------------------------------------ small helpers
def _span(seconds):
    if seconds is None:
        return "?"
    s = int(max(0, seconds))
    if s < 60:
        return "%ds" % s
    if s < 3600:
        return "%dm" % (s // 60)
    if s < 86400:
        return "%dh %dm" % (s // 3600, s % 3600 // 60)
    return "%dd %dh" % (s // 86400, s % 86400 // 3600)


def _bytes(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "?"


class Paint:
    """ANSI colour when the output is a terminal and nobody asked for none."""

    def __init__(self, on):
        self.on = on

    def __call__(self, code, text):
        return "\033[%sm%s\033[0m" % (code, text) if self.on else text

    def dim(self, t): return self("2", t)
    def bold(self, t): return self("1", t)
    def red(self, t): return self("31", t)
    def amber(self, t): return self("33", t)
    def green(self, t): return self("32", t)
    def blue(self, t): return self("36", t)


def colour_wanted(no_color=False, stream=None):
    stream = stream or sys.stdout
    return not no_color and not os.environ.get("NO_COLOR") and hasattr(stream, "isatty") and stream.isatty()


# ------------------------------------------------------------------ finding what was meant
def find(rows, ports=(), pids=(), names=(), exact=False, include_system=True):
    """-> [(label, [rows])] in the order the targets were given. A target that
    matches nothing still appears, with an empty list, so the caller can say so."""
    live = [r for r in rows if include_system or not r.get("quiet")]
    out = []
    for p in ports:
        out.append(("port %s" % p, [r for r in live if r.get("port") == p]))
    for pid in pids:
        out.append(("pid %s" % pid, [r for r in live if r.get("pid") == pid]))
    for name in names:
        n = name.lower()
        def hit(r):
            fields = [r.get("service") or "", r.get("cmd") or "", (r.get("project") or {}).get("name") or ""]
            if exact:
                return any(f.lower() == n for f in fields)
            return any(n in f.lower() for f in fields + [r.get("cmdline") or ""])
        out.append(("name %s" % name, [r for r in live if hit(r)]))
    return out


# ------------------------------------------------------------------ the facts
def _rss(pid):
    if pid is None:
        return None
    try:
        from . import collect
        out = collect.run(["ps", "-o", "rss=", "-p", str(pid)], timeout=3).strip()
        return int(out.split()[0]) * 1024 if out else None
    except Exception:
        return None


def _restarts(port, service, now):
    """Opens of this port by this same service in the last day, from the history.
    Another program that once used the port is not this one restarting."""
    try:
        from . import history
        return sum(1 for h in history.recent(2000)
                   if h.get("port") == port and h.get("type") == "opened" and now - (h.get("ts") or 0) < 86400
                   and (not service or h.get("service") == service))
    except Exception:
        return 0


def warnings(row, det, now=None, rss=None, restarts=0):
    """-> [str]: what deserves a look, each a measured fact. Unknown origin is
    not on this list: unknown is not the same as dangerous."""
    now = now or time.time()
    w = []
    exp = row.get("exposure") or {}
    ver = exp.get("verified") or {}
    if ver.get("accepting"):
        w.append("reachable from beyond this machine: portlist connected on %s (%s) and got in"
                 % (ver.get("ip", "?"), ver.get("iface", "?")))
    elif exp.get("level") not in (None, "loopback"):
        w.append("bound beyond loopback (%s), not verified reachable" % ", ".join(exp.get("addrs") or ["?"]))
    if row.get("risk_band") in ("High", "Critical"):
        why = "; ".join(x.get("label", "") for x in (row.get("reasons") or [])[:3])
        w.append("risk %s %s%s" % (row.get("risk"), row.get("risk_band"), (": " + why) if why else ""))
    if (row.get("user") or "") == "root":
        w.append("running as root")
    exe = row.get("exe") or ""
    if exe and exe.startswith("/") and not os.path.exists(exe):
        w.append("its executable is no longer on disk (%s), deleted or replaced since it started" % exe)
    env = set((det or {}).get("environ_names") or [])
    inj = [v for v in INJECTION_VARS if v in env]
    if inj:
        w.append("a library injection variable is set: %s" % ", ".join(inj))
    lo = row.get("leftover") or {}
    if lo.get("likely"):
        w.append("looks left over: %s" % "; ".join((lo.get("reasons") or [])[:2]))
    st = row.get("starter") or {}
    if st.get("ai") and st.get("alive") is False:
        w.append("%s started it and has since exited" % (st.get("name") or "the agent"))
    if (row.get("uptime") or 0) > LONG_UP:
        w.append("running for %s" % _span(row.get("uptime")))
    if rss and rss > BIG_RSS:
        w.append("using %s of memory" % _bytes(rss))
    if restarts >= 3:
        w.append("started %d times in the last day on this port" % restarts)
    return w


def _chain(det, row):
    up = list(((det or {}).get("tree") or {}).get("ancestry") or [])
    if not up or up[-1].get("pid") != row.get("pid"):
        up.append({"pid": row.get("pid"), "name": row.get("cmd") or "?", "cmdline": row.get("cmdline") or ""})
    return [{"pid": a.get("pid"), "name": a.get("name") or "?"} for a in up]


def explain(row, det=None, now=None):
    """-> one JSON-able answer for one listener."""
    now = now or time.time()
    det = det or {}
    st = row.get("starter") or {}
    exp = row.get("exposure") or {}
    act = row.get("activity") or {}
    proj = row.get("project") or {}
    rss = _rss(row.get("pid"))
    rst = _restarts(row.get("port"), row.get("service"), now)
    chain = _chain(det, row)
    kids = [{"pid": c.get("pid"), "name": c.get("name") or "?"}
            for c in (((det.get("tree") or {}).get("children")) or [])[:10]]
    return {
        "port": row.get("port"), "pid": row.get("pid"), "user": row.get("user"),
        "service": row.get("service") or row.get("cmd") or "?", "category": row.get("service_cat"),
        "command": row.get("cmd"), "cmdline": row.get("cmdline"),
        "project": {"name": proj.get("name"), "path": proj.get("short") or row.get("dir_short")} if proj or row.get("dir_short") else None,
        "started": {"ago_seconds": row.get("uptime"), "by": st.get("name"), "class": st.get("class"),
                    "ai": bool(st.get("ai")), "still_running": st.get("alive"), "evidence": st.get("evidence")},
        "chain": chain, "children": kids,
        "origin": (det.get("provenance") or {}).get("summary"),
        "reachable": {"level": exp.get("level"), "label": exp.get("label"), "addrs": exp.get("addrs") or [],
                      "verified": bool((exp.get("verified") or {}).get("accepting"))},
        "use": {"connections": row.get("conns") or 0, "from_outside": row.get("conns_public") or 0,
                "idle_seconds": act.get("idle_seconds"), "ever_used": act.get("ever_busy"), "watched_seconds": act.get("watched_for")},
        "risk": {"score": row.get("risk"), "band": row.get("risk_band"),
                 "reasons": [x.get("label") for x in (row.get("reasons") or [])]},
        "memory_bytes": rss, "opens_last_day": rst,
        "warnings": warnings(row, det, now, rss=rss, restarts=rst),
        "stop": ("kill %s" % row.get("pid")) if row.get("pid") is not None else None,
        "system": bool(row.get("quiet")),
    }


# ------------------------------------------------------------------ rendering
def _chain_text(e, c):
    parts = ["%s (pid %s)" % (a["name"], a["pid"]) for a in e["chain"]]
    if parts:
        parts[-1] = c.bold(parts[-1])
    return " → ".join(parts) or "?"


def render_full(e, c):
    L = []
    kv = lambda k, v: L.append("%-12s %s" % (c.dim(k) if c.on else k, v))
    kv("Target", c.bold(":%s" % e["port"]))
    who = []
    if e["command"]:
        who.append(e["command"])
    who.append("pid %s" % e["pid"] if e["pid"] is not None else "pid hidden")
    if e["user"]:
        who.append("user %s" % e["user"])
    kv("Service", "%s  %s" % (c.bold(e["service"]), c.dim("(" + ", ".join(who) + ")")))
    if e["cmdline"]:
        kv("Command", e["cmdline"][:160])
    if e["project"]:
        kv("Project", "%s  %s" % (e["project"].get("name") or "", c.dim(e["project"].get("path") or "")))
    s = e["started"]
    by = s.get("by") or "nobody on record"
    if s.get("still_running") is False:
        by += c.amber(" (exited)")
    kv("Started", "%s ago by %s" % (_span(s.get("ago_seconds")), by))
    kv("Why it runs", _chain_text(e, c))
    if e["origin"]:
        kv("Origin", e["origin"])
    r = e["reachable"]
    reach = r["label"] or r["level"] or "?"
    reach = c.red(reach) if r["verified"] else (c.amber(reach) if r["level"] not in (None, "loopback") else c.green(reach))
    kv("Reachable", "%s  %s" % (reach, c.dim(", ".join(r["addrs"]))))
    u = e["use"]
    use = "%d connection%s now" % (u["connections"], "" if u["connections"] == 1 else "s")
    if u.get("idle_seconds") is not None:
        use += ", last used %s ago" % _span(u["idle_seconds"])
    elif u.get("ever_used") is False and u.get("watched_seconds"):
        use += ", never seen in use in %s of watching" % _span(u["watched_seconds"])
    kv("In use", use)
    if e["memory_bytes"]:
        kv("Memory", _bytes(e["memory_bytes"]))
    band = e["risk"]["band"] or ""
    rtxt = "%s %s" % (e["risk"]["score"], band)
    kv("Risk", c.red(rtxt) if band in ("High", "Critical") else c.amber(rtxt) if band == "Medium" else rtxt)
    if e["warnings"]:
        kv("Warnings", c.amber(e["warnings"][0]))
        for w in e["warnings"][1:]:
            L.append("%-12s %s" % ("", c.amber(w)))
    else:
        kv("Warnings", c.green("none"))
    if e["stop"]:
        kv("To stop it", "%s  %s" % (e["stop"], c.dim("(portlist prints it; you run it)")))
    return "\n".join(L)


def render_short(e, c):
    return "%s  %s" % (_chain_text(e, c), c.dim("[:%s %s]" % (e["port"], e["service"])))


def render_tree(e, c):
    L = []
    for i, a in enumerate(e["chain"]):
        label = "%s (pid %s)" % (a["name"], a["pid"])
        last = i == len(e["chain"]) - 1
        if last:
            label = c.bold(label) + c.dim("   :%s %s" % (e["port"], e["service"]))
        L.append(("  " * i) + ("└─ " if i else "") + label)
    depth = len(e["chain"])
    for j, k in enumerate(e["children"]):
        L.append(("  " * depth) + ("└─ " if j == len(e["children"]) - 1 else "├─ ") + "%s (pid %s)" % (k["name"], k["pid"]))
    return "\n".join(L)


def render_warnings(e, c):
    if not e["warnings"]:
        return ":%s %s  %s" % (e["port"], e["service"], c.green("no warnings"))
    return "\n".join(":%s %s  %s" % (e["port"], e["service"], c.amber(w)) for w in e["warnings"])


def list_row(r):
    st = r.get("starter") or {}
    exp = r.get("exposure") or {}
    return {"port": r.get("port"), "pid": r.get("pid"), "service": r.get("service") or r.get("cmd") or "?",
            "project": (r.get("project") or {}).get("name"), "reachable": exp.get("label"),
            "exposure": exp.get("level"), "verified": bool((exp.get("verified") or {}).get("accepting")),
            "risk": r.get("risk"), "risk_band": r.get("risk_band"), "started_by": st.get("name"),
            "starter_exited": st.get("alive") is False, "uptime_seconds": r.get("uptime"),
            "leftover": bool((r.get("leftover") or {}).get("likely")), "system": bool(r.get("quiet"))}


def render_list(items, c):
    head = "%-7s %-24s %-18s %-16s %-10s %s" % ("PORT", "SERVICE", "PROJECT", "REACHABLE", "RISK", "STARTED BY")
    L = [c.bold(head)]
    for x in items:
        reach = (x["reachable"] or "?")[:16]
        reach_c = c.red(reach.ljust(16)) if x["verified"] else c.amber(reach.ljust(16)) if x["exposure"] not in (None, "loopback") else reach.ljust(16)
        by = (x["started_by"] or "-") + (" (exited)" if x["starter_exited"] else "")
        L.append("%-7s %-24s %-18s %s %-10s %s" % (":%s" % x["port"], (x["service"] or "")[:24], (x["project"] or "-")[:18],
                                                  reach_c, ("%s %s" % (x["risk"], x["risk_band"] or ""))[:10], by))
    return "\n".join(L)


# ------------------------------------------------------------------ the command
def run(ports=(), pids=(), names=(), exact=False, mode="full", as_json=False, no_color=False,
        list_mode=False, only=None, out=None, err=None, scan_fn=None, detail_fn=None):
    """-> exit code. `scan_fn` and `detail_fn` are for tests."""
    out = out or sys.stdout
    err = err or sys.stderr
    c = Paint(colour_wanted(no_color, out) and not as_json)
    for p in ports:
        if not (0 < p < 65536):
            print("portlist: %s is not a port (1-65535)" % p, file=err)
            return EXIT_INPUT
    try:
        if scan_fn is None or detail_fn is None:
            from . import scan as scan_mod
            scan_fn = scan_fn or (lambda: scan_mod.scan())
            detail_fn = detail_fn or scan_mod.detail
        rows, _host = scan_fn()
    except Exception as e:                                     # pragma: no cover - reported, not raised
        print("portlist: the scan failed: %s" % e, file=err)
        return EXIT_INTERNAL

    if list_mode:
        pick = {"exposed": lambda r: (r.get("exposure") or {}).get("level") not in (None, "loopback"),
                "leftovers": lambda r: (r.get("leftover") or {}).get("likely"),
                "attention": lambda r: r.get("risk_band") in ("Medium", "High", "Critical")}.get(only)
        sel = [r for r in rows if not r.get("quiet") and (pick is None or pick(r))]
        sel.sort(key=lambda r: r.get("port") or 0)
        items = [list_row(r) for r in sel]
        if as_json:
            json.dump(items, out, indent=2, default=str)
            out.write("\n")
        else:
            print(render_list(items, c) if items else "nothing %s" % ({"exposed": "reachable beyond loopback",
                  "leftovers": "looks left over", "attention": "needs attention"}.get(only, "is listening")), file=out)
        return EXIT_OK

    groups = find(rows, ports, pids, names, exact)
    if not groups:
        print("portlist: name a port, a pid or a name, e.g. `portlist 3000`", file=err)
        return EXIT_INPUT
    answers, code, missing, hidden = [], EXIT_OK, 0, 0
    for label, hits in groups:
        if not hits:
            missing += 1
            answers.append((label, None))
            continue
        for r in hits:
            try:
                e = explain(r, detail_fn(r))
            except Exception as ex:                          # pragma: no cover
                print("portlist: could not explain %s: %s" % (label, ex), file=err)
                return EXIT_INTERNAL
            if e["pid"] is None:
                hidden += 1
            if e["warnings"]:
                code = EXIT_WARN
            answers.append((label, e))
    if as_json:
        for label, e in answers:
            if e is None:
                print("portlist: nothing is listening that matches %s" % label, file=err)
        found = [e for _, e in answers if e]
        json.dump(found[0] if len(found) == 1 and len(groups) == 1 else found, out, indent=2, default=str)
        out.write("\n")
    else:
        many = len(answers) > 1
        for i, (label, e) in enumerate(answers):
            if many:
                print(c.dim("----- [%s] -----" % label), file=out)
            if e is None:
                print("nothing is listening that matches %s" % label, file=out)
            else:
                print({"short": render_short, "tree": render_tree, "warnings": render_warnings}.get(mode, render_full)(e, c), file=out)
            if many and i < len(answers) - 1:
                print("", file=out)
        if hidden:
            print(c.dim("\nsome details belong to another user's process; run with sudo to see them"), file=err)
    if missing and missing == len(answers):
        return EXIT_NOTFOUND
    if hidden and code == EXIT_OK:
        return EXIT_PERM
    return code


# ------------------------------------------------------------------ shell completions
FLAGS = ["--port", "--pid", "--json", "--short", "--tree", "--warnings", "--exact", "--list",
         "--exposed", "--leftovers", "--attention", "--no-color", "--world", "--world-port",
         "--no-open", "--windowed", "--keys", "--data-dir", "--vibe-bg", "--completion", "--version", "--help"]


def completion(shell):
    words = " ".join(FLAGS)
    if shell == "bash":
        return ("# portlist completion for bash: add to ~/.bashrc\n"
                "#   eval \"$(portlist --completion bash)\"\n"
                "_portlist() {\n"
                "  local cur=\"${COMP_WORDS[COMP_CWORD]}\"\n"
                "  if [[ \"$cur\" == -* ]]; then COMPREPLY=( $(compgen -W \"%s\" -- \"$cur\") ); fi\n"
                "}\n"
                "complete -F _portlist portlist\n") % words
    if shell == "zsh":
        opts = "\n".join("  '%s[%s]'" % (f, f.strip("-").replace("-", " ")) for f in FLAGS)
        return ("#compdef portlist\n# portlist completion for zsh: add to ~/.zshrc\n"
                "#   eval \"$(portlist --completion zsh)\"\n"
                "_portlist() {\n  _arguments \\\n%s\n}\ncompdef _portlist portlist\n") % " \\\n".join(opts.splitlines())
    if shell == "fish":
        return ("# portlist completion for fish: portlist --completion fish > ~/.config/fish/completions/portlist.fish\n"
                + "\n".join("complete -c portlist -l %s" % f.lstrip("-") for f in FLAGS) + "\n")
    raise ValueError("unknown shell %r (bash, zsh or fish)" % shell)


def parse_targets(targets):
    """Positional targets: a number is a port, ':3000' is a port, anything else a name."""
    ports, names = [], []
    for t in targets:
        m = re.fullmatch(r":?(\d+)", t)
        if m:
            ports.append(int(m.group(1)))
        else:
            names.append(t)
    return ports, names
