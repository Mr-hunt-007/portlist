<h1 align="center">portlist</h1>

<p align="center">
  <strong>Every port on this machine, and where it came from.</strong><br>
  A terminal program. No web UI, no dashboard, no server, no dependencies.
</p>

<p align="center">
  <a href="https://mr-hunt-007.github.io/portlist/">Website</a> &middot;
  <a href="docs/USAGE.md">Usage</a> &middot;
  <a href="CHANGELOG.md">Changelog</a> &middot;
  <a href="https://github.com/Mr-hunt-007/portlist/issues">Issues</a> &middot;
  <a href="LICENSE">MIT</a>
</p>

```
 PORTLIST  devbox   12 listening  2 off-box  2 need attention              21:20:37
  1 Services(12)  2 Exposed(2)  3 Attention(2)  4 Leftovers(5)  5 Agents(3)  6 Containers(0)  7 Sessions(8)  8 System

 PORT    SERVICE             PROJECT           REACHABLE       RISK      STARTED BY
 :3000   Next.js             storefront        Localhost only   12 Info  Claude Code 2h
 :5173   Vite                admin-ui          Localhost only   12 Info  terminal 5h
 :8787   Python http.server  data-export       All interfaces   71 High  Claude Code 5d
 :9050   Tor                 /opt/homebrew     Localhost only   12 Info  launchd 24d

 j/k move   enter detail   O open   1-8 view   / search   f free port   r rescan   q quit
```

Twelve things are listening. You started three of them today and you cannot name
the rest. `lsof` tells you a PID; portlist tells you the agent session, the
project directory and whether anyone has used it since Tuesday.

## Install

**Homebrew** (macOS, Linux)

```sh
brew tap Mr-hunt-007/portlist https://github.com/Mr-hunt-007/homebrew-portlist
brew install portlist
```

**winget** (Windows)

```powershell
winget install Mr-hunt-007.portlist
```

**pipx** (anywhere, and the simplest route on Windows because it brings
`windows-curses` with it)

```sh
pipx install portlist
```

**One line**, into `~/.local`, no root and nothing system-wide:

```sh
curl -fsSL https://mr-hunt-007.github.io/portlist/install.sh | sh
```

**From source**, which needs nothing but Python:

```sh
git clone https://github.com/Mr-hunt-007/portlist && cd portlist && python3 portlist.py
```

Then run `portlist`.

## The dashboard

`0`, and it is where portlist opens. Everything about the machine on one screen,
so a single screenshot tells the whole story.

```
  MACHINE                                           EXPOSURE                    AGENTS                      CONTAINERS
     ·  ●  ●         ·  ●  ●         ◉  ●  ●        LISTENING      16           Claude Code    14           ENGINE         docker
   ·         ●     ·         ●     ●         ●      EXPOSED        2            terminal       1            STATE          no answer
  ·    36%    ◉   ◉    85%    ●   ●    96%    ●     NEEDS WORK     2            launchd        1                           count unknown
   ·   CPU   ·     ●   RAM   ●     ●  DISK   ●      UNKNOWN ORIGIN 12                                                      not zero
     ·  ·  ·         ●  ●  ●         ●  ●  ●
  LOAD  3.56 3.37 3.64

  LISTENING  14 services                                                                                      Tab  next section
    PORT    SERVICE               PROJECT           STARTED BY          REACH           RISK
  ● :7337   Portboard             portboard         terminal            Localhost only  12 Info
  ○ :8000   Python http.server    CredRadar         Claude Code         Localhost only  12 Info
  ○ :8787   Python http.server    data-export       Claude Code         All interfaces  71 High

  SELECTED SERVICE                                                          │ ACTIVITY
                                                                            │
  Portboard :7337                                                           │ 22:52:49 · Bun on :10065 stopped listening
  ~/code/portboard                                                          │ 22:23:58 · Bun opened on :57155 (loopback)
                                                                            │
  REACH      Localhost only                                                 │ CPU
  PID        9561   Python                                                  │ ▃▃▄▃▃▂▃▄▅▄▃▃▃
  LAST USED  in use now                                                     │ MEMORY
                                                                            │ ▇▇▇▇▇▇▇▇▇▇▇▇▇
  RISK  71 / 100   High                                                     │
    +42   Listening on all interfaces (0.0.0.0)                             │
    +10   No authentication seen and reachable off-box                      │

  ● 2 exposed    ◆ 2 need attention    ⚠ 12 unknown origin    ◉ 3 agents    firewall on
```

**Tab** moves to the next view, in the same order as the number keys, and
**shift-Tab** goes back. **`h`** and **`l`** (or the arrows) move between the
dashboard's panes, and `j`/`k` move inside whichever has focus.

The three dials are live: each ring is twelve segments, the leading one pulses,
and the ring eases round rather than jumping when the reading changes. An
unmeasured value draws an empty ring and says so instead of resting at zero.

The risk score is never a bare number. The pane lists what it was made of, so
`71 High` is auditable rather than magical, and `⚠ 12 unknown origin` is counted
precisely so those services are not quietly attributed to whatever owns the port
now.

## Nine views

| key | view | what it answers |
|-----|------|-----------------|
| `0` | dashboard | everything at once, and where it opens |
| `1` | services | everything listening, with who started it |
| `2` | exposed | reachable from beyond this machine |
| `3` | attention | critical, high and medium risk |
| `4` | leftovers | looks abandoned, with the measurements behind the guess |
| `5` | agents | grouped by the agent, editor or terminal that started it |
| `6` | containers | by compose project, and the host ports they hold |
| `7` | sessions | coding-agent sessions, what they were about, context used |
| `8` | system | this machine: load, memory, disks, network, exposure |
| `V` | vibe | the ambient screen, for the second monitor |

Views 5 and 6 group rather than filter. Every view is a different question asked
of one scan, not a different scan.

## Keys

```
j / k, arrows   move                    tab shift-tab   the next view, the
h / l           the dashboard's panes                   same order as 0-8
enter, o        detail pane             /   search
O               open it in a browser    f   a port that is free now, and not
                (ctrl+enter too, where      spoken for by anything later
                the terminal sends it)  a   animation      V   vibe mode
0-8             views                   r   rescan now     ?   keys    q  quit
```

macOS never delivers Cmd+Enter to a terminal program, so `O` is the binding that
always works.

## The sessions you left open

Ten agent windows, none of them closed, and no way to tell which is which.

Press **7**:

```
  sessions                     5 running, 60 on disk, 42 stale

  Refactor the billing webhook retries                  2d 4h ago
   claude     payments                 621,511 tokens, 11 turns
   first: the stripe webhook retries twice on 5xx, work out why and fix it
   4 agents are running in that directory, so which one is this cannot be told

  Port the admin table to server components              2d 6h ago
   claude     admin-ui                 182,000 tokens, 34 turns
   running as pid 14502   -   close it with: kill 14502
```

Six tools, each read from the store it already writes:

| | |
|---|---|
| **Claude Code** | `~/.claude/projects/**/*.jsonl` |
| **Codex** | `~/.codex/sessions/**/rollout-*.jsonl` |
| **GitHub Copilot CLI** | `~/.copilot/session-store.db`, which keeps its own summary |
| **VS Code chat** | `.../Code/User/workspaceStorage/*/chatSessions/*.jsonl` |
| **Cursor** | the same layout under `Cursor/`, because it is a VS Code fork |
| **Gemini CLI** | `~/.gemini/tmp/*/logs.json`, where a build writes one |

Each gives the generated title, the first prompt you typed, the project, the
model, the turn count, and where available the **context it is carrying** - the
token total from the last turn, which is the number that decides what to clear.

It also shows which plan each tool is signed in under, so "which account burned
this week's quota" is answerable:

```
  Claude Code      max - default max 20x
  Codex            not signed in
  GitHub Copilot   signed in
  Gemini           signed in
```

Live sessions are matched to running agent processes by working directory. Where
several agents share one directory it says so rather than guessing.

**Prompts never leave the machine.** portlist has no server and no network code
at all, so there is nowhere for them to go. Account details are narrower still:
the plan and the organisation, never the address or the account id.

It never reads a whole transcript either - they reach eight megabytes. The head
has the first prompt and the directory, the tail has the title, the latest usage
and the last activity. Sixty sessions in a tenth of a second.

## Vibe mode

Press **V**, or leave it alone for thirty seconds:

```
                              P O R T L I S T

                                LOCAL NETWORK

                                   ○ :8787
                  :8422 ○ ·           ·           · ○ :8807
                            ·····     ·     ·····
             :8078 ○ ···················HOST···········●······ ◉ :7337
                            ·····     ·     ·····
                  :9050 ○ ·           ·           · ○ :8000

                  1 connection observed between local services
```

Five scenes rotate: the cockpit (everything at once), the machine and its
meters, the network between local services, each agent and what it started, and
what has actually happened lately. Five themes, four speeds, `t` and `s` to
cycle them, any other key to come back.

When a service really appears while you are watching, it is marked **NEW** for a
few seconds and the strip redraws around it; when one stops listening, that is
reported too. The first frame marks nothing, because everything is new to the
screen the moment it opens and none of it is new to the machine.

**Nothing on that screen moves unless something was measured.** A dot pulses
because that service was measured busy inside the last minute. A particle
crosses an edge because a loopback connection between those two ports was
observed. Where nothing has been measured, it says so and sits still: inventing
motion would make the prettiest part of the program the one lying to you.

## What it can tell you that `lsof` cannot

- **Who started it.** Claude Code, Cursor, Codex, Copilot, Aider, Goose,
  Windsurf, a terminal, a service manager - from process ancestry first and the
  environment second. And whether that session has since exited.
- **Whether it survived a restart.** A launch record is written the first time a
  service is seen and never rewritten, so attribution outlives both the agent
  exiting and the service being restarted by something else.
- **Whether anyone is using it.** Measured over time, not inferred from uptime.
- **Whether the network can reach it**, checked by connecting to this machine's
  real address rather than reading a bind string.
- **Which container holds the port**, and which compose project it belongs to.
- **A port that is free** now and not spoken for by anything you run later.

## It never stops anything

The detail pane prints the command; you run it. There is no kill key, no daemon,
and nothing here writes to another machine.

It does open sockets, and it is worth being exact about which. It connects
*outward* to the ports on this machine to see what answers, and it binds a
candidate port for a moment to check it is free, then closes it. Neither ever
calls `listen()`, so portlist has no port of its own and nothing can connect
to it.

## Where its data lives

`~/.portlist/` - the launch ledger, use history and the recipe book. Override
with `--data-dir` or `PORTLIST_DATA`.

## Requirements

Python 3.9+ with `curses`, standard on macOS, Linux and BSD. On Windows,
`pip install windows-curses`, which `pipx install portlist` does for you. No
third-party packages on any platform otherwise, ever.

## Documentation

- [Setup](docs/SETUP.md) - every install route, and what each one puts where
- [Usage](docs/USAGE.md) - the views, the keys, and what each column means
- [Features](docs/FEATURES.md) - the full list, and how each answer is reached
- [Architecture](docs/ARCHITECTURE.md) - one scan, one model, eight views
- [Security](SECURITY.md) - what it reads, what it never sends
- [Contributing](CONTRIBUTING.md)

## Related

portlist is the terminal half of [Portboard](https://github.com/Mr-hunt-007/portboard),
which adds a web dashboard, a fleet view over SSH and an HTTP API. Same engine,
same answers. If you only ever wanted the screen, this is it.

MIT.
