"""Authentication, roles, CSRF, read-only mode and the audit log.

Design rules:
  - Binding anywhere but loopback REQUIRES at least one token. Portlist refuses
    to start otherwise; there is no "temporarily open to the network" default.
  - Roles are checked per action, not per endpoint, so a new action cannot
    accidentally inherit write permission.
  - --read-only disables every mutating action for everyone, including admins.
    It is a deployment property, not a permission.
  - Every attempt at a mutating action is audited: allowed and denied alike.
"""
import hashlib
import hmac
import json
import os
import secrets
import time

ROLES = {
    "viewer":   {"read": True,  "act": False, "admin": False, "ingest": False,
                 "blurb": "Read the inventory. Cannot change anything."},
    "operator": {"read": True,  "act": True,  "admin": False, "ingest": False,
                 "blurb": "Read, and run allowed actions such as stopping a service."},
    "admin":    {"read": True,  "act": True,  "admin": True,  "ingest": True,
                 "blurb": "Everything, including managing tokens."},
    "agent":    {"read": False, "act": False, "admin": False, "ingest": True,
                 "blurb": "Report this host's inventory to a Portlist server. Cannot read the fleet or act."},
}

# The command allowlist. Nothing outside this table can be invoked over HTTP,
# and each entry declares what it needs. Adding an endpoint does not grant power;
# adding a row here does.
ACTIONS = {
    "rescan":  {"role": "read", "destructive": False, "confirm": False,
                "desc": "Force a fresh scan"},
    "reveal":  {"role": "act",  "destructive": False, "confirm": False,
                "desc": "Open a service's working directory in the local file manager"},
    "stop":    {"role": "act",  "destructive": True,  "confirm": True,
                "desc": "Send SIGTERM to a listening process"},
    "token":   {"role": "admin", "destructive": True, "confirm": True,
                "desc": "Create or revoke API tokens"},
    "ingest":  {"role": "ingest", "destructive": False, "confirm": False,
                "desc": "Submit a host inventory report (agents only)"},
    "read":    {"role": "read", "destructive": False, "confirm": False,
                "desc": "Read the inventory, system metrics and change history"},
    "audit":   {"role": "admin", "destructive": False, "confirm": False,
                "desc": "Read the audit log"},
    "adopt":   {"role": "act",  "destructive": False, "confirm": False,
                "desc": "Give a service a name and notes in Portlist's own records"},
    "ignore":  {"role": "act",  "destructive": False, "confirm": False,
                "desc": "Stop listing a service as a probable leftover"},
    "panels":  {"role": "act",  "destructive": False, "confirm": False,
                "desc": "Turn a panel on or off"},
    "stage":   {"role": "act",  "destructive": False, "confirm": False,
                "desc": "Change what sits behind a panel, and what a panel remembers"},
    "asset":   {"role": "admin", "destructive": True,  "confirm": True,
                "desc": "Add or remove a file in ui/panels/assets/, which every "
                        "page this server serves may then load"},
    "embed":   {"role": "admin", "destructive": False, "confirm": True,
                "desc": "Allow or block a third-party embed, which widens the "
                        "content policy for every page this server serves"},
}

PBKDF_ROUNDS = 200_000


def data_dir():
    return os.environ.get("PORTLIST_DATA", os.path.expanduser("~/.portlist"))


def _path(name):
    return os.path.join(data_dir(), name)


def _load(name, default):
    try:
        with open(_path(name)) as f:
            return json.load(f)
    except Exception:
        return default


def _save(name, obj, mode=0o600):
    os.makedirs(data_dir(), exist_ok=True)
    tmp = _path(name) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2)
    os.chmod(tmp, mode)
    os.replace(tmp, _path(name))


# ------------------------------------------------------------------ tokens

def hash_token(token, salt):
    return hashlib.pbkdf2_hmac("sha256", token.encode(), bytes.fromhex(salt),
                               PBKDF_ROUNDS).hex()


def load_tokens():
    return _load("tokens.json", {"tokens": []})["tokens"]


def add_token(name, role="viewer", token=None):
    if role not in ROLES:
        raise ValueError("unknown role %r (pick one of %s)" % (role, ", ".join(ROLES)))
    token = token or ("pb_" + secrets.token_urlsafe(32))
    salt = secrets.token_hex(16)
    entry = {"name": name, "role": role, "salt": salt,
             "hash": hash_token(token, salt), "created": time.time(),
             "id": secrets.token_hex(4)}
    tokens = load_tokens()
    tokens.append(entry)
    _save("tokens.json", {"tokens": tokens})
    return token, entry


def revoke_token(ident):
    tokens = load_tokens()
    keep = [t for t in tokens if t["id"] != ident and t["name"] != ident]
    _save("tokens.json", {"tokens": keep})
    return len(tokens) - len(keep)


def verify_token(presented):
    """-> the token entry, or None. Constant-time against every stored hash."""
    if not presented:
        return None
    found = None
    for t in load_tokens():
        candidate = hash_token(presented, t["salt"])
        if hmac.compare_digest(candidate, t["hash"]):
            found = t
    return found


# ------------------------------------------------------------------- policy

class Policy:
    """One place that answers 'is this allowed', for every request."""

    def __init__(self, read_only=False, bind_host="127.0.0.1", allow_anonymous=None,
                 local_token=None):
        self.read_only = read_only
        self.bind_host = bind_host
        self.local_token = local_token          # in-memory token for the local UI
        self.loopback_only = bind_host in ("127.0.0.1", "::1", "localhost")
        # On loopback the OS already restricts callers to this machine, so reads
        # are anonymous by default and only actions need the UI token.
        self.allow_anonymous = (self.loopback_only if allow_anonymous is None
                                else allow_anonymous)

    def startup_check(self, insecure=False):
        """Refuse dangerous configurations rather than warning about them."""
        problems = []
        if not self.loopback_only and not load_tokens() and not insecure:
            problems.append(
                "Refusing to bind %s with no tokens configured. Run "
                "`portlist token add <name> --role viewer` first, or pass --insecure "
                "if this host is already isolated." % self.bind_host)
        if not self.loopback_only and not self.read_only and not insecure:
            problems.append(
                "Refusing to expose management actions on %s. Drop --enable-actions "
                "for a monitoring deployment, or pass --insecure to accept the risk."
                % self.bind_host)
        return problems

    def identify(self, headers, cookies):
        """-> (role, actor). Anonymous loopback reads get the 'viewer' role."""
        role, actor, _ = self.identify_detail(headers, cookies)
        return role, actor

    def identify_detail(self, headers, cookies):
        """-> (role, actor, stale).

        `stale` means a token was presented and matched nothing. That is a very
        different situation from presenting no token at all: it is almost always
        a page that was loaded before this server process started, since the
        local token is minted fresh each run. Reporting it as a plain 'viewer'
        sent people hunting for a permissions problem they did not have.
        """
        presented = None
        auth = headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            presented = auth[7:].strip()
        presented = presented or headers.get("X-Portlist-Token") or cookies.get("pb_token")

        if presented and self.local_token and hmac.compare_digest(presented, self.local_token):
            return "admin", "local-ui", False
        entry = verify_token(presented) if presented else None
        if entry:
            return entry["role"], entry["name"], False
        stale = bool(presented)
        if self.allow_anonymous:
            return "viewer", "anonymous@loopback", stale
        return None, None, stale

    def may(self, role, action):
        """-> (ok, reason)."""
        spec = ACTIONS.get(action)
        if not spec:
            return False, "unknown action %r - not in the allowlist" % action
        if role is None:
            return False, "authentication required"
        if self.read_only and spec["destructive"]:
            return False, "server is running in --read-only mode"
        if self.read_only and spec["role"] not in ("read", "ingest"):
            return False, "server is running in --read-only mode"
        need = spec["role"]
        caps = ROLES.get(role, {})
        if not caps.get(need):
            return False, "role %r cannot %s (needs %s)" % (role, action, need)
        return True, "ok"


# --------------------------------------------------------------------- CSRF

def check_origin(headers, expected_hosts):
    """A browser cannot forge Origin. Reject anything cross-site outright."""
    origin = headers.get("Origin") or headers.get("Referer")
    if not origin:
        return True, "no origin header (not a browser form post)"
    for host in expected_hosts:
        if origin.startswith("http://" + host) or origin.startswith("https://" + host):
            return True, "same origin"
    return False, "cross-origin request from %r refused" % origin[:80]


# ---------------------------------------------------------------- audit log

AUDIT = "audit.jsonl"
MAX_AUDIT = 20000


def audit(action, actor, role, target, allowed, reason, remote=""):
    rec = {"ts": time.time(), "action": action, "actor": actor, "role": role,
           "target": target, "allowed": bool(allowed), "reason": reason,
           "remote": remote}
    try:
        os.makedirs(data_dir(), exist_ok=True)
        with open(_path(AUDIT), "a") as f:
            f.write(json.dumps(rec) + "\n")
        os.chmod(_path(AUDIT), 0o600)
    except OSError:
        pass
    return rec


def audit_tail(limit=200):
    try:
        with open(_path(AUDIT)) as f:
            lines = f.readlines()[-limit:]
    except OSError:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return list(reversed(out))


def trim_audit():
    try:
        with open(_path(AUDIT)) as f:
            lines = f.readlines()
    except OSError:
        return
    if len(lines) > MAX_AUDIT:
        with open(_path(AUDIT), "w") as f:
            f.writelines(lines[-MAX_AUDIT:])
