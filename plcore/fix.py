"""How to close what Portlist found - as instructions, not as an action.

Every fix here is text you run yourself. Portlist prints the command and the
consequence; you decide. That is deliberate: the fastest way to take down
someone's production database is a security tool that "helpfully" rebinds it.

A fix has a `verify` line wherever one exists, because a remediation you cannot
confirm is a belief, not a change.
"""

# Per service: how to put this specific thing back on localhost.
BIND = {
    "postgres": dict(
        title="Bind PostgreSQL to localhost",
        steps=["Set listen_addresses = 'localhost' in postgresql.conf",
               "Restrict host lines in pg_hba.conf to 127.0.0.1/32",
               "Reload: pg_ctl reload   (or: brew services restart postgresql)"],
        docker="docker run -p 127.0.0.1:5432:5432 ...   (not -p 5432:5432)",
        verify="psql -h <your-lan-ip> -U postgres  should now fail to connect"),
    "mysql": dict(
        title="Bind MySQL to localhost",
        steps=["Set bind-address = 127.0.0.1 in my.cnf",
               "Restart the server"],
        docker="docker run -p 127.0.0.1:3306:3306 ...",
        verify="mysql -h <your-lan-ip>  should now be refused"),
    "mongodb": dict(
        title="Bind MongoDB to localhost and require auth",
        steps=["Set net.bindIp: 127.0.0.1 in mongod.conf",
               "Set security.authorization: enabled",
               "Restart mongod"],
        docker="docker run -p 127.0.0.1:27017:27017 ...",
        verify="mongosh --host <your-lan-ip>  should now be refused"),
    "redis": dict(
        title="Bind Redis to localhost and set a password",
        steps=["bind 127.0.0.1 -::1     in redis.conf",
               "requirepass <a long random string>",
               "protected-mode yes",
               "redis-cli shutdown nosave  then start it again"],
        docker="docker run -p 127.0.0.1:6379:6379 ...",
        verify="redis-cli -h <your-lan-ip> PING  should fail or ask for AUTH"),
    "elasticsearch": dict(
        title="Bind Elasticsearch to localhost",
        steps=["network.host: 127.0.0.1 in elasticsearch.yml",
               "Enable xpack.security.enabled: true",
               "Restart the node"],
        verify="curl http://<your-lan-ip>:9200  should not answer"),
    "clickhouse": dict(
        title="Bind ClickHouse to localhost",
        steps=["<listen_host>127.0.0.1</listen_host> in config.xml",
               "Restart clickhouse-server"]),
    "minio": dict(
        title="Restrict MinIO",
        steps=["Run with --address 127.0.0.1:9000 --console-address 127.0.0.1:9001",
               "Rotate MINIO_ROOT_PASSWORD if the console was reachable"]),
    "ollama": dict(
        title="Keep Ollama on localhost",
        steps=["Unset OLLAMA_HOST, or set OLLAMA_HOST=127.0.0.1:11434",
               "launchctl setenv OLLAMA_HOST 127.0.0.1:11434  (macOS app)",
               "Restart Ollama"],
        verify="curl http://<your-lan-ip>:11434/api/tags  should not answer",
        note="Ollama has no authentication. Anyone who reaches it can run inference, "
             "pull models and read every model name on the machine."),
    "vllm": dict(
        title="Keep vLLM on localhost",
        steps=["Start with --host 127.0.0.1",
               "If it must be reachable, put it behind a reverse proxy with auth "
               "and start it with --api-key <key>"]),
    "jupyter": dict(
        title="Lock down Jupyter",
        steps=["jupyter server --ip 127.0.0.1",
               "Never run with --NotebookApp.token='' or --allow-root on a shared network",
               "jupyter server password   to set one"],
        note="A reachable notebook without a token is remote code execution as your user."),
    "comfyui": dict(
        title="Keep ComfyUI on localhost",
        steps=["Start without --listen, or with --listen 127.0.0.1"],
        note="ComfyUI can load custom nodes, which run arbitrary Python."),
    "openwebui": dict(
        title="Restrict Open WebUI",
        steps=["Publish it on 127.0.0.1 only, or put it behind a proxy that authenticates",
               "docker run -p 127.0.0.1:3000:8080 ..."]),
    "n8n": dict(
        title="Restrict n8n",
        steps=["N8N_HOST=127.0.0.1 and publish on 127.0.0.1 only",
               "Set N8N_BASIC_AUTH_ACTIVE=true with a real password"],
        note="n8n workflows hold credentials for everything they automate."),
    "docker": dict(
        title="Close the Docker API",
        steps=["Do not publish 2375/2376. Use the unix socket instead",
               "If remote access is genuinely needed, use TLS client certificates"],
        note="Reaching the Docker API is root on the host. There is no lesser reading of it."),
    "kubernetes": dict(
        title="Close the Kubernetes API",
        steps=["Bind the apiserver to a private address",
               "Confirm anonymous-auth=false"]),
    "grafana": dict(
        title="Restrict Grafana",
        steps=["http_addr = 127.0.0.1 in grafana.ini",
               "Change the default admin password if it was ever reachable"]),
    "chromedev": dict(
        title="Close the browser debugging port",
        steps=["Quit the browser started with --remote-debugging-port",
               "Never start it with --remote-debugging-address=0.0.0.0"],
        note="The DevTools protocol reads every cookie and session in that browser."),
    "pyhttp": dict(
        title="Stop serving this directory",
        steps=["kill {pid}    # this process, serving {dir}",
               "or put it back on localhost:",
               "cd {dir} && python3 -m http.server {port} --bind 127.0.0.1"],
        note="python -m http.server serves its working directory with no auth and no filter. "
             "Right now that directory is {dir}."),
    "qdrant": dict(title="Restrict Qdrant",
                   steps=["Publish on 127.0.0.1 only", "Set an API key in config"]),
    "chroma": dict(title="Restrict Chroma", steps=["Publish on 127.0.0.1 only"]),
    "smb": dict(title="Turn off file sharing",
                steps=["System Settings > General > Sharing > File Sharing: off"]),
    "vnc": dict(title="Turn off screen sharing",
                steps=["System Settings > General > Sharing > Screen Sharing: off"]),
}

GENERIC_BIND = dict(
    title="Bind this service to localhost",
    steps=["kill {pid}    # {cmd}, running from {dir}",
           "then start it again with its bind address set to 127.0.0.1",
           "in Docker that is: -p 127.0.0.1:{port}:{port}"])


def _fill(spec, row):
    """Put this service's own pid, port and directory into the instructions.

    "Stop the process" is not an instruction, it is a category. The steps say
    which process, from which directory, on which port - because the person
    reading them is looking at a list of six services that all say Python.
    """
    ctx = {"pid": row.get("pid"), "port": row.get("port"),
           "dir": row.get("dir_short") or row.get("dir") or ".",
           "cmd": row.get("cmd") or "the process",
           "service": row.get("service") or row.get("cmd") or "it"}
    out = dict(spec)
    for field in ("steps",):
        out[field] = [_sub(x, ctx) for x in spec.get(field, [])]
    for field in ("title", "note", "verify", "docker", "why"):
        if spec.get(field):
            out[field] = _sub(spec[field], ctx)
    return out


def _sub(text, ctx):
    try:
        return text.format(**ctx)
    except (KeyError, IndexError, ValueError):
        return text


def for_row(row):
    """-> [{title, why, steps, verify, note, severity}] for one service."""
    out = []
    exp = row.get("exposure", {}).get("level")
    sid = row.get("service_id")
    exposed = exp in ("all", "lan")
    auth = (row.get("probe") or {}).get("auth")
    sens = row.get("sensitivity", "low")

    if exposed:
        spec = _fill(BIND.get(sid) or GENERIC_BIND, row)
        spec["why"] = ("This is reachable from %s. Bringing it back to 127.0.0.1 removes the "
                       "exposure without touching anything else."
                       % ("your whole network and possibly beyond"
                          if exp == "all" else "other devices on your network"))
        spec["severity"] = "critical" if sens == "critical" else "high"
        spec.setdefault("verify", "portlist scan   should show 'Localhost only'")
        if not any("kill" in step for step in spec.get("steps", [])):
            spec["steps"] = list(spec["steps"]) + [
                "if you would rather it were simply gone: kill %s   # %s"
                % (row.get("pid"), row.get("cmd") or "this process")]
        out.append(spec)

    if auth == "none" and sens in ("critical", "high"):
        out.append(dict(
            title="Put authentication in front of it",
            why="Portlist reached it without credentials and it handles sensitive data.",
            severity="high" if exposed else "medium",
            steps=["Enable the service's own authentication (see its docs)",
                   "Or front it with a reverse proxy that requires a password",
                   "Rotate anything it exposed while it was open"]))

    if row.get("user") == "root" and exposed:
        out.append(dict(
            title="Stop running it as root",
            why="A flaw in a root-owned listener is a whole-machine compromise, not a service one.",
            severity="medium",
            steps=["Run it under a dedicated user account",
                   "Or drop privileges after binding the port"]))

    m = row.get("mcp")
    if m and (m.get("sensitive") or []) and exposed:
        out.append(dict(
            title="Take this MCP server off the network",
            why="Its tools grant %s. Anyone who reaches the port can call them."
                % ", ".join(c["capability"] for c in m["sensitive"][:3]),
            severity="critical",
            steps=["Bind the MCP server to 127.0.0.1",
                   "If it must be remote, require an Authorization header and use TLS",
                   "Reduce its tool set to what the agent actually needs"]))

    acc = row.get("access") or {}
    strong = [c for c in acc.get("credentials", []) if c["weight"] >= 3]
    if strong and (exposed or (row.get("mcp") or row.get("ai"))):
        out.append(dict(
            title="Reduce what it inherits",
            why="It runs with %s in its environment. Whatever reaches this process reaches those."
                % ", ".join(c["label"].lower() for c in strong[:3]),
            severity="high" if exposed else "medium",
            steps=["Start it from a shell that does not export those variables",
                   "Or scope the credential down: a read-only token, a restricted role",
                   "Prefer short-lived credentials over long-lived keys"]))

    wide = [g for g in acc.get("paths", []) if g["scope"] in
            ("everything", "home directory", "credential store", "home folder")
            and g["source"] == "argument"]
    if wide:
        g = wide[0]
        reach = g["reaches"][0]["path"] if g["reaches"] else None
        out.append(dict(
            title="Narrow the directories it was given",
            why="%s is in scope%s. Filesystem tools do not stop at the interesting files."
                % (g["short"], " and %s is inside it" % reach if reach else ""),
            severity="high",
            steps=["Pass only the project directories it actually needs",
                   "Never pass ~ or / to a filesystem server",
                   "Restart it and re-check"]))
    return out


def for_finding(f):
    """Fixes for the machine-level findings that are not tied to one port."""
    kind = f.get("kind")
    if kind == "mcp-plaintext-secret":
        return dict(title="Move that credential out of the config file",
                    steps=["Replace the literal value with ${ENV_VAR} if the client supports it",
                           "Otherwise store it in the keychain and inject at launch",
                           "Rotate the credential: it has been on disk in cleartext",
                           "chmod 600 the config file either way"])
    if kind == "agent-reaches-secrets":
        return dict(title="Narrow the scope you handed it",
                    steps=["Restart the server with only the project directories it needs",
                           "Never pass ~ or / to a tool that can read files",
                           "If it already ran with that scope, treat the keys inside as seen"])
    if kind == "agent-holds-cloud-keys":
        return dict(title="Take the cloud keys out of its environment",
                    steps=["Launch the agent from a shell without those variables exported",
                           "Give it a scoped, short-lived credential if it genuinely needs one",
                           "Prefer a role with read-only access over a long-lived key"])
    if kind == "agent-reaches-database":
        return dict(title="Scope the database credential",
                    steps=["Point the agent at a read-only role, or a copy of the data",
                           "Keep production connection strings out of agent environments",
                           "Rotate the credential if an exposed tool could read it"])
    if kind in ("shadow-mcp", "shadow-mcp-http"):
        return dict(title="Account for it or stop it",
                    steps=["Find the parent process to see what started it",
                           "If you recognise it, add it to a client config so it is inventoried",
                           "If you do not, stop it and look at what spawned it"])
    return None


def cli_lines(fixes):
    """The same advice, flattened for a terminal."""
    lines = []
    for f in fixes:
        lines.append("  %s" % f["title"])
        if f.get("why"):
            lines.append("    %s" % f["why"])
        for s in f.get("steps", []):
            lines.append("      - %s" % s)
        if f.get("docker"):
            lines.append("      - docker: %s" % f["docker"])
        if f.get("note"):
            lines.append("      note: %s" % f["note"])
        if f.get("verify"):
            lines.append("      verify: %s" % f["verify"])
    return lines
