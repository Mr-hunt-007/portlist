"""Snapshot the port inventory and turn the difference into events."""
import json
import os
import time

HOME = os.path.expanduser("~/.portlist")
STATE = os.path.join(HOME, "state.json")
EVENTS = os.path.join(HOME, "events.jsonl")
MAX_EVENTS = 4000

# Fields whose change is worth an event, and how to describe it.
WATCH = [
    ("health", "Health changed"),
    ("service", "Service changed"),
    ("exposure", "Exposure changed"),
    ("risk_band", "Risk changed"),
    ("dir", "Working directory changed"),
    ("cmd", "Process changed"),
]


def _load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except Exception:
        return {"ports": {}, "first_seen": {}}


def _save(state):
    os.makedirs(HOME, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f)
    os.replace(tmp, STATE)


def _append(events):
    if not events:
        return
    os.makedirs(HOME, exist_ok=True)
    with open(EVENTS, "a") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")


def _key(row):
    return "%s/%s" % (row["port"], row["pid"])


def _snap(row):
    return {"port": row["port"], "pid": row["pid"], "cmd": row["cmd"],
            "health": row.get("health", ""),
            "dir": row.get("dir", ""), "service": row.get("service") or "",
            "exposure": row["exposure"]["level"], "risk_band": row.get("risk_band", ""),
            "risk": row.get("risk", 0), "ai": bool(row.get("ai"))}


def reconcile(rows):
    """Diff this scan against the last one. Returns (events, first_seen map)."""
    state = _load()
    prev, first_seen = state.get("ports", {}), state.get("first_seen", {})
    now = time.time()
    cur, events = {}, []
    # First ever run: record what exists without claiming it all just appeared.
    bootstrap = not prev

    for row in rows:
        k = _key(row)
        snap = _snap(row)
        cur[k] = snap
        pk = str(row["port"])
        if pk not in first_seen:
            first_seen[pk] = 0 if bootstrap else now
        old = prev.get(k)
        if not old:
            events.append({"ts": now, "type": "opened", "port": row["port"],
                           "service": snap["service"] or row["cmd"],
                           "exposure": snap["exposure"], "risk_band": snap["risk_band"],
                           "ai": snap["ai"], "pid": row["pid"],
                           "text": "%s opened on :%d (%s)" % (
                               snap["service"] or row["cmd"], row["port"],
                               snap["exposure"])})
            continue
        for field, label in WATCH:
            if old.get(field) != snap.get(field):
                events.append({"ts": now, "type": field, "port": row["port"],
                               "service": snap["service"] or row["cmd"],
                               "exposure": snap["exposure"], "risk_band": snap["risk_band"],
                               "ai": snap["ai"], "pid": row["pid"],
                               "from": old.get(field), "to": snap.get(field),
                               "text": "%s on :%d - %s: %s -> %s" % (
                                   snap["service"] or row["cmd"], row["port"], label,
                                   old.get(field) or "-", snap.get(field) or "-")})

    for k, old in prev.items():
        if k not in cur:
            events.append({"ts": now, "type": "closed", "port": old["port"],
                           "service": old.get("service") or old.get("cmd", ""),
                           "exposure": old.get("exposure"), "risk_band": "",
                           "ai": old.get("ai", False), "pid": old.get("pid"),
                           "text": "%s on :%s stopped listening" % (
                               old.get("service") or old.get("cmd", "?"), old["port"])})

    if bootstrap:
        events = []
    _append(events)
    # A scan every few seconds does not justify a disk write every few seconds.
    if events or cur != prev or first_seen != state.get("first_seen", {}):
        _save({"ports": cur, "first_seen": first_seen})
    return events, first_seen


def recent(limit=200):
    try:
        with open(EVENTS) as f:
            lines = f.readlines()[-limit:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return list(reversed(out))


def trim():
    try:
        with open(EVENTS) as f:
            lines = f.readlines()
    except Exception:
        return
    if len(lines) > MAX_EVENTS:
        with open(EVENTS, "w") as f:
            f.writelines(lines[-MAX_EVENTS:])
