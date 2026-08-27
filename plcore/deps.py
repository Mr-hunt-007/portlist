"""What a project's dependencies are, and the command that would audit them.

Portlist does not run `npm audit`. That command talks to a registry, takes
seconds, and produces a result that is stale the moment it finishes - none of
which belongs inside a scan that a dashboard polls. What Portlist can say
cheaply and truthfully is: this project uses pnpm, its lockfile was last touched
forty days ago, and here is the one command that would tell you whether that
matters.

Same rule as every other fix in this codebase: the command is printed, and you
run it.
"""
import os
import time

# (lockfile, manifest, ecosystem, audit command, install command)
STACKS = [
    ("pnpm-lock.yaml", "package.json", "pnpm", "pnpm audit", "pnpm install"),
    ("yarn.lock", "package.json", "yarn", "yarn npm audit", "yarn install"),
    ("bun.lockb", "package.json", "bun", "bun audit", "bun install"),
    ("bun.lock", "package.json", "bun", "bun audit", "bun install"),
    ("package-lock.json", "package.json", "npm", "npm audit", "npm ci"),
    ("poetry.lock", "pyproject.toml", "poetry", "poetry check && pip-audit", "poetry install"),
    ("uv.lock", "pyproject.toml", "uv", "uv pip list | pip-audit -r /dev/stdin", "uv sync"),
    ("Pipfile.lock", "Pipfile", "pipenv", "pipenv check", "pipenv install"),
    ("requirements.txt", "requirements.txt", "pip", "pip-audit -r requirements.txt",
     "pip install -r requirements.txt"),
    ("Cargo.lock", "Cargo.toml", "cargo", "cargo audit", "cargo build"),
    ("go.sum", "go.mod", "go", "govulncheck ./...", "go mod download"),
    ("Gemfile.lock", "Gemfile", "bundler", "bundle audit check --update", "bundle install"),
    ("composer.lock", "composer.json", "composer", "composer audit", "composer install"),
]
DAY = 86400


def for_project(path):
    """-> {ecosystem, lockfile, age_days, audit, install, stale} or None."""
    if not path or not os.path.isdir(path):
        return None
    now = time.time()
    for lock, manifest, eco, audit, install in STACKS:
        lpath = os.path.join(path, lock)
        if not os.path.isfile(lpath):
            continue
        try:
            age = (now - os.path.getmtime(lpath)) / DAY
        except OSError:
            age = None
        return {"ecosystem": eco, "lockfile": lock, "manifest": manifest,
                "age_days": round(age, 1) if age is not None else None,
                "audit": audit, "install": install,
                # "Stale" is a statement about the lockfile's age, not about
                # whether anything in it is vulnerable. Portlist does not know
                # that and will not imply it.
                "stale": bool(age is not None and age > 90),
                "note": "Portlist does not run this - it reaches a registry and "
                        "would make a scan slow and non-local."}
    return None


def summary(info):
    if not info:
        return None
    bits = [info["ecosystem"]]
    if info["age_days"] is not None:
        bits.append("lockfile %s" % ("%.0f days old" % info["age_days"]
                                     if info["age_days"] >= 1 else "updated today"))
    return " · ".join(bits)
