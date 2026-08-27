# Features

Grouped by the question each one answers. Every answer here is reached by
measuring something, and where it cannot be measured portlist says so instead of
guessing.

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

## Vibe mode

- **An ambient screen worth leaving open**, on `V` or after thirty idle seconds.
- **Four scenes**: the machine and its meters; the host with its services around
  it; each agent and what it started; what has actually happened lately.
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
