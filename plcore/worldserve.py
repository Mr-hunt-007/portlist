"""`portlist --world`: the living harbour, served to a browser on this machine.

The terminal stays the product. This is a second view over the same model,
meant for a second screen: one loopback-only HTTP server, one page, one JSON
endpoint, no dependencies.

Security, briefly, because a local web server is a door:
- it binds 127.0.0.1 and nothing else, and there is no flag to change that;
- every request must name this host and port in its Host header, so a web page
  that rebinds its own DNS name to 127.0.0.1 cannot read the world;
- the page needs the per-run key in its URL and the API needs it in a header,
  so another local user who finds the port finds nothing;
- it is read-only. There is no endpoint that changes anything.
"""
import http.server
import os
import secrets
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
PAGE = os.path.join(HERE, "data", "world.html")
HEADER = "X-Portlist-Token"

CSP = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
       "connect-src 'self'; img-src 'self' data:; font-src 'self' data:; "
       "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

_lock = threading.Lock()


class _Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_handler(token, port_ref, keep_fresh=True):
    from . import world

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "portlist-world"
        sys_version = ""

        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="text/plain; charset=utf-8"):
            data = body.encode() if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            host = (self.headers.get("Host") or "").lower()
            port = port_ref[0]
            return host in ("127.0.0.1:%d" % port, "localhost:%d" % port)

        def do_GET(self):
            try:
                self._get()
            except Exception as e:                       # never leave a socket mid-stream
                try:
                    self.close_connection = True
                    self._send(500, "world error: %s" % type(e).__name__)
                except Exception:
                    pass

        def _get(self):
            if not self._host_ok():
                return self._send(421, "wrong host")
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            if u.path in ("/", "/world"):
                if not secrets.compare_digest((q.get("k") or [""])[0], token):
                    return self._send(403, "open the address portlist printed; it carries the key")
                try:
                    with open(PAGE, encoding="utf-8") as f:
                        page = f.read()
                except OSError:
                    return self._send(500, "world.html is missing from this install")
                return self._send(200, page.replace("__TOKEN__", token),
                                  "text/html; charset=utf-8")
            if u.path == "/api/world":
                if not secrets.compare_digest(self.headers.get(HEADER, ""), token):
                    return self._send(403, "missing or wrong key")
                try:
                    since = int((q.get("since") or ["0"])[0])
                except ValueError:
                    since = 0
                with _lock:
                    doc = world.payload(since=max(0, since), keep_fresh=keep_fresh)
                return self._send(200, world.dumps(doc), "application/json")
            return self._send(404, "not here")

    return Handler


def serve(port=0, keep_fresh=True):
    """-> (server, url). Starts in a background thread.

    `keep_fresh` runs the scan keeper; off when the host process (the terminal
    view) already refreshes the scan, so there is only ever one scanner."""
    token = secrets.token_urlsafe(18)
    ref = [0]
    srv = _Server(("127.0.0.1", port), make_handler(token, ref, keep_fresh))
    ref[0] = srv.server_address[1]
    t = threading.Thread(target=srv.serve_forever, name="portlist-world", daemon=True)
    t.start()
    return srv, "http://127.0.0.1:%d/?k=%s" % (ref[0], token)


# ------------------------------------------------------------------ browser
CHROMIUMS_MAC = ["Google Chrome", "Chromium", "Microsoft Edge", "Brave Browser", "Arc"]
CHROMIUMS_BIN = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "brave-browser"]


def _profile_dir():
    try:
        from . import security
        base = security.data_dir()
    except Exception:
        base = os.path.expanduser("~/.portlist")
    d = os.path.join(base, "world-browser")
    os.makedirs(d, exist_ok=True)
    return d


def open_browser(url, fullscreen=True):
    """-> a sentence saying how the world was opened.

    Full screen means a Chromium-family browser in app mode with its own small
    profile, because that is the only way a program can ask for a window with no
    tabs, no address bar and no border. Without one, the default browser opens
    the page, and F inside it goes full screen.
    """
    if fullscreen:
        flags = ["--app=" + url, "--start-fullscreen", "--no-first-run",
                 "--no-default-browser-check", "--user-data-dir=" + _profile_dir()]
        if sys.platform == "darwin":
            for app in CHROMIUMS_MAC:
                if os.path.isdir("/Applications/%s.app" % app) or \
                        os.path.isdir(os.path.expanduser("~/Applications/%s.app" % app)):
                    try:
                        subprocess.Popen(["open", "-na", app, "--args"] + flags,
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        return "opened full screen in %s" % app
                    except OSError:
                        break
        else:
            for b in CHROMIUMS_BIN:
                exe = shutil.which(b)
                if exe:
                    try:
                        subprocess.Popen([exe] + flags, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
                        return "opened full screen in %s" % b
                    except OSError:
                        break
    try:
        webbrowser.open(url)
        return "opened in your browser. Press F there for full screen"
    except Exception:
        return "could not open a browser. Open the address above yourself"


def run(port=0, open_it=True, fullscreen=True):
    """Serve until interrupted. What `portlist --world` does."""
    try:
        srv, url = serve(port)
    except OSError as e:
        print("could not start the world on port %s: %s" % (port or "auto", e.strerror or e),
              file=sys.stderr)
        return 2
    print("portlist world  %s" % url, flush=True)
    print("loopback only, read-only. The key in that address is this run's; ctrl-c stops it.", flush=True)
    if open_it:
        print(open_browser(url, fullscreen), flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("")
    finally:
        srv.shutdown()
    return 0


_bg = {"srv": None, "url": None}


def ensure_background():
    """For the TUI's W key: one server per process, started on first use."""
    if _bg["srv"] is None:
        _bg["srv"], _bg["url"] = serve(0, keep_fresh=False)   # the terminal already scans
    return _bg["url"]
