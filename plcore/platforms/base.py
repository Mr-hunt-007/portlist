"""Shared helpers and the contract every platform backend implements.

A backend provides:
    listening()          [{pid, cmd, addr, port}]
    established()        {pid: [{laddr,lport,raddr,rport,scope}]}
    processes()          {pid: {pid,ppid,user,cpu,mem,uptime,started,cmdline}}
    cwds(pids)           {pid: path}
    exe_paths(pids)      {pid: path}
    host()               {hostname, lan[], firewall{}}
    system()             the System page payload
Anything a platform cannot answer returns None or an empty container rather
than a guess. The UI renders "unknown" and moves on.
"""
import ipaddress
import os
import subprocess
import time

LOOPBACK = {"127.0.0.1", "::1", "[::1]", "localhost", "0:0:0:0:0:0:0:1"}
WILDCARD = {"*", "0.0.0.0", "::", "[::]", "0:0:0:0:0:0:0:0"}


def run(cmd, timeout=8, env=None):
    """Run a command, return stdout, never raise."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env=env).stdout
    except Exception:
        return ""


def have(binary):
    from shutil import which
    return which(binary) is not None


def split_hostport(val):
    """'127.0.0.1:8000' / '*:8000' / '[::1]:8000' / '0.0.0.0.8000' -> (addr, port)."""
    val = val.strip()
    if val.count(":") > 1 and "]" not in val and "." not in val.rsplit(":", 1)[-1]:
        addr, _, port = val.rpartition(":")
    else:
        addr, _, port = val.rpartition(":")
    if not port.isdigit() and "." in val:          # BSD netstat style: 127.0.0.1.8000
        addr, _, port = val.rpartition(".")
    return addr, (int(port) if port.isdigit() else None)


def ip_scope(addr):
    a = (addr or "").strip("[]").split("%")[0]
    try:
        ip = ipaddress.ip_address(a)
    except ValueError:
        return "unknown"
    if ip.is_loopback:
        return "loopback"
    if ip.is_private or ip.is_link_local:
        return "private"
    return "public"


def pct(used, total):
    return round(100.0 * used / total, 1) if total else 0.0


def human(n):
    if n is None:
        return None
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if abs(n) < 1024 or unit == "PB":
            return "%.1f %s" % (n, unit) if unit != "B" else "%d B" % n
        n /= 1024.0


class RateMeter:
    """Turn monotonically increasing counters into per-second rates."""

    def __init__(self):
        self.prev = {}

    def rate(self, key, value, now=None):
        now = now or time.time()
        old = self.prev.get(key)
        self.prev[key] = (now, value)
        if not old or value < old[1]:      # first sample, or counter reset
            return None
        dt = now - old[0]
        if dt <= 0:
            return None
        return (value - old[1]) / dt


def cached(ttl):
    """Decorator: cache a zero-arg collector for `ttl` seconds."""
    def deco(fn):
        box = {"t": 0.0, "v": None}

        def wrapper():
            now = time.time()
            if box["v"] is not None and now - box["t"] < ttl:
                return box["v"]
            box["v"] = fn()
            box["t"] = now
            return box["v"]
        wrapper.__name__ = fn.__name__
        wrapper.clear = lambda: box.update(t=0.0, v=None)
        return wrapper
    return deco


def disk_usage(path):
    try:
        st = os.statvfs(path)
    except Exception:
        return None
    total = st.f_blocks * st.f_frsize
    free = st.f_bavail * st.f_frsize
    return {"total": total, "free": free, "used": total - free, "pct": pct(total - free, total)}


def ancestry(pid, procs, limit=10):
    chain, seen, cur = [], set(), pid
    while cur and cur not in seen and len(chain) < limit:
        seen.add(cur)
        p = procs.get(cur)
        if not p:
            break
        chain.append({"pid": cur, "name": short_name(p["cmdline"]),
                      "user": p.get("user"), "cmdline": p.get("cmdline", "")})
        cur = p.get("ppid") or 0
        if cur in (0,):
            break
    return list(reversed(chain))


def children(pid, procs, limit=20):
    return [{"pid": p["pid"], "name": short_name(p["cmdline"])}
            for p in procs.values() if p.get("ppid") == pid][:limit]


def short_name(cmdline):
    if not cmdline:
        return "?"
    first = cmdline.split()[0]
    return os.path.basename(first) or first
