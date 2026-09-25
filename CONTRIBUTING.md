# Contributing

## Run it

```sh
git clone https://github.com/Mr-hunt-007/portlist && cd portlist
python3 portlist.py
```

No build step, no dependencies, no virtualenv needed.

## The rules this codebase keeps

They are worth reading before a change, because most of the bugs worth having
found here were breaches of one of them.

1. **Never dress a guess as a fact.** Unknown is a state to render, not a blank.
   `None` means "cannot tell" and must not collapse into `False`.
2. **Absence of evidence is not evidence of absence.** "No container answered"
   is not "no containers".
3. **A live claim and a remembered claim never collapse.** The ledger knows only
   what portlist has observed, and says so.
4. **Never let a row borrow a label from its port.** Two processes can hold one
   port with different bind scopes.
5. **The selection follows the service, not the row index.** A screen that
   redraws every few seconds must never move under the cursor.
6. **Verify against live output, not green tests.** Every recurring bug in this
   project has been a confident wrong answer rather than a crash.

## Add an agent

Each coding agent and editor portlist recognises is one file in
`plcore/adapters/`, and every "was this started by an agent?" answer is built
from them: the ancestry patterns, the environment variable names, the agent
processes the Sessions view counts, and where its transcripts live. Adding one
you use (Amp, Continue, Cline, Roo, Kiro...) is a single file:

```python
# plcore/adapters/amp.py
from . import Adapter

ADAPTER = Adapter(
    kind="amp", name="Amp", cls="AI agent", order=78,
    ancestry=r"(?:^|/)amp(?:\s|$)",   # matched against each ancestor's command line
    env=(),                            # names the tool sets in what it launches; values are never read
    processes=("amp",),                # its own executable, for the Sessions view
)
```

`plcore/adapters/__init__.py` documents every field. Two rules: a pattern must
not match anything else (a wrong name is worse than "unknown"), and show the
evidence in the pull request, a `ps -o pid,ppid,command` line from a real
session is enough. `tests/test_report_adapters.py` checks the table is still
consistent.

## Terminal work

`plcore/tui.py`, `vibe.py`, `dash.py` and `graphview.py` are the drawing layer.
Keep them free of anything that assumes a web server exists: they are read by
another project that renders the same model, and an import of something only
this tree has breaks it silently.

Check any layout change at 200, 110, 80 and 60 columns, and at 10 rows. Most
terminal bugs are width bugs.

## Sending a change

Open an issue first for anything that changes what a column means. For the rest,
a pull request with a short note on what you saw before and after is plenty.
