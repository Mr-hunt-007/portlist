"""What a service can reach - credentials, files, tools, network.

Exposure answers "who can reach this". This module answers the other half:
**if someone did reach it, what would they get?** A localhost-only MCP server
with a GitHub token and your home directory in scope is a bigger problem than a
LAN-exposed static file server, and a port inventory cannot say so.

Two rules hold everywhere in here:

  Names, never values.   Environment variables are read as names only. A
                         credential's presence is a fact worth reporting; its
                         value is the thing being protected.
  Unknown is not clean.  A process whose environment cannot be read (another
                         user, another platform) is reported as unreadable, not
                         as having no credentials. Silence is not evidence.
"""
import os
import re

HOME = os.path.expanduser("~")

# ---------------------------------------------------------------- credentials
# (class, label, name pattern, dimension it opens up, impact weight)
CRED_CLASSES = [
    ("aws",        "AWS credentials",        r"^AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)$", "cloud", 3),
    ("aws_profile","AWS profile",            r"^AWS_(PROFILE|DEFAULT_PROFILE|ROLE_ARN|WEB_IDENTITY_TOKEN_FILE)$", "cloud", 2),
    ("gcp",        "Google Cloud credentials", r"^(GOOGLE_APPLICATION_CREDENTIALS|GCLOUD_PROJECT|GOOGLE_CLOUD_PROJECT|GCP_.*KEY)$", "cloud", 3),
    ("azure",      "Azure credentials",      r"^AZURE_(CLIENT_SECRET|CLIENT_ID|TENANT_ID|SUBSCRIPTION_ID)$", "cloud", 3),
    ("github",     "GitHub token",           r"^(GITHUB_TOKEN|GH_TOKEN|GITHUB_PAT|GITHUB_ACCESS_TOKEN|GH_ENTERPRISE_TOKEN)$", "source_control", 3),
    ("gitlab",     "GitLab token",           r"^(GITLAB_TOKEN|CI_JOB_TOKEN|GITLAB_ACCESS_TOKEN)$", "source_control", 3),
    ("database",   "Database credentials",   r"^(DATABASE_URL|DATABASE_URI|POSTGRES_(PASSWORD|URL|USER)|PG(PASSWORD|URI)|MYSQL_(PWD|PASSWORD|ROOT_PASSWORD)|MONGO(DB)?_(URI|URL|PASSWORD)|REDIS_(URL|PASSWORD)|CLICKHOUSE_PASSWORD|SUPABASE_(SERVICE_ROLE_KEY|DB_URL))$", "database", 3),
    ("kube",       "Cluster access",         r"^(KUBECONFIG|KUBERNETES_SERVICE_HOST|DOCKER_HOST|DOCKER_CERT_PATH)$", "shell", 3),
    ("payments",   "Payment provider key",   r"^(STRIPE_(SECRET|RESTRICTED)_KEY|PAYPAL_CLIENT_SECRET|RAZORPAY_KEY_SECRET)$", "money", 3),
    ("messaging",  "Messaging token",        r"^(SLACK_(BOT_)?TOKEN|SLACK_(APP|SIGNING)_(TOKEN|SECRET)|DISCORD_(BOT_)?TOKEN|TELEGRAM_BOT_TOKEN|TWILIO_AUTH_TOKEN|SENDGRID_API_KEY|RESEND_API_KEY|POSTMARK_.*TOKEN)$", "messaging", 2),
    ("vault",      "Secret store token",     r"^(VAULT_TOKEN|DOPPLER_TOKEN|OP_SERVICE_ACCOUNT_TOKEN|INFISICAL_TOKEN|BW_SESSION)$", "credentials", 3),
    ("llm",        "LLM provider key",       r"^(OPENAI_API_KEY|ANTHROPIC_(API_KEY|AUTH_TOKEN)|GEMINI_API_KEY|GOOGLE_API_KEY|GROQ_API_KEY|MISTRAL_API_KEY|COHERE_API_KEY|TOGETHER_API_KEY|FIREWORKS_API_KEY|DEEPSEEK_API_KEY|XAI_API_KEY|HF_TOKEN|HUGGING(FACE)?_.*TOKEN|REPLICATE_API_TOKEN|OPENROUTER_API_KEY)$", "llm", 2),
    ("npm",        "Package registry token", r"^(NPM_TOKEN|NODE_AUTH_TOKEN|PYPI_(API_)?TOKEN|TWINE_PASSWORD|CARGO_REGISTRY_TOKEN)$", "supply_chain", 2),
    ("ci",         "CI/deploy token",        r"^(VERCEL_TOKEN|NETLIFY_AUTH_TOKEN|CLOUDFLARE_API_(TOKEN|KEY)|FLY_API_TOKEN|HEROKU_API_KEY|CIRCLE_TOKEN|BUILDKITE_.*TOKEN)$", "cloud", 2),
]
# Anything that ends in a secret-shaped suffix and did not match above.
GENERIC_SECRET = re.compile(
    r"(?:^|_)(?:API_?KEY|SECRET(?:_KEY)?|TOKEN|PRIVATE_?KEY|PASSWORD|PASSWD|CREDENTIALS)$")
# Names that look secret-shaped but hold a switch, a path or a public id.
GENERIC_EXCLUDE = re.compile(
    r"^(?:.*_(?:ENABLED|PATH|FILE|DIR|URL_?PUBLIC)|NEXT_PUBLIC_.*|VITE_.*|REACT_APP_.*|PUBLIC_.*)$")


def credentials(env_names):
    """-> [{class, label, vars, dimension, weight}] from variable names alone."""
    found, claimed = {}, set()
    for name in env_names or []:
        for cid, label, pattern, dim, weight in CRED_CLASSES:
            if re.match(pattern, name):
                e = found.setdefault(cid, {"class": cid, "label": label, "vars": [],
                                           "dimension": dim, "weight": weight})
                e["vars"].append(name)
                claimed.add(name)
                break
    loose = [n for n in (env_names or [])
             if n not in claimed and GENERIC_SECRET.search(n) and not GENERIC_EXCLUDE.match(n)]
    if loose:
        found["other"] = {"class": "other", "label": "Unclassified secret",
                          "vars": sorted(loose)[:12], "dimension": "credentials", "weight": 1}
    out = sorted(found.values(), key=lambda c: (-c["weight"], c["class"]))
    for c in out:
        c["vars"] = sorted(set(c["vars"]))
    return out


# ------------------------------------------------------------------ filesystem
# Directories whose contents are the reason anyone breaks into a laptop.
SENSITIVE_DIRS = [
    ("~/.ssh", "private SSH keys"),
    ("~/.aws", "AWS credentials file"),
    ("~/.gnupg", "GPG private keys"),
    ("~/.kube", "cluster credentials"),
    ("~/.config/gh", "GitHub CLI token"),
    ("~/.docker", "registry credentials"),
    ("~/.netrc", "stored logins"),
    ("~/.npmrc", "registry token"),
    ("~/.gitconfig", "git identity and credential helper"),
    ("~/Library/Keychains", "the macOS keychain"),
    ("/etc", "system configuration"),
    ("/etc/shadow", "password hashes"),
]
ARG_PATH = re.compile(r"^(?:--?[\w-]+=)?((?:~|/|\./)[^\s'\"]*)$")


def _abs(p):
    p = os.path.expanduser(p.strip("'\""))
    return os.path.normpath(os.path.abspath(p))


def short(path):
    return "~" + path[len(HOME):] if path and path.startswith(HOME) else path


def _contains(parent, child):
    try:
        return os.path.commonpath([parent, child]) == parent
    except ValueError:
        return False


def paths(cmdline, cwd=""):
    """Directories this process was handed on its command line, plus its cwd.

    A filesystem MCP server takes its allowed roots as arguments; that argument
    list *is* the access grant, and it is sitting in the process table where
    nobody ever looks at it.
    """
    seen, out = set(), []

    def add(raw, source):
        try:
            p = _abs(raw)
        except Exception:
            return
        if p in seen or not os.path.isdir(p):
            return
        # A binary's own path is not a grant of access to its directory.
        if p in ("/", "/usr", "/usr/bin", "/usr/local/bin", "/bin", "/sbin", "/opt/homebrew/bin"):
            if source != "argument" or p != "/":
                return
        seen.add(p)
        out.append({"path": p, "short": short(p), "source": source,
                    "scope": _scope(p), "reaches": _reaches(p)})

    if cwd:
        add(cwd, "working directory")
    for tok in (cmdline or "").split():
        m = ARG_PATH.match(tok)
        if m:
            add(m.group(1), "argument")
    return out[:12]


def _scope(p):
    if p == "/":
        return "everything"
    if p == HOME:
        return "home directory"
    if any(_contains(_abs(s), p) or p == _abs(s) for s, _ in SENSITIVE_DIRS if not s.startswith("/etc")):
        return "credential store"
    if p.startswith("/etc") or p in ("/var", "/usr", "/opt"):
        return "system"
    if os.path.dirname(p) == HOME:
        return "home folder"
    return "project"


def _reaches(p):
    """Sensitive things that live *inside* a granted directory.

    Handing an agent your home folder reads as ordinary until you notice that
    ~/.ssh is inside it.
    """
    hits = []
    for raw, why in SENSITIVE_DIRS:
        target = _abs(raw)
        if target == p or not _contains(p, target):
            continue
        if os.path.exists(target):
            hits.append({"path": short(target), "why": why})
    return hits[:8]


# --------------------------------------------------------------- blast radius
DIMS = [
    ("files", "Files"),
    ("credentials", "Credentials"),
    ("source_control", "Source control"),
    ("database", "Databases"),
    ("cloud", "Cloud accounts"),
    ("shell", "Command execution"),
    ("messaging", "Messaging"),
    ("network", "Network"),
]
LEVELS = ["none", "low", "medium", "high"]
# MCP tool capability -> the dimension it actually opens.
TOOL_DIM = {
    "filesystem access": ("files", "high"),
    "database access": ("database", "high"),
    "command execution": ("shell", "high"),
    "source control access": ("source_control", "high"),
    "messaging": ("messaging", "medium"),
    "browser control": ("network", "medium"),
    "credential access": ("credentials", "high"),
    "cloud access": ("cloud", "high"),
}
def _cred_level(weight):
    return "high" if weight >= 3 else "medium" if weight == 2 else "low"


def _raise(radius, dim, level, why):
    d = radius.setdefault(dim, {"level": "none", "why": []})
    if LEVELS.index(level) > LEVELS.index(d["level"]):
        d["level"] = level
    if why and why not in d["why"]:
        d["why"].append(why)


def analyse(row, env_names, env_readable=True, conns=None):
    """-> the access picture for one service or stdio process.

    `row` needs: cmdline, dir, user, mcp (optional), service/ai flags.
    """
    creds = credentials(env_names)
    grants = paths(row.get("cmdline", ""), row.get("dir", ""))
    mcp = row.get("mcp") or {}
    tools = mcp.get("tools") or []
    sensitive = mcp.get("sensitive") or []
    conns = conns or []

    radius = {}
    for cred in creds:
        dim = cred["dimension"]
        if dim in ("cloud", "source_control", "database", "shell", "messaging"):
            _raise(radius, dim, "high" if cred["weight"] >= 3 else "medium",
                   "%s in the environment (%s)" % (cred["label"], ", ".join(cred["vars"][:3])))
        else:
            _raise(radius, "credentials", _cred_level(cred["weight"]),
                   "%s in the environment (%s)" % (cred["label"], ", ".join(cred["vars"][:3])))
    if creds:
        _raise(radius, "credentials", _cred_level(max(c["weight"] for c in creds)),
               "%d credential class%s inherited from the shell that started it"
               % (len(creds), "" if len(creds) == 1 else "es"))

    for cap in sensitive:
        dim, level = TOOL_DIM.get(cap["capability"], ("network", "medium"))
        _raise(radius, dim, level, "MCP tools: %s" % ", ".join(cap["tools"][:4]))

    # A working directory is not an access grant: a process can already read
    # everything its user can, wherever it was started from. Only a directory
    # handed to a tool as an argument is a boundary anyone declared.
    WIDE = ("everything", "home directory", "credential store", "system", "home folder")
    for g in grants:
        if g["source"] != "argument":
            _raise(radius, "files", "medium" if g["scope"] in ("credential store", "system")
                   else "low", "runs from %s" % g["short"])
            continue
        if g["scope"] in WIDE:
            _raise(radius, "files", "high", "%s handed to it as an argument (%s)"
                   % (g["short"], g["scope"]))
        else:
            _raise(radius, "files", "medium", "%s handed to it as an argument" % g["short"])
        for hit in g["reaches"]:
            _raise(radius, "credentials", "high",
                   "%s is inside that scope - %s" % (hit["path"], hit["why"]))

    # A filesystem or shell tool is bounded by the process user, not by the
    # directory it happens to have been started in. Saying otherwise would be a
    # comforting and wrong answer.
    if any(c["capability"] in ("filesystem access", "command execution") for c in sensitive):
        if not any(g["source"] == "argument" and g["scope"] not in WIDE for g in grants):
            _raise(radius, "files", "high",
                   "its tools run as %s with no declared root, so its reach is that "
                   "whole account" % (row.get("user") or "this user"))

    if row.get("user") == "root":
        _raise(radius, "shell", "high", "runs as root, so its file and process access is unrestricted")
        _raise(radius, "files", "high", "runs as root")

    pub = sum(1 for c in conns if c.get("scope") == "public")
    if pub:
        _raise(radius, "network", "medium", "%d established connection%s to public addresses"
               % (pub, "" if pub == 1 else "s"))
    elif conns:
        _raise(radius, "network", "low", "%d established connection%s, all local or private"
               % (len(conns), "" if len(conns) == 1 else "s"))

    if not env_readable:
        # Silence here is the tool's limit, not the process's innocence.
        d = radius.setdefault("credentials", {"level": "none", "why": []})
        d["why"].append("environment could not be read (another user, or a platform that does "
                        "not expose it) - inherited credentials are unknown, not absent")

    for dim, _ in DIMS:
        radius.setdefault(dim, {"level": "none", "why": []})

    worst = max((LEVELS.index(radius[d]["level"]) for d, _ in DIMS), default=0)
    highs = sum(1 for d, _ in DIMS if radius[d]["level"] == "high")
    overall = ("critical" if highs >= 3 else
               "high" if worst == 3 else
               "medium" if worst == 2 else
               "low" if worst == 1 else "none")

    return {
        "credentials": creds,
        "credentials_readable": bool(env_readable),
        "env_count": len(env_names or []),
        "paths": grants,
        "tools": len(tools),
        "tool_capabilities": [c["capability"] for c in sensitive],
        "radius": [{"dim": d, "label": label, "level": radius[d]["level"],
                    "why": radius[d]["why"][:4]} for d, label in DIMS],
        "overall": overall,
        "headline": headline(row, creds, grants, sensitive, overall) + (
            "" if env_readable else
            " Its environment could not be read, so inherited credentials are unknown."),
    }


def _trim(path, keep=42):
    if len(path) <= keep:
        return path
    parts = path.split(os.sep)
    return os.sep.join([parts[0], "..."] + parts[-2:]) if len(parts) > 4 else path[:keep] + "..."


def headline(row, creds, grants, sensitive, overall):
    """One sentence a developer can act on, not a score.

    "Port 5432 open" is a fact. "Your AI agent can reach your production
    database" is the same fact with the part that matters left in.
    """
    name = row.get("service") or row.get("name") or row.get("cmd") or "This process"
    if overall == "none":
        return "%s holds no credentials Portlist can see and was given no file scope." % name
    bits = []
    if sensitive:
        bits.append("exposes " + ", ".join(c["capability"] for c in sensitive[:3]))
    strong = [c for c in creds if c["weight"] >= 3]
    if strong:
        bits.append("inherits " + ", ".join(c["label"].lower() for c in strong[:3]))
    wide = [g for g in grants if g["scope"] != "project" and g["source"] == "argument"]
    if wide:
        bits.append("can read " + ", ".join(_trim(g["short"]) for g in wide[:3]))
    elif [g for g in grants if g["source"] == "argument"]:
        bits.append("was given " + ", ".join(
            _trim(g["short"]) for g in grants if g["source"] == "argument"))
    reach = [h for g in grants for h in g["reaches"]]
    if reach:
        bits.append("including " + reach[0]["path"] + " (" + reach[0]["why"] + ")")
    if not bits and creds:
        bits.append("holds " + ", ".join(
            "%s (%s)" % (c["label"].lower(), ", ".join(c["vars"][:2])) for c in creds[:2]))
    if not bits:
        return "%s has file access but no credentials Portlist can see." % name
    return name + " " + "; ".join(bits) + "."


def for_row(row, environ, conns=None):
    """Convenience wrapper: `environ` is a callable pid -> [names]."""
    try:
        names = environ(row["pid"]) or []
    except Exception:
        names = []
    return analyse(row, names, env_readable=bool(names), conns=conns)
