"""Coding-agent sessions: the ones you left open, and what they were about.

Portlist's answer to "what is running" has always stopped at the process. A
`claude` process tells you almost nothing: same name, same command, five of them,
one six days old. What you actually want to know is which conversation it is,
what it was for, how much context it is carrying, and whether you still need it.

That is on disk. Claude Code writes a transcript per session under
`~/.claude/projects/<slugified-cwd>/<session-id>.jsonl`, and Codex writes one
under `~/.codex/sessions/<date>/rollout-*.jsonl`. Both carry the first prompt,
the running token usage, and a timestamp per record.

Three things this module is careful about.

**It reads, and only locally.** Prompts are the most personal thing on the
machine. Nothing here goes into `/llm.txt`, the manifest, or an agent report -
`REDACT` in `agent.py` drops it, and the endpoint is local-only. A tool that
quietly shipped your prompts to a central server would be indefensible.

**It never reads a whole transcript.** They reach eight megabytes. The head has
the first prompt and the working directory; the tail has the title, the latest
usage and the last activity. Both ends, nothing in between.

**A process is matched to a session only when it can be.** Four `claude`
processes in one directory cannot be told apart from the outside, so they are
reported as four processes against that project rather than guessed one-to-one.
"""
import json
import os
import re
import time

CLAUDE_ROOT = "~/.claude/projects"
CODEX_ROOT = "~/.codex/sessions"
COPILOT_DB = "~/.copilot/session-store.db"
# Cursor is a VS Code fork and keeps chats in the same place under its own name.
VSCODE_CHAT = ("~/Library/Application Support/Code/User/workspaceStorage/*/chatSessions/*.jsonl",
               "~/.config/Code/User/workspaceStorage/*/chatSessions/*.jsonl")
CURSOR_CHAT = ("~/Library/Application Support/Cursor/User/workspaceStorage/*/chatSessions/*.jsonl",
               "~/.config/Cursor/User/workspaceStorage/*/chatSessions/*.jsonl")
# Gemini CLI keeps a per-project scratch directory; older builds wrote logs.json.
GEMINI_GLOBS = ("~/.gemini/tmp/*/logs.json", "~/.gemini/tmp/*/chats/*.json",
                "~/.gemini/history/*.json")
HEAD_BYTES = 96 * 1024
TAIL_BYTES = 256 * 1024
MAX_SESSIONS = 60
# Processes that are a coding-agent session rather than something it spawned.
AGENT_NAMES = ("claude", "codex")


def _root(path):
    return os.path.expanduser(path)


def slug(cwd):
    """`/Users/me/Downloads` -> `-Users-me-Downloads`, the way Claude Code names
    its transcript directories."""
    return (cwd or "").replace("/", "-").replace(".", "-").replace("_", "-")


def _tail(path, n):
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            if size > n:
                f.seek(size - n)
                f.readline()          # drop the partial line we landed in
            return f.read().decode("utf-8", "replace")
    except OSError:
        return ""


def _head(path, n):
    try:
        with open(path, "rb") as f:
            return f.read(n).decode("utf-8", "replace")
    except OSError:
        return ""


def _lines(text):
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def _text_of(content):
    """Claude and Codex both allow a string or a list of parts."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in ("text", "input_text") and part.get("text"):
                return part["text"]
    return ""


def _stamp(value):
    if not value:
        return None
    try:
        # 2026-08-20T09:51:42.582Z
        return time.mktime(time.strptime(value[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
    except (ValueError, TypeError):
        return None


def read_claude(path):
    rec = {"tool": "claude", "id": os.path.basename(path)[:-6], "path": path,
           "title": None, "first_prompt": None, "last_prompt": None,
           "summary": None, "cwd": None, "model": None, "context": None,
           "turns": 0, "started": None, "last_active": None}
    try:
        rec["bytes"] = os.path.getsize(path)
        rec["last_active"] = os.path.getmtime(path)
    except OSError:
        rec["bytes"] = 0

    for d in _lines(_head(path, HEAD_BYTES)):
        rec["cwd"] = d.get("cwd") or rec["cwd"]
        if rec["started"] is None:
            rec["started"] = _stamp(d.get("timestamp"))
        if rec["first_prompt"] is None and d.get("type") == "user":
            body = _text_of((d.get("message") or {}).get("content"))
            # Skip the harness's own injected turns; they are not what you typed.
            if body and not body.startswith("<") and "system-reminder" not in body[:60]:
                rec["first_prompt"] = body.strip()

    for d in _lines(_tail(path, TAIL_BYTES)):
        t = d.get("type")
        if t == "ai-title" and d.get("aiTitle"):
            rec["title"] = d["aiTitle"]
        elif t == "last-prompt" and d.get("lastPrompt"):
            rec["last_prompt"] = d["lastPrompt"]
        elif t == "system" and d.get("subtype") == "away_summary" and d.get("content"):
            rec["summary"] = d["content"]
        elif t == "assistant":
            m = d.get("message") or {}
            rec["model"] = m.get("model") or rec["model"]
            u = m.get("usage") or {}
            if u:
                # What the model was carrying on that turn: fresh input plus
                # everything read from or written to the cache. This is the
                # number people mean by "how full is this session".
                rec["context"] = ((u.get("input_tokens") or 0)
                                  + (u.get("cache_read_input_tokens") or 0)
                                  + (u.get("cache_creation_input_tokens") or 0))
            rec["turns"] += 1
        ts = _stamp(d.get("timestamp"))
        if ts:
            rec["last_active"] = max(rec["last_active"] or 0, ts)
    return rec


def read_codex(path):
    rec = {"tool": "codex", "id": os.path.basename(path)[:-6], "path": path,
           "title": None, "first_prompt": None, "last_prompt": None,
           "summary": None, "cwd": None, "model": None, "context": None,
           "turns": 0, "started": None, "last_active": None}
    try:
        rec["bytes"] = os.path.getsize(path)
        rec["last_active"] = os.path.getmtime(path)
    except OSError:
        rec["bytes"] = 0

    for d in _lines(_head(path, HEAD_BYTES)):
        p = d.get("payload") or {}
        if d.get("type") == "session_meta":
            rec["id"] = p.get("id") or rec["id"]
            rec["cwd"] = p.get("cwd") or p.get("cwd_path") or rec["cwd"]
            rec["started"] = _stamp(d.get("timestamp") or p.get("timestamp"))
            inst = p.get("instructions")
            if isinstance(inst, str) and inst.strip():
                rec["summary"] = inst.strip()[:400]
        if rec["first_prompt"] is None and p.get("role") == "user":
            body = _text_of(p.get("content"))
            if body and not body.startswith("<"):
                rec["first_prompt"] = body.strip()

    for d in _lines(_tail(path, TAIL_BYTES)):
        p = d.get("payload") or {}
        if p.get("role") == "user":
            body = _text_of(p.get("content"))
            if body and not body.startswith("<"):
                rec["last_prompt"] = body.strip()
        if p.get("role") == "assistant":
            rec["turns"] += 1
        u = p.get("usage") or p.get("token_usage") or {}
        if isinstance(u, dict) and u:
            rec["context"] = (u.get("total_tokens")
                              or ((u.get("input_tokens") or 0)
                                  + (u.get("cached_input_tokens") or 0))
                              or rec["context"])
        if p.get("model"):
            rec["model"] = p["model"]
        ts = _stamp(d.get("timestamp"))
        if ts:
            rec["last_active"] = max(rec["last_active"] or 0, ts)
    return rec


def read_copilot(path, row=None, turns=None):
    """GitHub Copilot CLI. It keeps a SQLite store beside a 9 MB event log, and
    the store has everything worth showing - including its own summary."""
    rec = {"tool": "copilot", "id": (row or {}).get("id") or os.path.basename(path),
           "path": path, "title": None, "first_prompt": None, "last_prompt": None,
           "summary": None, "cwd": None, "model": None, "context": None,
           "turns": 0, "started": None, "last_active": None, "bytes": 0}
    if not row:
        return rec
    rec["cwd"] = row.get("cwd")
    rec["summary"] = (row.get("summary") or "").strip() or None
    if rec["summary"]:
        rec["title"] = " ".join(rec["summary"].split())[:70]
    rec["started"] = _stamp(row.get("created_at"))
    rec["last_active"] = _stamp(row.get("updated_at")) or rec["started"]
    if row.get("branch"):
        rec["branch"] = row["branch"]
    for t in (turns or []):
        rec["turns"] += 1
        msg = (t.get("user_message") or "").strip()
        if msg:
            if rec["first_prompt"] is None:
                rec["first_prompt"] = msg
            rec["last_prompt"] = msg
    return rec


def _copilot_sessions():
    """-> [(mtime, path, reader)] for the Copilot CLI store, read-only."""
    import sqlite3
    db = _root(COPILOT_DB)
    if not os.path.isfile(db):
        return []
    out = []
    try:
        con = sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=1.0)
        con.row_factory = sqlite3.Row
        rows = con.execute("select * from sessions order by updated_at desc "
                           "limit ?", (MAX_SESSIONS,)).fetchall()
        for r in rows:
            row = dict(r)
            turns = [dict(t) for t in con.execute(
                "select user_message, assistant_response, timestamp from turns "
                "where session_id = ? order by turn_index", (row["id"],)).fetchall()]
            rec = read_copilot(db, row, turns)
            out.append(((rec.get("last_active") or 0), db,
                        (lambda _p, _rec=rec: _rec)))
        con.close()
    except Exception:
        return []
    return out


def read_vscode(path, tool="vscode"):
    """VS Code / Cursor chat panel. One JSONL per session; the first record is a
    header with the title and the responder, the rest are the exchange."""
    rec = {"tool": tool, "id": os.path.basename(path)[:-6], "path": path,
           "title": None, "first_prompt": None, "last_prompt": None,
           "summary": None, "cwd": None, "model": None, "context": None,
           "turns": 0, "started": None, "last_active": None}
    try:
        rec["bytes"] = os.path.getsize(path)
        rec["last_active"] = os.path.getmtime(path)
    except OSError:
        rec["bytes"] = 0
    for d in _lines(_head(path, HEAD_BYTES)):
        v = d.get("v") if isinstance(d.get("v"), dict) else d
        if not isinstance(v, dict):
            continue
        if v.get("responderUsername"):
            rec["model"] = v["responderUsername"]
        if v.get("customTitle") and not rec["title"]:
            rec["title"] = v["customTitle"]
        if v.get("creationDate") and not rec["started"]:
            try:
                rec["started"] = float(v["creationDate"]) / 1000.0
            except (TypeError, ValueError):
                pass
        for req in (v.get("requests") or []):
            rec["turns"] += 1
            text = ((req.get("message") or {}).get("text")
                    or _text_of((req.get("message") or {}).get("parts")))
            if text:
                if rec["first_prompt"] is None:
                    rec["first_prompt"] = text.strip()
                rec["last_prompt"] = text.strip()
        msg = v.get("message") or {}
        text = msg.get("text") if isinstance(msg, dict) else None
        if text and rec["first_prompt"] is None:
            rec["first_prompt"] = str(text).strip()
    if not rec["title"] and rec["first_prompt"]:
        rec["title"] = " ".join(rec["first_prompt"].split())[:70]
    return rec


def read_gemini(path):
    """Gemini CLI. Its layout has moved between releases, so this reads what it
    recognises and reports the rest as an untitled session rather than guessing."""
    rec = {"tool": "gemini", "id": os.path.basename(path).rsplit(".", 1)[0],
           "path": path, "title": None, "first_prompt": None, "last_prompt": None,
           "summary": None, "cwd": os.path.basename(os.path.dirname(path)),
           "model": None, "context": None, "turns": 0, "started": None,
           "last_active": None}
    try:
        rec["bytes"] = os.path.getsize(path)
        rec["last_active"] = os.path.getmtime(path)
    except OSError:
        rec["bytes"] = 0
    text = _head(path, HEAD_BYTES)
    try:
        doc = json.loads(text)
    except ValueError:
        doc = [d for d in _lines(text)]
    items = doc if isinstance(doc, list) else (doc.get("messages") or doc.get("history") or [])
    for it in items if isinstance(items, list) else []:
        if not isinstance(it, dict):
            continue
        role = it.get("role") or it.get("type")
        body = _text_of(it.get("content") or it.get("parts") or it.get("text"))
        if role in ("user", "human") and body:
            if rec["first_prompt"] is None:
                rec["first_prompt"] = body.strip()
            rec["last_prompt"] = body.strip()
        elif role in ("model", "assistant"):
            rec["turns"] += 1
    if rec["first_prompt"]:
        rec["title"] = " ".join(rec["first_prompt"].split())[:70]
    return rec


def _glob_sessions(patterns, reader, tool=None):
    import glob as _glob
    out = []
    for pat in patterns:
        for p in _glob.glob(_root(pat)):
            try:
                out.append((os.path.getmtime(p), p,
                            (lambda path, _r=reader, _t=tool:
                             _r(path, _t) if _t else _r(path))))
            except OSError:
                pass
    return out


def _files(newest_first=True, limit=MAX_SESSIONS):
    out = []
    root = _root(CLAUDE_ROOT)
    if os.path.isdir(root):
        for project in os.listdir(root):
            d = os.path.join(root, project)
            if not os.path.isdir(d):
                continue
            for name in os.listdir(d):
                if name.endswith(".jsonl"):
                    p = os.path.join(d, name)
                    try:
                        out.append((os.path.getmtime(p), p, read_claude))
                    except OSError:
                        pass
    croot = _root(CODEX_ROOT)
    if os.path.isdir(croot):
        for base, _dirs, names in os.walk(croot):
            for name in names:
                if name.startswith("rollout-") and name.endswith(".jsonl"):
                    p = os.path.join(base, name)
                    try:
                        out.append((os.path.getmtime(p), p, read_codex))
                    except OSError:
                        pass
    out += _copilot_sessions()
    out += _glob_sessions(VSCODE_CHAT, read_vscode, "vscode")
    out += _glob_sessions(CURSOR_CHAT, read_vscode, "cursor")
    out += _glob_sessions(GEMINI_GLOBS, read_gemini)
    out.sort(key=lambda t: t[0], reverse=newest_first)
    return out[:limit]


def running(procs=None, cwds=None):
    """-> the live agent processes, with their working directory."""
    from . import collect
    if procs is None:
        try:
            procs = collect.processes()
        except Exception:
            return []
    out = []
    for pid, p in procs.items():
        name = os.path.basename((p.get("cmdline") or p.get("name") or "").split(" ")[0])
        if name not in AGENT_NAMES:
            continue
        out.append({"pid": pid, "tool": name, "cmdline": p.get("cmdline") or name,
                    "uptime": p.get("uptime"), "started": p.get("started"),
                    "user": p.get("user")})
    if out:
        try:
            where = collect.cwds([o["pid"] for o in out])
        except Exception:
            where = {}
        for o in out:
            o["cwd"] = where.get(o["pid"]) or ""
    return out


def listing(limit=25, live_only=False):
    """-> {sessions, processes, note}. The whole answer, cheap enough to poll."""
    procs = running()
    by_slug = {}
    for p in procs:
        by_slug.setdefault(slug(p.get("cwd") or ""), []).append(p)

    sessions = []
    for mtime, path, reader in _files():
        try:
            rec = reader(path)
        except Exception as e:
            rec = {"tool": "?", "id": os.path.basename(path), "path": path,
                   "error": str(e)[:120], "last_active": mtime}
        project_slug = (slug(rec.get("cwd") or "")
                        or os.path.basename(os.path.dirname(path)))
        here = by_slug.get(project_slug, [])
        rec["project"] = os.path.basename(rec.get("cwd") or "") or project_slug
        rec["live_pids"] = [p["pid"] for p in here]
        # One process in this directory and this is its most recent transcript:
        # that is a match. Several processes share a directory all the time, and
        # nothing visible from outside tells them apart, so say so instead.
        rec["ambiguous"] = len(here) > 1
        rec["live"] = bool(here) and rec.get("last_active", 0) > time.time() - 86400
        sessions.append(rec)
        if len(sessions) >= limit * 2:
            break

    sessions.sort(key=lambda r: -(r.get("last_active") or 0))
    if live_only:
        sessions = [r for r in sessions if r["live"]]
    return {"sessions": sessions[:limit], "processes": procs,
            "accounts": accounts(),
            "note": "read from local transcripts. Prompts never leave this machine: "
                    "they are not in /llm.txt, not in the manifest, and not in an "
                    "agent report."}


# ------------------------------------------------------------------ accounts
# Which plan each tool is signed in under. Read from the config the tool already
# wrote, and deliberately narrow: the plan and the organisation are useful when
# you are wondering which account burned the week's quota. The email address and
# the account UUID are not, so they are never read out of the file.
NEVER_SHOW = ("email", "uuid", "token", "key", "secret", "id")
# Filtering by key name is not enough, and this was caught by checking rather
# than by thinking: the organisation on this machine is literally named
# "someone@example.com's Organization", so the address travelled inside a field
# called "org". Values are scrubbed too.
EMAILISH = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _scrub(value):
    if isinstance(value, str):
        return EMAILISH.sub("[address]", value)
    return value


def accounts():
    out = []

    claude = os.path.expanduser("~/.claude.json")
    if os.path.isfile(claude):
        try:
            with open(claude) as f:
                doc = json.load(f)
            oa = doc.get("oauthAccount") or {}
            plan = (oa.get("organizationType") or "").replace("_", " ") or None
            tier = (oa.get("organizationRateLimitTier") or "").replace("_", " ") or None
            out.append({"tool": "claude", "name": "Claude Code",
                        "who": oa.get("displayName") or oa.get("fullName"),
                        "org": oa.get("organizationName"),
                        "plan": plan, "tier": tier,
                        "billing": oa.get("billingType"),
                        "extra_usage": oa.get("hasExtraUsageEnabled"),
                        "since": oa.get("subscriptionCreatedAt")})
        except (OSError, ValueError):
            pass

    codex_cfg = os.path.expanduser("~/.codex/config.toml")
    codex_auth = os.path.expanduser("~/.codex/auth.json")
    if os.path.isdir(os.path.expanduser("~/.codex")):
        plan = None
        if os.path.isfile(codex_auth):
            try:
                with open(codex_auth) as f:
                    a = json.load(f)
                plan = (a.get("plan") or a.get("tier")
                        or ("ChatGPT sign-in" if a.get("tokens") else None))
            except (OSError, ValueError):
                pass
        model = None
        if os.path.isfile(codex_cfg):
            try:
                with open(codex_cfg) as f:
                    for line in f:
                        if line.strip().startswith("model"):
                            model = line.split("=", 1)[-1].strip().strip('"')
                            break
            except OSError:
                pass
        out.append({"tool": "codex", "name": "Codex", "plan": plan,
                    "model": model,
                    "signed_in": os.path.isfile(codex_auth)})

    cop = os.path.expanduser("~/.copilot/config.json")
    if os.path.isfile(cop):
        try:
            with open(cop) as f:
                c = json.load(f)
            out.append({"tool": "copilot", "name": "GitHub Copilot",
                        "plan": c.get("plan") or c.get("sku"),
                        "model": c.get("model"),
                        "signed_in": True})
        except (OSError, ValueError):
            out.append({"tool": "copilot", "name": "GitHub Copilot", "signed_in": True})

    gem = os.path.expanduser("~/.gemini/settings.json")
    if os.path.isfile(gem):
        try:
            with open(gem) as f:
                g = json.load(f)
            out.append({"tool": "gemini", "name": "Gemini",
                        "model": g.get("model"),
                        "plan": g.get("authType") or g.get("selectedAuthType"),
                        "signed_in": True})
        except (OSError, ValueError):
            pass

    # Belt and braces: nothing that looks like an address or a credential leaves
    # this function, whatever a future config file decides to put in those keys.
    clean = []
    for a in out:
        clean.append({k: _scrub(v) for k, v in a.items()
                      if not any(bad in k.lower() for bad in NEVER_SHOW)
                      or k in ("tool", "signed_in")})
    return clean


def summary(doc=None):
    doc = doc if doc is not None else listing()
    s = doc["sessions"]
    now = time.time()
    return {
        "processes": len(doc["processes"]),
        "sessions": len(s),
        "live": sum(1 for r in s if r.get("live")),
        "stale_7d": sum(1 for r in s if (now - (r.get("last_active") or now)) > 7 * 86400),
        "context_total": sum(r.get("context") or 0 for r in s if r.get("live")),
        "biggest": max((r.get("context") or 0 for r in s), default=0),
    }
