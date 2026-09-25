"""Agent adapters: one file per coding agent or editor portlist recognises.

Every place portlist asks "was this started by an agent?" reads from here:
the ancestry patterns and environment variable names in lifecycle.py, the
agent processes the Sessions view counts, and the transcripts it lists. Adding
an agent is one file in this directory; nothing else needs to change.

A file defines ADAPTER = Adapter(...) with:

  kind       a short stable id, e.g. "opencode". Used in the ledger, so never
             rename one that has shipped.
  name       what a person calls it: "OpenCode".
  cls        "AI agent", "AI editor" or "editor". AI kinds are counted as AI
             everywhere (the violet in the views, the harbour's robots).
  order      where it sits in the ancestry search. Lower is tried first, which
             matters when two patterns could match the same command line: the
             more specific pattern needs the lower number.
  ancestry   a regular expression matched against the command line of each
             ancestor of a listening process. None if it cannot be told apart
             that way.
  env        environment variable NAMES the tool sets in what it launches.
             Values are never read; the presence of the name is the signal.
  processes  executable names of the agent itself, for "N agent processes
             running" in the Sessions view.
  sessions   optional: a function returning [(mtime, path, reader)] for its
             transcripts, where reader(path) returns the session record (see
             sessions.read_claude for the shape). Read head and tail only:
             transcripts can be very large.

Evidence only. An adapter says how to recognise a tool; it never guesses one.
If a pattern would also match something else, leave it out: an unknown origin
is reported as unknown, and a wrong name is worse than none.
"""
import importlib
import os
import pkgutil


class Adapter:
    __slots__ = ("kind", "name", "cls", "order", "ancestry", "env", "processes", "sessions")

    def __init__(self, kind, name, cls="AI agent", order=100, ancestry=None, env=(), processes=(),
                 sessions=None):
        if cls not in ("AI agent", "AI editor", "editor"):
            raise ValueError("adapter %s: cls must be 'AI agent', 'AI editor' or 'editor'" % kind)
        self.kind, self.name, self.cls, self.order = kind, name, cls, order
        self.ancestry, self.env, self.processes, self.sessions = ancestry, tuple(env), tuple(processes), sessions

    @property
    def ai(self):
        return self.cls.startswith("AI")

    def __repr__(self):
        return "Adapter(%r)" % self.kind


def _load():
    found = []
    here = os.path.dirname(__file__)
    for info in pkgutil.iter_modules([here]):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module("%s.%s" % (__name__, info.name))
        a = getattr(mod, "ADAPTER", None)
        if isinstance(a, Adapter):
            found.append(a)
    kinds = [a.kind for a in found]
    dupes = {k for k in kinds if kinds.count(k) > 1}
    if dupes:
        raise ValueError("two adapters claim the same kind: %s" % ", ".join(sorted(dupes)))
    return sorted(found, key=lambda a: (a.order, a.kind))


ADAPTERS = _load()


def by_kind(kind):
    return next((a for a in ADAPTERS if a.kind == kind), None)
