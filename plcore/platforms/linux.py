"""Linux backend: /proc first, ss/ip as a fallback, no root required.

Socket->pid mapping works three ways, in order of preference:
  1. `ss -tlnpH`            (fast, gives pid inline)
  2. `netstat -tlnp`        (older boxes)
  3. /proc/net/tcp{,6} inode -> /proc/*/fd scan   (no tools at all)
Without root, other users' processes appear without pid attribution rather
than being dropped: an unattributed listener is still an exposure.
"""
import os
import platform
import re
import socket
import time

from .base import (RateMeter, cached, disk_usage, have, ip_scope, pct, run,
                   split_hostport)

_net_rates = RateMeter()
_cpu_prev = {}


# ------------------------------------------------------------------ sockets

def _hex_addr(h):
    """/proc/net/tcp address: little-endian hex '0100007F:1F90'."""
    addr, _, port = h.partition(":")
    port = int(port, 16)
    if len(addr) == 8:
        b = bytes.fromhex(addr)[::-1]
        return socket.inet_ntop(socket.AF_INET, b), port
    if len(addr) == 32:
        raw = bytes.fromhex(addr)
        b = b"".join(raw[i:i + 4][::-1] for i in range(0, 32, 4))
        return socket.inet_ntop(socket.AF_INET6, b), port
    return addr, port


def _inode_to_pid():
    """Map socket inodes to pids by walking /proc/*/fd. Only sees our own procs
    unless running as root, which is exactly what the caller should expect."""
    table = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        fd_dir = "/proc/%s/fd" % pid
        try:
            fds = os.listdir(fd_dir)
        except OSError:
            continue
        for fd in fds:
            try:
                link = os.readlink(os.path.join(fd_dir, fd))
            except OSError:
                continue
            if link.startswith("socket:["):
                table[link[8:-1]] = int(pid)
    return table


def _proc_net(path, state_hex):
    rows = []
    try:
        with open(path) as f:
            lines = f.readlines()[1:]
    except OSError:
        return rows
    for line in lines:
        p = line.split()
        if len(p) < 10 or p[3] != state_hex:
            continue
        la, lp = _hex_addr(p[1])
        ra, rp = _hex_addr(p[2])
        rows.append({"laddr": la, "lport": lp, "raddr": ra, "rport": rp, "inode": p[9]})
    return rows


def _proc_names():
    names = {}
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/comm" % pid) as f:
                names[int(pid)] = f.read().strip()
        except OSError:
            pass
    return names


def listening():
    rows = []
    if have("ss"):
        out = run(["ss", "-tlnpH"])
        for line in out.splitlines():
            p = line.split()
            if len(p) < 4:
                continue
            addr, port = split_hostport(p[3])
            if not port:
                continue
            pid, cmd = None, "?"
            m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
            if m:
                cmd, pid = m.group(1), int(m.group(2))
            rows.append({"pid": pid, "cmd": cmd, "addr": addr.strip("[]"), "port": port})
        if rows:
            return rows

    if have("netstat"):
        out = run(["netstat", "-tlnp"])
        for line in out.splitlines():
            if "LISTEN" not in line:
                continue
            p = line.split()
            if len(p) < 4:
                continue
            addr, port = split_hostport(p[3])
            if not port:
                continue
            pid, cmd = None, "?"
            if len(p) >= 7 and "/" in p[6]:
                pidstr, _, cmd = p[6].partition("/")
                pid = int(pidstr) if pidstr.isdigit() else None
            rows.append({"pid": pid, "cmd": cmd or "?", "addr": addr.strip("[]"), "port": port})
        if rows:
            return rows

    inodes, names = _inode_to_pid(), _proc_names()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        for r in _proc_net(path, "0A"):          # 0A = TCP_LISTEN
            pid = inodes.get(r["inode"])
            rows.append({"pid": pid, "cmd": names.get(pid, "?") if pid else "?",
                         "addr": r["laddr"], "port": r["lport"]})
    return rows


def established():
    conns = {}
    if have("ss"):
        out = run(["ss", "-tnpH", "state", "established"])
        for line in out.splitlines():
            p = line.split()
            if len(p) < 4:
                continue
            la, lp = split_hostport(p[2])
            ra, rp = split_hostport(p[3])
            if not rp:
                continue
            m = re.search(r'users:\(\("([^"]+)",pid=(\d+)', line)
            pid = int(m.group(2)) if m else 0
            conns.setdefault(pid, []).append(
                {"cmd": m.group(1) if m else "?", "laddr": la.strip("[]"), "lport": lp,
                 "raddr": ra.strip("[]"), "rport": rp, "scope": ip_scope(ra)})
        if conns:
            return conns

    inodes = _inode_to_pid()
    for path in ("/proc/net/tcp", "/proc/net/tcp6"):
        for r in _proc_net(path, "01"):          # 01 = TCP_ESTABLISHED
            pid = inodes.get(r["inode"], 0)
            conns.setdefault(pid, []).append(
                {"cmd": "?", "laddr": r["laddr"], "lport": r["lport"],
                 "raddr": r["raddr"], "rport": r["rport"], "scope": ip_scope(r["raddr"])})
    return conns


# ---------------------------------------------------------------- processes

def processes():
    out = run(["ps", "-axo", "pid=,ppid=,user=,pcpu=,pmem=,etime=,args="])
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
    if procs:
        return procs
    return _processes_proc()


_ETIME = re.compile(r"^(?:(\d+)-)?(?:(\d+):)?(\d+):(\d+)$")


def _etime_seconds(s):
    m = _ETIME.match(s.strip())
    if not m:
        return None
    d, h, mi, sec = m.groups()
    return int(d or 0) * 86400 + int(h or 0) * 3600 + int(mi) * 60 + int(sec)


def _processes_proc():
    """ps-free fallback straight out of /proc."""
    procs, hz = {}, os.sysconf("SC_CLK_TCK")
    boot = _boot_time() or 0
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            with open("/proc/%s/stat" % pid) as f:
                stat = f.read()
            with open("/proc/%s/cmdline" % pid, "rb") as f:
                cmdline = f.read().replace(b"\0", b" ").decode("utf-8", "replace").strip()
            st = os.stat("/proc/%s" % pid)
        except OSError:
            continue
        rp = stat.rfind(")")
        fields = stat[rp + 2:].split()
        ppid = int(fields[1]) if len(fields) > 1 else 0
        starttime = int(fields[19]) / hz if len(fields) > 19 else 0
        started = boot + starttime
        try:
            import pwd
            user = pwd.getpwuid(st.st_uid).pw_name
        except Exception:
            user = str(st.st_uid)
        procs[int(pid)] = {"pid": int(pid), "ppid": ppid, "user": user, "cpu": 0.0,
                           "mem": 0.0, "uptime": time.time() - started,
                           "started": started, "cmdline": cmdline or stat[stat.find("(") + 1:rp]}
    return procs


def cwds(pids):
    res = {}
    for pid in pids:
        try:
            res[pid] = os.readlink("/proc/%s/cwd" % pid)
        except OSError:
            pass
    return res


def exe_paths(pids):
    res = {}
    for pid in pids:
        try:
            res[pid] = os.readlink("/proc/%s/exe" % pid)
        except OSError:
            pass
    return res


def environ(pid):
    """Variable NAMES only. Values are never read."""
    try:
        with open("/proc/%s/environ" % pid, "rb") as f:
            raw = f.read().decode("utf-8", "replace")
    except OSError:
        return []
    return sorted({e.split("=", 1)[0] for e in raw.split("\0") if "=" in e})[:60]


def environs(pids=None):
    """{pid: [names]} for every environment this user may read.

    /proc/<pid>/environ is 0400 and owned by the process user, so another
    user's process simply raises here. That absence is reported as unknown by
    the caller, never as "holds no credentials".
    """
    if pids is None:
        pids = [int(d) for d in os.listdir("/proc") if d.isdigit()]
    out = {}
    for pid in pids:
        names = environ(int(pid))
        if names:
            out[int(pid)] = names
    return out


# --------------------------------------------------------------------- host

@cached(60)
def host():
    addrs = []
    if have("ip"):
        for line in run(["ip", "-o", "-4", "addr", "show"]).splitlines():
            p = line.split()
            if len(p) >= 4 and p[2] == "inet":
                ip = p[3].split("/")[0]
                if not ip.startswith("127.") and p[1] != "lo":
                    addrs.append({"iface": p[1], "ip": ip, "scope": ip_scope(ip)})
    elif have("ifconfig"):
        iface = None
        for line in run(["ifconfig"]).splitlines():
            if line and not line[0].isspace():
                iface = line.split(":")[0].split()[0]
            m = re.search(r"inet (?:addr:)?(\d+\.\d+\.\d+\.\d+)", line)
            if m and iface != "lo":
                ip = m.group(1)
                if not ip.startswith("127."):
                    addrs.append({"iface": iface, "ip": ip, "scope": ip_scope(ip)})

    fw = {"enabled": None, "stealth": None, "detail": "unknown", "name": "unknown"}
    if have("ufw"):
        out = run(["ufw", "status"])
        if out:
            fw = {"name": "ufw", "enabled": "Status: active" in out,
                  "stealth": None, "detail": out.splitlines()[0].strip() if out else ""}
    if fw["enabled"] is None and have("firewall-cmd"):
        out = run(["firewall-cmd", "--state"]).strip()
        if out:
            fw = {"name": "firewalld", "enabled": out == "running", "stealth": None, "detail": out}
    if fw["enabled"] is None and have("nft"):
        out = run(["nft", "list", "ruleset"])
        if out.strip():
            fw = {"name": "nftables", "enabled": True, "stealth": None,
                  "detail": "%d ruleset lines" % len(out.splitlines())}
    if fw["enabled"] is None and have("iptables"):
        out = run(["iptables", "-S"])
        if out:
            drops = [l for l in out.splitlines() if l.startswith("-P") and "DROP" in l]
            fw = {"name": "iptables", "enabled": bool(drops) or len(out.splitlines()) > 3,
                  "stealth": None, "detail": "%d rules" % len(out.splitlines())}
    return {"lan": addrs, "firewall": fw, "hostname": socket.gethostname()}


# ------------------------------------------------------------------- system

@cached(3600)
def _os_info():
    info = {}
    try:
        with open("/etc/os-release") as f:
            for line in f:
                k, _, v = line.strip().partition("=")
                info[k] = v.strip('"')
    except OSError:
        pass
    return {"name": info.get("NAME", "Linux"),
            "version": info.get("VERSION_ID", ""),
            "build": info.get("BUILD_ID", ""),
            "kernel": platform.release(),
            "arch": platform.machine(),
            "pretty": info.get("PRETTY_NAME") or "Linux %s" % platform.release()}


@cached(3600)
def _cpu_info():
    model, cores = None, 0
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.startswith("model name") and not model:
                    model = line.split(":", 1)[1].strip()
                if line.startswith("processor"):
                    cores += 1
    except OSError:
        pass
    return {"cores": cores or os.cpu_count(), "model": model or platform.machine(),
            "performance_cores": None, "efficiency_cores": None}


def _boot_time():
    try:
        with open("/proc/uptime") as f:
            return time.time() - float(f.read().split()[0])
    except OSError:
        return None


def _cpu_usage():
    """Percent busy since the previous call, from /proc/stat."""
    try:
        with open("/proc/stat") as f:
            fields = [int(x) for x in f.readline().split()[1:]]
    except (OSError, ValueError):
        return None
    idle = fields[3] + (fields[4] if len(fields) > 4 else 0)
    total = sum(fields)
    prev = _cpu_prev.get("all")
    _cpu_prev["all"] = (total, idle)
    if not prev or total <= prev[0]:
        return None
    return round(100.0 * (1 - (idle - prev[1]) / (total - prev[0])), 1)


def _memory():
    m = {}
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, v = line.partition(":")
                m[k.strip()] = int(v.split()[0]) * 1024
    except OSError:
        return {}
    total = m.get("MemTotal")
    avail = m.get("MemAvailable", m.get("MemFree", 0))
    used = (total - avail) if total else None
    return {"total": total, "used": used, "available": avail,
            "pct": pct(used, total) if total else None,
            "app": used, "wired": None, "compressed": None,
            "cached_files": m.get("Cached"),
            "swap_total": m.get("SwapTotal"),
            "swap_used": (m.get("SwapTotal", 0) - m.get("SwapFree", 0)) or 0}


def _disks():
    disks, seen = [], set()
    try:
        with open("/proc/mounts") as f:
            mounts = f.readlines()
    except OSError:
        mounts = []
    for line in mounts:
        p = line.split()
        if len(p) < 3:
            continue
        dev, mount, fstype = p[0], p[1].replace("\\040", " "), p[2]
        if fstype in ("proc", "sysfs", "devtmpfs", "devpts", "tmpfs", "cgroup",
                      "cgroup2", "overlay", "squashfs", "autofs", "mqueue",
                      "debugfs", "tracefs", "securityfs", "pstore", "bpf",
                      "configfs", "fusectl", "hugetlbfs", "ramfs", "nsfs"):
            continue
        if not dev.startswith("/"):
            continue
        u = disk_usage(mount)
        if not u or not u["total"] or dev in seen:
            continue
        seen.add(dev)
        disks.append({"mount": mount, "device": dev, **u})
    return sorted(disks, key=lambda d: -d["total"])[:8]


def _network_io():
    ifaces = []
    try:
        with open("/proc/net/dev") as f:
            lines = f.readlines()[2:]
    except OSError:
        lines = []
    for line in lines:
        name, _, rest = line.partition(":")
        p = rest.split()
        if len(p) < 9:
            continue
        name = name.strip()
        rx, tx = int(p[0]), int(p[8])
        ifaces.append({"name": name, "rx": rx, "tx": tx,
                       "rx_rate": _net_rates.rate(name + ":rx", rx),
                       "tx_rate": _net_rates.rate(name + ":tx", tx)})
    live = [i for i in ifaces if i["name"] != "lo"]
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


@cached(120)
def _gpu():
    if not have("nvidia-smi"):
        return []
    out = run(["nvidia-smi",
               "--query-gpu=name,memory.total,memory.used,utilization.gpu,temperature.gpu",
               "--format=csv,noheader,nounits"], timeout=10)
    gpus = []
    for line in out.strip().splitlines():
        p = [x.strip() for x in line.split(",")]
        if len(p) >= 4:
            gpus.append({"name": p[0], "memory": "%s MiB" % p[1],
                         "memory_used": "%s MiB" % p[2], "utilization": p[3] + "%",
                         "temperature": (p[4] + " C") if len(p) > 4 else None})
    return gpus


@cached(120)
def _services():
    if not have("systemctl"):
        return {"manager": "unknown", "total": None, "running": None}
    out = run(["systemctl", "list-units", "--type=service", "--all", "--no-legend",
               "--no-pager", "--plain"], timeout=12)
    lines = [l for l in out.splitlines() if l.strip()]
    running = sum(1 for l in lines if " running " in l)
    return {"manager": "systemd", "total": len(lines), "running": running}


@cached(900)
def _updates():
    path = "/var/lib/update-notifier/updates-available"
    if os.path.exists(path):
        try:
            with open(path) as f:
                txt = f.read()
            m = re.search(r"(\d+)\s+update", txt)
            sec = re.search(r"(\d+)\s+.*security", txt)
            return {"count": int(m.group(1)) if m else None,
                    "security": int(sec.group(1)) if sec else None,
                    "source": "update-notifier"}
        except OSError:
            pass
    return None


def _ssh_enabled():
    return any(r["port"] == 22 for r in listening())


def system():
    cpu, h = _cpu_info(), host()
    boot = _boot_time()
    try:
        load = os.getloadavg()
    except OSError:
        load = (None, None, None)
    return {
        "os": _os_info(), "hostname": h["hostname"], "boot_time": boot,
        "uptime": (time.time() - boot) if boot else None,
        "cpu": {**cpu, "load": list(load), "usage_pct": _cpu_usage(),
                "load_pct": pct(load[0], cpu["cores"]) if load[0] is not None and cpu["cores"] else None},
        "memory": _memory(), "disks": _disks(),
        "network": {**_network_io(), "addresses": h["lan"]},
        "processes": {"count": len(processes())},
        "users": _users(), "gpu": _gpu(), "services": _services(),
        "security": {"firewall": h["firewall"], "ssh": _ssh_enabled()},
        "updates": _updates(),
    }
