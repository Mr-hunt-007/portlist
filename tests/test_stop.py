"""`portlist kill` and `portlist cleanup`: nothing is stopped without a yes, the
right thing is stopped (a container, not its proxy), and a restart is caught.
Every signal here goes to a fake: the tests never touch a real process."""
import io
import os
import signal
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import stop  # noqa: E402


def row(port=8787, pid=4412, **kw):
    r = {"id": "%s-%s" % (port, pid), "port": port, "pid": pid, "user": "me", "cmd": "python3",
         "cmdline": "python3 -m http.server %d" % port, "service": "Python http.server", "uptime": 5 * 86400,
         "project": {"name": "data-export", "short": "~/code/data-export"},
         "exposure": {"level": "all", "label": "All interfaces", "addrs": ["0.0.0.0"],
                      "verified": {"accepting": True, "ip": "192.0.2.14", "iface": "en0"}},
         "activity": {"idle_seconds": None, "ever_busy": False, "watched_for": 5 * 86400},
         "conns": 0, "risk": 71, "risk_band": "High", "reasons": [],
         "leftover": {"likely": True, "reasons": ["nothing has connected to it in 5 days"]},
         "starter": {"name": "a Claude Code session", "ai": True, "alive": False}, "quiet": False}
    r.update(kw)
    return r


class Machine:
    """A process table that only changes when the fakes are called."""

    def __init__(self, rows, respawn=None, ignores_term=False):
        self.rows, self.respawn, self.ignores_term = list(rows), respawn or {}, ignores_term
        self.signals, self.ran = [], []

    def scan(self, force=False):
        return list(self.rows), {"hostname": "devbox"}

    def detail(self, r):
        return {"tree": {"ancestry": [{"pid": 1, "name": "launchd"}, {"pid": r["pid"], "name": r["cmd"]}]}}

    def kill(self, pid, sig):
        self.signals.append((pid, sig))
        if sig == signal.SIGTERM and self.ignores_term:
            return
        gone = [r for r in self.rows if r["pid"] == pid]
        self.rows = [r for r in self.rows if r["pid"] != pid]
        for r in gone:
            if r["port"] in self.respawn:
                self.rows.append(dict(r, pid=self.respawn[r["port"]]))

    def alive(self, pid):
        return any(r["pid"] == pid for r in self.rows)

    def run(self, cmd):
        self.ran.append(cmd)
        if cmd[:2] == ["docker", "stop"]:
            self.rows = [r for r in self.rows if (r.get("container") or {}).get("name") != cmd[2]]
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def go(fn, argv, m, answers=(), interactive=True):
    out = io.StringIO()
    it = iter(answers)
    code = fn(argv, out=out, err=out, scan_fn=m.scan, detail_fn=m.detail, kill_fn=m.kill, alive_fn=m.alive,
              run_fn=m.run, sleep=lambda s: None, probe=False, interactive=interactive, ask=lambda q: next(it, ""))
    return code, out.getvalue()


def test_kill_shows_what_it_is_and_stops_only_after_yes():
    m = Machine([row()])
    code, out = go(stop.kill_main, ["8787"], m, answers=["n"])
    assert code == stop.EXIT_KEPT and m.signals == []
    assert "a Claude Code session" in out and "verified from 0.0.0.0" in out and "kept" in out
    code, out = go(stop.kill_main, ["8787"], m, answers=["y"])
    assert code == stop.EXIT_OK and m.signals == [(4412, signal.SIGTERM)] and ":8787 is free" in out


def test_kill_never_asks_a_pipe_and_needs_yes_to_act():
    m = Machine([row()])
    code, out = go(stop.kill_main, ["8787"], m, interactive=False)
    assert code == stop.EXIT_KEPT and m.signals == [] and "--yes" in out
    code, _ = go(stop.kill_main, ["8787", "--yes"], m, interactive=False)
    assert code == stop.EXIT_OK and m.signals


def test_dry_run_stops_nothing():
    m = Machine([row()])
    code, out = go(stop.kill_main, ["8787", "--dry-run"], m)
    assert code == stop.EXIT_OK and m.signals == [] and "would run: SIGTERM to pid 4412" in out


def test_a_container_is_stopped_as_a_container_not_through_its_proxy():
    m = Machine([row(5432, 2211, service="PostgreSQL", container={"name": "shop-db-1", "image": "postgres:16"})])
    code, out = go(stop.kill_main, ["5432", "--yes"], m)
    assert m.ran == [["docker", "stop", "shop-db-1"]] and m.signals == []
    assert code == stop.EXIT_OK and "docker stop shop-db-1" in out


def test_a_restart_is_caught_and_reported():
    m = Machine([row()], respawn={8787: 9001})
    code, out = go(stop.kill_main, ["8787", "--yes"], m)
    assert code == stop.EXIT_KEPT and "came back as pid 9001" in out


def test_sigterm_ignored_means_force_is_asked_for_not_assumed():
    m = Machine([row()], ignores_term=True)
    code, out = go(stop.kill_main, ["8787", "--yes"], m)
    assert code == stop.EXIT_KEPT and (4412, stop.SIGKILL) not in m.signals and "--force" in out
    m = Machine([row()], ignores_term=True)
    code, _ = go(stop.kill_main, ["8787", "--yes", "--force"], m)
    assert code == stop.EXIT_OK and (4412, stop.SIGKILL) in m.signals


def test_refusals_nothing_matched_bad_port_other_user_system():
    m = Machine([row(), row(5000, 380, quiet=True, service="AirPlay"), row(22, None, service="sshd")])
    assert go(stop.kill_main, ["9999"], m)[0] == stop.EXIT_NOTFOUND
    assert go(stop.kill_main, ["70000"], m)[0] == stop.EXIT_INPUT
    code, out = go(stop.kill_main, ["22", "--yes"], m)
    assert code == stop.EXIT_PERM and "sudo portlist kill 22" in out
    code, out = go(stop.kill_main, ["5000", "--yes"], m)
    assert code == stop.EXIT_KEPT and "will not stop it" in out and m.signals == []


def test_the_shared_guard_refuses_pid_1_and_a_stale_pid():
    m = Machine([row()])
    assert stop.signal_listener(1, 8787, scan_fn=m.scan, kill_fn=m.kill)[0] == "refused"
    assert stop.signal_listener(4412, 9999, scan_fn=m.scan, kill_fn=m.kill)[0] == "stale"
    assert m.signals == []


def test_cleanup_walks_the_leftovers_and_keeps_what_you_keep(tmp_path, monkeypatch):
    monkeypatch.setenv("PORTLIST_DATA", str(tmp_path))
    rows = [row(), row(5173, 4480, service="Vite", leftover={"likely": True, "reasons": ["idle 3 days"]},
                       exposure={"level": "loopback", "label": "Localhost only", "addrs": ["127.0.0.1"], "verified": None}),
            row(3000, 4123, service="Next.js", leftover={"likely": False, "reasons": []})]
    m = Machine(rows)
    code, out = go(stop.cleanup_main, [], m, answers=["y", "k"])
    assert "2 listeners look left over" in out and "1/2" in out and "2/2" in out
    assert m.signals == [(4412, signal.SIGTERM)]                  # the verified-exposed one is asked first
    assert "stopped 1 (:8787)" in out and "stopped asking about :5173" in out
    from plcore import lifecycle
    assert "5173" in lifecycle.ignored()


def test_cleanup_dry_run_and_json_stop_nothing():
    m = Machine([row()])
    code, out = go(stop.cleanup_main, ["--dry-run"], m)
    assert code == 0 and m.signals == [] and "nothing was stopped" in out
    code, out = go(stop.cleanup_main, ["--json"], m)
    import json
    doc = json.loads(out)
    assert doc[0]["port"] == 8787 and doc[0]["leftover_reasons"] and m.signals == []


def test_cleanup_idle_offers_the_unused_too():
    fresh = row(3000, 4123, leftover={"likely": False, "reasons": []},
                activity={"idle_seconds": 30 * 3600, "ever_busy": True, "watched_for": 40 * 3600})
    assert stop.candidates([fresh]) == []
    assert stop.candidates([fresh], idle_hours=24) == [fresh]
