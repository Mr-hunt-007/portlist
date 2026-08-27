"""Machine-level AI exposure: one score, its reasons, and what to do about it.

Per-service risk answers "how bad is this port". This answers a different
question that no port row can: **how much of this machine has an AI agent been
handed?** It counts MCP servers, the tools they carry, the credentials those
processes inherited, the directories they were given, and the AI services that
are reachable off-box.

The score is a sum of labelled contributions, the same as the port risk model,
so it can always be read back as sentences instead of trusted as a number.
"""
from . import access, fix, mcpclients

BANDS = [(70, "Critical"), (45, "High"), (20, "Moderate"), (0, "Low")]
STRONG_DIMS = ("shell", "files", "database", "cloud", "source_control", "credentials")
DB_IDS = ("postgres", "mysql", "mongodb", "redis", "clickhouse", "elasticsearch", "opensearch")


def _band(total):
    return next(name for cut, name in BANDS if total >= cut)


def _cap(points, limit):
    return min(points, limit)


def ai_exposure(rows, stdio, decl_rows=(), shadow=(), latent=(), mcp_findings=(),
                http_shadow=()):
    """-> {score, band, reasons, estate}. `rows` must already carry `access`."""
    reasons = []

    def add(points, label, detail=None):
        if points:
            reasons.append({"points": points, "label": label, "detail": detail})

    live = [r for r in rows if not r.get("quiet")]
    ai_rows = [r for r in live if r.get("ai")]
    mcp_rows = [r for r in live if r.get("mcp")]
    agents = mcp_rows + list(stdio)

    exposed_mcp = [r for r in mcp_rows if r["exposure"]["level"] in ("all", "lan")]
    open_mcp = [r for r in exposed_mcp
                if (r["mcp"] or {}).get("authenticated") and (r["mcp"] or {}).get("status") == 200]
    if open_mcp:
        add(_cap(25 * len(open_mcp), 30),
            "%d MCP server%s answered a full handshake off-box with no authentication"
            % (len(open_mcp), "" if len(open_mcp) == 1 else "s"),
            ", ".join(":%d" % r["port"] for r in open_mcp))
    elif exposed_mcp:
        add(_cap(12 * len(exposed_mcp), 20), "%d MCP server%s reachable beyond localhost"
            % (len(exposed_mcp), "" if len(exposed_mcp) == 1 else "s"))

    caps = sorted({c for r in agents for c in (r.get("access") or {}).get("tool_capabilities", [])})
    if caps:
        add(_cap(5 * len(caps), 20),
            "agent tools grant %s" % ", ".join(caps[:5]),
            "counted once per capability, however many servers expose it")

    cred_classes, cred_owner = {}, {}
    for r in agents:
        for c in (r.get("access") or {}).get("credentials", []):
            if c["weight"] >= 3:
                cred_classes[c["class"]] = c["label"]
                cred_owner.setdefault(c["class"], r.get("service") or r.get("name") or "?")
    if cred_classes:
        add(_cap(6 * len(cred_classes), 22),
            "AI processes inherit %s" % ", ".join(sorted(cred_classes.values())),
            "; ".join("%s via %s" % (v, cred_owner[k]) for k, v in sorted(cred_classes.items())))

    wide, project = [], 0
    for r in agents:
        for g in (r.get("access") or {}).get("paths", []):
            if g["source"] != "argument":
                continue
            if g["scope"] in ("everything", "home directory", "credential store", "home folder",
                              "system"):
                wide.append(g)
            else:
                project += 1
    if wide:
        add(_cap(12 * len(wide), 24),
            "agents were given wide filesystem scope: %s"
            % ", ".join(sorted({g["short"] for g in wide})[:4]),
            "; ".join(sorted({"%s reaches %s" % (g["short"], h["path"])
                              for g in wide for h in g["reaches"]})[:4]) or None)
    elif project:
        add(2, "agents were given %d project director%s" % (project, "y" if project == 1 else "ies"))

    exposed_ai = [r for r in ai_rows if r["exposure"]["level"] in ("all", "lan")]
    if exposed_ai:
        add(_cap(8 * len(exposed_ai), 20),
            "%d AI service%s reachable beyond localhost"
            % (len(exposed_ai), "" if len(exposed_ai) == 1 else "s"),
            ", ".join("%s :%d" % (r.get("service") or "?", r["port"]) for r in exposed_ai[:5]))
    open_ai = [r for r in exposed_ai if (r.get("probe") or {}).get("auth") == "none"]
    if open_ai:
        add(_cap(6 * len(open_ai), 15),
            "%d of those answer without authentication" % len(open_ai))

    undeclared = [p["name"] for p in shadow] + [":%d" % r["port"] for r in http_shadow]
    if undeclared:
        add(_cap(4 * len(undeclared), 12),
            "%d MCP server%s running that no known client config declares"
            % (len(undeclared), "" if len(undeclared) == 1 else "s"),
            ", ".join(undeclared[:5]))

    plaintext = [f for f in mcp_findings if f["kind"] == "mcp-plaintext-secret"]
    if plaintext:
        add(_cap(6 * len(plaintext), 12),
            "%d MCP config entr%s stores a credential in plaintext"
            % (len(plaintext), "y" if len(plaintext) == 1 else "ies"))

    unreadable = [r for r in agents if not (r.get("access") or {}).get("credentials_readable", True)]
    total = max(0, min(100, sum(r["points"] for r in reasons)))
    reasons.sort(key=lambda r: -r["points"])

    return {
        "score": total,
        "band": _band(total),
        "reasons": reasons,
        "estate": {
            "mcp_http": len(mcp_rows), "mcp_stdio": len(stdio),
            "mcp_declared": len(decl_rows),
            "mcp_shadow": len(shadow) + len(http_shadow),
            "mcp_latent": len(latent),
            "ai_services": len(ai_rows), "ai_exposed": len(exposed_ai),
            "tools": sum(len(((r.get("mcp") or {}).get("tools") or [])) for r in mcp_rows),
            "capabilities": caps,
            "credential_classes": sorted(cred_classes.values()),
            "wide_paths": sorted({g["short"] for g in wide}),
        },
        "unmeasured": [ (r.get("service") or r.get("name") or "?") for r in unreadable ][:8],
    }


def headlines(rows, stdio):
    """The sentence a developer actually reacts to.

    Deliberately careful: Portlist reports that a process holds database
    credentials and that a database is listening. It does not claim they are the
    same database, because it has not tested that and will not.
    """
    out = []
    live = [r for r in rows if not r.get("quiet")]
    dbs = [r for r in live if r.get("service_id") in DB_IDS]
    agents = [r for r in live if r.get("mcp") or r.get("ai")] + list(stdio)
    for a in agents:
        acc = a.get("access") or {}
        name = a.get("service") or a.get("name") or a.get("cmd") or "an AI process"
        classes = {c["class"] for c in acc.get("credentials", [])}
        if "database" in classes and dbs:
            out.append({
                "severity": "high", "kind": "agent-reaches-database",
                "title": "%s holds database credentials, and a database is running here" % name,
                "detail": "%s has %s in its environment. %s %s listening on this machine. "
                          "Portlist has not tested whether they are the same database - it does "
                          "not connect with credentials it finds."
                          % (name,
                             ", ".join(v for c in acc["credentials"] if c["class"] == "database"
                                       for v in c["vars"][:3]),
                             ", ".join("%s :%d" % (d["service"], d["port"]) for d in dbs[:3]),
                             "is" if len(dbs) == 1 else "are"),
                "target": name})
        if "aws" in classes or "gcp" in classes or "azure" in classes:
            out.append({
                "severity": "high", "kind": "agent-holds-cloud-keys",
                "title": "%s runs with cloud credentials in scope" % name,
                "detail": "Anything that can drive this process can use them. Cloud keys in an "
                          "agent's environment are reachable by every tool that agent exposes.",
                "target": name})
        reach = [h for g in acc.get("paths", []) for h in g["reaches"] if g["source"] == "argument"]
        if reach:
            out.append({
                "severity": "high", "kind": "agent-reaches-secrets",
                "title": "%s was given a directory that contains %s" % (name, reach[0]["why"]),
                "detail": "%s is inside the scope it was handed. A filesystem tool does not stop "
                          "at the interesting files." % reach[0]["path"],
                "target": name})
    return out


SEV_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def report(rows, stdio, host, summary):
    """The security receipt: score, findings, fixes. One structure, three renderers."""
    decl, clients = mcpclients.declared()
    dirs = sorted({r["dir"] for r in rows if r.get("dir")})
    decl += mcpclients.project_configs(dirs[:20])
    http_mcp = [r for r in rows if r.get("mcp")]
    decl_rows, shadow, latent = mcpclients.reconcile(decl, stdio, http_mcp)
    declared_ports = {s.get("url") for s in decl_rows if s.get("running")}
    http_shadow = [r for r in http_mcp
                   if not any(str(r["port"]) in (u or "") for u in declared_ports)]
    mfind = mcpclients.findings(decl_rows, shadow, http_shadow)

    ai = ai_exposure(rows, stdio, decl_rows, shadow, latent, mfind, http_shadow)

    # Every finding says whether it is part of the AI story. A static file
    # server on :8787 is a real finding and belongs on the Overview; putting it
    # under "AI / MCP" because it shares a machine with an agent is how a page
    # stops meaning anything.
    findings = [dict(f, ai=True) for f in list(mfind) + headlines(rows, stdio)]
    for r in rows:
        if r.get("quiet"):
            continue
        if r["risk_band"] in ("Critical", "High"):
            findings.append({
                "ai": bool(r.get("ai") or r.get("mcp")),
                "severity": r["risk_band"].lower(), "kind": "service-risk",
                "title": "%s on :%d - %s" % (r.get("service") or r["cmd"], r["port"],
                                             r["exposure"]["label"]),
                "detail": "; ".join(x["label"] for x in (r.get("reasons") or [])[:3]),
                "target": ":%d" % r["port"], "id": r["id"],
                "fixes": fix.for_row(r)})
    for f in findings:
        f.setdefault("fixes", [])
        if not f["fixes"]:
            one = fix.for_finding(f)
            if one:
                f["fixes"] = [one]
    findings.sort(key=lambda f: SEV_RANK.get(f["severity"], 5))

    counts = {s: sum(1 for f in findings if f["severity"] == s)
              for s in ("critical", "high", "medium", "low")}
    counts["ai"] = sum(1 for f in findings if f.get("ai"))
    counts["other"] = sum(1 for f in findings if not f.get("ai"))
    return {
        "ai": ai, "findings": findings, "counts": counts,
        "clients": clients, "declared": decl_rows, "shadow": shadow, "latent": latent,
        "http_shadow": [{"port": r["port"], "pid": r["pid"], "id": r["id"]} for r in http_shadow],
        "summary": summary, "host": {"hostname": host.get("hostname"), "lan": host.get("lan", [])},
    }


def receipt(rep, width=78):
    """The terminal rendering of `report`. Short enough to read, long enough to act on."""
    L = []
    ai, est, s = rep["ai"], rep["ai"]["estate"], rep["summary"]
    L.append("PORTLIST SECURITY REPORT")
    L.append("=" * width)
    L.append("Machine            %s" % (rep["host"].get("hostname") or "?"))
    L.append("Services           %d listening, %d reachable beyond localhost"
             % (s.get("shown", 0), s.get("exposed", 0)))
    L.append("AI services        %d (%d reachable off-box)"
             % (est["ai_services"], est["ai_exposed"]))
    L.append("MCP servers        %d over HTTP, %d over stdio, %d declared, %d shadow"
             % (est["mcp_http"], est["mcp_stdio"], est["mcp_declared"], est["mcp_shadow"]))
    L.append("")
    L.append("AI EXPOSURE        %d / 100   %s" % (ai["score"], ai["band"].upper()))
    for r in ai["reasons"]:
        L.append("  +%-3d %s" % (r["points"], r["label"]))
        if r.get("detail"):
            L.append("       %s" % r["detail"])
    if not ai["reasons"]:
        L.append("  nothing scored: no MCP servers, no AI services, no inherited credentials")
    if ai["unmeasured"]:
        L.append("  note: could not read the environment of %s - reported as unknown, not clean"
                 % ", ".join(ai["unmeasured"]))
    L.append("")
    c = rep["counts"]
    L.append("FINDINGS           %d critical, %d high, %d medium"
             % (c["critical"], c["high"], c["medium"]))
    L.append("=" * width)
    for f in rep["findings"][:14]:
        L.append("")
        L.append("[%s] %s" % (f["severity"].upper(), f["title"]))
        if f.get("detail"):
            L.append("  %s" % f["detail"])
        lines = fix.cli_lines(f.get("fixes", [])[:2])
        if lines:
            L.append("  fix:")
            L.extend(lines)
    if len(rep["findings"]) > 14:
        L.append("")
        L.append("... and %d more. Run the dashboard for the full list: portlist"
                 % (len(rep["findings"]) - 14))
    if not rep["findings"]:
        L.append("")
        L.append("Nothing to act on. Everything listening is on localhost, authenticated, or both.")
    return "\n".join(L)
