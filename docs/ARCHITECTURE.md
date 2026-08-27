# Architecture

One scan, one model, eight views.

```
    the machine                 one model                 eight views
  ┌───────────────┐         ┌───────────────┐         ┌───────────────┐
  │ sockets       │         │               │         │ 1 services    │
  │ processes     │────────▶│  a row per    │────────▶│ 2 exposed     │
  │ containers    │  read   │  service on   │  filter │ 3 attention   │
  │ git roots     │         │  a port       │  group  │ 4 leftovers   │
  │ transcripts   │         │               │         │ 5 agents      │
  └───────────────┘         └───────┬───────┘         │ 6 containers  │
                                    │                 │ 7 sessions    │
                            ┌───────▼───────┐         │ 8 system      │
                            │ ~/.portlist   │         └───────────────┘
                            │ launch ledger │
                            │ use history   │
                            └───────────────┘
```

A view is a question asked of the model, never a second trip to the machine.
That is why switching views is instant, why the numbers in the tab bar always
agree with the rows underneath, and why a new view costs a filter rather than a
collector.

## The layers

**Collect** (`collect.py`, `platforms/`) runs the platform's own tools and parses
them. Everything platform-specific is here and nowhere else.

**Model** (`scan.py`) turns that into one row per service on a port, then asks
the specialists to decorate it:

| | |
|---|---|
| `recipes.py` | the durable signature that identifies a service across restarts |
| `provenance.py`, `gitinfo.py`, `projects.py` | where it was started from |
| `ledger.py` | the launch record, written once and never rewritten |
| `lifecycle.py` | how long, started by what, and the sentence that says so |
| `access.py`, `posture.py` | who can reach it, checked by connecting |
| `risk.py` | the score, and every reason that fed it |
| `activity.py` | use measured over time, not inferred from uptime |
| `containers.py` | which container and compose project holds the port |
| `depends.py` | what uses this, and what it uses |
| `freeport.py` | a port that is free now and later |
| `sessions.py` | the six agent transcript stores |
| `mcp.py`, `mcpclients.py` | MCP servers and the clients that speak to them |

**Draw** (`tui.py`) is the only file that knows about curses, and the only one
that knows there is a screen at all.

## The launch ledger

`~/.portlist/ledger.jsonl`, append-only. The first time a service is seen,
portlist writes what it saw: the timestamp, a signature built from the command
line and working directory, the ports, the launching process and its parent, the
git root and the project.

It is never rewritten. On a later scan a service is matched to its record by
**signature, never by pid**, so a service that restarts under a new pid keeps its
origin, and an agent that has exited still gets the credit for what it started.

Three states come out of that, and they are kept apart on purpose:

- **live** - the process that started it is still running and still says so;
- **recorded** - portlist saw the launch, the starter has since exited, and the
  record stands;
- **unknown** - it was already listening before portlist ever ran, so nothing is
  claimed at all.

The third is the important one. A stale process must never inherit a repository
label from whatever owns the port now.

## What it never does

No daemon, no server, no background process. portlist runs while its window is
open and stops when you quit. It writes to `~/.portlist` and nowhere else, and
the only sockets it opens go to this machine.
