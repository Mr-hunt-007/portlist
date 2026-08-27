"""Git state for the directory a service is running from.

Answers the question a project card raises immediately: *this is running - from
what?* A branch, whether the tree is dirty, how far it has drifted from its
remote, and when it was last touched.

Read-only by construction: `git status`, `git log -1`, nothing that writes, and
never a fetch - a status page that reaches the network is a status page that
hangs.
"""
import os
import time

from .platforms.base import cached, have, run

TTL = 30.0
_cache = {}


def status(path):
    """-> {branch, dirty, ahead, behind, last_commit, last_author, age} or None."""
    if not path or not have("git") or not os.path.isdir(os.path.join(path, ".git")):
        return None
    now = time.time()
    hit = _cache.get(path)
    if hit and now - hit[0] < TTL:
        return hit[1]
    out = run(["git", "-C", path, "status", "--porcelain=v2", "--branch",
               "--untracked-files=normal"], timeout=6)
    if not out:
        _cache[path] = (now, None)
        return None
    info = {"branch": None, "dirty": 0, "untracked": 0, "ahead": 0, "behind": 0,
            "upstream": None, "detached": False}
    for line in out.splitlines():
        if line.startswith("# branch.head"):
            head = line.split(" ", 2)[-1]
            info["branch"] = head
            info["detached"] = head == "(detached)"
        elif line.startswith("# branch.upstream"):
            info["upstream"] = line.split(" ", 2)[-1]
        elif line.startswith("# branch.ab"):
            parts = line.split()
            for p in parts[2:]:
                if p.startswith("+"):
                    info["ahead"] = int(p[1:])
                elif p.startswith("-"):
                    info["behind"] = int(p[1:])
        elif line.startswith("?"):
            info["untracked"] += 1
        elif line[:1] in ("1", "2", "u"):
            info["dirty"] += 1
    log = run(["git", "-C", path, "log", "-1", "--format=%h\t%an\t%ct\t%s"], timeout=6).strip()
    if log:
        parts = log.split("\t")
        if len(parts) >= 4:
            info["last_commit"] = parts[0]
            info["last_author"] = parts[1]
            try:
                info["last_ts"] = float(parts[2])
                info["age"] = time.time() - info["last_ts"]
            except ValueError:
                pass
            info["last_subject"] = parts[3][:100]
    info["clean"] = info["dirty"] == 0 and info["untracked"] == 0
    _cache[path] = (now, info)
    return info


def summary(info):
    if not info:
        return None
    bits = [info.get("branch") or "?"]
    if info["dirty"] or info["untracked"]:
        bits.append("%d changed%s" % (info["dirty"],
                                      ", %d untracked" % info["untracked"]
                                      if info["untracked"] else ""))
    else:
        bits.append("clean")
    if info["ahead"]:
        bits.append("%d ahead" % info["ahead"])
    if info["behind"]:
        bits.append("%d behind" % info["behind"])
    return " · ".join(bits)
