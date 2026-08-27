"""Group services into the projects they came from.

"Is my project up?" is one question, and answering it with a port table makes
the developer do the join in their head. A project card does it for them:
frontend, API, database, cache and MCP server side by side, with one health
answer for the stack.

Grouping key, in order of confidence: compose project, git root, project
directory. Services that belong to no project (system daemons, an agent's stdio
server) are not forced into one - they land in "not part of a project", which is
a true statement rather than a tidy one.
"""
import os

# Which slot in a stack a service occupies. Order is display order.
ROLES = [
    ("frontend", "Frontend", {"vite", "webpack", "nextjs", "bun", "gradio", "streamlit"}),
    ("api", "API", {"uvicorn", "express", "flask", "django", "rails", "gunicorn", "fastapi"}),
    ("database", "Database", {"postgres", "mysql", "mongodb", "clickhouse"}),
    ("cache", "Cache", {"redis", "memcached"}),
    ("search", "Search", {"elasticsearch", "opensearch"}),
    ("vector", "Vector store", {"qdrant", "chroma", "weaviate", "milvus"}),
    ("ai", "AI", {"ollama", "vllm", "lmstudio", "localai", "openwebui", "jupyter", "comfyui",
                  "anythingllm", "mlflow", "langflow", "flowise", "dify", "n8n"}),
    ("mcp", "MCP", {"mcp"}),
    ("storage", "Storage", {"minio"}),
    ("proxy", "Proxy", {"nginx", "apache", "caddy", "portainer"}),
]
ROLE_OF = {sid: (key, label) for key, label, ids in ROLES for sid in ids}
ORDER = {key: i for i, (key, _, _) in enumerate(ROLES)}


def role(row):
    hit = ROLE_OF.get(row.get("service_id") or "")
    if hit:
        return hit
    cat = row.get("service_cat") or ""
    if "Dev server" in cat or "App server" in cat:
        return ("api", "App")
    return ("other", "Service")


def key_for(row):
    """-> (key, name, path) or None. What project is this part of?"""
    prov = row.get("provenance") or {}
    # The scan attaches the cheap answer (git root, else working directory);
    # a full provenance chain, when one has been built, beats it.
    for node in prov.get("chain", []):
        if node.get("kind") == "compose" and node.get("path"):
            return ("compose:" + node["path"], node["label"].replace("compose: ", ""),
                    node["path"])
    for kind in ("project", "git"):
        for node in prov.get("chain", []):
            if node.get("kind") == kind and node.get("path"):
                return (node["path"], node["label"].split(": ", 1)[-1], node["path"])
    if "project" in row:
        # The scan computed it, and None means "no project" - not "ask again".
        # Falling through to the working directory here is how /opt/homebrew
        # became a project called "homebrew".
        p = row["project"]
        return (p["key"], p["name"], p["path"]) if p else None
    d = row.get("dir")
    if d and d not in ("/", os.path.expanduser("~")):
        return (d, os.path.basename(d) or d, d)
    return None


def group(rows, with_provenance=None):
    """-> [{key, name, path, services, health, exposure, roles, leftovers}]

    `with_provenance` is an optional callable(row) -> provenance dict, used when
    the caller can afford the walk. Without it, grouping falls back to the
    working directory, which is weaker but never wrong in a different way.
    """
    live = [r for r in rows if not r.get("quiet")]
    buckets, loose = {}, []
    for r in live:
        if with_provenance and "provenance" not in r:
            try:
                r = dict(r, provenance=with_provenance(r))
            except Exception:
                pass
        k = key_for(r)
        if not k:
            loose.append(r)
            continue
        b = buckets.setdefault(k[0], {"key": k[0], "name": k[1], "path": k[2], "services": []})
        b["services"].append(r)

    out = []
    for b in buckets.values():
        out.append(_finish(b))
    if loose:
        out.append(_finish({"key": "_loose", "name": "Not part of a project", "path": None,
                            "services": loose}))
    out.sort(key=lambda p: (p["key"] == "_loose", -p["attention"], -len(p["services"])))
    return out


HEALTH_RANK = {"down": 5, "major": 4, "partial": 3, "minor": 2, "nodata": 1, "up": 0}
EXP_RANK = {"all": 3, "lan": 2, "unknown": 1, "loopback": 0}


def _finish(b):
    from . import deps, gitinfo
    svcs = b["services"]
    try:
        b["git"] = gitinfo.status(b.get("path"))
        b["git_summary"] = gitinfo.summary(b["git"])
    except Exception:
        b["git"], b["git_summary"] = None, None
    try:
        b["deps"] = deps.for_project(b.get("path"))
        b["deps_summary"] = deps.summary(b["deps"])
    except Exception:
        b["deps"], b["deps_summary"] = None, None
    for r in svcs:
        rk, label = role(r)
        r["_role"], r["_role_label"] = rk, label
    svcs.sort(key=lambda r: (ORDER.get(r["_role"], 99), r["port"]))
    worst_health = max(svcs, key=lambda r: HEALTH_RANK.get(r.get("health"), 0))
    worst_exp = max(svcs, key=lambda r: EXP_RANK.get(r["exposure"]["level"], 0))
    b["roles"] = [{"role": r["_role"], "label": r["_role_label"], "port": r["port"],
                   "service": r.get("service") or r.get("cmd"),
                   "health": r.get("health"), "exposure": r["exposure"]["level"],
                   "risk_band": r["risk_band"], "url": r.get("serves_url") or r.get("url"),
                   "id": r["id"], "leftover": bool((r.get("leftover") or {}).get("likely"))}
                  for r in svcs]
    b["count"] = len(svcs)
    b["health"] = worst_health.get("health") or "nodata"
    b["health_label"] = ("all up" if b["health"] == "up"
                         else "%s is %s" % (worst_health.get("service") or worst_health["cmd"],
                                            worst_health.get("health_label") or b["health"]))
    b["exposure"] = worst_exp["exposure"]["level"]
    b["attention"] = sum(1 for r in svcs if r["risk_band"] in ("Critical", "High"))
    b["leftovers"] = sum(1 for r in svcs if (r.get("leftover") or {}).get("likely"))
    b["ai"] = sum(1 for r in svcs if r.get("ai"))
    b["starter"] = next((r["starter"]["name"] for r in svcs if r.get("starter")), None)
    b["services"] = [r["id"] for r in svcs]
    return b
