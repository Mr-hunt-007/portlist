# The living harbour

`portlist --world` (or `-world`, or `W` inside the terminal) opens this machine as
a harbour in a browser, full screen, meant for a second screen. It is another
view over the same scan as the ten terminal views. It never inspects the machine
itself.

> Don't build a game around portlist. Build a world that makes portlist understandable.

## What everything is

| On the screen | What portlist measured |
|---|---|
| A building | One listening service. The shape and the emblem on its wall say what kind: lighthouse for SSH, tanks for Postgres, MySQL, Mongo and friends, a short block for Redis, a dome for local models and AI apps, a radio mast for MCP, an onion tower for Tor, a gatehouse for nginx and Caddy, a garage for dev servers, a factory for app servers, a warehouse for file and object storage, a shed for system services and anything unidentified |
| Logos | On the wall, the service's own mark (Redis, MongoDB, PostgreSQL, nginx, Docker, Grafana...). On the sign, chips for what it runs on and what it was built with: the runtime (Python, Node, Bun, Deno...) is read from the process, the framework (React, Next.js, Vue, Svelte, Angular, FastAPI, Django, Flask...) from the project's own package.json, requirements.txt or pyproject.toml. Nothing is inferred from a port. Marks from Simple Icons (CC0) |
| The dot on its sign | Green in use, amber idle, brown long idle, blue still measuring |
| Smoke | Only from a service seen in use. Fewer samples than needed is "still measuring", never "idle" |
| Dust, weeds, a cobweb | Long idle, or it looks left over, with the reasons in the panel |
| Roof beacon | Risk as scored. Amber medium, red high and critical |
| Grey plate, no paperwork, `?` | Nobody knows who started it. Unknown, not dangerous: never red, never prioritised above exposure |
| Bulb on the sign | The agent that started it has exited, and it is still running |
| Crossed swords | More than one process listens on this port, on different addresses |
| The external-access gate | The boom rises only when portlist connected to this machine's own network address and was let in. A 0.0.0.0 bind alone lights the lamp amber and leaves the boom down. A refused connection shuts the building's door |
| Red line to the gate | This service is reachable from beyond the machine |
| Robots | Coding agents that are running now and started something here |
| Hard hats | Terminals, shells and editors that started something here |
| Harbour master's office | Coding sessions. A lit window is a live session; robots at the door are live sessions with nothing listening. Titles only, never prompts |
| Container yard | Containers, with a lamp lit while running. A yard the engine did not answer for is shown closed, not empty |
| MV `<hostname>` | This machine. Deck cargo is memory in use, crane speed is load, clutter at the yard edge is a full disk |
| Trucks, feeder ships | A service or container that started while the page was open |
| Red-roofed cars | A real established connection from outside |
| Pale carts | A loopback connection between two services |
| Powered-down robot | An agent that started a service and has since exited: its robot waits by the door, eyes dark, for as long as the service runs |
| Highway and toll plaza | The causeway is a six-lane highway: three lanes each way, a median barrier, shoulders and lamps. Cars spread across the plaza's six booths; the arms lift as they approach and nobody stops. A gantry sign shows the real network rate and outbound host count |
| Traffic light | At the car park exit. Leaving cars get a green phase only when one is waiting; amber between phases |
| Forklift | Takes pallets to services with connections open right now, then returns; parked when nothing is in use |
| The groundskeeper | Sweeps up an old foundation once its service has been gone 90 seconds. The stop stays in the Timeline |
| Old foundations | Something that stopped here. Kept for a while so a restart lands in the same lot |
| The lighthouse | SSH. Full beam while any SSH session is open, in or out; a steady lamp while a server listens with nobody connected; dark otherwise. Someone logged in to this machine arrives as a big ship and moors at the lighthouse |
| Customs house | By the gate: this machine's firewall, read from its own settings. Lit with a green flag while it is on, dark with a red flag when it is off, blinds down in stealth mode. The gate stays a separate measurement: a firewall that is on can still let a service through |
| Walls, fence, barriers | Sea walls on every edge that meets water, a security fence on the landward side with the gate as the only way through, a parapet on the south wall, barriers where a road would run into the sea, and a causeway carrying the road to the mainland. Structure, not data |
| Islands and boats | Every machine you hold an SSH or database session to (MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch...) is an island on the horizon with its logo. A small boat shuttles out and back while the session is open: SSH from a jetty between the third and fourth piers, databases from the water east of the last pier. Never from the lighthouse, whose rocks would sink it |
| The car park | Outside the gate: every machine your apps are talking to right now (HTTPS, push and so on), one car per remote host, labelled with the app. A new host drives in over the causeway, a finished one drives out |
| System quarter | Small sheds beside the office for services portlist files as system (AirPlay, Handoff, editor helpers). Drawn so nothing listening is hidden, never counted, never at the gate, never a pet's job |
| Sky and sea | The sun and moon follow the real clock and the moon shows tonight's real phase, with its light on the water. Stars, clouds, the distant town, buoys, whitecaps, surf and gulls are scenery and mean nothing; the gulls glide, beat their wings now and then and cast a shadow on the water. Street lamps come on after dark |

## The pets

Five cats, each with a job. Each takes the most important fact its role cares
about, walks there, looks, writes it down, and reacts. Click one and it says what
it is doing and why, with the evidence.

| Pet | Role | Cares about |
|---|---|---|
| Kelp | guard | reachable from outside, bound beyond loopback, high risk |
| Bosun | inspector | new services, unknown or ambiguous origins, shared ports, services whose owner left |
| Pilot | janitor | leftovers, long idle, departures, a full disk |
| Rivet | mechanic | not answering, restarts, flapping, memory pressure |
| Skipper | courier | provenance: which agent started what, which container publishes which port |

Priorities follow the activity library: external exposure 100, port conflict 95,
not answering 90, high risk 85, unknown origin 60, agent left a service 55, new
service 45. A change seen in the last 90 seconds outranks a standing fact of
similar weight, so it is noticed; once it is old the pet returns to whatever is
still true. With nothing to do, a pet patrols and says so. When two pets look at
the same thing they may talk about it, and every line is built from the evidence.

## Rules

- **Nothing is drawn that was not measured.** Every entity is a row, a group, a
  container or a session.
- **Randomise presentation, never meaning.** Which way a pet walks and where it
  sits vary. Exposure, ownership, risk and newness never do.
- **The first frame marks nothing.** Opening the page does not announce fourteen
  arrivals. Only a change between two scans starts a truck, a ship or a toast.
- **A restart keeps its identity.** Same port, same command, same directory: the
  building stays and says the process changed.

## Physics

Checked automatically in the page, not by eye:

- **Boats** keep their own pace, 0.8 to 1.5 tiles a second at the peak and a
  little different each trip, and wait a varying time at either end. They
  leave their slip due north past the pier heads, then turn on one continuous
  curve; the hull faces the true heading and the wake trails the stern. Every
  route is sampled against land, piers, the moored ship, the crane berth and
  the lighthouse rocks.
- **Road vehicles** accelerate and brake (no standstill-to-full-speed jumps),
  queue behind each other, and never overlap.
- **The car park** has an in lane (east) and an out lane (west) with bays on
  both sides. Moves that stay on their own side run at the same time: arriving
  into an east bay, leaving from a west bay into a gap. Only the two moves
  that cut across the other lane (arriving west, leaving east) take a crossing
  token, one at a time. Arrivals are released in order, 1.5 s apart, one per
  booth, and a signal controls the exit.
- **Props** (trees, lamps, bench, shelter, booths) are placed from one layout
  table with footprints; `layoutCheck()` in the page proves none stands in a
  lane, a bay or another prop.
- **`tools/worldcheck/run.py`** serves the page on a scripted machine (inbound
  SSH, SSH and MongoDB islands, containers, a six-host burst, starts and stops)
  and checks every frame in headless Chromium. It runs in CI
  (`.github/workflows/world.yml`) on any change to the harbour.
- **Pets** never walk on water: anything at sea is watched from the quay.
- **The causeway** is solid wherever traffic drives; vehicles thin into the
  fog before the deck does.

## Timing

While a page is open the scan runs back to back, so a service that starts or
stops shows up within about three seconds. Buildings rise with easing and power on
floor by floor, go dark row by row and sink in dust when they stop; system sheds fade in and out and the
lighthouse lamp warms up and cools down.

## Reading it at a glance

Signs are drawn at a fixed size and never overlap: the most important one wins
(selected, exposed, not answering, high risk, just started) and the rest step up
with a leader line or wait until you zoom in. Zoomed out, only what needs you is
labelled; closer, the port and its marks; close, the logos too. A change that
matters surfaces as one small card with its logo, folded with others of its kind
("3 services started", "Claude Code exited, :3000 still running"), then the world
is left alone again. The corner log holds the last few seconds only; the full
record is in the Timeline tab. Tools and pills fade back after a few quiet
seconds. Pets with nothing to do sit at home rather than wander.

## The machine panel

Bottom left: host, OS, chip, uptime, process count, then CPU (with load
average), memory (with swap), disk and network, each with a sparkline of the
samples this page has received. The same figures as the terminal's system view,
read from the same scan. Click its title to fold it.

## What it costs

There is one scanner per process, always. `/api/world` reads the scan every
other view reads, cached and shared. In portboard the server's own on-demand
refresh keeps it current (a change reaches the page in about six seconds), and
the terminal's `W` key reuses the terminal's scan. Only standalone
`portlist --world`, where nothing else is scanning, runs its own keeper: every 2 seconds for 20 seconds after
anything changes, and every 4 seconds while nothing does; it stops 30 seconds
after the last poll. Measured on an M4 with 14 services: about 2.6% of one core
for the server, 46 MB resident, 5 ms per `/api/world` answer, 51 KB per answer.
A scan is about 0.075 s of CPU, a third less than before, because whether a
command line is an MCP server is now decided once per command line rather than
on every scan.

## First visit

A short card explains the harbour once, with a tour, the legend, or nothing.
It is remembered per browser.

## Keys

`F` full screen, `S` ambient mode (tour + captions, chrome fades), `T` tour,
`/` find, `?` legend, `A` what needs a look, `L` light (the clock, day, dusk,
night), `0` whole harbour, `+` `-` zoom, `Esc` close.

## How it is built

- `plcore/world.py` is the semantic engine. `build()` turns rows, groups,
  containers, sessions and system info into a snapshot with states and
  conditions; `Differ.feed()` turns two snapshots into events; `plan_pets()`
  gives each pet one task; `chatter()` the lines. Pure and tested
  (`tests/test_world.py`).
- `plcore/worldserve.py` serves one page and one endpoint on 127.0.0.1 only. The
  Host header must name that address, the page needs the per-run key in its URL
  and the API needs it in a header. Read-only.
- `plcore/data/world.html` is the renderer: one file, canvas, no dependencies and
  no network. Full screen comes from a Chromium-family browser in app mode with
  its own small profile under the data directory; without one, the default
  browser opens it and `F` goes full screen.
