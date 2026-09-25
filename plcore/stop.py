"""`portlist kill` and `portlist cleanup`: stop a listener, the right way, after
showing you what it is.

`kill -9 $(lsof -ti :3000)` stops a process. It does not tell you that the
process was Postgres in a container (stop the container, or Docker starts it
again), that launchd owns it (it will be back in a second), or that it was the
file server a Claude Code session left open to your network five days ago. This
does, before it asks.

What it will not do:
  - stop anything without a yes, unless you pass --yes
  - stop something a fresh scan does not show listening on that port right now
  - stop pid 0, pid 1, itself, or a service portlist files as part of the system
  - guess: a supervisor is named only when it was measured (a systemd unit in
    the process's cgroup, a launchd job holding that pid, PM2 in its ancestry,
    a container publishing the port)

After a stop it looks again: if the port is held by a new process a moment
later, something restarted it, and you are told what to stop instead.

Exit codes:
  0  every target stopped (or, with --dry-run, would be)
  1  something was kept, declined, still running, or came back
  2  nothing matched
  3  another user's process: run with sudo
  4  the question itself was unusable
"""
import json
import os
import re
import signal
import subprocess
import sys
import time

from . import explain as ex

EXIT_OK, EXIT_KEPT, EXIT_NOTFOUND, EXIT_PERM, EXIT_INPUT = 0, 1, 2, 3, 4
SIGKILL = getattr(signal, "SIGKILL", signal.SIGTERM)       # Windows has no SIGKILL
WAIT = 5.0              # seconds a SIGTERM gets before we say it did not work


# ------------------------------------------------------------------ who else owns it
def _cgroup_unit(pid):
    """-> ("system"|"user", unit) from /proc/<pid>/cgroup, or None. Linux only."""
    try:
        with open("/proc/%d/cgroup" % pid) as f:
            text = f.read()
    except (OSError, TypeError):
        return None
    for line in text.splitlines():
        path = line.split(":", 2)[-1]
        units = re.findall(r"([A-Za-z0-9@_.\\-]+\.service)", path)
        if not units:
            continue
        unit = units[-1]
        if unit.startswith("user@"):            # the user manager itself, not a unit in it
            continue
        return ("user" if "user@" in path else "system"), unit
    return None


def _launchd_label(pid):
    """-> the launchd job label running this pid, or None. macOS only, and only
    the caller's own domain: `launchctl list` prints PID, status, label."""
    if sys.platform != "darwin" or pid is None:
        return None
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    for line in out.splitlines()[1:]:
        parts = line.split(None, 2)
        if len(parts) == 3 and parts[0] == str(pid):
            return parts[2].strip()
    return None


def supervisor(row, chain=None, probe=True):
    """-> how this listener should be stopped, from what was measured.

    {kind, name, command, runnable, note}. `command` is the right stop; if it
    is `runnable` portlist can run it for you after a yes, otherwise it is
    printed for you to run.
    """
    c = row.get("container") or {}
    if c.get("name"):
        return {"kind": "container", "name": c["name"],
                "command": ["docker", "stop", c["name"]], "runnable": True,
                "note": "published by container %s: stopping the process behind the port "
                        "would only stop the engine's proxy" % c["name"]}
    pid = row.get("pid")
    names = " ".join((a.get("name") or "") for a in (chain or []))
    if re.search(r"(?i)\bPM2\b|God Daemon", names):
        return {"kind": "pm2", "name": "PM2", "command": None, "runnable": False,
                "note": "PM2 restarts what it manages. Stop it there: `pm2 list`, then "
                        "`pm2 stop <name>`"}
    if probe:
        unit = _cgroup_unit(pid)
        if unit:
            scope, name = unit
            cmd = ["systemctl"] + (["--user"] if scope == "user" else []) + ["stop", name]
            return {"kind": "systemd", "name": name, "command": cmd,
                    "runnable": scope == "user" or os.geteuid() == 0,
                    "note": "systemd unit %s runs it, and a unit can restart what it runs" % name}
        label = _launchd_label(pid)
        if label:
            m = re.match(r"homebrew\.mxcl\.(.+)$", label)
            if m:
                return {"kind": "brew", "name": m.group(1),
                        "command": ["brew", "services", "stop", m.group(1)], "runnable": True,
                        "note": "Homebrew runs it as a service (%s); launchd would start it again" % label}
            return {"kind": "launchd", "name": label,
                    "command": ["launchctl", "bootout", "gui/%d/%s" % (os.getuid(), label)], "runnable": True,
                    "note": "launchd job %s runs it, and launchd restarts jobs that exit" % label}
    return None


# ------------------------------------------------------------------ the stop itself
def _alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def signal_listener(pid, port, force=False, scan_fn=None, kill_fn=None):
    """Signal a process, but only one a fresh scan shows listening on `port` right
    now. -> (status, message, row). Status: ok, gone, refused, stale, denied.
    The harbour's stop button and the command line share this."""
    kill_fn = kill_fn or os.kill
    if pid in (0, 1, None) or pid in (os.getpid(), os.getppid()):
        return "refused", "refusing to signal that process", None
    if scan_fn is None:
        from . import scan
        scan_fn = lambda: scan.scan(force=True)
    rows, _ = scan_fn()
    row = next((r for r in rows if r.get("pid") == pid and r.get("port") == port), None)
    if not row:
        return "stale", "pid %d is not listening on :%d any more" % (pid, port), None
    try:
        kill_fn(pid, SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        return "gone", "process already gone", row
    except PermissionError:
        return "denied", "not permitted: the process belongs to another user", row
    return "ok", "signalled", row


class Stopper:
    """Everything a stop needs, injectable so it can be tested without killing."""

    def __init__(self, out=None, err=None, ask=None, yes=False, force=False, dry_run=False,
                 no_color=False, scan_fn=None, detail_fn=None, kill_fn=None, alive_fn=None,
                 run_fn=None, sleep=None, probe=True, interactive=None):
        self.out, self.err = out or sys.stdout, err or sys.stderr
        self.c = ex.Paint(ex.colour_wanted(no_color, self.out))
        self.yes, self.force, self.dry = yes, force, dry_run
        if scan_fn is None or detail_fn is None:
            from . import scan as scan_mod
            scan_fn = scan_fn or (lambda force=False: scan_mod.scan(force=force))
            detail_fn = detail_fn or scan_mod.detail
        self.scan, self.detail = scan_fn, detail_fn
        self.kill = kill_fn or os.kill
        self.alive = alive_fn or _alive
        self.run = run_fn or (lambda cmd: subprocess.run(cmd, capture_output=True, text=True, timeout=60))
        self.sleep = sleep or time.sleep
        self.probe = probe
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self._ask = ask or (lambda q: input(q))

    def say(self, text=""):
        print(text, file=self.out)

    def ask(self, question, choices="yN"):
        """-> the lower-case first letter of the answer; the capital in `choices`
        is what an empty answer means."""
        default = next((ch.lower() for ch in choices if ch.isupper()), "n")
        try:
            a = self._ask("%s [%s] " % (question, "/".join(choices))).strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.say()
            return "q"
        return (a[:1] or default) if (a[:1] or default) in choices.lower() else default

    # -- what is it ----------------------------------------------------------
    def card(self, row, det, lead=""):
        """The facts a yes should rest on, and nothing else."""
        c = self.c
        e = ex.explain(row, det)
        chain = ex._chain_text(e, c)
        s = e["started"]
        who = s.get("by") or "nobody on record"
        if s.get("still_running") is False:
            who += c.amber(" (exited)")
        u = e["use"]
        if u.get("idle_seconds") is not None:
            use = "last used %s ago" % ex._span(u["idle_seconds"]) if u["idle_seconds"] > 60 else "in use now"
        elif u.get("ever_used") is False and u.get("watched_seconds"):
            use = c.amber("never seen in use in %s of watching" % ex._span(u["watched_seconds"]))
        else:
            use = "%d connection%s now" % (u["connections"], "" if u["connections"] == 1 else "s")
        r = e["reachable"]
        reach = r["label"] or "?"
        reach = c.red(reach + ", verified from " + ", ".join(r["addrs"])) if r["verified"] else (
            c.amber(reach) if r["level"] not in (None, "loopback") else c.green(reach))
        L = ["%s%s  %s  %s" % (lead, c.bold(":%s" % e["port"]), c.bold(e["service"]),
                                c.dim("pid %s, %s" % (e["pid"], e["user"] or "?")))]
        kv = lambda k, v: L.append("   %-11s %s" % (c.dim(k) if c.on else k, v))
        if e["project"]:
            kv("project", "%s  %s" % (e["project"].get("name") or "", c.dim(e["project"].get("path") or "")))
        kv("started", "%s ago by %s" % (ex._span(s.get("ago_seconds")), who))
        kv("chain", chain)
        kv("reachable", reach)
        kv("use", use)
        lo = row.get("leftover") or {}
        for i, why in enumerate((lo.get("reasons") or [])[:3]):
            kv("left over" if i == 0 else "", why)
        risky = [w for w in e["warnings"] if not w.startswith(("looks left over", "reachable from beyond"))]
        for i, w in enumerate(risky[:3]):
            kv("warning" if i == 0 else "", c.amber(w))
        return e, L

    # -- stop one -------------------------------------------------------------
    def stop(self, row, det, confirm=True):
        """-> "stopped", "kept", "failed", "back" or "denied"."""
        c = self.c
        pid, port = row.get("pid"), row.get("port")
        chain = ((det or {}).get("tree") or {}).get("ancestry") or []
        sup = supervisor(row, chain, probe=self.probe)
        if sup:
            self.say("   %-11s %s" % (c.dim("stop with") if c.on else "stop with",
                                       (" ".join(sup["command"]) if sup["command"] else sup["kind"]) + "  " + c.dim("(" + sup["note"] + ")")))
        if pid is None:
            self.say(c.amber("   another user owns it: run `sudo portlist kill %s`" % port))
            return "denied"
        if row.get("quiet"):
            self.say(c.dim("   portlist files this under the system; it will not stop it"))
            return "kept"
        runnable = sup and sup["runnable"] and sup["command"]
        verb = " ".join(sup["command"]) if runnable else "SIGTERM to pid %s" % pid
        if self.dry:
            self.say(c.dim("   would run: %s" % verb))
            return "stopped"
        if confirm and not self.yes:
            if not self.interactive:
                self.say(c.amber("   not a terminal, so not asking: pass --yes to stop without a question"))
                return "kept"
            a = self.ask("   Stop it (%s)?" % verb)
            if a == "q":
                raise KeyboardInterrupt
            if a != "y":
                self.say(c.dim("   kept"))
                return "kept"
        if runnable:
            res = self.run(sup["command"])
            if getattr(res, "returncode", 1) != 0:
                self.say(c.red("   %s failed: %s" % (" ".join(sup["command"]),
                                                    ((res.stderr or res.stdout or "").strip().splitlines() or ["?"])[-1])))
                return "failed"
        else:
            status, msg, _ = signal_listener(pid, port, scan_fn=lambda: self.scan(force=True), kill_fn=self.kill)
            if status == "denied":
                self.say(c.amber("   %s: run `sudo portlist kill %s`" % (msg, port)))
                return "denied"
            if status in ("refused", "stale"):
                self.say(c.amber("   " + msg))
                return "failed"
            if status == "ok" and not self._gone(pid):
                if self.force or (self.interactive and not self.yes and
                                  self.ask("   Still running after %ds. Force it (SIGKILL)?" % WAIT) == "y"):
                    try:
                        self.kill(pid, SIGKILL)
                    except ProcessLookupError:
                        pass
                    if not self._gone(pid, 2.0):
                        self.say(c.red("   pid %s survived SIGKILL" % pid))
                        return "failed"
                else:
                    self.say(c.amber("   still running after %ds; `portlist kill %s --force` sends SIGKILL" % (WAIT, port)))
                    return "failed"
        return self._after(row, sup)

    def _gone(self, pid, wait=WAIT):
        t = 0.0
        while t < wait:
            if not self.alive(pid):
                return True
            self.sleep(0.2)
            t += 0.2
        return not self.alive(pid)

    def _after(self, row, sup):
        """Look again: stopped, or brought straight back by something."""
        c, port = self.c, row.get("port")
        self.sleep(0.8)
        rows, _ = self.scan(force=True)
        back = next((r for r in rows if r.get("port") == port and r.get("pid") != row.get("pid")), None)
        if back:
            who = (sup or {}).get("note") or "something restarted it"
            self.say(c.amber("   it came back as pid %s (%s)." % (back.get("pid"), back.get("service") or back.get("cmd"))))
            self.say(c.amber("   %s" % who) + (("; stop it with: " + " ".join(sup["command"])) if sup and sup.get("command") else ""))
            return "back"
        self.say(c.green("   stopped. :%s is free." % port))
        return "stopped"


# ------------------------------------------------------------------ portlist kill
def kill_main(argv, **kw):
    import argparse
    p = argparse.ArgumentParser(prog="portlist kill", description=(
        "Stop what is listening on a port, after showing what it is, who started it "
        "and whether the network can reach it. Stops a container, a Homebrew service "
        "or a launchd or systemd job the right way, and checks it did not come back."))
    p.add_argument("targets", nargs="+", metavar="PORT|NAME", help="a port (3000 or :3000) or a name")
    p.add_argument("-p", "--pid", action="store_true", help="the targets are pids, not ports")
    p.add_argument("-y", "--yes", action="store_true", help="do not ask")
    p.add_argument("-f", "--force", action="store_true", help="SIGKILL if SIGTERM has not worked in 5 seconds")
    p.add_argument("-n", "--dry-run", action="store_true", help="show what would be stopped, stop nothing")
    p.add_argument("-x", "--exact", action="store_true", help="names must match exactly")
    p.add_argument("--no-color", action="store_true", help="plain text")
    a = p.parse_args(argv)
    st = Stopper(yes=a.yes, force=a.force, dry_run=a.dry_run, no_color=a.no_color, **kw)
    if a.pid:
        if not all(t.isdigit() for t in a.targets):
            print("portlist kill: --pid wants numbers", file=st.err)
            return EXIT_INPUT
        ports, pids, names = [], [int(t) for t in a.targets], []
    else:
        ports, names = ex.parse_targets(a.targets)
        pids = []
    for port in ports:
        if not 0 < port < 65536:
            print("portlist kill: %s is not a port (1-65535)" % port, file=st.err)
            return EXIT_INPUT
    rows, _ = st.scan(force=True)
    groups = ex.find(rows, ports, pids, names, a.exact)
    results, missing = [], 0
    try:
        for label, hits in groups:
            if not hits:
                missing += 1
                st.say("nothing is listening that matches %s" % label)
                continue
            if len(hits) > 1 and names:
                st.say(st.c.dim("%s matches %d listeners; each is asked separately" % (label, len(hits))))
            seen = set()
            for r in hits:
                if (r.get("pid"), r.get("port")) in seen:
                    continue
                seen.add((r.get("pid"), r.get("port")))
                det = st.detail(r) if r.get("pid") is not None else {}
                _, lines = st.card(r, det)
                st.say("\n".join(lines))
                results.append(st.stop(r, det))
                st.say()
    except KeyboardInterrupt:
        st.say(st.c.dim("stopped asking"))
        return EXIT_KEPT
    if missing == len(groups):
        return EXIT_NOTFOUND
    if "denied" in results:
        return EXIT_PERM
    return EXIT_OK if results and all(x == "stopped" for x in results) and not missing else EXIT_KEPT


# ------------------------------------------------------------------ portlist cleanup
def candidates(rows, idle_hours=None):
    """-> listeners worth asking about, most worth asking first.

    The leftover guess (lifecycle.leftover) with its reasons, and with --idle,
    anything not seen in use for that long. Ignored ports and system services
    are never offered."""
    out = []
    for r in rows:
        if r.get("quiet"):
            continue
        lo = r.get("leftover") or {}
        if lo.get("ignored"):
            continue
        act = r.get("activity") or {}
        idle = act.get("idle_seconds")
        never = act.get("ever_busy") is False
        watched = act.get("watched_for") or 0
        stale = idle_hours is not None and ((idle is not None and idle >= idle_hours * 3600)
                                            or (never and watched >= idle_hours * 3600))
        if lo.get("likely") or stale:
            out.append(r)
    exposed = lambda r: (r.get("exposure") or {}).get("level") not in (None, "loopback")
    out.sort(key=lambda r: (not (r.get("exposure") or {}).get("verified"), not exposed(r),
                            -((r.get("activity") or {}).get("idle_seconds") or (r.get("uptime") or 0))))
    return out


def cleanup_main(argv, **kw):
    import argparse
    p = argparse.ArgumentParser(prog="portlist cleanup", description=(
        "Walk through what looks left over, one at a time, with the evidence, and "
        "stop what you say yes to. Nothing is stopped without a yes unless you pass --yes."))
    p.add_argument("--idle", type=float, metavar="HOURS", default=None,
                   help="also offer anything not seen in use for this many hours")
    p.add_argument("-y", "--yes", action="store_true", help="stop every candidate without asking")
    p.add_argument("-f", "--force", action="store_true", help="SIGKILL what ignores SIGTERM for 5 seconds")
    p.add_argument("-n", "--dry-run", action="store_true", help="list the candidates and the evidence, stop nothing")
    p.add_argument("--json", action="store_true", help="the candidates as JSON, stop nothing")
    p.add_argument("--no-color", action="store_true", help="plain text")
    a = p.parse_args(argv)
    st = Stopper(yes=a.yes, force=a.force, dry_run=a.dry_run or a.json, no_color=a.no_color or a.json, **kw)
    rows, _ = st.scan(force=True)
    cands = candidates(rows, a.idle)
    if a.json:
        items = []
        for r in cands:
            det = st.detail(r) if r.get("pid") is not None else {}
            e = ex.explain(r, det)
            sup = supervisor(r, ((det or {}).get("tree") or {}).get("ancestry") or [], probe=st.probe)
            e["leftover_reasons"] = (r.get("leftover") or {}).get("reasons") or []
            e["stop_with"] = " ".join(sup["command"]) if sup and sup.get("command") else e["stop"]
            items.append(e)
        json.dump(items, st.out, indent=2, default=str)
        st.out.write("\n")
        return EXIT_OK
    c = st.c
    if not cands:
        st.say(c.green("Nothing looks left over.") + c.dim(
            " (%d listening%s)" % (len([r for r in rows if not r.get("quiet")]),
                                   "" if a.idle else "; --idle 24 also offers anything unused for a day")))
        return EXIT_OK
    st.say(c.bold("%d listener%s look%s left over." % (len(cands), "" if len(cands) == 1 else "s",
                                                       "s" if len(cands) == 1 else ""))
           + c.dim(" Nothing is stopped unless you say y. " if not (a.yes or a.dry_run) else " ")
           + c.dim("y stop, n keep, k keep and stop asking about this port, a stop the rest, q quit"
                   if not (a.yes or a.dry_run) else ""))
    st.say()
    done = {"stopped": [], "kept": [], "ignored": [], "other": []}
    all_rest = False
    try:
        for i, r in enumerate(cands, 1):
            det = st.detail(r) if r.get("pid") is not None else {}
            _, lines = st.card(r, det, lead=c.dim("%d/%d  " % (i, len(cands))))
            st.say("\n".join(lines))
            if a.dry_run or a.yes or all_rest:
                res = st.stop(r, det, confirm=False)
            elif not st.interactive:
                st.say(c.amber("   not a terminal, so not asking: pass --yes, or --dry-run to only list"))
                return EXIT_KEPT
            else:
                ans = st.ask("   Stop it?", "yNkaq")
                if ans == "q":
                    raise KeyboardInterrupt
                if ans == "k":
                    from . import lifecycle
                    lifecycle.ignore(r.get("port"), r.get("cmd") or "", "kept from portlist cleanup")
                    st.say(c.dim("   kept; portlist will not call :%s a leftover again "
                                 "(undo: edit %s)" % (r.get("port"), lifecycle.ignore_path())))
                    done["ignored"].append(r.get("port"))
                    st.say()
                    continue
                if ans == "a":
                    all_rest = True
                res = st.stop(r, det, confirm=False) if ans in ("y", "a") else "kept"
                if res == "kept":
                    st.say(c.dim("   kept"))
            done["stopped" if res == "stopped" else "kept" if res == "kept" else "other"].append(r.get("port"))
            st.say()
    except KeyboardInterrupt:
        st.say(c.dim("stopped asking"))
    ports = lambda xs: " ".join(":%s" % x for x in xs)
    if a.dry_run:
        st.say(c.dim("dry run: nothing was stopped. `portlist cleanup` asks about each one."))
        return EXIT_OK
    bits = []
    if done["stopped"]:
        bits.append(c.green("stopped %d (%s)" % (len(done["stopped"]), ports(done["stopped"]))))
    if done["kept"]:
        bits.append("kept %d (%s)" % (len(done["kept"]), ports(done["kept"])))
    if done["ignored"]:
        bits.append("stopped asking about %s" % ports(done["ignored"]))
    if done["other"]:
        bits.append(c.amber("could not stop %s" % ports(done["other"])))
    st.say(", ".join(bits) or "nothing done")
    return EXIT_OK if not done["other"] and not done["kept"] else EXIT_KEPT
