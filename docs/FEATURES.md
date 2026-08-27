# Features

Grouped by the question each one answers. Every answer here is reached by
measuring something, and where it cannot be measured portlist says so instead of
guessing.

## The dashboard

- **Everything on one screen**, and where portlist opens: machine, exposure,
  agents and containers as cards; the listening table; the selected service with
  its origin and risk; the activity feed and the sparklines; a status line.
- **Travelling waves whose amplitude and speed are the reading.** One pattern,
  used under every card and across the table, each riding on its own real ratio:
  what fraction is reachable off-box, what fraction an agent started, what
  fraction is being used right now. A quiet reading ripples slowly and shallowly,
  a busy one moves faster and taller, and something unmeasured draws a flat line
  rather than a wave at zero. It is ornament in shape and a measurement in
  amplitude, and it is never used where a history belongs.
- **A lifetime column** on wide terminals, in the space that is otherwise dead
  to the right of the risk column: how long each service has been listening, on
  one log axis shared by every row, so a glance separates the thing that has
  been up for a month from the one that arrived while you were making coffee.
- **Live dials.** Three twelve-segment rings for CPU, memory and disk. The ring
  eases round when the reading changes and the leading segment pulses; an
  unmeasured value draws an empty ring instead of resting at zero.
- **Tab moves between views** in the same order as the number keys; `h` and `l`
  move between the dashboard's panes and `j`/`k` move inside the focused one.
- **It stays alive while you watch it.** The dials, the state dots, the risk
  diamonds, the selected row and the newest event all pulse, and a service that
  starts or stops listening while you are looking is marked. `a` stops all of
  it, and then the screen repaints only when the data changes.
- **The risk score is itemised, never bare.** `71 High` is followed by the points
  and the reason for each, so the number is auditable rather than magical.
- **Unknown origin is counted, not hidden.** Services already listening before
  portlist first looked get their own number, so none of them quietly inherits a
  repository label from whatever owns the port now.
- **"The engine did not answer" is its own state** on the containers card, and it
  never renders as a count of zero.

## What is listening

- Every listening socket, IPv4 and IPv6, TCP and UDP, deduplicated into one row
  per service rather than one row per socket.
- A **row is a service on a port**, not a port. Two processes can hold the same
  port number with different bind scopes, and collapsing them loses the one that
  matters.
- Named from the command, the port and the project together. A port number alone
  names nothing: `:8000` is not "an HTTP server", it is whichever of four things
  got there first.
- A pid of `None` is a normal state, not an error: on Linux a socket owned by
  another user is visible while its process is not.

## Who started it

- **What an agent has already started.** The agents view lists each session's
  history from the ledger: services it launched that are since gone, how many
  launches it is on record for, and how long ago the first and most recent were.
  A session that exited an hour ago still has a history, and that is usually the
  question being asked of it.

- **Process ancestry first, environment second.** Claude Code, Codex, Cursor,
  Copilot, Aider, Goose, Windsurf, VS Code, a terminal, `launchd`, `systemd`, a
  container runtime.
- **A launch ledger** written the first time a service is seen and never
  rewritten. Attribution survives the agent exiting and survives the service
  being restarted by something else, because the record is matched by a durable
  signature rather than by a pid.
- **Live, remembered and unknown are three different states.** A process that was
  already running before portlist ever ran has unknown origin, and says so,
  rather than inheriting a label from whatever owns the port now.
- The ledger only knows what portlist has observed, and shows when that started.

## Whether it matters

- **Reachability checked by connecting** to this machine's real address, not by
  reading a bind string. `0.0.0.0` in a config is a claim; an answered socket is
  a fact.
- **Risk as a score with its reasons attached.** The detail pane shows every
  input that produced the number.
- **Leftovers with the measurements behind the guess**: use measured over time,
  not inferred from uptime. A process can be up for a month and used this
  morning, or started an hour ago and never touched.
- **Blast radius and dependencies** from loopback connections: what uses this
  service, and what it uses.

## Containers

- Which container holds a host port, and which compose project it belongs to.
- Dual-stack publishes are deduplicated: Docker announces each mapping twice.
- Uptime read from the status rather than the creation time, so a container
  restarted this morning does not report "up 4 months".
- "The engine did not answer" is reported as its own state. It is not "no
  containers".

## Agent sessions

- Six tools read from the stores they already write: **Claude Code**, **Codex**,
  **GitHub Copilot CLI** (SQLite, opened read-only), **VS Code chat**, **Cursor**
  and **Gemini CLI**.
- The generated title, the first prompt you typed, the project, the model, the
  turn count, and the **context each session is carrying** - the number that
  decides what to clear.
- **Which plan each tool is signed in under**, so "which account burned this
  week's quota" is answerable.
- Live sessions matched to running processes by working directory. Where several
  agents share a directory it says so rather than picking one.
- Head and tail reads only. Transcripts reach eight megabytes; sixty sessions
  read in a tenth of a second.

## This machine

- Load, memory and disk as meters, with the numbers beside them.
- CPU and memory sparklines, one sample a second, with gaps where nothing was
  measured.
- Uptime, process count, CPU model and core split.
- The addresses this host answers on, and how many interfaces it has.
- Firewall state, stealth mode, SSH, and the container engine.
- What the listening ports add up to: exposed, critical, high, AI assets.

## The graph

- **The web dashboard's graph, in the terminal.** Started by, project, process,
  port and reachable from, as layered columns with the same edge names.
- **Sharing is what it shows.** A parent is printed once and carried down with a
  rule, so eleven services under one agent session reads at a glance.
- **The address that proved it.** Where reachability was verified by connecting,
  the graph says `confirmed on 192.168.0.2` rather than just naming the zone.
- **It degrades by dropping columns**, the process first, and becomes headed
  groups below 100 columns.

## Vibe mode

- **An ambient screen worth leaving open**, on `V` or after thirty idle seconds.
- **Seven scenes**: the cockpit, with everything at once; the machine and its
  meters; the host with its services around it; each agent and what it started;
  what has actually happened lately; a grid of every listening service; and the
  room, a plate that ships with the program and is drawn as characters, with the
  three readings that fit placed where the picture is dark.
- **A picture behind the scenes**, off until you ask for it with
  `portlist --vibe-bg thing.png`. PNG only, decoded with nothing but `zlib`.
  Opacity is density rather than alpha, capped at 60 per cent, painted into the
  negative space so the text stays legible, and turned down per scene where the
  scene is already busy. `b` tunes it live.
- **Arrivals and departures are animated because they happened.** A service that
  starts listening while you watch is marked NEW for a few seconds; one that
  stops is reported. The first frame marks nothing, since everything is new to
  the screen and none of it is new to the machine.
- **Five themes** (observatory, neon, terminal, aurora, minimal) and **four
  speeds** (static to cinematic), remembered between runs.
- **Every moving thing is a measurement.** A dot pulses because that service was
  measured busy inside the last minute. A particle crosses an edge because a
  loopback connection between those two ports was observed. "No connections
  observed between them yet" is a real answer and is what gets drawn when that
  is the truth.
- **Any key returns**, and the key that returned you is swallowed rather than
  acted on.
- Turning animation off also stops vibe mode arriving on its own: asking for a
  still screen and being given a moving one is not a feature.

## Getting out of your way

- **A free port** that is free now and not spoken for by anything you run later:
  it avoids the crowded bands and is stable per project, so the same project
  suggests the same port tomorrow.
- **`O` opens the port** in a browser.
- **Search** across port, service, command, project, directory and starter at
  once.
- **The selection follows the service**, never the row index, so a screen that
  redraws every few seconds never moves under your cursor.
- Width-adaptive layout: columns are given up in order of what they earn, from
  200 columns down to 60.

## What it will not do

- It never stops, kills or restarts anything. The detail pane prints the command
  and you run it.
- It opens no listening socket. A tool for watching what is listening should not
  add to the list.
- It sends nothing anywhere. There is no telemetry, no update check and no
  network code beyond connecting to this host.
