"""Stable names for services, so nobody has to remember a port.

`*.localhost` already resolves to 127.0.0.1 in every browser and every modern
resolver (RFC 6761). That means a name can be served by the dashboard that is
already running, on the port it is already listening on:

    http://shop.localhost:7337     ->  http://localhost:3000
    http://portlist:7337/go/shop  ->  the same

No proxy, no root, no /etc/hosts, no new listener, and nothing forwarded: the
answer is a redirect, and the browser goes to the service directly.

The one rule that matters here: **a name can only ever point at a service that is
listening on this machine right now.** A redirect endpoint that will send a
browser wherever the URL says is an open redirect, and this one refuses to be.
"""
import re

RESERVED = {"www", "api", "app", "localhost", "portlist", "status", "go", "dashboard"}


def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return re.sub(r"-{2,}", "-", s)[:40]


SOURCES = {0: "you named it", 1: "from its project", 2: "from what it is"}


def build(rows, recipes_book=None, with_source=False):
    """-> {name: row} for everything listening, plus name-with-port aliases.

    Sources, most deliberate first: the name a person gave the service, the
    project it came from, the service's own type. Every service also gets a
    <name>-<port> alias, so a collision is always resolvable rather than a
    coin toss - and with `with_source` the caller gets to see which of the three
    produced each name, because "why is it called that" is the first question
    anyone asks.
    """
    live = [r for r in rows if not r.get("quiet")]
    claims, out, source = {}, {}, {}

    def claim(name, row, rank):
        if not name or name in RESERVED:
            return
        held = claims.get(name)
        if held is None or rank < held[0] or (rank == held[0] and row["port"] < held[1]["port"]):
            claims[name] = (rank, row)

    for r in live:
        rec = r.get("recipe") or {}
        given = slug(rec.get("name")) if rec.get("name") else None
        project = slug((r.get("project") or {}).get("name"))
        service = slug(r.get("service") or r.get("cmd"))
        if given:
            claim(given, r, 0)
        if project:
            claim(project, r, 1)
        if service:
            claim(service, r, 2)
        for rank, base in ((0, given), (1, project), (2, service)):
            if base:
                alias = "%s-%d" % (base, r["port"])
                out[alias] = r
                source.setdefault(alias, rank)
        out[str(r["port"])] = r

    for name, (rank, row) in claims.items():
        out[name] = row
        source[name] = rank
    return (out, source) if with_source else out


def names_for(row, table):
    """Every name that currently points at this service."""
    return sorted({n for n, r in table.items()
                   if r["id"] == row["id"] and not n.isdigit()},
                  key=lambda n: (n.count("-"), len(n)))


def url_for(name, port):
    return "http://%s.localhost:%d" % (name, port)


def target_for(row):
    """Where a name sends you: always a loopback URL of a live service."""
    scheme = "https" if (row.get("probe") or {}).get("https") else "http"
    return "%s://localhost:%d" % (scheme, row["port"])


def table_lines(table, dashboard_port, source=None):
    """One line per service: its main name, where that name came from, the
    aliases that also work, and what it points at."""
    source = source or {}
    by_row, order = {}, []
    for name, row in sorted(table.items()):
        if name.isdigit():
            continue
        rid = row["id"]
        if rid not in by_row:
            by_row[rid] = {"row": row, "names": []}
            order.append(rid)
        by_row[rid]["names"].append((source.get(name, 3), name))
    lines = []
    for rid in order:
        entry = by_row[rid]
        entry["names"].sort(key=lambda n: (n[0], n[1].count("-"), len(n[1])))
        rank, main = entry["names"][0]
        row = entry["row"]
        lines.append({
            "name": main, "url": url_for(main, dashboard_port),
            "target": target_for(row), "service": row.get("service") or row.get("cmd"),
            "port": row["port"], "id": rid,
            "source": SOURCES.get(rank, "alias"),
            "chosen": rank == 0,
            "aliases": [n for _, n in entry["names"][1:]],
            "project": (row.get("project") or {}).get("short"),
        })
    lines.sort(key=lambda l: (not l["chosen"], l["name"]))
    return lines
