"""When was this service last actually used?

Uptime is not use. A dev server you touched ten minutes ago and one you last
opened three days ago look identical if both have been running since Tuesday and
neither happens to hold a connection at this instant. That is the difference
between "old" and "abandoned", and until this module existed Portlist could only
measure the first and was quietly reporting it as the second.

So: on every scan, record whether each service had anyone connected. Keep the
last time the answer was yes. That is a measurement, not an inference.

Two rules this module exists to keep.

**Not measured is not idle.** Portlist only knows what happened while it was
running. If it has been watching for twenty minutes it must not say "no activity
for 11 days" - it must say it has been watching for twenty minutes. Every answer
carries `watched_for` and `known` so no surface can accidentally present a short
observation as a long silence.

**A service keeps its history across a restart.** Rows are keyed by port and pid,
both of which change. Activity is keyed by the same command signature the recipe
book uses, so restarting `npm run dev` continues the same record rather than
starting a fresh one that looks abandoned by tomorrow.
"""
import json
import os
import time

from . import recipes, security

# Sampling is cheap; writing to disk on every poll is not. The file is flushed at
# most this often, and always when something turned busy, because that is the
# edge worth not losing.
FLUSH_EVERY = 30.0
# A record nothing has matched for this long is dropped: the machine has moved on.
FORGET_AFTER = 45 * 86400
MAX_RECORDS = 800

_mem = None          # the whole store, in memory between flushes
_loaded_at = 0.0
_dirty = False
_flushed = 0.0


def path():
    return os.path.join(security.data_dir(), "activity.json")


def _load():
    global _mem, _loaded_at
    if _mem is not None:
        return _mem
    try:
        with open(path()) as f:
            doc = json.load(f)
        _mem = doc if isinstance(doc, dict) else {}
    except (OSError, ValueError):
        _mem = {}
    _loaded_at = time.time()
    return _mem


def flush(force=False):
    """Write the store if it has changed. Safe to call on every scan."""
    global _dirty, _flushed
    doc = _load()
    now = time.time()
    if not _dirty or (not force and now - _flushed < FLUSH_EVERY):
        return False
    # Forget what has not been seen in a long time, newest kept first.
    stale = [k for k, v in doc.items()
             if now - (v.get("last_seen") or 0) > FORGET_AFTER]
    for k in stale:
        del doc[k]
    if len(doc) > MAX_RECORDS:
        keep = sorted(doc.items(), key=lambda kv: -(kv[1].get("last_seen") or 0))[:MAX_RECORDS]
        doc = dict(keep)
        _set(doc)
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            json.dump(doc, f, indent=1, sort_keys=True)
        os.replace(tmp, p)
    except OSError:
        return False
    _dirty, _flushed = False, now
    return True


def _set(doc):
    global _mem
    _mem = doc


def key_for(row):
    """The same identity the recipe book uses, so a restart continues the record.

    Falls back to the port when there is no command line to sign - another user's
    process, mostly. A port is a weaker identity, so the record says so.
    """
    if row.get("cmdline") and row.get("dir"):
        return "sig:" + recipes.key_for(row)
    return "port:%s" % row.get("port")


def observe(rows, now=None):
    """Record one sample per live service. Called from the scan, never from a view."""
    global _dirty
    doc = _load()
    now = now or time.time()
    for r in rows:
        if r.get("quiet"):
            continue
        k = key_for(r)
        e = doc.get(k)
        if not e:
            e = {"first_seen": now, "samples": 0, "busy_samples": 0,
                 "last_busy": None, "peak_conns": 0}
            doc[k] = e
        conns = r.get("conns") or 0
        e["last_seen"] = now
        e["samples"] = (e.get("samples") or 0) + 1
        if conns > 0:
            e["busy_samples"] = (e.get("busy_samples") or 0) + 1
            e["last_busy"] = now
            if conns > (e.get("peak_conns") or 0):
                e["peak_conns"] = conns
        _dirty = True
    return doc


def of(row, now=None):
    """-> what is known about this service's use. Never guesses.

    `known` is False until Portlist has watched long enough for silence to mean
    anything. `idle_seconds` is None in that case rather than a large number,
    because a large number would be read as evidence.
    """
    now = now or time.time()
    e = _load().get(key_for(row))
    if not e:
        return {"known": False, "watched_for": 0, "samples": 0,
                "last_busy": None, "idle_seconds": None, "ever_busy": False,
                "note": "not watched yet"}
    watched = max(0.0, now - (e.get("first_seen") or now))
    last = e.get("last_busy")
    # Under an hour of observation, "quiet" is not a finding, it is a short look.
    known = watched >= 3600
    return {"known": known,
            "watched_for": round(watched),
            "samples": e.get("samples") or 0,
            "busy_samples": e.get("busy_samples") or 0,
            "peak_conns": e.get("peak_conns") or 0,
            "ever_busy": bool(last),
            "last_busy": last,
            "idle_seconds": (round(now - last) if (last and known)
                             else None),
            "note": ("watching for %s" % _short(watched)) if not known else ""}


def _short(seconds):
    seconds = int(seconds or 0)
    if seconds < 90:
        return "%ds" % seconds
    if seconds < 5400:
        return "%dm" % (seconds // 60)
    if seconds < 172800:
        return "%dh" % (seconds // 3600)
    return "%dd" % (seconds // 86400)


def phrase(act):
    """One line a person can read, which never overstates what was measured."""
    if not act:
        return "not measured"
    if not act.get("known"):
        return "watching since %s ago" % _short(act.get("watched_for") or 0)
    if not act.get("ever_busy"):
        return "nothing has connected while Portlist has been watching (%s)" \
               % _short(act.get("watched_for"))
    idle = act.get("idle_seconds")
    if idle is None:
        return "in use"
    if idle < 120:
        return "in use now"
    return "last used %s ago" % _short(idle)
