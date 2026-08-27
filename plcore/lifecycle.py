"""Who started this, and is anyone still using it?

Two questions the port table cannot answer and every developer asks:

    "why is this alive?"    -> the thing that started it, named. Not "node", not
                               "pid 4821" - Claude Code, Cursor, a terminal you
                               closed, launchd, a container runtime.
    "can I kill it?"        -> whether it looks abandoned, with the reasons that
                               led to that guess spelled out.

Both are guesses built from evidence, and both are reported as guesses. Portlist
never stops anything on the strength of them; the most it will do is put a
service in a list called "probably leftovers" and show you why it thinks so.
"""
import os
import re
import time

# Ancestry command lines that name the thing a developer would recognise.
# Order matters: the most specific claim wins.
STARTERS = [
    ("claude-code", "Claude Code", r"(?:^|/)claude(?:\s|$)|claude-code|\bclaude\.js\b", "AI agent"),
    ("cursor", "Cursor", r"(?i)/cursor(?:\.app|/|\s)|cursor helper|cursor-agent", "AI editor"),
    ("codex", "Codex CLI", r"(?:^|/)codex(?:\s|$)|codex-cli", "AI agent"),
    ("copilot", "GitHub Copilot", r"(?i)copilot(-agent|-cli)?", "AI agent"),
    ("aider", "Aider", r"(?:^|/)aider(?:\s|$)", "AI agent"),
    ("goose", "Goose", r"(?:^|/)goose(?:\s|$)", "AI agent"),
    ("windsurf", "Windsurf", r"(?i)windsurf", "AI editor"),
    ("zed", "Zed", r"(?i)/zed(?:\.app|/|\s)", "editor"),
    ("vscode", "VS Code", r"(?i)visual studio code|/code helper|(?:^|/)code(?:\s|$)|electron.*vscode",
     "editor"),
    ("jetbrains", "JetBrains IDE", r"(?i)(intellij|pycharm|webstorm|goland|rubymine|jetbrains)",
     "editor"),
    ("docker", "a container runtime", r"(?i)dockerd|docker-proxy|containerd|com\.docker", "runtime"),
    ("tmux", "tmux", r"(?:^|/)tmux(?:\s|$)|tmux: server", "terminal"),
    ("screen", "screen", r"(?:^|/)SCREEN(?:\s|$)", "terminal"),
    ("ssh", "an SSH session", r"sshd:?\s", "remote"),
    ("cron", "cron", r"(?:^|/)(cron|crond|anacron)(?:\s|$)", "scheduler"),
    ("systemd", "systemd", r"(?:^|/)systemd(?:\s|$)", "service manager"),
    ("launchd", "launchd", r"(?:^|/)launchd(?:\s|$)", "service manager"),
    ("terminal", "a terminal", r"(?i)(iterm|terminal\.app|warp|alacritty|kitty|wezterm|hyper)",
     "terminal"),
    ("shell", "a shell", r"(?:^|/)(bash|zsh|fish|sh|dash)(?:\s|$)", "terminal"),
]

# Environment variable NAMES that identify the tool that spawned a process.
# Values are never read; the presence of the name is the whole signal.
ENV_STARTERS = [
    ("claude-code", "Claude Code", ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT",
                                    "CLAUDE_CODE_SESSION_ID"), "AI agent"),
    ("cursor", "Cursor", ("CURSOR_TRACE_ID", "CURSOR_AGENT", "CURSOR_SESSION_ID"), "AI editor"),
    ("codex", "Codex CLI", ("CODEX_SANDBOX", "CODEX_HOME", "CODEX_SESSION_ID"), "AI agent"),
    ("copilot", "GitHub Copilot", ("COPILOT_AGENT_ID", "GITHUB_COPILOT_SESSION"), "AI agent"),
    ("vscode", "VS Code", ("VSCODE_GIT_ASKPASS_NODE", "VSCODE_PID", "VSCODE_CWD"), "editor"),
    ("windsurf", "Windsurf", ("WINDSURF_SESSION_ID", "CODEIUM_API_KEY"), "AI editor"),
    ("jetbrains", "JetBrains IDE", ("IDEA_INITIAL_DIRECTORY", "PYCHARM_HOSTED"), "editor"),
    ("ci", "a CI runner", ("GITHUB_ACTIONS", "GITLAB_CI", "BUILDKITE", "CIRCLECI"), "automation"),
]

AI_KINDS = {"claude-code", "cursor", "codex", "copilot", "aider", "goose", "windsurf"}


def starter(row, chain_up, env_names=()):
    """-> {kind, name, class, pid, alive, evidence} or None.

    The ancestry is searched from the outside in, so "Claude Code" beats the
    `bash` it spawned and the `npm` that bash ran. A dead parent still counts:
    knowing the agent that started something and then exited is the whole point
    of the orphan question.
    """
    # Ancestry first, but pid 1 is not a starter - it is a reaper. A dev server
    # whose shell exited gets reparented to launchd/systemd, and reporting that
    # as "started by launchd" hides the thing you actually want to know: which
    # session started it and then went away.
    #
    # Between candidates, the specific beats the generic: a chain of
    # launchd -> zsh -> claude -> npm is "started by Claude Code", not "a shell",
    # even though the shell is closer to the top of the tree.
    REAPERS = ("launchd", "systemd")
    RANK = {"AI agent": 0, "AI editor": 0, "editor": 1, "runtime": 2, "automation": 2,
            "scheduler": 3, "remote": 3, "terminal": 4, "service manager": 5}
    candidates, fallback = [], None
    for depth, anc in enumerate(chain_up or []):
        cl = anc.get("cmdline") or anc.get("name") or ""
        for kind, label, pattern, cls in STARTERS:
            if not re.search(pattern, cl):
                continue
            hit = {"kind": kind, "name": label, "class": cls, "pid": anc.get("pid"),
                   "alive": True, "ai": kind in AI_KINDS, "via": "ancestry",
                   "evidence": "ancestor pid %s is %s" % (anc.get("pid"), cl[:70])}
            if kind in REAPERS and anc.get("pid") in (1, 0):
                fallback = fallback or hit
            else:
                candidates.append((RANK.get(cls, 6), -depth, hit))
            break
    if candidates:
        candidates.sort(key=lambda c: (c[0], c[1]))
        return candidates[0][2]
    for name in env_names or []:
        for kind, label, wanted, cls in ENV_STARTERS:
            if name in wanted:
                orphaned = bool(fallback)
                return {"kind": kind, "name": "a %s session" % label, "class": cls,
                        "pid": None, "alive": False if orphaned else None,
                        "ai": kind in AI_KINDS, "via": "environment", "reparented": orphaned,
                        "evidence": "its environment carries %s, so it was launched from a %s "
                                    "session%s" % (name, label,
                                                   " - and its parent is gone, so that session "
                                                   "has since exited" if orphaned
                                                   else "; that session may since have exited")}
    return fallback


def _short_cmd(cmdline, limit=76):
    """`/opt/homebrew/Cellar/python@3.14/…/Python -m http.server` is not what
    anyone typed. Collapse the interpreter path, keep the arguments."""
    parts = (cmdline or "").split()
    if not parts:
        return ""
    parts[0] = os.path.basename(parts[0])
    out = " ".join(parts)
    return out if len(out) <= limit else out[:limit - 1] + "…"


# The command a person would recognise, as opposed to the one the OS ended up
# running. `npm run dev` is what somebody typed; the process behind it is
# `/opt/homebrew/Cellar/node/.../bin/node /Users/.../next/dist/bin/next dev`,
# which answers a question nobody asked.
LAUNCHERS = re.compile(
    r"(?:^|/)(?:"
    r"npm|pnpm|yarn|npx|bun|deno"                       # javascript
    r"|python[\d.]*|uv|poetry|pipenv|uvicorn|gunicorn|flask|fastapi|streamlit"
    r"|ruby|rails|bundle|rake"
    r"|go|cargo|dotnet|mvn|gradle"
    r"|php|artisan|composer"
    r"|docker|docker-compose|podman"
    r"|make|just|task|air|nodemon|vite|next|nuxt|ng|expo"
    r")(?:\s|$)")


def _launcher(chain_up):
    """-> the recognisable command from the ancestry, or None.

    Walked from the process outward, so the innermost match wins: in
    zsh -> npm -> node the answer is `npm run dev`, not the shell above it and
    not the node below it. Returns None rather than a guess when nothing in the
    chain looks like something a person would have typed, and the caller then
    falls back to the process's own command line.
    """
    for anc in (chain_up or []):
        cl = (anc.get("cmdline") or "").strip()
        if not cl:
            continue
        head = cl.split()[0]
        # A shell is not a launcher: "started by zsh" is true of almost
        # everything and useful about almost nothing.
        if os.path.basename(head) in ("sh", "bash", "zsh", "fish", "dash", "login",
                                      "launchd", "systemd", "init", "tmux", "screen"):
            continue
        if LAUNCHERS.search(cl):
            return _short_cmd(cl)
    return None


def sentence(row, provenance=None, who=None, chain_up=()):
    """The one line the drawer leads with.

    ":3000 is running because Claude Code started `npm run dev` in ~/shop/frontend
    3 hours ago." Everything in it was measured; where a part is unknown the
    sentence gets shorter rather than vaguer.
    """
    what = row.get("service") or row.get("cmd") or "something"
    # A published container port is held by the engine's proxy. Saying ":6379 is
    # Redis, started by launchd running `OrbStack Helper vmgr -build-id ...` in /"
    # is true of the proxy and useless about the service: nobody started that
    # helper to get a Redis, they ran a compose file.
    c = row.get("container")
    if c:
        where = ("the %s service of the %s compose project"
                 % (c.get("service") or c.get("name"), c["project"])
                 if c.get("project") else "the %s container" % c["name"])
        line = ":%d is %s, running in %s" % (row["port"], what, where)
        if c.get("image"):
            line += " (%s)" % c["image"]
        # `docker ps --format {{.RunningFor}}` measures from *created*, not from
        # started, so a container built in April and restarted this morning
        # reported "up 4 months ago". Status says "Up 24 minutes", which is the
        # question being asked.
        if c.get("status"):
            line += ", %s" % c["status"][0].lower() + c["status"][1:]
        return line + "."
    bits = [":%d is %s" % (row["port"], what if what != "something" else "a process")]
    if who:
        bits.append("started by %s" % who["name"])
    cmd = _launcher(chain_up) or _short_cmd(row.get("cmdline") or "")
    if cmd:
        bits.append("running `%s`" % cmd)
    d = row.get("dir_short")
    if d:
        bits.append("in %s" % d)
    up = row.get("uptime")
    if up:
        bits.append("%s ago" % _dur(up))
    line = ", ".join(bits[:2]) + (" " + " ".join(bits[2:]) if len(bits) > 2 else "")
    return line.replace(" ago", " ago").strip() + "."


def _dur(s):
    s = int(s or 0)
    d, h, m = s // 86400, (s % 86400) // 3600, (s % 3600) // 60
    if d:
        return "%dd %dh" % (d, h)
    if h:
        return "%dh %dm" % (h, m)
    return "%dm" % m if m else "%ds" % s


# --------------------------------------------------------------- leftovers

DAY = 86400
# Services that are supposed to sit idle for weeks. Calling sshd a leftover
# because nobody is logged in would be worse than saying nothing.
NEVER_LEFTOVER = {"ssh", "smb", "vnc", "nginx", "apache", "caddy", "docker", "kubernetes",
                  "postgres", "mysql", "mongodb", "redis", "portlist", "rapportd",
                  "airplay", "tor", "prometheus", "grafana"}
DEV_CATS = {"Dev server", "App server", "Static file server", "AI app", "Notebook server"}


def leftover(row, procs=None, now=None):
    """-> {likely, score, reasons, idle_days} - is this an abandoned dev server?

    Deliberately conservative. Every reason is a measurement, the score is the
    sum, and nothing here ever stops a process: the output is a list called
    "probably leftovers" with its own justification attached.
    """
    now = now or time.time()
    reasons, score = [], 0
    sid = row.get("service_id")
    if sid in NEVER_LEFTOVER or row.get("quiet"):
        return {"likely": False, "score": 0, "reasons": [], "idle_days": None,
                "measured_use": False, "last_used": None, "idle_seconds": None}

    up = row.get("uptime") or 0
    days = up / DAY

    # A dev server is meant to be short-lived. One that has been up for days is
    # the shape of a thing somebody forgot.
    if row.get("service_cat") in DEV_CATS or sid in ("vite", "webpack", "bun", "pyhttp",
                                                     "express", "nextjs", "streamlit", "gradio"):
        if days >= 7:
            score += 40
            reasons.append("a dev server that has been running for %d days" % days)
        elif days >= 3:
            score += 25
            reasons.append("a dev server that has been running for %d days" % days)
        elif days >= 1:
            score += 12
            reasons.append("a dev server that has been running for %.0f hours" % (up / 3600))

    # "Nothing is connected right now" is a weak signal on its own: every dev
    # server is idle between two keystrokes. It is worth much more once Portlist
    # has been watching long enough for the silence to mean something, and worth
    # nothing at all before that.
    act = row.get("activity") or {}
    if act.get("known"):
        if not act.get("ever_busy"):
            score += 25
            reasons.append("nothing has connected to it in the %s Portlist has "
                           "been watching" % _span(act.get("watched_for")))
        else:
            idle = act.get("idle_seconds")
            if idle is not None and idle >= 7 * DAY:
                score += 30
                reasons.append("last used %s ago" % _span(idle))
            elif idle is not None and idle >= 2 * DAY:
                score += 20
                reasons.append("last used %s ago" % _span(idle))
            elif idle is not None and idle >= 6 * 3600:
                score += 10
                reasons.append("last used %s ago" % _span(idle))
    elif not row.get("conns"):
        score += 12
        reasons.append("nothing is connected to it right now")

    # Reparented to init: the shell, terminal or agent that started it is gone.
    if row.get("ppid") in (1, 0) and row.get("service_cat") in DEV_CATS:
        score += 22
        reasons.append("its parent is gone - it was reparented to the init process")

    who = row.get("starter")
    if who and who.get("class") in ("terminal", "AI agent", "AI editor") and who.get("pid"):
        if procs is not None and who["pid"] not in procs:
            score += 25
            reasons.append("the %s that started it has exited" % who["name"])

    d = row.get("dir")
    if d and os.path.isdir(d):
        try:
            age = (now - os.path.getmtime(d)) / DAY
            if age >= 7:
                score += 15
                reasons.append("its project directory has not changed in %d days" % age)
            elif age >= 3:
                score += 8
                reasons.append("its project directory has not changed in %d days" % age)
        except OSError:
            pass

    health = row.get("health")
    if health in ("down", "major"):
        score += 15
        reasons.append("it is listening but not answering properly")

    return {"likely": score >= 45, "score": min(100, score), "reasons": reasons,
            "idle_days": round(days, 1) if up else None,
            # Uptime and use are different questions and used to be reported as
            # one. This says which of the two the score actually rests on.
            "measured_use": bool(act.get("known")),
            "last_used": act.get("last_busy"),
            "idle_seconds": act.get("idle_seconds")}


def _span(seconds):
    seconds = int(seconds or 0)
    if seconds < 5400:
        return "%d minutes" % max(1, seconds // 60)
    if seconds < 172800:
        return "%d hours" % (seconds // 3600)
    return "%d days" % (seconds // 86400)


# ------------------------------------------------------------------ ignore

def ignore_path():
    from .security import data_dir
    return os.path.join(data_dir(), "ignored.json")


def ignored():
    """Ports the user has said to stop asking about. 'Ignore forever' has to
    survive a restart or it is not forever."""
    import json
    try:
        with open(ignore_path()) as f:
            return json.load(f)
    except Exception:
        return {}


def ignore(port, cmd="", note=""):
    import json
    data = ignored()
    data[str(port)] = {"port": port, "cmd": cmd, "note": note, "at": time.time()}
    tmp = ignore_path() + ".tmp"
    os.makedirs(os.path.dirname(tmp), exist_ok=True)
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, ignore_path())
    return data


def unignore(port):
    import json
    data = ignored()
    data.pop(str(port), None)
    tmp = ignore_path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, ignore_path())
    return data
