"""Platform-neutral facade. Everything above this line is OS-agnostic."""
from .platforms import NAME, SYSTEM, VERIFIED, impl
from .platforms.base import (LOOPBACK, WILDCARD, ancestry, children, human,
                             ip_scope, run, short_name)

import time as _time
import threading as _threading

_cache = {}
_cache_lock = _threading.Lock()
_TTL = 1.5          # one request should not shell out for the same data twice


_MAX_KEYS = 32


def _shared(name, fn, ttl=_TTL):
    """Collapse repeat calls within a request. Several endpoints need the same
    process table and socket list; without this, one /api/connections spawned
    lsof four times and ps twice for data it already had.

    Entries expire by time, and the map is swept when it grows: one key here is
    derived from a set of pids, which changes as processes come and go, so
    without a sweep this would accumulate a dead entry per scan forever.
    """
    now = _time.time()
    with _cache_lock:
        hit = _cache.get(name)
        if hit and now - hit[0] < ttl:
            return hit[1]
    val = fn()
    with _cache_lock:
        _cache[name] = (now, val)
        if len(_cache) > _MAX_KEYS:
            for k in [k for k, v in _cache.items() if now - v[0] > ttl]:
                _cache.pop(k, None)
    return val


def listening():
    return _shared("listening", impl.listening)


def established():
    return _shared("established", impl.established)


def processes():
    return _shared("processes", impl.processes)


def invalidate():
    with _cache_lock:
        _cache.clear()


cwds = impl.cwds
exe_paths = impl.exe_paths
host = impl.host
system = impl.system
environ = getattr(impl, "environ", lambda pid: [])


def environs(pids=None):
    """{pid: [env names]} for the pids that can be read. A pid missing from the
    result is unreadable, which is not the same as having no environment."""
    fn = getattr(impl, "environs", None)
    if fn:
        key = "environs:" + (str(hash(frozenset(pids))) if pids else "all")
        return _shared(key, lambda: fn(pids), ttl=3.0)
    return {p: environ(p) for p in (pids or []) if environ(p)}

__all__ = ["invalidate", "listening", "established", "processes", "cwds", "exe_paths", "host",
           "system", "environ", "environs", "ancestry", "children", "ip_scope", "short_name",
           "human", "run", "LOOPBACK", "WILDCARD", "NAME", "SYSTEM", "VERIFIED",
           "reachable_from"]


def reachable_from(ip, port, timeout=0.4):
    """Prove a bind is really accepting on a non-loopback address."""
    import socket
    try:
        s = socket.create_connection((ip, port), timeout)
        s.close()
        return True
    except Exception:
        return False
