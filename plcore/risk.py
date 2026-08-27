"""Exposure classification and risk scoring.

Every score is built from labelled contributions so the drawer can show exactly
why a row is Critical rather than asking anyone to trust a number.
"""
from . import catalog, collect

EXPOSURE = {
    "loopback": dict(level="loopback", label="Localhost only", dot="green", rank=0,
                     blurb="Bound to 127.0.0.1/::1. Only processes on this Mac can reach it."),
    "lan": dict(level="lan", label="LAN accessible", dot="amber", rank=1,
                blurb="Bound to a specific network address. Other devices on your network can reach it."),
    "all": dict(level="all", label="All interfaces", dot="red", rank=2,
                blurb="Bound to 0.0.0.0/::. Reachable from your network, and from the internet if your router forwards the port."),
    "unknown": dict(level="unknown", label="Unknown", dot="grey", rank=1,
                    blurb="Could not determine the bind address."),
}

SENS_POINTS = {"critical": 26, "high": 18, "medium": 9, "low": 3}

BANDS = [(75, "Critical"), (55, "High"), (35, "Medium"), (15, "Low"), (0, "Info")]


def classify_exposure(addrs):
    """addrs: set of bind addresses for one pid+port."""
    if any(a in collect.WILDCARD for a in addrs):
        return "all"
    if addrs and all(a in collect.LOOPBACK for a in addrs):
        return "loopback"
    if addrs:
        return "lan"
    return "unknown"


def verify_exposure(level, port, host):
    """Prove a non-loopback bind actually accepts on a real network address."""
    if level not in ("all", "lan"):
        return None
    for a in host.get("lan", []):
        if collect.reachable_from(a["ip"], port):
            return {"ip": a["ip"], "iface": a["iface"], "accepting": True,
                    "note": "Accepted a connection on %s (%s). Whether the internet can reach it "
                            "also depends on your router and firewall." % (a["ip"], a["iface"])}
        return {"ip": a["ip"], "iface": a["iface"], "accepting": False,
                "note": "Bound to all interfaces but did not accept on %s - likely filtered." % a["ip"]}
    return None


def score(row, host):
    """-> (points, band, [{label, points}])"""
    reasons = []

    def add(points, label):
        if points:
            reasons.append({"points": points, "label": label})

    exp = row["exposure"]["level"]
    if exp == "all":
        add(42, "Listening on all interfaces (0.0.0.0)")
    elif exp == "lan":
        add(28, "Listening on a network address, not just localhost")
    elif exp == "unknown":
        add(12, "Bind address could not be determined")
    else:
        add(3, "Localhost only")

    sig = row.get("service_sig")
    sens = (sig or {}).get("sensitivity", "low")
    if sig:
        add(SENS_POINTS.get(sens, 3),
            "%s is a %s-sensitivity service (%s)" % (sig["name"], sens, sig["cat"]))
    else:
        add(4, "Unidentified service")

    if sig and sig.get("ai"):
        add(8, "AI/ML asset - models, prompts, embeddings or agent credentials")

    exposed = exp in ("all", "lan")
    auth = row["probe"].get("auth")
    if auth == "none" and sens in ("critical", "high"):
        add(22 if exposed else 8, "No authentication seen on a sensitive service")
    elif auth == "none" and exposed:
        add(10, "No authentication seen and reachable off-box")
    elif auth == "required":
        add(-8, "Authentication is enforced (401/auth challenge)")
    elif auth == "forbidden":
        add(-4, "Returns 403 to unauthenticated requests")

    if row.get("user") == "root":
        add(12, "Running as root")

    if sig and sig["id"] == "pyhttp" and exposed:
        add(10, "Static file server exposing its working directory off-box")
    if sig and sig["id"] in ("docker", "kubernetes") and exposed:
        add(20, "Container/orchestrator control plane reachable off-box")
    if sig and sig["id"] == "redis" and auth == "none":
        add(20, "Redis answered PING without authentication")

    m = row.get("mcp")
    if m:
        caps = m.get("sensitive") or []
        if caps:
            add(14 if exposed else 6,
                "MCP server exposes %s" % ", ".join(c["capability"] for c in caps[:3]))
        if m.get("authenticated") and m.get("status") == 200 and exposed:
            add(24, "MCP server answered a full handshake with no authentication")
        if m.get("tools"):
            add(4, "%d MCP tools callable by anyone who reaches it" % len(m["tools"]))

    ver = row["exposure"].get("verified")
    if exposed and ver and ver.get("accepting") is False:
        add(-18, "Did not accept on the LAN address - appears filtered")
    if exposed and host.get("firewall", {}).get("enabled") and not (ver or {}).get("accepting"):
        add(-6, "macOS application firewall is on")

    total = max(0, min(100, sum(r["points"] for r in reasons)))
    band = next(name for cut, name in BANDS if total >= cut)
    reasons.sort(key=lambda r: -abs(r["points"]))
    return total, band, reasons
