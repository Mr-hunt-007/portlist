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
