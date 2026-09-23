"""The living world must never draw something portlist did not measure.

These pin the rules the harbour depends on: the gate opens only on a verified
connection, unknown is neither dangerous nor clean, the first snapshot marks
nothing as new, a restart keeps its identity, and prompts never reach the page.
"""
import json
import os
import sys
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from plcore import world  # noqa: E402

NOW = 1_800_000_000.0


def row(port=3000, pid=100, **kw):
    r = {
        "id": "%d-%d" % (port, pid), "port": port, "pid": pid, "cmd": "node",
        "cmdline": "node server.js", "dir": "/work/app", "dir_short": "~/app",
        "service": "Node / Express", "service_id": "express", "service_cat": "App server",
        "exposure": {"level": "loopback", "addrs": ["127.0.0.1"]},
        "activity": {"known": True, "ever_busy": True, "idle_seconds": 30, "watched_for": 9000},
        "conns": 0, "conns_public": 0, "health": "up", "risk": 0, "risk_band": "Info",
        "reasons": [], "leftover": {"likely": False}, "quiet": False,
        "starter": {"kind": "shell", "name": "a shell", "class": "terminal", "pid": 9},
        "origin": {"live": {"kind": "shell", "name": "a shell", "class": "terminal"},
                   "carries_context": True, "matched": "signature"},
        "depends_on": [], "used_by": [], "url": "http://localhost:%d" % port,
    }
    r.update(kw)
    return r


def exposed(verified):
    e = {"level": "all", "label": "All interfaces", "addrs": ["*"]}
    if verified is not None:
        e["verified"] = {"ip": "192.168.1.5", "iface": "en0", "accepting": verified}
    return e


def snap(rows, **kw):
    return world.build(rows, now=NOW, **kw)


# ------------------------------------------------------------------ the gate
def test_gate_opens_only_on_a_verified_connection():
    s = snap([row(exposure=exposed(True))])
    assert s["gate"]["state"] == "open"
    assert s["services"][0]["exposure"] == "reachable"


def test_a_bind_alone_does_not_open_the_gate():
    s = snap([row(exposure=exposed(None))])
    assert s["gate"]["state"] == "watch"
    assert s["services"][0]["exposure"] == "bound"
    assert s["gate"]["reachable"] == []


def test_a_refused_connection_is_listening_but_unreachable():
    s = snap([row(exposure=exposed(False))])
    assert s["services"][0]["exposure"] == "unreachable"
    assert s["gate"]["state"] == "closed"
    assert any(c["trigger"] == "LISTENING_BUT_UNREACHABLE" for c in s["conditions"])


# ------------------------------------------------------------------ unknown
def test_unknown_origin_is_curious_not_alarming():
    r = row(starter={}, origin={"live": None, "recorded": None, "carries_context": False})
    s = snap([r])
    svc = s["services"][0]
    assert svc["origin"] == "unknown"
    c = [c for c in s["conditions"] if c["trigger"] == "UNKNOWN_ORIGIN"][0]
    assert c["emotion"] == "curious"
    # below every exposure and risk signal: unknown alone never outranks them
    assert c["priority"] < world.PRIORITY["HIGH_RISK"]
    assert c["priority"] < world.PRIORITY["SERVICE_BINDS_EXTERNAL_INTERFACE"]
    assert svc["risk_band"] == "Info"


def test_too_few_samples_is_measuring_not_idle():
    s = snap([row(activity={"known": False, "note": "watching for 6s"})])
    assert s["services"][0]["activity"] == "unmeasured"
    assert s["stats"]["idle"] == 0 and s["stats"]["measuring"] == 1


def test_a_closed_yard_is_not_an_empty_yard():
    cdoc = {"engine": "docker", "reachable": False, "containers": [],
            "note": "docker is installed but its daemon did not answer"}
    s = snap([row()], containers=cdoc)
    assert s["yard"]["reachable"] is False
    assert "did not answer" in s["yard"]["note"]


# ------------------------------------------------------------------ agents
def test_an_agent_that_left_leaves_the_lights_on():
    r = row()
    groups = [{"key": "claude-code:-", "name": "a Claude Code session", "class": "AI agent",
               "kind": "claude-code", "ai": True, "alive": False, "pid": None,
               "services": [{"id": r["id"]}], "ports": [3000]}]
    s = snap([r], groups=groups)
    assert s["services"][0]["lights_left_on"] is True
    assert any(c["trigger"] == "AGENT_LEFT_SERVICE" for c in s["conditions"])


def test_liveness_unknown_is_not_an_exit():
    r = row()
    groups = [{"key": "claude-code:-", "name": "Claude Code", "class": "AI agent",
               "kind": "claude-code", "ai": True, "alive": None, "services": [{"id": r["id"]}]}]
    assert snap([r], groups=groups)["services"][0]["lights_left_on"] is False


def test_shared_port_is_a_conflict_with_both_binds():
    a = row(port=8000, pid=1)
    b = row(port=8000, pid=2, exposure=exposed(True), cmdline="python -m http.server 8000")
    s = snap([a, b])
    c = [c for c in s["conditions"] if c["trigger"] == "PORT_CONFLICT"]
    assert len(c) == 1 and sorted(c[0]["evidence"]["services"]) == sorted([a["id"], b["id"]])


# ------------------------------------------------------------------ events
def test_first_snapshot_marks_nothing():
    d = world.Differ()
    assert d.feed(snap([row(), row(port=5173)])) == []


def test_start_stop_and_restart():
    d = world.Differ()
    d.feed(snap([row(port=3000, pid=1)]))
    ev = d.feed(snap([row(port=3000, pid=2), row(port=5173, pid=3)]))
    trig = sorted(e["trigger"] for e in ev)
    # same command in the same directory on the same port: a restart, not a new service
    assert trig == ["SERVICE_RESTARTED", "SERVICE_STARTED"]
    ev = d.feed(snap([row(port=3000, pid=2)]))
    assert [e["trigger"] for e in ev] == ["SERVICE_STOPPED"]
    assert d.since(0)[-1]["seq"] == d.seq


def test_exposure_change_is_an_event_both_ways():
    d = world.Differ()
    d.feed(snap([row()]))
    ev = d.feed(snap([row(exposure=exposed(True))]))
    assert "SERVICE_EXTERNALLY_REACHABLE" in [e["trigger"] for e in ev]
    ev = d.feed(snap([row()]))
    assert "SERVICE_NO_LONGER_EXTERNALLY_REACHABLE" in [e["trigger"] for e in ev]


def test_flapping_is_noticed():
    d = world.Differ()
    d.feed(snap([]))
    trig = []
    for i in range(3):
        trig += [e["trigger"] for e in d.feed(snap([row(pid=10 + i)]), now=NOW + i * 10)]
        d.feed(snap([]), now=NOW + i * 10 + 5)
    assert "SERVICE_FLAPS" in trig


# ------------------------------------------------------------------ pets
def test_guard_goes_to_the_open_gate_and_quiet_pets_say_so():
    s = snap([row(exposure=exposed(True))])
    tasks = {t["role"]: t for t in world.plan_pets(s)}
    assert tasks["guard"]["trigger"] == "SERVICE_EXTERNALLY_REACHABLE"
    assert tasks["mechanic"]["trigger"] == "SYSTEM_QUIET"
    assert tasks["mechanic"]["meaning"]


def test_every_pet_task_carries_its_reason():
    s = snap([row(exposure=exposed(True), starter={}, origin={})])
    for t in world.plan_pets(s):
        assert t["trigger"] and t["meaning"]
        if t["subject"]:
            assert t["evidence"]


def test_chatter_only_repeats_facts():
    s = snap([row(exposure=exposed(True), starter={}, origin={})])
    lines = world.chatter(world.plan_pets(s), s)
    assert lines, "guard and inspector share an exposed unknown service"
    text = " ".join(l[1] for c in lines for l in c["lines"])
    assert ":3000" in text and "unknown" in text


# ------------------------------------------------------------------ privacy
def test_prompts_never_reach_the_world():
    sdoc = {"sessions": [{"id": "abc", "tool": "claude", "title": "Fix the login page",
                          "first_prompt": "SECRET PROMPT TEXT", "last_prompt": "ALSO SECRET",
                          "live": True, "live_pids": [], "project": "app"}]}
    out = json.dumps(snap([row()], sessions=sdoc))
    assert "SECRET" not in out
    assert "Fix the login page" in out


def test_addresses_are_scrubbed_from_titles():
    sdoc = {"sessions": [{"id": "x", "title": "mail someone@example.com about it", "live_pids": []}]}
    assert "example.com" not in json.dumps(snap([], sessions=sdoc))


# ------------------------------------------------------------------ server
def test_server_checks_host_and_key(monkeypatch):
    from plcore import worldserve
    monkeypatch.setattr(world, "payload", lambda since=0, **kw: {"ok": True, "since": since})
    srv, url = worldserve.serve(0)
    try:
        port = srv.server_address[1]
        key = url.split("k=")[1]

        def get(path, headers=None):
            req = urllib.request.Request("http://127.0.0.1:%d%s" % (port, path), headers=headers or {})
            try:
                with urllib.request.urlopen(req, timeout=5) as r:
                    return r.status, r.read()
            except urllib.error.HTTPError as e:
                return e.code, e.read()

        assert get("/")[0] == 403                                   # no key
        assert get("/?k=" + key)[0] == 200
        assert get("/api/world")[0] == 403
        code, body = get("/api/world?since=abc", {worldserve.HEADER: key})
        assert code == 200 and json.loads(body)["since"] == 0       # bad int, clean answer
        assert get("/?k=" + key, {"Host": "evil.example:%d" % port})[0] == 421
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.shutdown()


# ------------------------------------------------------------------ landmarks
def test_quiet_services_are_drawn_but_never_counted():
    q = row(port=5000, pid=50, quiet=True, service_id="airplay", exposure=exposed(True))
    s = snap([row(), q])
    sysv = [x for x in s["services"] if x["system"]]
    assert len(sysv) == 1 and sysv[0]["shape"] == "shed"
    assert s["stats"]["services"] == 1 and s["stats"]["exposed"] == 0
    assert s["gate"]["state"] == "closed" and s["gate"]["system_reachable"] == [q["id"]]
    assert all(c["subject"] != "service:" + q["id"] for c in s["conditions"])
    d = world.Differ(); d.feed(snap([row()]))
    assert d.feed(snap([row(), q])) == []          # a helper appearing starts no truck


def test_the_lighthouse_is_lit_only_by_a_listening_ssh_server():
    assert snap([row()])["lighthouse"]["listening"] is False
    s = snap([row(port=22, service_id="ssh", service="SSH", cmdline="sshd")])
    assert s["lighthouse"]["listening"] is True and s["lighthouse"]["ports"] == [22]


def test_ssh_destinations_come_from_the_shared_endpoint_grouping():
    eps = [{"address": "203.0.113.4", "alias": "deploy@box.example", "ssh": True, "scope": "public", "count": 1,
            "ports": [{"port": 2222}], "processes": [{"name": "ssh", "pid": 7}], "scan_command": "x ssh box"},
           {"address": "10.0.0.2", "ssh": False, "ports": [{"port": 443}], "processes": []}]
    out = world.ssh_destinations(eps)
    assert [o["target"] for o in out] == ["box.example"]           # host only, never the login
    assert out[0]["rport"] == 2222 and out[0]["pids"] == [7]
    assert out[0]["scan_command"] is None                          # no command offered where it cannot run
    assert world.ssh_destinations(eps, can_inventory=True)[0]["scan_command"] == "x ssh box"
    d = world.Differ(); d.feed(snap([row()]))
    ev = d.feed(snap([row()], outbound=out))
    assert [e["trigger"] for e in ev] == ["SSH_SESSION_OPENED"]
    assert [e["trigger"] for e in d.feed(snap([row()]))] == ["SSH_SESSION_CLOSED"]


def test_the_lighthouse_guides_only_sessions_coming_in():
    sshd = row(port=22, pid=1, service_id="ssh", service="SSH", cmdline="sshd")
    assert snap([row()])["lighthouse"]["state"] == "dark"
    assert snap([sshd])["lighthouse"]["state"] == "standby"
    out_only = [{"direction": "outbound", "lport": 5000, "raddr": "1.2.3.4", "rport": 22}]
    assert snap([sshd], conns=out_only)["lighthouse"]["inbound"] == []           # going out is not a visitor
    mine = [{"target": "box", "kind": "ssh", "raddr": "1.2.3.4", "rport": 22}]
    assert snap([row()], outbound=mine)["lighthouse"]["state"] == "guiding"      # but it lights the lamp
    inn = [{"direction": "inbound", "lport": 22, "raddr": "10.0.0.9", "rport": 51000, "pid": 1}]
    s = snap([sshd], conns=inn)
    assert s["lighthouse"]["state"] == "guiding" and s["lighthouse"]["inbound"][0]["raddr"] == "10.0.0.9"
    d = world.Differ(); d.feed(snap([sshd]))
    assert "SSH_INBOUND_OPENED" in [e["trigger"] for e in d.feed(s)]


def test_traffic_is_every_outbound_host_but_ssh_and_loopback():
    eps = [{"address": "54.1.1.1", "ssh": True}, {"address": "127.0.0.1", "local": True},
           {"address": "2607:6bc0::10", "services": ["HTTPS"], "ports": [{"port": 443}], "count": 4,
            "processes": [{"name": "Google Chrome Helper"}, {"name": "claude.exe"}, {"name": "Google Chrome Helper (GPU)"}]}]
    t = world.traffic_endpoints(eps)
    assert [x["address"] for x in t] == ["2607:6bc0::10"] and t[0]["apps"] == ["Google Chrome", "claude.exe"]


def test_remote_databases_are_islands_and_https_is_traffic():
    eps = [{"address": "10.1.1.1", "ports": [{"port": 27017, "service": "MongoDB"}], "processes": [{"name": "mongosh", "pid": 3}]},
           {"address": "10.1.1.2", "ports": [{"port": 443, "service": "HTTPS"}], "processes": [{"name": "curl"}]}]
    isl = world.sea_destinations(eps)
    assert [(i["target"], i["kind"], i["logo"]) for i in isl] == [("10.1.1.1", "db", "mongodb")]
    assert [t["address"] for t in world.traffic_endpoints(eps)] == ["10.1.1.2"]
    s = snap([row()], outbound=isl)
    assert s["lighthouse"]["state"] == "dark"                                   # a database is not SSH
    d = world.Differ(); d.feed(snap([row()]))
    assert [e["trigger"] for e in d.feed(s)] == ["DB_SESSION_OPENED"]


# ------------------------------------------------------------------ the past
def test_reconstruct_walks_opens_and_closes_back():
    now_rows = [row(port=3000, pid=1), row(port=5173, pid=2)]
    events = [
        {"ts": NOW - 10, "type": "opened", "port": 5173, "pid": 2, "service": "vite"},
        {"ts": NOW - 20, "type": "closed", "port": 8080, "pid": 3, "service": "api", "exposure": "all"},
        {"ts": NOW - 90, "type": "opened", "port": 8080, "pid": 3, "service": "api"},
    ]
    at30 = world.reconstruct(now_rows, events, NOW - 30)
    assert [(x["port"], x["exposure"]) for x in at30] == [(3000, "loopback"), (8080, "all")]   # vite not yet, api still up
    assert [x["port"] for x in world.reconstruct(now_rows, events, NOW - 5)] == [3000, 5173]  # the present
    assert [x["port"] for x in world.reconstruct(now_rows, events, NOW - 100)] == [3000]       # before api opened


def test_fleet_harbours_skip_this_machine_and_keep_the_quiet_ones():
    hosts = [{"id": "127.0.0.1", "name": "127.0.0.1", "status": "gone"},
             {"id": "me", "name": "mybox.local", "status": "online"},
             {"id": "web-1", "name": "web-1", "status": "gone", "age": 99999, "ports": 12, "exposed": 2,
              "os": {"pretty": "Ubuntu"}, "addresses": [{"ip": "10.0.0.5"}]},
             {"id": "db-1", "name": "db-1", "status": "online", "ports": 4, "exposed": 0}]
    out = world.fleet_harbours(hosts, "mybox")
    assert [h["id"] for h in out] == ["db-1", "web-1"]         # online first; loopback and this machine left out
    assert out[1]["status"] == "gone" and out[1]["address"] == "10.0.0.5"


def test_memory_counts_only_what_the_history_records():
    import time
    lt = time.localtime(NOW)
    midnight = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, 0, 0, 0, 0, 0, -1))
    hist = [
        {"ts": midnight + 60, "type": "opened", "port": 3000, "exposure": "loopback"},
        {"ts": midnight + 120, "type": "closed", "port": 3000},
        {"ts": midnight + 180, "type": "opened", "port": 3000, "exposure": "all"},
        {"ts": midnight - 86400 * 3, "type": "opened", "port": 3000, "exposure": "all"},   # three days ago
        {"ts": midnight + 90, "type": "opened", "port": 9999},                               # not listening now
        {"ts": midnight + 95, "type": "risk_band", "port": 3000},                            # not an open or close
    ]
    mem = world.memory_of([{"port": 3000}, {"port": 5432}], hist, now=max(NOW, midnight + 200))
    assert mem[3000] == {"opens_today": 2, "stops_today": 1, "exposed_before": 2, "since": midnight - 86400 * 3}
    assert 5432 not in mem and 9999 not in mem           # nothing recorded is not zero, it is absent
