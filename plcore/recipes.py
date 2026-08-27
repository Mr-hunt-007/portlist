"""Remember how a service was started, so it can be started again.

Portlist watches processes it did not create. That is the whole security
posture, and it does not change here: a recipe is a **record**, not a daemon.
Portlist writes down the command, the directory and the port a service used,
and hands that back to you or to your shell. The HTTP server never spawns
anything; `portlist open` runs it in your terminal, as you, where you can see
it.

Three things live in this file:

    adopt     name an unknown service, and keep notes on it
    recipe    the command + directory + port that ran it, saved automatically
    shelve    keep the recipe, stop the process yourself

Recipes are keyed by what the service *is* (command signature plus directory),
not by port. A dev server that comes back on :3001 because :3000 was taken is
the same service, and everything remembered about it should follow it there.
"""
import hashlib
import json
import os
import re
import time

from .security import data_dir

STORE = "recipes.json"


def _path():
    return os.path.join(data_dir(), STORE)


def _load():
    try:
        with open(_path()) as f:
            doc = json.load(f)
    except Exception:
        doc = {}
    return doc if isinstance(doc, dict) else {}


MAX_RECIPES = 300


def _save(doc):
    # Bounded: a machine that runs a thousand one-off servers should not leave a
    # thousand recipes behind. Anything a person named or shelved is kept first.
    if len(doc) > MAX_RECIPES:
        keep = sorted(doc.values(),
                      key=lambda e: (bool(e.get("adopted") or e.get("shelved")),
                                     e.get("last_seen") or 0), reverse=True)[:MAX_RECIPES]
        doc = {e["key"]: e for e in keep}
    os.makedirs(data_dir(), exist_ok=True)
    tmp = _path() + ".tmp"
    with open(tmp, "w") as f:
        json.dump(doc, f, indent=1)
    os.replace(tmp, _path())


# Volatile bits of a command line: a port, a pid, a temp path, a session id.
# Two runs of the same dev server differ in these and in nothing that matters.
VOLATILE = [
    (r"(?<=[:= ])\d{4,5}\b", "<port>"),
    (r"/(?:var/folders|tmp|private/tmp)/[\w./-]+", "<tmp>"),
    (r"\b[0-9a-f]{16,}\b", "<hash>"),
    (r"--(?:pid|session|token|id)[= ]\S+", ""),
]


def signature(cmdline, cwd=""):
    """A stable identity for "the same service, started again"."""
    text = " ".join((cmdline or "").split())
    for pattern, repl in VOLATILE:
        text = re.sub(pattern, repl, text)
    base = (cwd or "") + "|" + text
    return hashlib.sha256(base.encode()).hexdigest()[:16]


def key_for(row):
    return signature(row.get("cmdline") or row.get("cmd") or "", row.get("dir") or "")


def observe(rows):
    """Update the recipe book from a scan, without touching what a human set.

    A recipe is only worth having if the command can actually be re-run, so
    services with no command line (another user's process) are skipped.
    """
    doc = _load()
    now = time.time()
    changed = False
    for r in rows:
        if r.get("quiet") or not r.get("cmdline") or not r.get("dir"):
            continue
        k = key_for(r)
        e = doc.get(k)
        if not e:
            e = {"key": k, "name": None, "notes": "", "adopted": False,
                 "first_seen": now, "shelved": False}
            changed = True
        # Measured fields are refreshed; anything a person typed is left alone.
        for field, value in (("cmdline", r["cmdline"]), ("dir", r["dir"]),
                             ("dir_short", r.get("dir_short")), ("cmd", r["cmd"]),
                             ("service", r.get("service")),
                             ("service_id", r.get("service_id")),
                             ("project", (r.get("project") or {}).get("name")),
                             ("user", r.get("user"))):
            if e.get(field) != value:
                e[field] = value
                changed = True
        ports = e.setdefault("ports", [])
        if r["port"] not in ports:
            ports.append(r["port"])
            ports[:] = sorted(set(ports))[-6:]
            changed = True
        if e.get("last_port") != r["port"]:
            e["last_port"] = r["port"]
            changed = True
        e["last_seen"] = now
        e["running"] = True
        doc[k] = e
    for k, e in doc.items():
        if e.get("last_seen", 0) < now - 1 and e.get("running"):
            e["running"] = False
            changed = True
    if changed:
        _save(doc)
    return doc


def all_recipes(running=None):
    doc = _load()
    out = sorted(doc.values(), key=lambda e: -(e.get("last_seen") or 0))
    if running is not None:
        out = [e for e in out if bool(e.get("running")) == running]
    return out


def get(ident):
    """Find a recipe by key, saved name, port or a fragment of its command."""
    doc = _load()
    if ident in doc:
        return doc[ident]
    ident = str(ident).strip()
    exact = [e for e in doc.values() if (e.get("name") or "").lower() == ident.lower()]
    if exact:
        return exact[0]
    if ident.isdigit():
        port = int(ident)
        hits = [e for e in doc.values() if e.get("last_port") == port or port in (e.get("ports") or [])]
        hits.sort(key=lambda e: (not e.get("running"), -(e.get("last_seen") or 0)))
        if hits:
            return hits[0]
    low = ident.lower()
    hits = [e for e in doc.values()
            if low in (e.get("name") or "").lower()
            or low in (e.get("cmdline") or "").lower()
            or low in (e.get("project") or "").lower()]
    hits.sort(key=lambda e: (not e.get("running"), -(e.get("last_seen") or 0)))
    return hits[0] if hits else None


def adopt(row_or_key, name=None, notes=None, shelved=None):
    """Name a service so it stops being "unidentified", and keep notes on it."""
    doc = _load()
    k = row_or_key if isinstance(row_or_key, str) else key_for(row_or_key)
    e = doc.get(k)
    if not e:
        if isinstance(row_or_key, str):
            return None
        r = row_or_key
        e = {"key": k, "cmdline": r.get("cmdline"), "dir": r.get("dir"),
             "dir_short": r.get("dir_short"), "cmd": r.get("cmd"),
             "service": r.get("service"), "project": (r.get("project") or {}).get("name"),
             "ports": [r["port"]], "last_port": r["port"], "first_seen": time.time(),
             "last_seen": time.time(), "running": True, "notes": ""}
    if name is not None:
        e["name"] = name.strip() or None
        e["adopted"] = bool(e["name"])
    if notes is not None:
        e["notes"] = notes
    if shelved is not None:
        e["shelved"] = bool(shelved)
    e["adopted_at"] = e.get("adopted_at") or time.time()
    doc[k] = e
    _save(doc)
    return e


def forget(ident):
    doc = _load()
    e = get(ident)
    if not e:
        return False
    doc.pop(e["key"], None)
    _save(doc)
    return True


def label(row):
    """The name a human gave this service, if they gave it one."""
    e = _load().get(key_for(row))
    if not e:
        return None
    return {"name": e.get("name"), "notes": e.get("notes"), "adopted": bool(e.get("adopted")),
            "shelved": bool(e.get("shelved")), "key": e["key"],
            "ports": e.get("ports") or [], "moved": _moved(e)}


def _moved(e):
    ports = e.get("ports") or []
    if len(ports) > 1 and e.get("last_port"):
        others = [p for p in ports if p != e["last_port"]]
        if others:
            return {"from": others[-1], "to": e["last_port"], "seen": sorted(ports)}
    return None


def command_for(e):
    """The line to paste into a shell to start it again."""
    if not e:
        return None
    cwd = e.get("dir") or "."
    cmd = e.get("cmdline") or ""
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    return "cd %s && %s" % (cwd, cmd)


def moved_events(rows, previous):
    """Same service, new port. Without this, a dev server that moves looks like
    one death and one unrelated birth."""
    out = []
    now_by_key = {}
    for r in rows:
        if r.get("cmdline") and r.get("dir"):
            now_by_key.setdefault(key_for(r), r)
    for k, r in now_by_key.items():
        old = previous.get(k)
        if old and old != r["port"]:
            out.append({"key": k, "from": old, "to": r["port"],
                        "service": r.get("service") or r["cmd"],
                        "text": "%s moved from :%d to :%d"
                                % (r.get("service") or r["cmd"], old, r["port"])})
    return out, {k: r["port"] for k, r in now_by_key.items()}
