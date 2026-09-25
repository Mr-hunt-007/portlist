"""`portlist report`: this machine's listeners as one HTML file you can hand on.

One self-contained page: no scripts, no fonts or pictures fetched from anywhere,
so it opens offline, in a mail client's preview, attached to an issue. It says
what was measured and how, and what was not: reachability was tested from this
machine's own network addresses, which is not a scan from the internet, and an
origin portlist never saw stays unknown.

Command lines are in it, with anything that looks like a secret masked
(`--token=...`, `password=...`, long random strings). `--redact` goes further for
a report leaving your team: host and user names, addresses, project names and
paths, and command lines are all taken out.
"""
import html
import os
import re
import sys
import time

from . import explain as ex

SECRETISH = re.compile(r"(?i)((?:--?|\b)[\w.-]*(?:token|secret|passw(?:or)?d|pwd|api[_-]?key|auth|key)[\w.-]*[=: ])(\S+)")
LONG = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")
URL_CRED = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/@\s]*:)[^@\s]+@", re.I)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def mask(cmdline):
    s = URL_CRED.sub(lambda m: m.group(1) + "***@", cmdline or "")
    s = SECRETISH.sub(lambda m: m.group(1) + "***", s)
    return LONG.sub("***", s)


class Redactor:
    """Stable stand-ins, so two mentions of one project stay one project."""

    def __init__(self, on):
        self.on = on
        self.seen = {}

    def _alias(self, kind, value):
        if not value:
            return value
        key = (kind, value)
        if key not in self.seen:
            n = sum(1 for k in self.seen if k[0] == kind) + 1
            self.seen[key] = "%s-%d" % (kind, n)
        return self.seen[key]

    def project(self, v): return self._alias("project", v) if self.on else v
    def host(self, v): return "this-machine" if self.on and v else v
    def user(self, v): return self._alias("user", v) if self.on and v not in ("root", None) else v
    def path(self, v): return "" if self.on else (v or "")
    def cmd(self, v):
        """The interpreter's install path is not what anybody typed: keep its name."""
        if self.on:
            return ""
        parts = (v or "").split(" ", 1)
        return mask(os.path.basename(parts[0]) + (" " + parts[1] if len(parts) > 1 else ""))

    def text(self, v):
        """Free text (a warning): addresses and paths out when redacting."""
        if not self.on or not v:
            return v
        return re.sub(r"(?:~|/)[^\s,;()]+", "[path]", self.addr(v))

    def box(self, v): return self._alias("container", v) if self.on else v

    def addr(self, v):
        if not self.on or not v:
            return v
        return IPV4.sub(lambda m: m.group(0) if m.group(0).startswith(("127.", "0.0.0.0")) else "x.x.x.x", v)


def _e(v):
    return html.escape("" if v is None else str(v))


def _tone(row):
    band = row.get("risk_band")
    exp = row.get("exposure") or {}
    if band in ("High", "Critical") or (exp.get("verified") or {}).get("accepting"):
        return "bad"
    if band == "Medium" or exp.get("level") not in (None, "loopback"):
        return "warn"
    return "ok"


CSS = """
:root{--paper:#F2EFE7;--paper2:#EAE6DC;--ink:#14110E;--soft:#2A2724;--grey:#6E6A63;--faint:#9A958C;--rule:#D8D3C7;
--shu:#C8452F;--warn:#A86F12;--ok:#4E7A3A;--disp:"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif;
--sans:-apple-system,"Segoe UI",system-ui,sans-serif;--mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
@media (prefers-color-scheme:dark){:root{--paper:#171513;--paper2:#201d1a;--ink:#EDE8DE;--soft:#D5CFC3;--grey:#A39C90;
--faint:#7D776C;--rule:#34302b;--shu:#EE6A4F;--warn:#E0A84A;--ok:#93B872}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 var(--sans)}
.wrap{max-width:1060px;margin:0 auto;padding:40px 28px 60px}
.meta{font:11px var(--mono);letter-spacing:.18em;text-transform:uppercase;color:var(--faint)}
header{border-bottom:2px solid var(--ink);padding-bottom:18px}
h1{font:800 44px/1.05 var(--disp);margin:6px 0 10px;letter-spacing:-.02em}h1 span{color:var(--shu)}
.verdict{font:600 21px/1.35 var(--disp);max-width:46ch;margin:22px 0 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:0;border-top:1px solid var(--rule);margin:26px 0 0}
.tile{padding:14px 12px 12px 0;border-bottom:1px solid var(--rule)}.tile b{display:block;font:700 34px/1 var(--disp)}
.tile small{font:11px var(--mono);letter-spacing:.12em;text-transform:uppercase;color:var(--grey)}
.tile.bad b{color:var(--shu)}.tile.warn b{color:var(--warn)}
h2{font:700 24px/1.2 var(--disp);margin:46px 0 4px}h2+p{margin:0 0 14px;color:var(--grey)}
.card{border-top:1px solid var(--ink);padding:14px 0 12px;display:grid;grid-template-columns:120px 1fr;gap:4px 18px}
.card .port{font:700 26px/1 var(--disp)}.card.bad .port{color:var(--shu)}.card.warn .port{color:var(--warn)}
.card .svc{font-weight:600}.card dl{margin:6px 0 0;display:grid;grid-template-columns:110px 1fr;gap:2px 12px;font-size:14px}
.card dt{font:11px var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--faint);padding-top:3px}.card dd{margin:0}
.card ul{margin:8px 0 0;padding-left:18px}.card li{color:var(--warn)}.card li.bad{color:var(--shu)}
code,.mono{font:12.5px var(--mono)}code{background:var(--paper2);padding:1px 5px;word-break:break-all}
table{width:100%;border-collapse:collapse;font-size:13.5px}th{font:11px var(--mono);letter-spacing:.1em;text-transform:uppercase;
color:var(--faint);text-align:left;border-bottom:1px solid var(--ink);padding:6px 8px 6px 0}
td{border-bottom:1px solid var(--rule);padding:7px 8px 7px 0;vertical-align:top}td.p{font:600 13px var(--mono)}
tr.bad td.p,tr.bad .r{color:var(--shu)}tr.warn td.p,tr.warn .r{color:var(--warn)}.dim{color:var(--grey)}
.scroll{overflow-x:auto}.group{margin:0 0 14px}.group h3{font:600 16px var(--disp);margin:0 0 4px}
.group h3 em{font:12px var(--mono);font-style:normal;color:var(--grey);margin-left:8px}.ai{color:var(--shu)}
.method{border-top:1px solid var(--rule);margin-top:46px;padding-top:14px;color:var(--grey);font-size:13.5px}
.method li{margin:0 0 6px}footer{margin-top:30px;font:11px var(--mono);color:var(--faint)}
@media print{body{background:#fff}.wrap{padding:0}.card{break-inside:avoid}}
@media (max-width:640px){.card{grid-template-columns:1fr}.card dl{grid-template-columns:90px 1fr}h1{font-size:34px}}
"""


def build(rows, host=None, sysinfo=None, details=None, redact=False, now=None, version=""):
    """-> the report as one HTML string. `details` maps pid -> scan.detail(row)."""
    now = now or time.time()
    R = Redactor(redact)
    details = details or {}
    live = sorted([r for r in rows if not r.get("quiet")], key=lambda r: r.get("port") or 0)
    quiet = [r for r in rows if r.get("quiet")]
    host = host or {}
    si = sysinfo or {}
    name = R.host((host.get("hostname") or si.get("hostname") or "this machine").split(".")[0])
    osname = ((si.get("os") or {}).get("pretty") or (si.get("os") or {}).get("name") or sys.platform)

    answers = {}
    for r in live:
        try:
            answers[id(r)] = ex.explain(r, details.get(r.get("pid")) or {}, now)
        except Exception:
            answers[id(r)] = None

    verified = [r for r in live if ((r.get("exposure") or {}).get("verified") or {}).get("accepting")]
    bound = [r for r in live if (r.get("exposure") or {}).get("level") not in (None, "loopback")]
    attention = [r for r in live if r.get("risk_band") in ("High", "Critical")]
    leftovers = [r for r in live if (r.get("leftover") or {}).get("likely")]
    by_ai = [r for r in live if (r.get("starter") or {}).get("ai")]
    ai_gone = [r for r in by_ai if (r.get("starter") or {}).get("alive") is False]

    # one sentence first: what a reader should take away before any table
    bits = []
    if verified:
        bits.append("%d reachable from beyond this machine" % len(verified))
    elif bound:
        bits.append("%d bound beyond loopback, none verified reachable" % len(bound))
    if attention:
        bits.append("%d at high or critical risk" % len(attention))
    if leftovers:
        bits.append("%d that look%s left over" % (len(leftovers), "s" if len(leftovers) == 1 else ""))
    if ai_gone:
        bits.append("%d started by an AI agent that has since exited" % len(ai_gone))
    said = "; ".join(bits)
    verdict = ("%d listening. " % len(live)) + (said[:1].upper() + said[1:] + "." if bits else
                                                "Nothing reachable from beyond this machine, nothing left over.")

    def tile(n, label, tone=""):
        return '<div class="tile %s"><b>%d</b><small>%s</small></div>' % (tone if n else "", n, _e(label))

    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           '<title>portlist report: %s</title><style>%s</style></head><body><div class="wrap">' % (_e(name), CSS),
           '<header><div class="meta">portlist report &middot; %s &middot; %s</div>' % (
               _e(time.strftime("%d %b %Y %H:%M", time.localtime(now))), _e(osname)),
           '<h1>%s<span>.</span></h1>' % _e(name),
           '<p class="verdict">%s</p>' % _e(verdict),
           '<div class="tiles">', tile(len(live), "listening"), tile(len(verified), "reachable, verified", "bad"),
           tile(len(bound), "beyond loopback", "warn"), tile(len(attention), "high or critical", "bad"),
           tile(len(leftovers), "left over", "warn"), tile(len(by_ai), "started by AI"),
           tile(len(ai_gone), "AI starter exited", "warn"), '</div></header>']

    # what needs a look: every listener with a warning, worst first
    look = [r for r in live if answers.get(id(r)) and answers[id(r)]["warnings"]]
    look.sort(key=lambda r: ({"bad": 0, "warn": 1, "ok": 2}[_tone(r)], -(r.get("risk") or 0)))
    out.append('<h2>What needs a look</h2><p>Each line below is a measurement, not a rating. '
               'Unknown origin is not on this list: unknown is not the same as dangerous.</p>')
    if not look:
        out.append('<p>Nothing. No listener has a warning.</p>')
    for r in look:
        e = answers[id(r)]
        tone = _tone(r)
        st = e["started"]
        by = st.get("by") or "nobody on record"
        if st.get("still_running") is False:
            by += " (since exited)"
        proj = e["project"] or {}
        dl = [("service", "%s <span class='dim'>pid %s, %s</span>" % (_e(e["service"]), _e(e["pid"]), _e(R.user(e["user"]))))]
        if proj.get("name"):
            dl.append(("project", _e(R.project(proj.get("name"))) + (" <span class='dim'>%s</span>" % _e(R.path(proj.get("path"))))))
        dl.append(("started", "%s ago by %s" % (_e(ex._span(st.get("ago_seconds"))), _e(by))))
        if not redact:
            dl.append(("chain", _e(" → ".join("%s (%s)" % (a["name"], a["pid"]) for a in e["chain"]))))
        reach = e["reachable"]
        dl.append(("reachable", _e(reach["label"] or "?") + " <span class='dim'>%s</span>" % _e(R.addr(", ".join(reach["addrs"])))))
        if e["cmdline"] and not redact:
            dl.append(("command", "<code>%s</code>" % _e(R.cmd(e["cmdline"])[:220])))
        if e["stop"]:
            dl.append(("stop it", "<code>portlist kill %s</code>" % _e(e["port"])))
        warns = "".join('<li class="%s">%s</li>' % ("bad" if w.startswith(("reachable from beyond", "risk")) else "",
                                                     _e(R.text(w))) for w in e["warnings"])
        out.append('<div class="card %s"><div class="port">:%s</div><div><div class="svc">%s</div><dl>%s</dl><ul>%s</ul></div></div>'
                   % (tone, _e(e["port"]), _e(e["service"]),
                      "".join("<dt>%s</dt><dd>%s</dd>" % (k, v) for k, v in dl), warns))

    # everything
    out.append('<h2>Everything listening</h2><p>%d service%s%s.</p>' % (
        len(live), "" if len(live) == 1 else "s",
        (", and %d that portlist files as part of the system (left out)" % len(quiet)) if quiet else ""))
    out.append('<div class="scroll"><table><tr><th>Port</th><th>Service</th><th>Project</th><th>Reachable</th>'
               '<th>Risk</th><th>Started by</th><th>Last used</th><th>Up</th></tr>')
    for r in live:
        e = answers.get(id(r)) or {}
        st = r.get("starter") or {}
        act = r.get("activity") or {}
        used = ("now" if (act.get("idle_seconds") or 0) <= 60 else ex._span(act.get("idle_seconds")) + " ago") \
            if act.get("idle_seconds") is not None else ("never seen" if act.get("ever_busy") is False else "?")
        who = (st.get("name") or "unknown") + (" (exited)" if st.get("alive") is False else "")
        out.append('<tr class="%s"><td class="p">:%s</td><td>%s</td><td>%s</td><td class="r">%s</td><td class="r">%s %s</td>'
                   '<td class="%s">%s</td><td>%s</td><td class="dim">%s</td></tr>' % (
                       _tone(r), _e(r.get("port")), _e(r.get("service") or r.get("cmd")),
                       _e(R.project((r.get("project") or {}).get("name")) or "-"),
                       _e((r.get("exposure") or {}).get("label") or "?"), _e(r.get("risk")), _e(r.get("risk_band") or ""),
                       "ai" if st.get("ai") else "", _e(who), _e(used), _e(ex._span(r.get("uptime")))))
        del e
    out.append('</table></div>')

    # who started what
    groups = {}
    for r in live:
        st = r.get("starter") or {}
        groups.setdefault(st.get("name") or "unknown origin", {"ai": st.get("ai"), "alive": st.get("alive"), "rows": []})["rows"].append(r)
    out.append('<h2>Who started what</h2><p>From the process ancestry and the launch ledger, recorded when portlist '
               'first saw each service. It is never inferred from whatever holds the port now.</p>')
    for gname, g in sorted(groups.items(), key=lambda kv: (not kv[1]["ai"], -len(kv[1]["rows"]))):
        state = " &middot; exited" if g["alive"] is False else ""
        out.append('<div class="group"><h3 class="%s">%s<em>%d service%s%s</em></h3><div class="mono dim">%s</div></div>' % (
            "ai" if g["ai"] else "", _e(gname), len(g["rows"]), "" if len(g["rows"]) == 1 else "s", state,
            _e("   ".join(":%s %s" % (r.get("port"), r.get("service") or r.get("cmd")) for r in g["rows"]))))

    # containers
    boxes = [r for r in live if r.get("container")]
    if boxes:
        out.append('<h2>Containers</h2><p>Ports published by containers. Stop the container, not the proxy behind the port.</p>'
                   '<div class="scroll"><table><tr><th>Port</th><th>Container</th><th>Image</th><th>Reachable</th></tr>')
        for r in boxes:
            c = r["container"] if isinstance(r["container"], dict) else {"name": r["container"]}
            out.append('<tr class="%s"><td class="p">:%s</td><td>%s</td><td class="dim">%s</td><td class="r">%s</td></tr>' % (
                _tone(r), _e(r.get("port")), _e(R.box(c.get("name"))), _e("" if redact else c.get("image") or ""),
                _e((r.get("exposure") or {}).get("label"))))
        out.append('</table></div>')

    out.append('<div class="method"><b>How this was measured</b><ul>'
               '<li><b>Reachable</b>: portlist connected to each port from this machine\'s own network addresses. '
               'That proves the local network can reach it; it is not a scan from the internet, and it says nothing '
               'about a router forwarding ports.</li>'
               '<li><b>Started by</b>: the process ancestry and environment variable names (never their values), '
               'recorded the first time portlist saw the service.</li>'
               '<li><b>Left over</b>: a guess from measured use, age and whether its starter is still running, '
               'with the reasons listed. Portlist never stops anything on the strength of it.</li>'
               '<li><b>Risk</b>: a score over the reasons shown with each service, which are the part to read.</li>'
               '%s</ul></div>' % ('<li>Redacted: host and user names, addresses, project names, paths and command '
                                  'lines were removed.</li>' if redact else
                                  '<li>Command lines are shown with anything that looks like a secret masked. '
                                  '<code>portlist report --redact</code> takes them out altogether.</li>'))
    out.append('<footer>made by portlist %s on this machine; nothing was sent anywhere to make it</footer>'
               '</div></body></html>' % _e(version))
    return "\n".join(out)


def report_main(argv, scan_fn=None, detail_fn=None, sys_fn=None, out=None, err=None):
    import argparse
    p = argparse.ArgumentParser(prog="portlist report", description=(
        "Write this machine's listeners to one self-contained HTML file: what is "
        "reachable, what needs a look, what is left over, who started what."))
    p.add_argument("-o", "--output", metavar="FILE", default=None,
                   help="where to write it (default: portlist-report-<host>-<date>.html here; - for stdout)")
    p.add_argument("--redact", action="store_true",
                   help="take out host and user names, addresses, project names, paths and command lines")
    p.add_argument("--open", action="store_true", help="open it in the browser afterwards")
    a = p.parse_args(argv)
    out, err = out or sys.stdout, err or sys.stderr
    if scan_fn is None:
        from . import scan as scan_mod
        scan_fn = lambda: scan_mod.scan(force=True)
        detail_fn = detail_fn or scan_mod.detail
        sys_fn = sys_fn or scan_mod.system_info
    rows, host = scan_fn()
    details = {}
    for r in rows:
        if r.get("pid") is not None and not r.get("quiet") and detail_fn:
            try:
                details[r["pid"]] = detail_fn(r)
            except Exception:
                pass
    try:
        si = sys_fn() if sys_fn else {}
    except Exception:
        si = {}
    from .app import VERSION
    page = build(rows, host, si, details, redact=a.redact, version=VERSION)
    if a.output == "-":
        out.write(page)
        return 0
    hostname = "this-machine" if a.redact else re.sub(r"[^A-Za-z0-9_-]", "", ((host or {}).get("hostname") or "machine").split(".")[0]) or "machine"
    path = a.output or "portlist-report-%s-%s.html" % (hostname, time.strftime("%Y%m%d-%H%M"))
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    print("wrote %s (%d KB)%s" % (path, max(1, len(page) // 1024), ", redacted" if a.redact else ""), file=out)
    if a.open:
        import webbrowser
        webbrowser.open("file://" + os.path.abspath(path))
    return 0
