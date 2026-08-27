"""macOS backend: lsof, ps, sysctl, vm_stat, netstat, system_profiler."""
import os
import platform
import re
import socket
import time

from .base import (RateMeter, cached, disk_usage, have, ip_scope, pct, run,
                   split_hostport)

_net_rates = RateMeter()


# ------------------------------------------------------------------ sockets

def listening():
    out = run(["lsof", "+c", "0", "-iTCP", "-sTCP:LISTEN", "-P", "-n", "-F", "pcfn"])
    rows, pid, cmd = [], None, None
    for line in out.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid = int(val) if val.isdigit() else None
        elif tag == "c":
            cmd = val
        elif tag == "n" and pid:
            addr, port = split_hostport(val)
            if port:
                rows.append({"pid": pid, "cmd": cmd or "?", "addr": addr, "port": port})
    return rows


def established():
    out = run(["lsof", "+c", "0", "-iTCP", "-sTCP:ESTABLISHED", "-P", "-n", "-F", "pcfn"])
    conns, pid, cmd = {}, None, None
    for line in out.splitlines():
        if not line:
            continue
        tag, val = line[0], line[1:]
        if tag == "p":
            pid = int(val) if val.isdigit() else None
        elif tag == "c":
            cmd = val
        elif tag == "n" and pid and "->" in val:
            local, _, remote = val.partition("->")
            la, lp = split_hostport(local)
            ra, rp = split_hostport(remote)
            if rp:
                conns.setdefault(pid, []).append(
                    {"cmd": cmd, "laddr": la, "lport": lp, "raddr": ra,
                     "rport": rp, "scope": ip_scope(ra)})
    return conns


# ---------------------------------------------------------------- processes

_ETIME = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$")


def _etime_seconds(s):
    m = _ETIME.match(s.strip())
    if not m:
        return None
    d, h, mi, sec = m.groups()
    return int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + int(sec)


def processes():
    out = run(["ps", "-axo", "pid=,ppid=,user=,pcpu=,pmem=,etime=,command="])
    now, procs = time.time(), {}
    for line in out.splitlines():
        parts = line.split(None, 6)
        if len(parts) < 7 or not parts[0].isdigit():
            continue
        pid, ppid, user, cpu, mem, etime, cmdline = parts
        secs = _etime_seconds(etime)
        procs[int(pid)] = {
            "pid": int(pid), "ppid": int(ppid) if ppid.isdigit() else 0,
            "user": user, "cpu": float(cpu or 0), "mem": float(mem or 0),
            # int, not float: ps reports whole seconds, so a float here jitters
            # every scan and makes an otherwise identical payload look changed.
            "uptime": secs, "started": int(now - secs) if secs is not None else None,
            "cmdline": cmdline}
    return procs


def cwds(pids):
    if not pids:
        return {}
    out = run(["lsof", "-a", "-p", ",".join(map(str, pids)), "-d", "cwd", "-F", "pn"])
    res, pid = {}, None
    for line in out.splitlines():
        if not line:
            continue
        if line[0] == "p":
            pid = int(line[1:]) if line[1:].isdigit() else None
        elif line[0] == "n" and pid:
            res[pid] = line[1:]
    return res


def exe_paths(pids):
    if not pids:
        return {}
    out = run(["ps", "-o", "pid=,comm=", "-p", ",".join(map(str, pids))])
    res = {}
    for line in out.splitlines():
        pid, _, comm = line.strip().partition(" ")
        if pid.isdigit():
            res[int(pid)] = comm.strip()
    return res


def environ(pid):
    """Names only - values are never read, let alone reported."""
    out = run(["ps", "-p", str(pid), "-wwEo", "command="])
    names = re.findall(r"(?:^| )([A-Z_][A-Z0-9_]{2,})=", out)
    return sorted(set(names))[:60]


def environs(pids=None):
    """Every readable environment in one ps, as {pid: [names]}.

    One subprocess instead of one per service: with twenty listeners the
    per-pid version turned a 40 ms scan into a second of forking.

    `ps -E` prints nothing extra for another user's processes, so a missing or
    empty entry means "not readable", never "no variables". Callers must keep
    that distinction; unknown is not clean.
    """
    out = run(["ps", "-axEww", "-o", "pid=,command="])
    res, cur = {}, None
    for line in out.splitlines():
        head, _, rest = line.strip().partition(" ")
        if head.isdigit():
            cur = int(head)
            res.setdefault(cur, set())
            text = rest
        elif cur is None:
            continue
        else:
            # An environment value containing a newline continues the record.
            text = line
        res[cur].update(re.findall(r"(?:^| )([A-Z_][A-Z0-9_]{2,})=", text))
    want = set(pids) if pids else None
    return {pid: sorted(names)[:80] for pid, names in res.items()
            if names and (want is None or pid in want)}


# --------------------------------------------------------------------- host

@cached(60)
def host():
    addrs, iface = [], None
    for line in run(["ifconfig"]).splitlines():
        if line and not line[0].isspace():
            iface = line.split(":")[0]
        m = re.search(r"\binet (\d+\.\d+\.\d+\.\d+)", line)
        if m and iface != "lo0":
            ip = m.group(1)
            if not ip.startswith("127."):
                addrs.append({"iface": iface, "ip": ip, "scope": ip_scope(ip)})

    fw = {"enabled": None, "stealth": None, "detail": "unknown", "name": "Application Firewall"}
    fwbin = "/usr/libexec/ApplicationFirewall/socketfilterfw"
    if os.path.exists(fwbin):
        g = run([fwbin, "--getglobalstate"]).strip()
        s = run([fwbin, "--getstealthmode"]).strip()
        if g:
            fw["enabled"] = "enabled" in g.lower() and "disabled" not in g.lower()
            fw["detail"] = g
        if s:
            fw["stealth"] = "enabled" in s.lower() and "disabled" not in s.lower()
    return {"lan": addrs, "firewall": fw, "hostname": socket.gethostname()}


# ------------------------------------------------------------------- system

@cached(3600)
def _os_info():
    return {"name": "macOS",
            "version": run(["sw_vers", "-productVersion"]).strip(),
            "build": run(["sw_vers", "-buildVersion"]).strip(),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "pretty": "macOS %s (%s)" % (run(["sw_vers", "-productVersion"]).strip(),
                                         platform.machine())}


@cached(3600)
def _cpu_info():
    cores = run(["sysctl", "-n", "hw.ncpu"]).strip()
    perf = run(["sysctl", "-n", "hw.perflevel0.logicalcpu"]).strip()
    eff = run(["sysctl", "-n", "hw.perflevel1.logicalcpu"]).strip()
    model = run(["sysctl", "-n", "machdep.cpu.brand_string"]).strip()
    return {"cores": int(cores) if cores.isdigit() else None,
            "model": model or platform.processor() or "unknown",
            "performance_cores": int(perf) if perf.isdigit() else None,
            "efficiency_cores": int(eff) if eff.isdigit() else None}


def _boot_time():
    out = run(["sysctl", "-n", "kern.boottime"])
    m = re.search(r"sec\s*=\s*(\d+)", out)
    return int(m.group(1)) if m else None


def _memory():
    total = run(["sysctl", "-n", "hw.memsize"]).strip()
    total = int(total) if total.isdigit() else None
    vm = run(["vm_stat"])
    page = 4096
    m = re.search(r"page size of (\d+) bytes", vm)
    if m:
        page = int(m.group(1))
    stats = {}
    for line in vm.splitlines():
        k, _, v = line.partition(":")
        v = v.strip().rstrip(".")
        if v.isdigit():
            stats[k.strip()] = int(v) * page
    # Activity Monitor's "Memory Used" = app memory + wired + compressed.
    # total-minus-free would read ~99% on any healthy Mac, because the kernel
    # spends idle RAM on file cache. That number is true and useless.
    wired = stats.get("Pages wired down", 0)
    compressed = stats.get("Pages occupied by compressor", 0)
    anon = stats.get("Anonymous pages", 0)
    purgeable = stats.get("Pages purgeable", 0)
    cached_files = stats.get("File-backed pages", 0)
    app = max(0, anon - purgeable)
    used = app + wired + compressed
    free = (total - used) if total else None
    sw = run(["sysctl", "-n", "vm.swapusage"])
    sm = re.search(r"total = ([\d.]+)M.*used = ([\d.]+)M", sw)
    return {"total": total, "used": used, "available": free,
            "pct": pct(used, total) if total else None,
            "app": app, "wired": wired, "compressed": compressed,
            "cached_files": cached_files,
            "swap_total": int(float(sm.group(1)) * 1048576) if sm else None,
            "swap_used": int(float(sm.group(2)) * 1048576) if sm else None}


def _disks():
    out, disks = run(["df", "-k"]), []
    for line in out.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9 or not parts[1].isdigit():
            continue
        mount = " ".join(parts[8:])
        if mount.startswith(("/System/Volumes/VM", "/System/Volumes/Preboot",
                             "/System/Volumes/Update", "/System/Volumes/xarts",
                             "/System/Volumes/iSCPreboot", "/System/Volumes/Hardware",
                             "/private/var/vm", "/dev")):
            continue
        u = disk_usage(mount)
        if not u:
            continue
        disks.append({"mount": mount, "device": parts[0], **u})
    seen, out2 = set(), []
    for d in sorted(disks, key=lambda x: -x["used"]):
        key = (d["total"], d["free"])       # / and /System/Volumes/Data share a store
        if d["device"] in seen or key in seen:
            continue
        seen.add(d["device"])
        seen.add(key)
        out2.append(d)
    return out2[:8]


def _network_io():
    """Per-interface byte counters from netstat -ibn, deduped to one row per iface."""
    out, ifaces, seen = run(["netstat", "-ibn"]), [], set()
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) < 10 or p[0] in seen:
            continue
        try:
            rx, tx = int(p[6]), int(p[9])
        except (ValueError, IndexError):
            continue
        seen.add(p[0])
        name = p[0].rstrip("*")
        ifaces.append({"name": name, "rx": rx, "tx": tx,
                       "rx_rate": _net_rates.rate(name + ":rx", rx),
                       "tx_rate": _net_rates.rate(name + ":tx", tx)})
    live = [i for i in ifaces if not i["name"].startswith(("lo", "gif", "stf", "utun", "awdl", "llw"))]
    return {"interfaces": ifaces,
            "rx_rate": sum(i["rx_rate"] or 0 for i in live) or None,
            "tx_rate": sum(i["tx_rate"] or 0 for i in live) or None}


def _users():
    users = []
    for line in run(["who"]).splitlines():
        p = line.split(None, 2)
        if len(p) >= 2:
            users.append({"name": p[0], "tty": p[1], "since": p[2].strip() if len(p) > 2 else ""})
    return users


@cached(600)
def _gpu():
    out = run(["system_profiler", "-detailLevel", "mini", "SPDisplaysDataType"], timeout=12)
    gpus, cur = [], None
    for line in out.splitlines():
        s = line.strip()
        if s.endswith(":") and not line.startswith("        ") and len(s) > 1 and ":" not in s[:-1]:
            cur = {"name": s[:-1]}
            gpus.append(cur)
        elif cur is not None:
            if s.startswith("Chipset Model:"):
                cur["name"] = s.split(":", 1)[1].strip()
            elif s.startswith("Total Number of Cores:"):
                cur["cores"] = s.split(":", 1)[1].strip()
            elif s.startswith("VRAM"):
                cur["memory"] = s.split(":", 1)[1].strip()
            elif s.startswith("Vendor:"):
                cur["vendor"] = s.split(":", 1)[1].strip()
    return [g for g in gpus if g.get("name") and "Displays" not in g["name"]][:4]


@cached(120)
def _services():
    out = run(["launchctl", "list"])
    lines = [l for l in out.splitlines()[1:] if l.strip()]
    running = sum(1 for l in lines if l.split("\t")[0].strip().isdigit())
    return {"manager": "launchd", "total": len(lines), "running": running}


def _ssh_enabled():
    return any(r["port"] == 22 for r in listening())


def system():
    cpu, mem = _cpu_info(), _memory()
    boot = _boot_time()
    try:
        load = os.getloadavg()
    except OSError:
        load = (None, None, None)
    procs = processes()
    h = host()
    return {
        "os": _os_info(),
        "hostname": h["hostname"],
        "boot_time": boot,
        "uptime": (time.time() - boot) if boot else None,
        "cpu": {**cpu, "load": list(load),
                "load_pct": pct(load[0], cpu["cores"]) if load[0] is not None and cpu["cores"] else None},
        "memory": mem,
        "disks": _disks(),
        "network": {**_network_io(), "addresses": h["lan"]},
        "processes": {"count": len(procs)},
        "users": _users(),
        "gpu": _gpu(),
        "services": _services(),
        "security": {"firewall": h["firewall"], "ssh": _ssh_enabled()},
        "updates": None,          # softwareupdate -l hits the network; opt-in only
    }
