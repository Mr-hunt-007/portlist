"""`portlist 3000`: one answer, then exit. Every warning is a measured fact,
and the exit code says what a script needs to know."""
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import explain  # noqa: E402


def row(port=3000, pid=4123, **kw):
    r = {"port": port, "pid": pid, "user": "me", "cmd": "node", "cmdline": "node server.js",
         "exe": "", "service": "Next.js", "service_cat": "Dev server", "uptime": 7200,
         "project": {"name": "shop", "short": "~/code/shop"},
         "exposure": {"level": "loopback", "label": "Localhost only", "addrs": ["127.0.0.1"], "verified": None},
         "activity": {"idle_seconds": 60, "ever_busy": True, "watched_for": 7200},
         "conns": 2, "conns_public": 0, "risk": 12, "risk_band": "Info", "reasons": [],
         "leftover": {"likely": False}, "starter": {"name": "Claude Code", "class": "AI agent", "ai": True, "alive": True},
         "quiet": False}
    r.update(kw)
    return r


def detail(r):
    return {"tree": {"ancestry": [{"pid": 1, "name": "launchd"}, {"pid": 900, "name": "claude"},
                                  {"pid": r["pid"], "name": "node"}],
                     "children": [{"pid": 5000, "name": "esbuild"}]},
            "provenance": {"summary": "a local project from shop"}, "environ_names": r.get("_env", [])}


def run(rows, **kw):
    out, err = io.StringIO(), io.StringIO()
    kw.setdefault("no_color", True)
    code = explain.run(out=out, err=err, scan_fn=lambda: (rows, {}), detail_fn=detail, **kw)
    return code, out.getvalue(), err.getvalue()


def test_a_clean_answer_exits_zero_and_names_the_chain():
    code, out, _ = run([row()], ports=[3000])
    assert code == explain.EXIT_OK
    assert "launchd (pid 1) → claude (pid 900) → node (pid 4123)" in out
    assert "Claude Code" in out and "kill 4123" in out and "Warnings     none" in out


def test_warnings_are_measured_facts_and_exit_one(monkeypatch):
    monkeypatch.setattr(explain, "_rss", lambda pid: 3 << 30)
    monkeypatch.setattr(explain, "_restarts", lambda port, service, now: 0)
    r = row(user="root", exe="/no/such/binary", uptime=100 * 86400, _env=["DYLD_INSERT_LIBRARIES"],
            exposure={"level": "all", "label": "All interfaces", "addrs": ["*"],
                      "verified": {"accepting": True, "ip": "192.168.1.5", "iface": "en0"}},
            starter={"name": "Claude Code", "ai": True, "alive": False})
    code, out, _ = run([r], ports=[3000], mode="warnings")
    assert code == explain.EXIT_WARN
    for fact in ("reachable from beyond this machine", "running as root", "no longer on disk",
                 "DYLD_INSERT_LIBRARIES", "has since exited", "running for 100d", "3.0 GB"):
        assert fact in out, fact


def test_unknown_origin_is_not_a_warning():
    code, out, _ = run([row(starter={}, origin={"live": None})], ports=[3000])
    assert code == explain.EXIT_OK and "Warnings     none" in out


def test_exit_codes_for_nothing_matched_bad_input_and_another_users_process():
    assert run([row()], ports=[9999])[0] == explain.EXIT_NOTFOUND
    assert run([row()], ports=[70000])[0] == explain.EXIT_INPUT
    code, _, err = run([row(pid=None)], ports=[3000])
    assert code == explain.EXIT_PERM and "sudo" in err


def test_json_is_one_object_for_one_target_and_a_list_for_many():
    code, out, _ = run([row(), row(port=5173, pid=77, service="Vite")], ports=[3000], as_json=True)
    doc = json.loads(out)
    assert doc["port"] == 3000 and doc["chain"][-1]["pid"] == 4123 and doc["stop"] == "kill 4123"
    code, out, _ = run([row(), row(port=5173, pid=77, service="Vite")], names=["e"], as_json=True)
    assert isinstance(json.loads(out), list)


def test_names_match_service_command_or_project_and_exact_is_exact():
    rows = [row(), row(port=5173, pid=77, service="Vite", cmd="vite", project={"name": "admin"})]
    assert [r["port"] for r in explain.find(rows, names=["vit"])[0][1]] == [5173]
    assert [r["port"] for r in explain.find(rows, names=["shop"])[0][1]] == [3000]
    assert explain.find(rows, names=["vit"], exact=True)[0][1] == []


def test_short_and_tree_show_the_chain():
    _, out, _ = run([row()], ports=[3000], mode="short")
    assert out.startswith("launchd (pid 1) → claude (pid 900) → node (pid 4123)")
    _, out, _ = run([row()], ports=[3000], mode="tree")
    assert "└─ node (pid 4123)" in out and "esbuild (pid 5000)" in out


def test_list_filters_and_leaves_system_services_out():
    rows = [row(), row(port=5000, pid=9, service="AirPlay", quiet=True),
            row(port=8787, pid=8, exposure={"level": "all", "label": "All interfaces", "addrs": ["*"], "verified": None})]
    _, out, _ = run(rows, list_mode=True, as_json=True)
    assert [x["port"] for x in json.loads(out)] == [3000, 8787]
    _, out, _ = run(rows, list_mode=True, only="exposed", as_json=True)
    assert [x["port"] for x in json.loads(out)] == [8787]


def test_targets_parse_ports_and_names():
    assert explain.parse_targets(["3000", ":5173", "node"]) == ([3000, 5173], ["node"])


def test_completions_exist_for_three_shells():
    assert "--json" in explain.completion("bash") and "--json" in explain.completion("zsh")
    assert "-l json" in explain.completion("fish")          # fish names long flags without dashes
