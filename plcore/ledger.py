"""The launch ledger: who started this, the first time anyone saw it.

Everything else in Portlist reconstructs the world from what is alive right
now. That works until the thing you want to know about is no longer alive.

    14:00  Claude Code starts a server
    14:30  Claude Code exits          <- ancestry gone, env still on the child
    16:00  the server crashes
    16:01  a supervisor restarts it   <- env gone too. Attribution: nothing.

The environment variable trick carries attribution across the *agent* exiting,
because the child inherited it and keeps it for its own lifetime. It does not
carry across the *service* exiting, because the replacement inherits whatever
restarted it. From that moment the machine has no memory of who started this,
and neither did Portlist.

So this file writes the birth down. Append-only, one JSON object per line, and
the answer to "who started this" becomes a lookup rather than an inference.

Three rules the rest of the module exists to keep.

**Never key on a pid.** A pid is the one identifier guaranteed to change on the
event this file exists to survive. Matching is by command signature, the same one
the recipe book uses, with weaker fallbacks below it - each of which reports how
sure it is.

**An uncertain match is not a match.** If two records could be this service, the
answer is "unknown", not the more interesting of the two. Inventing attribution
is worse than admitting there is none, because a confident wrong answer about who
started something is exactly what makes somebody stop the wrong process.

**Live and remembered are different claims.** "Started by Claude Code" and
"originally started by Claude Code, and this process no longer carries that" are
not the same sentence, and this module never lets a surface collapse them.
"""
import json
import os
import time

from . import recipes, security

STORE = "ledger.jsonl"
MAX_LINES = 20000          # roughly a year of a busy laptop; trimmed oldest-first
TRIM_TO = 15000

# Events the ledger records. Deliberately few: this is the birth certificate and
# the death notice, not a general log. `history.py` already keeps the per-port
# open/close stream and is a better place for anything finer grained.
LAUNCH = "launch"          # first time this signature was ever seen
RESPAWN = "respawn"        # seen again after having been gone
STOP = "stop"              # it was there last scan and is not now
ATTRIB = "attribution"     # the live attribution changed from what was recorded

_mem = None                # every record, newest last
_by_sig = None             # sig -> the live record for that signature
_dirty = False
_pending = []              # records appended since the last flush


def path():
    return os.path.join(security.data_dir(), STORE)


def _read():
    global _mem, _by_sig
    if _mem is not None:
        return _mem
    _mem, _by_sig = [], {}
    try:
        with open(path()) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue               # a torn last line is not a reason to lose the file
                if isinstance(rec, dict) and rec.get("sig"):
                    _mem.append(rec)
    except OSError:
        pass
    _reindex()
    return _mem


def _reindex():
    """Fold the append-only log into "what is true now" per signature."""
    global _by_sig
    _by_sig = {}
    for rec in _mem:
        sig = rec["sig"]
        cur = _by_sig.get(sig)
        if rec["event"] == LAUNCH:
            # The first launch is the origin. A later launch for the same
            # signature means the ledger was trimmed or removed; keep the older.
            if not cur:
                _by_sig[sig] = dict(rec, respawns=0, stopped_at=None,
                                    current_pid=rec.get("pid"))
        elif cur:
            if rec["event"] == RESPAWN:
                cur["respawns"] = cur.get("respawns", 0) + 1
                cur["stopped_at"] = None
                cur["current_pid"] = rec.get("pid")
                cur["last_respawn_at"] = rec.get("ts")
                if rec.get("carries_context") is not None:
                    cur["carries_context"] = rec["carries_context"]
            elif rec["event"] == STOP:
                cur["stopped_at"] = rec.get("ts")
            elif rec["event"] == ATTRIB:
                cur.setdefault("attribution_changes", []).append(rec)


def _append(rec):
    global _dirty
    _read()
    _mem.append(rec)
    _pending.append(rec)
    _dirty = True
    _reindex()
    return rec


def flush():
    """Write what has been appended. Append-only: the file is never rewritten
    except to trim, and a trim keeps the newest records."""
    global _dirty, _pending
    if not _dirty:
        return False
    p = path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a") as f:
            for rec in _pending:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
    except OSError:
        return False
    _pending = []
    _dirty = False
    if len(_mem) > MAX_LINES:
        _trim()
    return True


def _trim():
    keep = _mem[-TRIM_TO:]
    p = path()
    try:
        tmp = p + ".tmp"
        with open(tmp, "w") as f:
            for rec in keep:
                f.write(json.dumps(rec, sort_keys=True) + "\n")
        os.replace(tmp, p)
    except OSError:
        return
    del _mem[:len(_mem) - TRIM_TO]
    _reindex()


# ------------------------------------------------------------------ identity
def sig_for(row, siblings=None):
    """The identity to file this row under.

    `siblings` is how many rows in *this same scan* share the base signature.
    That matters: `recipes.signature` deliberately normalises the port out, so
    "the same service that came back on :3001" keeps its identity - but it also
    means two `python -m http.server` in one directory on :8787 and :8807 look
    identical. They are not the same service; they are two, running at once, and
    filing them together made the second one look like a respawn of the first.
    When a signature collides inside one scan the port joins the identity, and
    the record says so.
    """
    base = _base_sig(row)
    if siblings and siblings.get(base, 0) > 1:
        return "%s@%d" % (base, row["port"])
    return base


def _base_sig(row):
    """The strongest identity available, and never a pid.

    `recipes.signature` is command line plus working directory, with volatile
    tokens (ports, temp paths, hashes) already normalised out. Two runs of
    `npm run dev` in the same repo produce the same signature; the same command
    in a different repo does not, which is the third test case.
    """
    return recipes.signature(row.get("cmdline") or row.get("cmd") or "",
                             row.get("dir") or "")


def _norm_cmd(row):
    return recipes.signature(row.get("cmdline") or row.get("cmd") or "", "")


# A reparented process is adopted by the init system. `lifecycle.starter` returns
# that as a last-resort fallback, which is honest but is not *context*: "started
# by launchd" is true of everything that outlived its parent and tells you
# nothing. It must never outrank a recorded origin.
REAPERS = ("launchd", "systemd", "init")


def _is_context(starter):
    """Does the live process actually carry who started it?"""
    if not starter or not starter.get("name"):
        return False
    if starter.get("kind") in REAPERS:
        return False
    if starter.get("class") == "service manager" and starter.get("pid") in (0, 1):
        return False
    return True


def _starter_of(row):
    w = row.get("starter") or {}
    if not w.get("name"):
        return None
    return {"kind": w.get("kind"), "name": w.get("name"), "class": w.get("class"),
            "pid": w.get("pid"), "via": w.get("via"), "ai": bool(w.get("ai"))}


def _container_starter(row):
    """A container-backed service was started by whatever brought the stack up.
    That is a real, durable answer and beats "launchd ran the engine's proxy"."""
    c = row.get("container") or {}
    if not c:
        return None
    if c.get("project"):
        return {"kind": "compose", "name": "Docker Compose (%s)" % c["project"],
                "class": "container", "pid": None, "via": "container label",
                "ai": False}
    return {"kind": "container", "name": "%s container" % (c.get("engine") or "docker"),
            "class": "container", "pid": None, "via": "container", "ai": False}


# ------------------------------------------------------------------ matching
def match(row, records=None):
    """-> (record, how, certain). Never uses a pid.

    Tried strongest first. Each tier says how it matched so a surface can show
    the difference between "this is certainly the same service" and "this looks
    like it". A tier that finds more than one candidate returns none of them:
    picking the more interesting of two possible origins is how a tool invents
    attribution.
    """
    live = records if records is not None else (_read() or None) and _by_sig
    if not live:
        return None, "none", False

    rec = live.get(_base_sig(row)) or live.get("%s@%d" % (_base_sig(row), row["port"]))
    if rec:
        return rec, "signature", True

    # The command is the same but the working directory moved. Common when a
    # repo is cloned to a new path, or a supervisor starts it from elsewhere.
    ncmd = _norm_cmd(row)
    root = (row.get("git_root") or "").strip()
    cands = [r for r in live.values()
             if r.get("norm_cmd") == ncmd and not r.get("port_scoped")]
    if root:
        same_root = [r for r in cands if r.get("git_root") == root]
        if len(same_root) == 1:
            return same_root[0], "command and git root", True
        if len(same_root) > 1:
            return None, "ambiguous", False

    # Weakest tier: the same command on the same port. Reported as uncertain,
    # because a port is a slot, not an identity.
    on_port = [r for r in cands if row["port"] in (r.get("ports") or [])]
    if len(on_port) == 1:
        return on_port[0], "command and port", False
    if len(on_port) > 1:
        return None, "ambiguous", False
    if len(cands) == 1:
        return cands[0], "command", False
    if len(cands) > 1:
        return None, "ambiguous", False
    return None, "none", False


# ----------------------------------------------------------------- observing
def observe(rows, now=None, git_root=None):
    """Record births, deaths and respawns; hand each row back its origin.

    Called once per scan, from the scan. Returns the rows.
    """
    now = now or time.time()
    _read()
    seen = set()

    # Which base signatures appear more than once in this scan. See sig_for.
    siblings = {}
    for row in rows:
        if row.get("quiet"):
            continue
        b = _base_sig(row)
        siblings[b] = siblings.get(b, 0) + 1

    for row in rows:
        if row.get("quiet"):
            continue
        sig = sig_for(row, siblings)
        seen.add(sig)
        live_starter = _starter_of(row) or _container_starter(row)
        root = row.get("git_root")
        if root is None and git_root:
            try:
                root = git_root(row.get("dir") or "")
            except Exception:
                root = None
        rec = _by_sig.get(sig)

        if not rec:
            # Nothing on file under this signature. Before writing a new birth,
            # ask whether this is a service we already know wearing a new path.
            prior, how, certain = match(row)
            if prior and certain and prior.get("stopped_at"):
                _append({"event": RESPAWN, "ts": now, "sig": prior["sig"],
                         "pid": row.get("pid"), "port": row.get("port"),
                         "matched": how,
                         "carries_context": bool(live_starter and
                                                 (row.get("starter") or {}).get("name"))})
                rec = _by_sig.get(prior["sig"])
            else:
                # Was Portlist watching when this started? If the process
                # predates the first record in this ledger, its origin is
                # inferred from what the process carries now, not observed at
                # launch, and the record must not pretend otherwise.
                began = row.get("started")
                since = watching_since()
                observed = bool(began and since and began >= since - 5)
                rec = _append({
                    "event": LAUNCH, "ts": now, "sig": sig,
                    # `ts` is when Portlist first saw it. `process_started` is
                    # when the OS says the process began. They are only the same
                    # when the launch was observed.
                    "process_started": began,
                    "observed": observed,
                    "port_scoped": sig != _base_sig(row),
                    "norm_cmd": _norm_cmd(row),
                    "pid": row.get("pid"), "port": row.get("port"),
                    "ports": [row["port"]],
                    "cmdline": (row.get("cmdline") or row.get("cmd") or "")[:600],
                    "cmd": row.get("cmd"),
                    "cwd": row.get("dir") or "",
                    "git_root": root or "",
                    "project": (row.get("project") or {}).get("name"),
                    "service": row.get("service"),
                    "starter": live_starter,
                    "starter_confident": bool(live_starter),
                })
                rec = _by_sig.get(sig)
        else:
            if rec.get("stopped_at"):
                _append({"event": RESPAWN, "ts": now, "sig": sig,
                         "pid": row.get("pid"), "port": row.get("port"),
                         "matched": "signature",
                         "carries_context": bool((row.get("starter") or {}).get("name"))})
                rec = _by_sig.get(sig)
            elif rec.get("current_pid") != row.get("pid") and row.get("pid") is not None:
                # Same signature, different process, and we never saw it stop -
                # a restart between two scans. Still a respawn.
                _append({"event": RESPAWN, "ts": now, "sig": sig,
                         "pid": row.get("pid"), "port": row.get("port"),
                         "matched": "signature",
                         "carries_context": bool((row.get("starter") or {}).get("name"))})
                rec = _by_sig.get(sig)
            # A port it has not held before is worth remembering: recipes does
            # the same, and it is what makes the weakest match tier work later.
            if rec and row["port"] not in (rec.get("ports") or []):
                rec.setdefault("ports", []).append(row["port"])

            # The live answer disagrees with what was written down. Record it
            # rather than overwriting: the ledger is append-only, and "it used
            # to say Cursor" is sometimes the interesting part.
            was = (rec.get("starter") or {}).get("kind")
            nowk = (live_starter or {}).get("kind")
            if live_starter and was and nowk and was != nowk:
                _append({"event": ATTRIB, "ts": now, "sig": sig,
                         "from": was, "to": nowk, "pid": row.get("pid")})
                rec = _by_sig.get(sig)

        row["origin"] = _origin(row, rec, live_starter, now)
        row["origin"]["sig"] = sig
        row["origin"]["port_scoped"] = bool(rec and rec.get("port_scoped"))

    # Anything on file that was live and is not in this scan has stopped.
    for sig, rec in list(_by_sig.items()):
        if sig in seen or rec.get("stopped_at"):
            continue
        _append({"event": STOP, "ts": now, "sig": sig,
                 "pid": rec.get("current_pid"), "port": rec.get("port")})
    flush()
    return rows


def _origin(row, rec, live_starter, now):
    """What a surface should say about where this came from.

    `live` is the claim the running process can support by itself. `recorded` is
    what the ledger remembers. They are kept apart so no surface can present the
    second as the first.
    """
    # Not "is there a live starter" but "does the live process carry context".
    # A process reparented to launchd has a starter and no context at all.
    has_live = _is_context(row.get("starter"))
    out = {
        # `live` is whatever the running process can support by itself: the
        # inherited environment, the ancestry, or - for a published container
        # port, where the process is the engine's proxy - the compose project.
        "live": live_starter,
        # Only a container starter, not "anything that is not live context" -
        # a process reparented to launchd has a starter and is not a container,
        # and conflating the two made every orphan read as "Started by launchd".
        "live_is_container": bool(live_starter
                                  and live_starter.get("class") == "container"),
        "recorded": None,
        "started_at": None, "first_seen_at": None, "process_started_at": None,
        "observed": False, "watching_since": watching_since(),
        "first_pid": None, "current_pid": row.get("pid"),
        "respawns": 0, "matched": "none", "certain": False,
        "carries_context": has_live,
        "project": (row.get("project") or {}).get("name"),
        "git_root": row.get("git_root") or "",
        "cwd": row.get("dir") or "",
        "sig": None,          # filled from the record, or by the caller
    }
    if not rec:
        return out
    out.update({
        "recorded": rec.get("starter"),
        # first_seen_at is a fact about Portlist. started_at is a fact about
        # the process, and is only known when the OS reported it.
        "first_seen_at": rec.get("ts"),
        "started_at": rec.get("process_started") or rec.get("ts"),
        "process_started_at": rec.get("process_started"),
        "observed": bool(rec.get("observed")),
        "watching_since": watching_since(),
        "first_pid": rec.get("pid"),
        "respawns": rec.get("respawns", 0),
        "matched": "signature",
        "certain": True,
        "git_root": out["git_root"] or rec.get("git_root") or "",
        "project": out["project"] or rec.get("project"),
        "last_respawn_at": rec.get("last_respawn_at"),
    })
    return out


def phrase(origin):
    """One line, and it never presents a memory as a live fact."""
    if not origin:
        return "not attributed"
    live, rec = origin.get("live"), origin.get("recorded")
    if live and origin.get("carries_context"):
        return "Started by %s" % live["name"]
    if origin.get("live_is_container") and live:
        return "Started by %s" % live["name"]
    # A recorded origin outranks a live starter that is only the init system
    # having adopted an orphan. That fallback is the absence of an answer.
    if rec and rec.get("name"):
        # "Originally" is a claim that something changed. When the record and
        # the live process say the same thing, nothing did, and the word is a
        # small lie about the history of the service.
        if (live or {}).get("kind") == rec.get("kind"):
            return "Started by %s" % rec["name"]
        return "Originally started by %s" % rec["name"]
    if origin.get("matched") == "ambiguous":
        return "More than one record could be this service, so it is not attributed"
    if live and live.get("name"):
        return "Started by %s" % live["name"]
    if origin.get("matched") == "ambiguous":
        return "More than one record could be this service, so it is not attributed"
    return "Not attributed"


def watching_since():
    """-> when this ledger started keeping records, or None if it never has.

    The single most important number for reading anything else here honestly.
    Portlist cannot know what happened before it was watching, so a service
    that was already running the first time it looked has an origin that was
    *inferred from the live process*, not *observed at launch*. Those are
    different claims and the ledger records which one it holds.
    """
    _read()
    if not _mem:
        return None
    return min(r.get("ts") or 0 for r in _mem) or None


def state():
    """-> every live record, newest first. For /api/ledger and the CLI."""
    _read()
    out = sorted(_by_sig.values(), key=lambda r: -(r.get("ts") or 0))
    return out


def events(limit=200, sig=None):
    """-> the raw append-only stream, newest first."""
    _read()
    out = [r for r in _mem if not sig or r.get("sig") == sig]
    return list(reversed(out))[:limit]


def forget():
    """Used by the tests, and by anyone who wants to start the record again."""
    global _mem, _by_sig, _dirty, _pending
    _mem, _by_sig, _pending, _dirty = None, None, [], False
    try:
        os.unlink(path())
    except OSError:
        pass
