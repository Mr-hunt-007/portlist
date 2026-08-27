"""Windows backend: netstat for sockets, CIM/WMI via PowerShell for the rest.

Written against documented output formats; not exercised on Windows hardware by
the author. Every collector degrades to an empty result rather than raising, so
a wrong assumption here shows as "unknown" in the UI instead of a stack trace.
"""
import json
import os
import platform
import socket
import time

from .base import RateMeter, cached, disk_usage, ip_scope, pct, run, split_hostport

_net_rates = RateMeter()

PS = ["powershell", "-NoProfile", "-NonInteractive", "-Command"]


def _ps_json(script, timeout=15):
    out = run(PS + [script + " | ConvertTo-Json -Depth 3 -Compress"], timeout=timeout)
    if not out.strip():
        return None
    try:
        val = json.loads(out)
    except ValueError:
        return None
    return val if isinstance(val, list) else [val]


def _netstat(state):
    rows = []
    for line in run(["netstat", "-ano", "-p", "TCP"], timeout=15).splitlines():
        p = line.split()
        if len(p) < 4 or p[0].upper() != "TCP":
            continue
        if state == "LISTEN" and (len(p) < 5 or p[3].upper() != "LISTENING"):
            continue
        if state == "ESTABLISHED" and (len(p) < 5 or p[3].upper() != "ESTABLISHED"):
            continue
        rows.append(p)
    return rows


@cached(10)
def _proc_names():
    data = _ps_json("Get-CimInstance Win32_Process | "
                    "Select-Object ProcessId,ParentProcessId,Name,CommandLine,ExecutablePath,CreationDate") or []
    out = {}
    for p in data:
        pid = p.get("ProcessId")
        if pid is None:
            continue
        out[int(pid)] = {
            "pid": int(pid), "ppid": int(p.get("ParentProcessId") or 0),
            "name": p.get("Name") or "?", "cmdline": p.get("CommandLine") or p.get("Name") or "",
            "exe": p.get("ExecutablePath") or "",
        }
    return out


def listening():
    names, rows = _proc_names(), []
    for p in _netstat("LISTEN"):
        addr, port = split_hostport(p[1])
        pid = int(p[4]) if len(p) > 4 and p[4].isdigit() else None
        rows.append({"pid": pid, "cmd": (names.get(pid) or {}).get("name", "?"),
                     "addr": (addr or "").strip("[]"), "port": port})
    return [r for r in rows if r["port"]]


def established():
    names, conns = _proc_names(), {}
    for p in _netstat("ESTABLISHED"):
        la, lp = split_hostport(p[1])
        ra, rp = split_hostport(p[2])
        pid = int(p[4]) if len(p) > 4 and p[4].isdigit() else 0
        if not rp:
            continue
        conns.setdefault(pid, []).append(
            {"cmd": (names.get(pid) or {}).get("name", "?"),
             "laddr": (la or "").strip("[]"), "lport": lp,
             "raddr": (ra or "").strip("[]"), "rport": rp, "scope": ip_scope(ra)})
    return conns


def processes():
    now, procs = time.time(), {}
    for pid, p in _proc_names().items():
        procs[pid] = {"pid": pid, "ppid": p["ppid"], "user": "", "cpu": 0.0,
                      "mem": 0.0, "uptime": None, "started": None,
                      "cmdline": p["cmdline"]}
    return procs


def cwds(pids):
    return {}          # not obtainable without injecting into the target process


def exe_paths(pids):
    names = _proc_names()
    return {pid: names[pid]["exe"] for pid in pids if pid in names and names[pid]["exe"]}


def environ(pid):
    return []


@cached(60)
def host():
    addrs = []
    for a in _ps_json("Get-NetIPAddress -AddressFamily IPv4 | "
                      "Select-Object IPAddress,InterfaceAlias") or []:
        ip = a.get("IPAddress", "")
        if ip and not ip.startswith("127."):
            addrs.append({"iface": a.get("InterfaceAlias", "?"), "ip": ip, "scope": ip_scope(ip)})

    fw = {"enabled": None, "stealth": None, "detail": "unknown", "name": "Windows Firewall"}
    profiles = _ps_json("Get-NetFirewallProfile | Select-Object Name,Enabled")
    if profiles:
        on = [p["Name"] for p in profiles if p.get("Enabled") in (1, True, "True")]
        fw.update(enabled=bool(on), detail="enabled on: " + (", ".join(on) or "no profiles"))
    return {"lan": addrs, "firewall": fw, "hostname": socket.gethostname()}


@cached(3600)
def _os_info():
    data = (_ps_json("Get-CimInstance Win32_OperatingSystem | "
                     "Select-Object Caption,Version,BuildNumber,OSArchitecture") or [{}])[0]
    return {"name": data.get("Caption", "Windows"), "version": data.get("Version", ""),
            "build": str(data.get("BuildNumber", "")), "kernel": platform.release(),
            "arch": data.get("OSArchitecture", platform.machine()),
            "pretty": data.get("Caption") or "Windows %s" % platform.release()}


@cached(3600)
def _cpu_info():
    data = (_ps_json("Get-CimInstance Win32_Processor | "
                     "Select-Object Name,NumberOfLogicalProcessors") or [{}])[0]
    return {"cores": data.get("NumberOfLogicalProcessors") or os.cpu_count(),
            "model": (data.get("Name") or platform.processor() or "unknown").strip(),
            "performance_cores": None, "efficiency_cores": None}


def _memory():
    d = (_ps_json("Get-CimInstance Win32_OperatingSystem | "
                  "Select-Object TotalVisibleMemorySize,FreePhysicalMemory,"
                  "TotalVirtualMemorySize,FreeVirtualMemory") or [{}])[0]
    total = (d.get("TotalVisibleMemorySize") or 0) * 1024
    free = (d.get("FreePhysicalMemory") or 0) * 1024
    used = total - free if total else None
    vt = (d.get("TotalVirtualMemorySize") or 0) * 1024
    vf = (d.get("FreeVirtualMemory") or 0) * 1024
    return {"total": total or None, "used": used, "available": free,
            "pct": pct(used, total) if total else None,
            "app": used, "wired": None, "compressed": None, "cached_files": None,
            "swap_total": max(0, vt - total) or None,
            "swap_used": max(0, (vt - vf) - (total - free)) if vt else None}


def _disks():
    disks = []
    for d in _ps_json("Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | "
                      "Select-Object DeviceID,Size,FreeSpace") or []:
        total, free = int(d.get("Size") or 0), int(d.get("FreeSpace") or 0)
        if not total:
            continue
        disks.append({"mount": d.get("DeviceID", "?"), "device": d.get("DeviceID", "?"),
                      "total": total, "free": free, "used": total - free,
                      "pct": pct(total - free, total)})
    return sorted(disks, key=lambda x: -x["total"])[:8]


def _network_io():
    ifaces = []
    for s in _ps_json("Get-NetAdapterStatistics | "
                      "Select-Object Name,ReceivedBytes,SentBytes") or []:
        name = s.get("Name", "?")
        rx, tx = int(s.get("ReceivedBytes") or 0), int(s.get("SentBytes") or 0)
        ifaces.append({"name": name, "rx": rx, "tx": tx,
                       "rx_rate": _net_rates.rate(name + ":rx", rx),
                       "tx_rate": _net_rates.rate(name + ":tx", tx)})
    return {"interfaces": ifaces,
            "rx_rate": sum(i["rx_rate"] or 0 for i in ifaces) or None,
            "tx_rate": sum(i["tx_rate"] or 0 for i in ifaces) or None}


def _users():
    out = run(["query", "user"], timeout=10)
    users = []
    for line in out.splitlines()[1:]:
        p = line.split()
        if len(p) >= 2:
            users.append({"name": p[0].lstrip(">"), "tty": p[1], "since": " ".join(p[-2:])})
    return users


@cached(300)
def _gpu():
    gpus = []
    for g in _ps_json("Get-CimInstance Win32_VideoController | "
                      "Select-Object Name,AdapterRAM,DriverVersion") or []:
        ram = g.get("AdapterRAM")
        gpus.append({"name": g.get("Name", "?"),
                     "memory": ("%.0f MiB" % (ram / 1048576)) if ram else None,
                     "driver": g.get("DriverVersion")})
    return gpus[:4]


@cached(120)
def _services():
    data = _ps_json("Get-Service | Select-Object Status") or []
    running = sum(1 for s in data if str(s.get("Status")) in ("4", "Running"))
    return {"manager": "Service Control Manager", "total": len(data), "running": running}


def _boot_time():
    d = (_ps_json("Get-CimInstance Win32_OperatingSystem | Select-Object LastBootUpTime") or [{}])[0]
    raw = str(d.get("LastBootUpTime") or "")
    if raw.startswith("/Date("):                 # /Date(1699999999999)/
        try:
            return int(raw[6:raw.index(")")]) / 1000.0
        except (ValueError, IndexError):
            return None
    try:
        return time.mktime(time.strptime(raw[:14], "%Y%m%d%H%M%S"))
    except ValueError:
        return None


def system():
    cpu, h = _cpu_info(), host()
    boot = _boot_time()
    return {
        "os": _os_info(), "hostname": h["hostname"], "boot_time": boot,
        "uptime": (time.time() - boot) if boot else None,
        "cpu": {**cpu, "load": [None, None, None], "usage_pct": None, "load_pct": None},
        "memory": _memory(), "disks": _disks(),
        "network": {**_network_io(), "addresses": h["lan"]},
        "processes": {"count": len(_proc_names())},
        "users": _users(), "gpu": _gpu(), "services": _services(),
        "security": {"firewall": h["firewall"],
                     "ssh": any(r["port"] == 22 for r in listening())},
        "updates": None,
    }
