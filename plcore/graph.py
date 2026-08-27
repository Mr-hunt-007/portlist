"""The machine as a graph, not a table.

A table is the right shape for "what is on :8000". It is the wrong shape for
"what is connected to what", which is the question behind most of the
interesting ones: which agent started this, which project it came from, what it
talks to, and who can reach it.

Three modes, one row set. Nodes carry a `layer` so the renderer can lay them out
in columns without a layout library and without any chance of two clients
drawing the same machine differently.

    machine    starter -> project -> process -> port -> exposure -> endpoint
    project    project -> service
    exposure   zone -> port -> outbound endpoint
"""
from . import projects

RISK_TONE = {"Critical": "red", "High": "red", "Medium": "amber", "Low": "blue", "Info": "grey"}
ZONES = [("all", "All interfaces", "red"), ("lan", "LAN", "amber"),
         ("loopback", "Localhost", "green"), ("unknown", "Unknown bind", "grey")]


def _node(nid, kind, label, layer, **kw):
    n = {"id": nid, "kind": kind, "label": label, "layer": layer, "sub": kw.pop("sub", None),
         "tone": kw.pop("tone", "grey")}
    n.update(kw)
    return n


def build(rows, mode="machine", host=None, conns=None, fleet=None):
    live = [r for r in rows if not r.get("quiet")]
    if mode == "project":
        return _project_graph(live)
    if mode == "exposure":
        return _exposure_graph(live, host, conns)
    if mode == "fleet":
        return _fleet_graph(fleet or [])
    if mode == "agent":
        return _agent_graph(live)
    if mode == "orrery":
        return _orrery_graph(live, host, conns)
    return _machine_graph(live, host, conns)


# ------------------------------------------------------------------- orrery
def _orrery_graph(live, host, conns):
    """Everything at once, with no layout.

    The other modes answer one question each and are laid out in columns to make
    that question readable. This one answers none of them: it is the whole
    machine as a single object you can turn over in your hands, and the shape it
    makes is the point. Which is why the server sends no coordinates - nodes
    carry a mass and edges carry a strength, and the client settles them.

    Every edge here is something measured, not a category somebody invented:
    an agent started a service, a service came out of a project, a container
    publishes a port, a service holds a connection into another one.
    """
    from . import agents as agents_mod
    nodes, edges, seen = {}, [], set()

    def add(nid, kind, label, **kw):
        if nid not in nodes:
            nodes[nid] = _node(nid, kind, label, 0, **kw)
        return nid

    def link(a, b, kind, strength=1.0, tone="grey"):
        key = (a, b, kind)
        if key in seen or a == b or a not in nodes or b not in nodes:
            return
        seen.add(key)
        edges.append({"from": a, "to": b, "kind": kind, "strength": strength,
                      "tone": tone})

    hostname = (host or {}).get("hostname") or "this machine"
    root = add("host", "host", hostname, tone="white", mass=8,
               sub="%d services listening" % len(live))

    for r in live:
        pid = "svc:%s" % r["id"]
        add(pid, "service", ":%d" % r["port"], row=r["id"],
            sub=r.get("service") or r.get("cmd") or "unidentified",
            tone=RISK_TONE.get(r.get("risk_band"), "grey"),
            mass=2 + min(4, (r.get("conns") or 0) / 3.0),
            exposure=(r.get("exposure") or {}).get("level"),
            ai=bool(r.get("ai")), url=r.get("url"),
            leftover=bool((r.get("leftover") or {}).get("likely")))

        proj = (r.get("project") or {}).get("name")
        if proj:
            p = add("proj:%s" % proj, "project", proj, tone="blue", mass=5,
                    sub="project")
            link(p, pid, "runs", 1.0)
            link(root, p, "hosts", 0.35)
        else:
            link(root, pid, "hosts", 0.5)

        c = r.get("container")
        if c:
            cid = add("ctr:%s" % c["id"], "container", c["name"], tone="cyan", mass=3,
                      sub=c.get("image") or "container")
            link(cid, pid, "publishes", 1.2)

        who = r.get("starter") or {}
        if who.get("name"):
            aid = add("agent:%s:%s" % (who.get("kind") or who["name"], who.get("pid")),
                      "agent", who["name"],
                      tone="violet" if who.get("ai") else "grey", mass=6,
                      sub=("session has exited" if who.get("alive") is False
                           else who.get("class") or ""),
                      gone=who.get("alive") is False, ai=bool(who.get("ai")))
            link(aid, pid, "started", 0.7,
                 tone="red" if who.get("alive") is False else "grey")

    # Measured dependencies, which is the only kind of edge here that says
    # something the other views cannot show at all.
    for r in live:
        for d in (r.get("depends_on") or []):
            link("svc:%s" % r["id"], "svc:%s" % d["id"], "depends",
                 1.6 + min(2.0, d["conns"] / 4.0), tone="green")

    # Where a service can be reached from. Only for the ones where that is not
    # the boring answer: a loopback node linked to everything is noise.
    for level, label, tone in ZONES:
        if level == "loopback":
            continue
        members = [r for r in live if (r.get("exposure") or {}).get("level") == level]
        if not members:
            continue
        zid = add("zone:%s" % level, "zone", label, tone=tone, mass=5,
                  sub="%d service%s reachable" % (len(members),
                                                  "" if len(members) == 1 else "s"))
        for r in members:
            link(zid, "svc:%s" % r["id"], "exposes", 0.5, tone=tone)

    return {"mode": "orrery", "nodes": list(nodes.values()), "edges": edges,
            "layers": [], "force": True,
            "legend": [{"kind": "host", "label": "this machine", "tone": "white"},
                       {"kind": "agent", "label": "who started it", "tone": "violet"},
                       {"kind": "project", "label": "project", "tone": "blue"},
                       {"kind": "container", "label": "container", "tone": "cyan"},
                       {"kind": "zone", "label": "reachable from", "tone": "amber"},
                       {"kind": "service", "label": "service, coloured by risk",
                        "tone": "grey"}]}


# -------------------------------------------------------------------- agent
def _agent_graph(live):
    """Agent -> project -> service. The tree people draw when they describe this
    problem to each other, which is a different shape from project -> service:
    one agent works across several projects, and one project gets touched by
    several agents."""
    from . import agents as agents_mod
    nodes, edges, seen = [], [], set()

    def add(n):
        if n["id"] not in seen:
            seen.add(n["id"])
            nodes.append(n)
        return n["id"]

    by_id = {r["id"]: r for r in live}
    for g in agents_mod.groups(live):
        gone = g["alive"] is False
        aid = add(_node("agent:%s" % g["key"], "agent", g["name"], 0,
                        # The node box is 196px: "session has exited" ran past it.
                        sub="%d service%s%s" % (g["count"], "" if g["count"] == 1 else "s",
                                                " · exited" if gone else ""),
                        tone="red" if gone and g["count"] else "green" if g["ai"] else "grey",
                        ai=g["ai"], alive=g["alive"], gone=gone))
        for svc in g["services"]:
            r = by_id.get(svc["id"])
            pname = svc.get("project") or svc.get("dir_short") or "no project"
            pid_node = add(_node("agentproj:%s|%s" % (g["key"], pname), "project", pname, 1,
                                 sub="", tone="grey"))
            edges.append({"from": aid, "to": pid_node, "label": None,
                          "tone": "red" if gone else "grey", "dashed": gone})
            nid = add(_node("port:%s" % svc["id"], "port", ":%d" % svc["port"], 2,
                            sub=svc.get("service") or "unidentified",
                            tone=RISK_TONE.get(svc.get("risk_band"), "grey"),
                            row=svc["id"], url=svc.get("url"),
                            leftover=bool((svc.get("leftover") or {}).get("likely")),
                            ai=bool(r and r.get("ai"))))
            edges.append({"from": pid_node, "to": nid, "label": None,
                          "tone": "grey", "dashed": False})
        for m in g["mcp"]:
            mid = add(_node("stdio:%s" % m["pid"], "process", m["name"] or "stdio MCP", 1,
                            sub="stdio MCP · no port", tone="purple", pid=m["pid"]))
            edges.append({"from": aid, "to": mid, "label": "stdio",
                          "tone": "grey", "dashed": True})
    return {"mode": "agent", "nodes": nodes, "edges": edges,
            "layers": ["agent", "project", "service"]}


# ------------------------------------------------------------------ machine
def _machine_graph(live, host, conns):
    nodes, edges, seen = [], [], set()

    def add(n):
        if n["id"] not in seen:
            seen.add(n["id"])
            nodes.append(n)
        return n["id"]

    def link(a, b, label=None, tone="grey", dashed=False):
        edges.append({"from": a, "to": b, "label": label, "tone": tone, "dashed": dashed})

    for r in live:
        pid_node = add(_node("proc:%d" % r["pid"], "process", r["cmd"], 2,
                             sub="pid %d · %s" % (r["pid"], r.get("user") or "?"),
                             pid=r["pid"]))
        port_node = add(_node("port:%s" % r["id"], "port", ":%d" % r["port"], 3,
                              sub=r.get("service") or "unidentified",
                              tone=RISK_TONE.get(r["risk_band"], "grey"),
                              risk=r["risk"], risk_band=r["risk_band"], row=r["id"],
                              url=r.get("serves_url") or r.get("url"),
                              ai=bool(r.get("ai")), mcp=bool(r.get("mcp")),
                              leftover=bool((r.get("leftover") or {}).get("likely"))))
        link(pid_node, port_node, "listens")

        who = r.get("starter")
        if who:
            sid = add(_node("starter:%s" % who["kind"], "starter", who["name"], 0,
                            sub=who["class"], tone="blue" if who.get("ai") else "grey",
                            ai=bool(who.get("ai"))))
            proj_key = None
        else:
            sid = None
        k = projects.key_for(r)
        if k:
            proj_node = add(_node("project:%s" % k[0], "project", k[1], 1, sub=k[2]))
            if sid:
                link(sid, proj_node, "started work in")
            link(proj_node, pid_node, "runs")
        elif sid:
            link(sid, pid_node, "started")

        zone = r["exposure"]["level"]
        zlabel = dict((z[0], z[1]) for z in ZONES).get(zone, zone)
        ztone = dict((z[0], z[2]) for z in ZONES).get(zone, "grey")
        znode = add(_node("zone:%s" % zone, "zone", zlabel, 4, tone=ztone,
                          sub="reachable from" if zone != "loopback" else "this machine only"))
        v = r["exposure"].get("verified") or {}
        link(port_node, znode, "confirmed on %s" % v["ip"] if v.get("accepting") else None,
             tone=ztone)

    # Outbound: what these processes are talking to. A listening socket and an
    # established connection are different facts, and the graph keeps them apart.
    pids = {r["pid"] for r in live}
    for c in (conns or [])[:120]:
        if c.get("pid") not in pids or c.get("direction") != "outbound":
            continue
        label = c.get("remote_service") or c.get("raddr")
        eid = add(_node("ep:%s:%s" % (c.get("raddr"), c.get("rport")), "endpoint",
                        "%s:%s" % (label, c.get("rport")), 5,
                        sub=c.get("scope"), tone="amber" if c.get("scope") == "public" else "grey"))
        link("proc:%d" % c["pid"], eid, "connects to", dashed=True)

    return {"mode": "machine", "nodes": nodes, "edges": edges,
            "layers": ["started by", "project", "process", "port", "reachable from", "talks to"]}


# ------------------------------------------------------------------ project
def _project_graph(live):
    nodes, edges = [], []
    groups = projects.group(live)
    by_id = {r["id"]: r for r in live}
    for g in groups:
        gid = "project:%s" % g["key"]
        nodes.append(_node(gid, "project", g["name"], 0,
                           sub="%d services · %s" % (g["count"], g["health_label"]),
                           tone="red" if g["attention"] else "green" if g["health"] == "up" else "amber",
                           attention=g["attention"], leftovers=g["leftovers"]))
        for slot in g["roles"]:
            r = by_id.get(slot["id"])
            nid = "port:%s" % slot["id"]
            nodes.append(_node(nid, "port", ":%d" % slot["port"], 1,
                               sub="%s · %s" % (slot["label"], slot["service"] or ""),
                               tone=RISK_TONE.get(slot["risk_band"], "grey"),
                               row=slot["id"], url=slot["url"],
                               leftover=slot["leftover"],
                               ai=bool(r and r.get("ai"))))
            edges.append({"from": gid, "to": nid, "label": slot["label"],
                          "tone": "grey", "dashed": False})
    return {"mode": "project", "nodes": nodes, "edges": edges,
            "layers": ["project", "service"]}


# ----------------------------------------------------------------- exposure
def _exposure_graph(live, host, conns):
    nodes, edges = [], []
    nodes.append(_node("zone:internet", "zone", "The internet", 0, tone="grey",
                       sub="reachability not measured - the router decides"))
    for level, label, tone in ZONES:
        rows = [r for r in live if r["exposure"]["level"] == level]
        if not rows:
            continue
        zid = "zone:%s" % level
        nodes.append(_node(zid, "zone", label, 1, tone=tone,
                           sub="%d service%s" % (len(rows), "" if len(rows) == 1 else "s")))
        if level in ("all", "lan"):
            edges.append({"from": "zone:internet", "to": zid, "label": "if the router forwards",
                          "tone": "grey", "dashed": True})
        for r in rows:
            nid = "port:%s" % r["id"]
            v = r["exposure"].get("verified") or {}
            nodes.append(_node(nid, "port", ":%d" % r["port"], 2,
                               sub=r.get("service") or r["cmd"],
                               tone=RISK_TONE.get(r["risk_band"], "grey"),
                               row=r["id"], risk=r["risk"], risk_band=r["risk_band"],
                               url=r.get("serves_url") or r.get("url"),
                               ai=bool(r.get("ai")), mcp=bool(r.get("mcp"))))
            edges.append({"from": zid, "to": nid,
                          "label": "verified on %s" % v["ip"] if v.get("accepting") else
                                   ("did not accept" if v else None),
                          "tone": tone, "dashed": bool(v and not v.get("accepting"))})
    pids = {r["pid"]: r for r in live}
    for c in (conns or [])[:120]:
        r = pids.get(c.get("pid"))
        if not r or c.get("direction") != "outbound":
            continue
        eid = "ep:%s:%s" % (c.get("raddr"), c.get("rport"))
        if not any(n["id"] == eid for n in nodes):
            nodes.append(_node(eid, "endpoint",
                               "%s:%s" % (c.get("remote_service") or c.get("raddr"),
                                          c.get("rport")), 3, sub=c.get("scope"),
                               tone="amber" if c.get("scope") == "public" else "grey"))
        edges.append({"from": "port:%s" % r["id"], "to": eid, "label": "connects to",
                      "tone": "grey", "dashed": True})
    return {"mode": "exposure", "nodes": nodes, "edges": edges,
            "layers": ["outside", "zone", "service", "talks to"]}


# -------------------------------------------------------------------- fleet
def _fleet_graph(fleet_hosts):
    nodes, edges = [], []
    for h in fleet_hosts:
        hid = "host:%s" % h["id"]
        off = [s for s in h.get("services", []) if s["exposure"] != "loopback"]
        nodes.append(_node(hid, "host", h["name"], 0,
                           sub="%d services · %d beyond localhost" % (len(h.get("services", [])),
                                                                      len(off)),
                           tone="red" if any(s["risk_band"] in ("Critical", "High")
                                             for s in h.get("services", [])) else "green"))
        for s in sorted(h.get("services", []), key=lambda s: -s["risk"])[:12]:
            nid = "%s:port:%s" % (hid, s["port"])
            nodes.append(_node(nid, "port", ":%d" % s["port"], 1,
                               sub=s.get("service") or s.get("process"),
                               tone=RISK_TONE.get(s["risk_band"], "grey"),
                               row=s.get("id"), ai=bool(s.get("ai"))))
            edges.append({"from": hid, "to": nid,
                          "label": s["exposure"] if s["exposure"] != "loopback" else None,
                          "tone": "red" if s["exposure"] == "all" else
                                  "amber" if s["exposure"] == "lan" else "grey",
                          "dashed": False})
    return {"mode": "fleet", "nodes": nodes, "edges": edges, "layers": ["host", "service"]}
