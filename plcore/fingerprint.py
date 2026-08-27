"""Probe a local port and work out what is actually answering on it.

Probe order is deliberately polite:
  1. connect
  2. listen for a banner the server volunteers (SSH, MySQL, VNC, FTP)
  3. if silent, send one HTTP GET /
  4. if that isn't HTTP, try a TLS handshake and one HTTPS GET /
  5. Redis-shaped ports get a single PING (the only way to tell open from AUTH-walled)
Ports that are known-destructive or noisy to poke are never touched.
"""
import html as _html
import re
import socket
import ssl
import time

from . import catalog

# Connecting and listening for a volunteered banner is passive and safe everywhere.
# SENDING bytes is what can log, lock out, or disturb a service - gate that instead.
NO_SEND = {22, 25, 53, 111, 137, 139, 445, 548, 631, 1433, 3306, 5432, 5900,
           9051, 9151, 11211, 27017}
NO_CONNECT = set()

# A port number alone is a hint, never an identification.
MIN_CLAIM = 30
TLS_LIKELY = {443, 8443, 9443, 4443, 6443, 5671, 9243}
REDIS_LIKE = {6379, 6380}

_cache = {}
_TTL = 20.0


_known_http = set()


def _ttl_for(port):
    """Spread cache expiry across ports.

    With one shared TTL every port expires on the same scan, so one poll in four
    costs a full re-probe of everything while the rest cost nothing. Deriving a
    deterministic offset from the port number turns that spike into a flat trickle.
    """
    return _TTL * (0.75 + (port % 40) / 80.0)


def _connect(port, timeout=0.6, host=None):
    """Dial a local port. `host` matters when two sockets share a port: the more
    specific bind wins for its own address, so each must be probed where it
    actually answers."""
    targets = ([(socket.AF_INET6 if ":" in host else socket.AF_INET, host)] if host
               else [(socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")])
    last = None
    for family, host in targets:
        try:
            s = socket.socket(family, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            return s
        except Exception as e:
            last = e
            try:
                s.close()
            except Exception:
                pass
    raise last if last else OSError("no route")


def _decode(b, limit=None):
    s = b.decode("utf-8", "replace")
    return s[:limit] if limit else s


def _clean_text(raw):
    txt = _html.unescape(raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw)
    return re.sub(r"\s+", " ", txt).strip()


def _parse_http(data):
    head, _, body = data.partition(b"\r\n\r\n")
    lines = head.split(b"\r\n")
    status = None
    parts = lines[0].split()
    if len(parts) > 1 and parts[1].isdigit():
        status = int(parts[1])
    headers = {}
    for ln in lines[1:]:
        k, _, v = ln.partition(b":")
        if v:
            headers[k.decode("latin-1").strip().lower()] = v.decode("latin-1").strip()

    title = None
    m = re.search(rb"<title[^>]*>(.*?)</title>", body, re.S | re.I)
    if m:
        title = _clean_text(m.group(1))[:110] or None
    if not title:
        m = re.search(rb"<h1[^>]*>(.*?)</h1>", body, re.S | re.I)
        if m:
            title = _clean_text(re.sub(rb"<[^>]+>", b"", m.group(1)))[:110] or None

    return {
        "status": status,
        "title": title,
        "headers": headers,
        "server": headers.get("server"),
        "powered_by": headers.get("x-powered-by"),
        "content_type": headers.get("content-type"),
        "redirect": headers.get("location"),
        "www_authenticate": headers.get("www-authenticate"),
        "body": _decode(body[:4096]),
        "body_preview": re.sub(r"\s+", " ", _decode(body[:600])).strip(),
    }


GET = ("GET {path} HTTP/1.1\r\nHost: localhost:{port}\r\n"
       "User-Agent: Portlist/2 (local security scan)\r\n"
       "Accept: */*\r\nConnection: close\r\n\r\n")


def _read_all(sock, cap=32768, deadline=1.6):
    data, end = b"", time.time() + deadline
    while len(data) < cap and time.time() < end:
        try:
            chunk = sock.recv(8192)
        except socket.timeout:
            break
        except Exception:
            break
        if not chunk:
            break
        data += chunk
    return data


def _one_pass(port, host=None, tls=False, send=True, banner_wait=0.2, timeout=1.6):
    """Listen for a volunteered banner and, if none comes, send the HTTP request
    on the SAME connection.

    Two connections per probe used to be enough to stall a single-threaded
    server: the banner phase held it for the full wait while the HTTP request
    queued behind it, and under a parallel scan that timed out. One connection
    removes the stall and halves the work.
    """
    t0 = time.time()
    banner = b""
    try:
        raw = _connect(port, host=host)
        sock = raw
        cert = None
        if tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw, server_hostname="localhost")
            cert = {"version": sock.version(), "cipher": (sock.cipher() or [None])[0]}
        else:
            sock.settimeout(banner_wait)
            try:
                banner = sock.recv(512)
            except Exception:
                banner = b""
        # A server that volunteered a non-HTTP banner has already identified
        # itself; do not send anything else at it.
        if (banner and not banner.startswith(b"HTTP/")) or not send:
            sock.close()
            return {"banner": banner, "parsed": None, "cert": None,
                    "error": None, "ms": int((time.time() - t0) * 1000)}
        sock.settimeout(timeout)
        sock.sendall(GET.format(path="/", port=port).encode())
        data = banner + _read_all(sock, deadline=timeout)
        sock.close()
    except Exception as e:
        return {"banner": banner, "parsed": None, "cert": None,
                "error": str(e), "ms": int((time.time() - t0) * 1000)}
    ms = int((time.time() - t0) * 1000)
    if not data.startswith(b"HTTP/"):
        return {"banner": banner or data[:200], "parsed": None, "cert": cert,
                "error": "not-http", "ms": ms}
    parsed = _parse_http(data)
    parsed["tls"] = cert
    return {"banner": banner, "parsed": parsed, "cert": cert, "error": None, "ms": ms}


def _http_get(port, path="/", tls=False, timeout=1.2, host=None):
    t0 = time.time()
    try:
        raw = _connect(port, host=host)
        raw.settimeout(timeout)
        sock = raw
        cert = None
        if tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sock = ctx.wrap_socket(raw, server_hostname="localhost")
            try:
                cert = sock.getpeercert(binary_form=False) or {}
                cert = {"version": sock.version(), "cipher": (sock.cipher() or [None])[0]}
            except Exception:
                cert = {"version": sock.version()}
        sock.sendall(GET.format(path=path, port=port).encode())
        data = _read_all(sock)
        sock.close()
    except Exception as e:
        return None, None, str(e), int((time.time() - t0) * 1000)
    ms = int((time.time() - t0) * 1000)
    if not data.startswith(b"HTTP/"):
        return None, data, "not-http", ms
    parsed = _parse_http(data)
    parsed["tls"] = cert if tls else None
    return parsed, data, None, ms


def _banner(port, timeout=0.45, host=None):
    """Read whatever the server says first, without sending anything."""
    try:
        s = _connect(port, host=host)
        s.settimeout(timeout)
        data = s.recv(512)
        s.close()
        return data
    except Exception:
        return b""


def _redis_ping(port, host=None):
    try:
        s = _connect(port, host=host)
        s.settimeout(0.8)
        s.sendall(b"PING\r\n")
        data = s.recv(256)
        s.close()
        return data
    except Exception:
        return b""


def probe(port, host=None):
    """One network fingerprint of a local port. Cached by port for _TTL seconds."""
    key = (host or "", port)
    hit = _cache.get(key)
    now = time.time()
    if hit and now - hit[0] < _ttl_for(port):
        return hit[1]

    res = {"probed": True, "http": False, "https": False, "status": None, "title": None,
           "server": None, "powered_by": None, "content_type": None, "redirect": None,
           "banner": None, "response_ms": None, "auth": "unknown", "tls": None,
           "body_preview": None, "error": None, "extra_path": None}

    send = port not in NO_SEND
    # We already know this one speaks HTTP, so do not spend the banner wait
    # listening for something it will never volunteer.
    wait = 0.02 if key in _known_http else 0.2
    out = _one_pass(port, host=host, tls=port in TLS_LIKELY, send=send, banner_wait=wait)
    # A remote address can lose a race under a parallel scan; give it one retry
    # before declaring a service unidentifiable.
    if send and not out["parsed"] and host and "timed out" in (out["error"] or ""):
        out = _one_pass(port, host=host, tls=port in TLS_LIKELY, send=send, timeout=2.5)
    if out["banner"]:
        res["banner"] = _decode(out["banner"][:200]).strip()
    res["response_ms"] = out["ms"]
    parsed = out["parsed"]
    if parsed and port in TLS_LIKELY:
        res["https"] = True
    if not parsed and send and port not in TLS_LIKELY and not out["banner"]:
        tls_out = _one_pass(port, host=host, tls=True, send=True)
        if tls_out["parsed"]:
            parsed = tls_out["parsed"]
            res["https"] = True
            res["response_ms"] = tls_out["ms"]
    if not send:
        res["error"] = "passive only (protocol not safe to send to)"
        res["probed"] = "passive"
    elif not parsed:
        res["error"] = out["error"]

    if parsed:
        res.update(http=True, status=parsed["status"], title=parsed["title"],
                   server=parsed["server"], powered_by=parsed["powered_by"],
                   content_type=parsed["content_type"], redirect=parsed["redirect"],
                   body_preview=parsed["body_preview"], tls=parsed.get("tls"))
        res["_body"] = parsed["body"]
        if parsed["status"] in (401, 407) or parsed["www_authenticate"]:
            res["auth"] = "required"
        elif parsed["status"] == 403:
            res["auth"] = "forbidden"
        elif parsed["status"] and parsed["status"] < 400:
            res["auth"] = "none"
    elif port in REDIS_LIKE and not out["banner"] and port not in NO_SEND:
        pong = _redis_ping(port, host=host)
        if pong:
            res["banner"] = _decode(pong[:120]).strip()
            res["auth"] = "none" if pong.startswith(b"+PONG") else "required"

    res["probed_at"] = host or "127.0.0.1"
    if res.get("http"):
        _known_http.add(key)
    else:
        _known_http.discard(key)
    _cache[key] = (now, res)
    return res


def confirm_path(port, path, pattern, https=False):
    """Second targeted request, only used when a port hint needs confirming."""
    parsed, _, err, ms = _http_get(port, path=path, tls=https)
    if not parsed:
        return None
    ok = bool(re.search(pattern, parsed["body"], re.I | re.M)) if pattern else True
    return {"path": path, "status": parsed["status"], "matched": ok,
            "preview": parsed["body_preview"][:200]}


# --------------------------------------------------------------- matching

def identify(cmdline, proc_name, port, pr):
    """Score every signature against the evidence. Returns (best, evidence, all)."""
    hay_proc = " ".join(filter(None, [proc_name, cmdline]))
    body = pr.get("_body") or ""
    header_blob = " ".join(filter(None, [pr.get("server"), pr.get("powered_by")]))
    title = pr.get("title") or ""
    banner = pr.get("banner") or ""

    scored = []
    for sig in catalog.SERVICES:
        score, ev = 0, []
        for pat in sig.get("proc", []):
            if re.search(pat, hay_proc):
                score += catalog.W_PROC
                ev.append(("process", "command line matches /%s/" % pat))
                break
        for pat in sig.get("body", []):
            if body and re.search(pat, body, re.I | re.M):
                score += catalog.W_BODY
                ev.append(("body", "response body matches /%s/" % pat))
                break
        for pat in sig.get("title", []):
            if title and re.search(pat, title):
                score += catalog.W_TITLE
                ev.append(("title", "page title %r" % title))
                break
        for pat in sig.get("header", []):
            if header_blob and re.search(pat, header_blob):
                score += catalog.W_HEADER
                ev.append(("header", "Server/X-Powered-By: %s" % header_blob))
                break
        for pat in sig.get("banner", []):
            if banner and re.search(pat, banner):
                score += catalog.W_BANNER
                ev.append(("banner", "banner %r" % banner[:60]))
                break
        if port in sig.get("ports", []):
            score += catalog.W_PORT
            ev.append(("port", "port %d is the conventional %s port" % (port, sig["name"])))
        if score:
            scored.append((score, sig, ev))

    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    if not scored:
        return None, [], []
    return scored[0], scored[0][2], scored


def resolve(cmdline, proc_name, port, pr):
    """Identify, and if only a port hint matched, spend one request confirming it."""
    best, ev, scored = identify(cmdline, proc_name, port, pr)
    if best and best[0] == catalog.W_PORT and pr.get("http"):
        sig = best[1]
        if sig.get("path"):
            path, pattern = sig["path"]
            got = confirm_path(port, path, pattern, https=pr.get("https"))
            if got and got["matched"]:
                pr["extra_path"] = got
                ev = ev + [("endpoint", "%s returned %s matching the %s signature"
                            % (path, got["status"], sig["name"]))]
                return sig, catalog.W_PORT + catalog.W_PATH, ev
            pr["extra_path"] = got
    if not best or best[0] < MIN_CLAIM:
        return None, (best[0] if best else 0), []
    return best[1], best[0], ev
