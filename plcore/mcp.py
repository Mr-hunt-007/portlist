"""Model Context Protocol detection and capability enumeration.

Two kinds of MCP server exist and only one of them has a port:

  HTTP / SSE   listens on a socket. Portlist finds it in the scan, completes a
               JSON-RPC handshake and lists what it offers.
  stdio        the common case today. It is spawned as a child of an agent and
               talks over pipes, so it holds no socket and no port scanner will
               ever see it. Portlist finds these in the process table instead.

Enumerate, never execute. Portlist calls initialize, tools/list,
resources/list and prompts/list. It never calls tools/call, never reads a
resource, and never sends a prompt. Listing what a server can do is
reconnaissance; using it is an action, and actions need a human.
"""
import json
import os
import re
import socket
import ssl
import time

PROTOCOL_VERSION = "2024-11-05"
CLIENT = {"name": "portlist", "version": "3.1"}

# Paths an HTTP MCP server usually answers on.
ENDPOINTS = ("/mcp", "/sse", "/message", "/")

# Command lines that mean "this process is an MCP server".
STDIO_PATTERNS = [
    r"@modelcontextprotocol/",
    r"\bmcp[-_]server[\w-]*",
    r"[-/]mcp\b(?!\.)",
    r"\bmodelcontextprotocol\b",
    r"\bfastmcp\b",
    r"\bmcp\s+(?:run|serve|start)\b",
]

# Tool names worth calling out: reaching this server means reaching these.
SENSITIVE_TOOLS = [
    (r"(?i)\b(read|write|edit|delete|move|create)_?file|filesystem|fs_", "filesystem access"),
    (r"(?i)\b(query|execute|sql|database|postgres|mysql|mongo)", "database access"),
    (r"(?i)\b(shell|bash|exec|command|run_|terminal|process)", "command execution"),
    (r"(?i)\b(github|gitlab|git_|repo)", "source control access"),
    (r"(?i)\b(slack|email|gmail|send_|message)", "messaging"),
    (r"(?i)\b(browser|navigate|screenshot|page_)", "browser control"),
    (r"(?i)\b(secret|credential|token|key|vault|env)", "credential access"),
    (r"(?i)\b(aws|gcp|azure|cloud|s3|bucket)", "cloud access"),
]


def _connect(port, timeout=1.2, tls=False):
    last = None
    for family, host in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            if tls:
                ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                s = ctx.wrap_socket(s, server_hostname="localhost")
            return s
        except Exception as e:
            last = e
    raise last if last else OSError("unreachable")


def _request(port, path, payload, session=None, tls=False, timeout=3.0):
    """One JSON-RPC POST. Handles plain JSON and SSE-framed replies."""
    body = json.dumps(payload).encode()
    headers = [
        "POST %s HTTP/1.1" % path,
        "Host: localhost:%d" % port,
        "User-Agent: portlist/3.1 (mcp enumerate)",
        "Content-Type: application/json",
        "Accept: application/json, text/event-stream",
        "Content-Length: %d" % len(body),
        "Connection: close",
    ]
    if session:
        headers.append("Mcp-Session-Id: " + session)
    raw = ("\r\n".join(headers) + "\r\n\r\n").encode() + body
    try:
        s = _connect(port, tls=tls)
        s.settimeout(timeout)
        s.sendall(raw)
        data, end = b"", time.time() + timeout
        while len(data) < 262144 and time.time() < end:
            try:
                chunk = s.recv(8192)
            except socket.timeout:
                break
            except Exception:
                break
            if not chunk:
                break
            data += chunk
            # SSE streams stay open; stop once a complete event has arrived.
            if b"\r\n\r\n" in data and b"event:" in data and data.rstrip().endswith(b"}"):
                break
        s.close()
    except Exception as e:
        return None, str(e)
    return _parse(data)


def _parse(data):
    if not data.startswith(b"HTTP/"):
        return None, "not http"
    head, _, body = data.partition(b"\r\n\r\n")
    status_line = head.split(b"\r\n")[0].decode("latin-1", "replace")
    parts = status_line.split()
    status = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    headers = {}
    for ln in head.split(b"\r\n")[1:]:
        k, _, v = ln.partition(b":")
        if v:
            headers[k.decode("latin-1").strip().lower()] = v.decode("latin-1").strip()

    text = body.decode("utf-8", "replace")
    # Chunked bodies: strip the size markers rather than pulling in a full parser.
    if headers.get("transfer-encoding") == "chunked":
        text = re.sub(r"(?m)^[0-9a-fA-F]+\r?$", "", text)
    # SSE frames: the payload lives on data: lines.
    if "text/event-stream" in (headers.get("content-type") or "") or "\ndata:" in text:
        chunks = re.findall(r"^data:\s*(.+)$", text, re.M)
        text = chunks[-1] if chunks else text

    obj = None
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
        except ValueError:
            obj = None
    return {"status": status, "headers": headers, "json": obj, "text": text[:400]}, None


def looks_like_mcp(port, path="/mcp", tls=False):
    """Cheap pre-check: does anything MCP-shaped answer here?

    An MCP endpoint rejects a bare GET (405, or a JSON-RPC error), which is a
    strong enough hint to justify the handshake. Without this, Portlist would
    be POSTing JSON-RPC at unrelated services.
    """
    try:
        s = _connect(port, tls=tls)
        s.settimeout(1.5)
        s.sendall(("GET %s HTTP/1.1\r\nHost: localhost:%d\r\nAccept: application/json, "
                   "text/event-stream\r\nUser-Agent: portlist/3.1\r\n"
                   "Connection: close\r\n\r\n" % (path, port)).encode())
        data = b""
        end = time.time() + 1.5
        while len(data) < 16384 and time.time() < end:
            try:
                chunk = s.recv(4096)
            except Exception:
                break
            if not chunk:
                break
            data += chunk
        s.close()
    except Exception:
        return False, None
    parsed, err = _parse(data)
    if not parsed:
        return False, None
    blob = (parsed["text"] or "").lower()
    if "jsonrpc" in blob or "mcp" in blob or "modelcontextprotocol" in blob:
        return True, parsed
    if parsed["status"] in (405, 406) or "text/event-stream" in (
            parsed["headers"].get("content-type") or ""):
        return True, parsed
    return False, parsed


def enumerate_server(port, tls=False, paths=ENDPOINTS):
    """Handshake and list capabilities. Read-only: no tool is ever invoked."""
    for path in paths:
        hint, _ = looks_like_mcp(port, path, tls)
        if not hint:
            continue
        init, err = _request(port, path, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                       "clientInfo": CLIENT}}, tls=tls)
        if not init or not init.get("json"):
            continue
        obj = init["json"]
        if "result" not in obj and "error" not in obj:
            continue

        session = init["headers"].get("mcp-session-id")
        result = obj.get("result") or {}
        info = {
            "endpoint": path,
            "transport": "sse" if "text/event-stream" in (
                init["headers"].get("content-type") or "") else "http",
            "protocol_version": result.get("protocolVersion"),
            "server": result.get("serverInfo") or {},
            "capabilities": sorted((result.get("capabilities") or {}).keys()),
            "session": bool(session),
            "authenticated": init["status"] not in (401, 403),
            "status": init["status"],
            "tools": [], "resources": [], "prompts": [],
            "errors": [],
        }
        if obj.get("error"):
            info["errors"].append(str(obj["error"])[:200])

        # Tell the server we are ready; some refuse to list before this.
        _request(port, path, {"jsonrpc": "2.0", "method": "notifications/initialized"},
                 session=session, tls=tls)

        for method, key, field in (("tools/list", "tools", "tools"),
                                   ("resources/list", "resources", "resources"),
                                   ("prompts/list", "prompts", "prompts")):
            resp, err = _request(port, path, {"jsonrpc": "2.0", "id": 2, "method": method,
                                              "params": {}}, session=session, tls=tls)
            if not resp or not resp.get("json"):
                continue
            payload = resp["json"].get("result") or {}
            items = payload.get(field) or []
            info[key] = [{"name": i.get("name") or i.get("uri") or "?",
                          "description": (i.get("description") or "")[:160]}
                         for i in items if isinstance(i, dict)][:80]
        info["sensitive"] = classify_tools(info["tools"])
        return info
    return None


def classify_tools(tools):
    """What reaching this server would actually let someone do."""
    found = {}
    for tool in tools:
        blob = tool["name"] + " " + tool.get("description", "")
        for pattern, label in SENSITIVE_TOOLS:
            if re.search(pattern, blob):
                found.setdefault(label, []).append(tool["name"])
    return [{"capability": k, "tools": sorted(set(v))[:12]} for k, v in sorted(found.items())]


# Things that merely *mention* mcp without being one: an editor with the file
# open, a grep, an interpreter given the path as an argument, Portlist itself.
STDIO_EXCLUDE = [
    r"(?:^|/)(?:python[\d.]*|node|ruby|perl)\s+-[ce]\s",   # inline script, not a server
    r"\bportlist\b",
    r"\b(?:grep|rg|ag|find|less|cat|tail|vim|nvim|emacs|code|subl)\b",
    r"\.py['\")\s]*$",                                     # a path being read, not run
    # A browser *driven by* an MCP server is not an MCP server. Playwright and
    # friends launch Chrome with a profile directory named after themselves,
    # which briefly made every renderer helper on the machine look like an
    # agent with tool access.
    r"(?i)(?:Google Chrome|Chromium|Firefox|Safari|Microsoft Edge|Brave Browser)"
    r"(?: Helper| Framework)?(?:\.app|/MacOS/|\s+--)",
    r"--type=(?:renderer|gpu-process|utility|zygote|broker|crashpad)",
]

# Flag values that carry a path. An MCP server named in one of these is a file
# the process touches, not the process itself.
PATH_FLAG = re.compile(
    r"--(?:user-data-dir|profile[\w-]*|log[\w-]*|output[\w-]*|cache[\w-]*|"
    r"storage[\w-]*|dir|cwd|config)[= ]\S+")


def find_stdio(procs, listening_pids, exclude_pids=()):
    """MCP servers that hold no socket. Invisible to every port scanner.

    These are spawned by an agent and speak over pipes. They have no exposure in
    the network sense, but they carry tool access, so they belong in the AI
    inventory even though there is no port to point at.

    One logical server is one row. A launcher and the server it execs are the
    same server seen twice, and a helper process tree underneath it is not
    seven more agents.
    """
    skip = set(exclude_pids) | {os.getpid()}
    hits = {}
    for pid, p in procs.items():
        cmd = p.get("cmdline") or ""
        if not cmd or pid in listening_pids or pid in skip:
            continue
        if any(re.search(x, cmd) for x in STDIO_EXCLUDE):
            continue
        # Match on what is being run, not on paths handed to it.
        subject = PATH_FLAG.sub("", cmd)
        for pattern in STDIO_PATTERNS:
            if re.search(pattern, subject):
                hits[pid] = {
                    "pid": pid, "ppid": p.get("ppid"), "user": p.get("user"),
                    "name": _stdio_name(subject), "cmdline": cmd[:200],
                    "uptime": p.get("uptime"), "matched": pattern,
                    "parent": _parent_name(p.get("ppid"), procs),
                }
                break

    # A launcher (npm exec @foo/mcp) and the binary it starts are one server.
    # Keep the outermost, and say how many processes it turned into.
    out, seen_cmd = [], {}
    for pid, hit in sorted(hits.items()):
        anc, ppid, depth = None, hit["ppid"], 0
        while ppid and depth < 12:
            if ppid in hits:
                anc = ppid
                break
            ppid = (procs.get(ppid) or {}).get("ppid")
            depth += 1
        if anc is not None:
            hits[anc]["children"] = hits[anc].get("children", 0) + 1
            continue
        key = (hit["name"], hit["cmdline"])
        if key in seen_cmd:
            seen_cmd[key]["instances"] = seen_cmd[key].get("instances", 1) + 1
            continue
        hit["instances"] = 1
        seen_cmd[key] = hit
        out.append(hit)
    return sorted(out, key=lambda x: x["name"])


def descendants(pid, procs, limit=40):
    """Everything this server spawned, and is therefore responsible for.

    A browser-driving MCP server is one row in the inventory and a dozen
    processes on the machine. Collapsing them keeps the list honest; hiding them
    would not - they are running, they belong to this server, and when it is
    stopped they are what is left behind.
    """
    kids = {}
    for p in procs.values():
        kids.setdefault(p.get("ppid"), []).append(p)
    out, stack, seen = [], list(kids.get(pid, [])), set()
    while stack and len(out) < limit:
        p = stack.pop(0)
        if p["pid"] in seen:
            continue
        seen.add(p["pid"])
        out.append({"pid": p["pid"], "ppid": p.get("ppid"),
                    "name": os.path.basename((p.get("cmdline") or "?").split()[0]),
                    "cmdline": (p.get("cmdline") or "")[:160],
                    "uptime": p.get("uptime"), "cpu": p.get("cpu"), "mem": p.get("mem")})
        stack.extend(kids.get(p["pid"], []))
    return out


def group_descendants(kids):
    """Seven renderer helpers are one line, not seven."""
    groups = {}
    for k in kids:
        g = groups.setdefault(k["name"], {"name": k["name"], "count": 0, "pids": [],
                                          "cmdline": k["cmdline"]})
        g["count"] += 1
        g["pids"].append(k["pid"])
    return sorted(groups.values(), key=lambda g: -g["count"])


def _stdio_name(cmd):
    m = re.search(r"@modelcontextprotocol/server-([\w-]+)", cmd)
    if m:
        return m.group(1) + " (official)"
    m = re.search(r"@([\w.-]+)/([\w.-]*mcp[\w.-]*)", cmd)      # @playwright/mcp@latest
    if m:
        return "%s/%s" % (m.group(1), m.group(2).split("@")[0])
    m = re.search(r"([\w.@/-]*mcp[\w.-]*)", cmd)
    if m:
        return os.path.basename(m.group(1)).split("@")[0] or m.group(1)
    return os.path.basename(cmd.split()[0])


def _parent_name(ppid, procs):
    p = procs.get(ppid or 0)
    if not p:
        return None
    return os.path.basename((p.get("cmdline") or "?").split()[0])
