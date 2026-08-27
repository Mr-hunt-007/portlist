"""Which MCP servers your AI tools are configured to run, and which are running.

An MCP server is declared in a config file by some agent or editor, then spawned
as a child process. Portlist already finds the processes; this finds the
declarations. The two lists rarely match, and the mismatch is the interesting
part:

  declared and running     the normal case
  declared, not running    latent - it starts the next time that client opens
  running, not declared    a **shadow server**: something spawned it that is not
                           in any config Portlist knows about

Config files hold secrets in plaintext. Portlist reads the *names* of env
entries and never the values, and it redacts anything secret-shaped out of the
argument lists it reports. A config with a live token sitting in it is reported
as a finding, without quoting the token.
"""
import json
import os
import re

from .access import GENERIC_SECRET, short

HOME = os.path.expanduser("~")
APPSUP = os.path.join(HOME, "Library", "Application Support")

# (id, label, path, dotted key holding the server map)
CLIENTS = [
    ("claude-desktop", "Claude Desktop",
     [os.path.join(APPSUP, "Claude", "claude_desktop_config.json"),
      os.path.join(HOME, ".config", "Claude", "claude_desktop_config.json"),
      os.path.join(os.environ.get("APPDATA", "/nonexistent"), "Claude",
                   "claude_desktop_config.json")], "mcpServers"),
    ("claude-code", "Claude Code", [os.path.join(HOME, ".claude.json")], "mcpServers"),
    ("cursor", "Cursor", [os.path.join(HOME, ".cursor", "mcp.json")], "mcpServers"),
    ("windsurf", "Windsurf",
     [os.path.join(HOME, ".codeium", "windsurf", "mcp_config.json")], "mcpServers"),
    ("vscode", "VS Code",
     [os.path.join(APPSUP, "Code", "User", "mcp.json"),
      os.path.join(HOME, ".config", "Code", "User", "mcp.json")], "servers"),
    ("vscode-settings", "VS Code (settings.json)",
     [os.path.join(APPSUP, "Code", "User", "settings.json"),
      os.path.join(HOME, ".config", "Code", "User", "settings.json")], "mcp.servers"),
    ("cline", "Cline",
     [os.path.join(APPSUP, "Code", "User", "globalStorage", "saoudrizwan.claude-dev",
                   "settings", "cline_mcp_settings.json")], "mcpServers"),
    ("zed", "Zed", [os.path.join(HOME, ".config", "zed", "settings.json")], "context_servers"),
    ("continue", "Continue", [os.path.join(HOME, ".continue", "config.json")], "mcpServers"),
    ("lmstudio", "LM Studio", [os.path.join(HOME, ".lmstudio", "mcp.json")], "mcpServers"),
    ("codex", "Codex CLI", [os.path.join(HOME, ".codex", "config.toml")], "mcp_servers"),
    ("gemini-cli", "Gemini CLI", [os.path.join(HOME, ".gemini", "settings.json")], "mcpServers"),
]

# A value that looks like a live credential rather than a setting.
SECRET_VALUE = re.compile(
    r"^(?:sk-|ghp_|gho_|github_pat_|xox[baprs]-|AKIA|ASIA|glpat-|hf_|pat_|Bearer\s+\S|"
    r"eyJ[\w-]+\.[\w-]+\.)|^[A-Za-z0-9_\-]{32,}$")


def _load_json(path):
    """Tolerant enough for the editor configs that allow comments."""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        raw = f.read()
    try:
        return json.loads(raw)
    except ValueError:
        stripped = re.sub(r"(?m)^\s*//.*$", "", raw)
        stripped = re.sub(r"/\*.*?\*/", "", stripped, flags=re.S)
        stripped = re.sub(r",(\s*[}\]])", r"\1", stripped)
        return json.loads(stripped)


def _load_toml(path):
    try:
        import tomllib
    except ImportError:
        return _toml_fallback(path)
    with open(path, "rb") as f:
        return tomllib.load(f)


def _toml_fallback(path):
    """Enough TOML to read [mcp_servers.name] blocks on Python < 3.11."""
    out, cur = {}, None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            m = re.match(r"^\[mcp_servers\.([\w.-]+)\]$", line)
            if m:
                cur = out.setdefault("mcp_servers", {}).setdefault(m.group(1), {})
                continue
            if line.startswith("["):
                cur = None
                continue
            if cur is None or "=" not in line:
                continue
            k, _, v = line.partition("=")
            v = v.strip()
            try:
                cur[k.strip()] = json.loads(v.replace("'", '"'))
            except ValueError:
                cur[k.strip()] = v.strip('"\'')
    return out


def _dig(doc, dotted):
    for part in dotted.split("."):
        if not isinstance(doc, dict):
            return None
        doc = doc.get(part)
    return doc


def _redact(args):
    """Arguments are reported; a token inside one is not."""
    out = []
    for a in args or []:
        a = str(a)
        if SECRET_VALUE.match(a.strip()) and len(a.strip()) >= 20:
            out.append("<redacted>")
        else:
            out.append(a[:120])
    return out[:12]


def _server(name, spec, client, label, path, scope="user", project=None):
    if not isinstance(spec, dict):
        return None
    env = spec.get("env") or spec.get("environment") or {}
    env_names = sorted(env.keys()) if isinstance(env, dict) else []
    inline = []
    if isinstance(env, dict):
        for k, v in env.items():
            if isinstance(v, str) and v and not v.startswith("${") and (
                    SECRET_VALUE.match(v.strip()) or GENERIC_SECRET.search(k.upper())):
                if not (v.startswith("$") or v.startswith("%")):
                    inline.append(k)
    url = spec.get("url") or spec.get("serverUrl") or spec.get("httpUrl")
    cmd = spec.get("command") or ""
    transport = spec.get("type") or spec.get("transport") or ("http" if url else "stdio")
    return {
        "name": name, "client": client, "client_label": label,
        "config": short(path), "scope": scope, "project": short(project) if project else None,
        "transport": transport, "command": cmd, "command_short": os.path.basename(cmd) if cmd else "",
        "args": _redact(spec.get("args")), "url": url,
        "env_names": env_names, "inline_secrets": sorted(inline),
        "disabled": bool(spec.get("disabled") or spec.get("enabled") is False),
    }


def declared():
    """-> (servers, clients). Every MCP server any known client is set up to run."""
    servers, clients = [], []
    for cid, label, paths, key in CLIENTS:
        for path in paths:
            if not os.path.isfile(path):
                continue
            entry = {"id": cid, "label": label, "path": short(path), "servers": 0, "error": None}
            try:
                doc = _load_toml(path) if path.endswith(".toml") else _load_json(path)
                found = _dig(doc, key) or {}
                for name, spec in (found.items() if isinstance(found, dict) else []):
                    s = _server(name, spec, cid, label, path)
                    if s:
                        servers.append(s)
                # Claude Code keeps a second, per-project set of servers.
                for proj, pdoc in (doc.get("projects") or {}).items() \
                        if isinstance(doc, dict) else []:
                    for name, spec in ((pdoc.get("mcpServers") or {}).items()
                                       if isinstance(pdoc, dict) else []):
                        s = _server(name, spec, cid, label, path, scope="project", project=proj)
                        if s:
                            servers.append(s)
                entry["servers"] = sum(1 for s in servers if s["client"] == cid)
            except Exception as e:
                entry["error"] = str(e)[:160]
            clients.append(entry)
            break                      # one config per client is enough
    plugins = claude_plugins()
    if plugins:
        servers += plugins
        clients.append({"id": "claude-plugin", "label": "Claude Code plugins",
                        "path": "~/.claude/plugins/installed_plugins.json",
                        "servers": len(plugins), "error": None})
    servers.sort(key=lambda s: (s["client"], s["name"]))
    return servers, clients


def claude_plugins():
    """Claude Code plugins ship their own MCP servers.

    They are declared nowhere near the user's config: each installed plugin
    carries a .mcp.json inside its install directory. Reading only ~/.claude.json
    reported every plugin server on the machine as a shadow server.
    """
    out = []
    reg = os.path.join(HOME, ".claude", "plugins", "installed_plugins.json")
    if not os.path.isfile(reg):
        return out
    try:
        doc = _load_json(reg)
    except Exception:
        return out
    for name, installs in (doc.get("plugins") or {}).items():
        for inst in (installs if isinstance(installs, list) else [installs]):
            path = os.path.join(inst.get("installPath", ""), ".mcp.json")
            if not os.path.isfile(path):
                continue
            try:
                doc2 = _load_json(path)
            except Exception:
                continue
            # Plugin manifests put the servers at the top level; some nest them.
            found = doc2.get("mcpServers") if isinstance(doc2.get("mcpServers"), dict) else doc2
            for sname, spec in (found.items() if isinstance(found, dict) else []):
                if not isinstance(spec, dict) or not (spec.get("command") or spec.get("url")):
                    continue
                srv = _server(sname, spec, "claude-plugin",
                              "Claude Code plugin (%s)" % name.split("@")[0], path,
                              scope="plugin")
                if srv:
                    out.append(srv)
    return out


def project_configs(dirs):
    """.mcp.json / .cursor/mcp.json next to the code a service runs from."""
    out = []
    for d in dirs or []:
        for rel, client, label, key in ((".mcp.json", "project", "Project (.mcp.json)", "mcpServers"),
                                        (os.path.join(".cursor", "mcp.json"), "cursor",
                                         "Cursor (project)", "mcpServers"),
                                        (os.path.join(".vscode", "mcp.json"), "vscode",
                                         "VS Code (project)", "servers")):
            path = os.path.join(d, rel)
            if not os.path.isfile(path):
                continue
            try:
                found = _dig(_load_json(path), key) or {}
            except Exception:
                continue
            for name, spec in (found.items() if isinstance(found, dict) else []):
                s = _server(name, spec, client, label, path, scope="project", project=d)
                if s:
                    out.append(s)
    return out


# ------------------------------------------------------------------ matching
_WORD = re.compile(r"[\w.@/-]+")


def _tokens(text):
    return {t.strip("'\"") for t in _WORD.findall(text or "") if len(t) > 2}


def _key_bits(server):
    """The distinctive parts of a declaration: the binary and its real arguments."""
    bits = set()
    cmd = server.get("command") or ""
    if cmd:
        bits.add(os.path.basename(cmd))
        bits.add(cmd)
    for a in server.get("args") or []:
        if a.startswith("-") or a == "<redacted>":
            continue
        bits.add(a)
        if "/" in a:
            bits.add(os.path.basename(a))
    return {b for b in bits if len(b) > 2}


def reconcile(declared_servers, running_stdio, http_rows=()):
    """Match declarations against processes. -> (rows, shadow, latent)

    Matching is on the command and its arguments, not the name: the name only
    exists inside the config, and the process table never sees it.
    """
    rows, used = [], set()
    for s in declared_servers:
        hit = None
        bits = _key_bits(s)
        for proc in running_stdio:
            toks = _tokens(proc.get("cmdline"))
            score = len(bits & toks)
            if bits and score >= max(1, min(2, len(bits))):
                hit = proc
                break
            if s.get("command") and s["command"] in (proc.get("cmdline") or ""):
                hit = proc
                break
        if hit is None and s.get("url"):
            for r in http_rows:
                if str(r.get("port")) and (":%d" % r["port"]) in (s["url"] or ""):
                    hit = {"pid": r["pid"], "cmdline": r.get("cmdline"), "port": r["port"]}
                    break
        if hit:
            used.add(hit.get("pid"))
        rows.append({**s, "running": bool(hit), "pid": (hit or {}).get("pid"),
                     "state": "disabled" if s["disabled"] else ("running" if hit else "declared")})
    shadow = [p for p in running_stdio if p.get("pid") not in used]
    latent = [r for r in rows if r["state"] == "declared"]
    return rows, shadow, latent


def findings(rows, shadow, http_shadow=()):
    """Plain statements about the MCP estate. Each one is actionable or it is not here."""
    out = []
    for s in rows:
        if s["inline_secrets"]:
            out.append({
                "severity": "high", "kind": "mcp-plaintext-secret",
                "title": "%s stores a credential in plaintext" % s["name"],
                "detail": "%s in %s holds %s directly in the config file. Anything that can read "
                          "that file - a backup, a sync client, another agent - has the credential."
                          % (s["name"], s["config"], ", ".join(s["inline_secrets"])),
                "target": s["name"]})
    for p in shadow:
        out.append({
            "severity": "medium", "kind": "shadow-mcp",
            "title": "%s is running but is not in any config Portlist knows" % p["name"],
            "detail": "pid %s, started by %s. Either it came from a client Portlist does not "
                      "read yet, or something spawned it outside your MCP configuration."
                      % (p["pid"], p.get("parent") or "an unknown parent"),
            "target": p["name"]})
    for r in http_shadow:
        out.append({
            "severity": "medium", "kind": "shadow-mcp-http",
            "title": "MCP server on :%d is not declared in any client config" % r["port"],
            "detail": "It completed an MCP handshake on port %d but no known client is configured "
                      "to use it." % r["port"],
            "target": ":%d" % r["port"]})
    return out
