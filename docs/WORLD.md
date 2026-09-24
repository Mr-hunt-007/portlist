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
| Smoke | Only from a service seen in use (or using CPU). Its density follows the service's own CPU when the scan has it: a light puff at a few percent, thick dark plumes near a whole core. Fewer samples than needed is "still measuring", never "idle" |
| Boats at the anchorage | Outbound connections that are not web traffic, as the vessel their port says they are: push (held open, waiting) is a fishing boat with a line out, mail the mail boat, chat a ferry, AI a fast launch, databases, caches and queues tugs, name and directory services a tender. They sail in off the causeway when the first connection opens and out when the last closes. Web traffic stays cars |
| Coal carrier and excavator | While a train tips and for a while after, the excavator trims the bunker, spreading coal along the pit. When the bunker is half full, a bulk carrier is towed in, ties up to the jetty, and an excavator loads it bucket by bucket; it sits lower as it fills and is towed out full or once the bunker is empty |
| Tugs, pilot boat, mooring lines, radar, reflections | How a real port works, following the ship they serve: two tugs bring every big ship in and out, a pilot boat meets the collier, a ship at the jetty is tied up. The radar on the harbour master's office and lights reflected on the water at night are scenery |
| Coal train | Data this machine is receiving. A long diesel at each end and hopper wagons on two-axle bogies: it comes in behind the front engine and backs out behind the rear one. The line ends at a buffer stop, and a signal at the staithe shows green for a train coming in to a clear staithe, red while one is on it. While the network brings data in, a train runs in over the trestle south of the harbour, tips its wagons into the staithe bunker and backs out the way it came, tail lamp leading. One wagon at about 100 KB/s, up to six. Nothing coming in, no train |
| Dust, weeds, a cobweb | Long idle, or it looks left over, with the reasons in the panel |
| Roof beacon | Risk as scored. Amber medium, red high and critical |
| Grey plate, no paperwork, `?` | Nobody knows who started it. Unknown, not dangerous: never red, never prioritised above exposure |
| Bulb on the sign | The agent that started it has exited, and it is still running |
| Crossed swords | More than one process listens on this port, on different addresses |
| The external-access gate | The boom rises only when portlist connected to this machine's own network address and was let in. A 0.0.0.0 bind alone lights the lamp amber and leaves the boom down. A refused connection shuts the building's door |
| Red line to the gate | This service is reachable from beyond the machine |
| Robots | Coding agents that are running now and started something here. They walk on two legs and swing their arms; at work their hands move in front of them |
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
| The harbour gate | A checkpoint canopy over both lanes: in on the north lane, out on the south, each with its own barrier that lifts for the vehicle in front of it. The lit panel reads EXT OPEN, EXT BOUND or EXT CLOSED, and while something is reachable from outside the north barrier stands open and a red lamp blinks |
| Other machines | Machines that report in to a fleet store, where there is one (standalone portlist has none), as harbours on the horizon west of the lighthouse: one small building per listening port, a red lamp if anything there is exposed. A host that has stopped reporting stays, dark and fogged, with how long ago it was last heard |
| The groundskeeper | Sweeps up an old foundation once its service has been gone 90 seconds. The stop stays in the Timeline |
| Old foundations | Something that stopped here. Kept for a while so a restart lands in the same lot |
| The lighthouse | SSH. Full beam while any SSH session is open, in or out; a steady lamp while a server listens with nobody connected; dark otherwise. Someone logged in to this machine arrives as a big ship and ties up to two mooring posts clear of the lighthouse rocks, and the beam swings round and holds on it as it comes in |
| Customs house | By the gate: this machine's firewall, read from its own settings. Lit with a green flag while it is on, dark with a red flag when it is off, blinds down in stealth mode. The gate stays a separate measurement: a firewall that is on can still let a service through |
| Walls, fence, barriers | Sea walls on every edge that meets water, a security fence on the landward side with the gate as the only way through, a parapet on the south wall, barriers where a road would run into the sea, and a causeway carrying the road to the mainland. Structure, not data |
| Islands and boats | Every machine you hold an SSH or database session to (MongoDB, PostgreSQL, MySQL, Redis, Elasticsearch...) is an island on the horizon with its logo. A small boat shuttles out and back while the session is open: SSH from a jetty between the third and fourth piers, databases from the water east of the last pier. Never from the lighthouse, whose rocks would sink it |
| The car park | Outside the gate: every machine your apps are talking to right now (HTTPS, push and so on), one car per remote host, labelled with the app. A new host drives in over the causeway, a finished one drives out |
| System quarter | Small sheds beside the office for services portlist files as system (AirPlay, Handoff, editor helpers). Drawn so nothing listening is hidden, never counted, never at the gate, never a pet's job |
| Rain | The CPU has stayed above 80% over the last few samples; it clears once it is back under 65%. A note says so when it starts and stops |
| Tape on the deck | Memory is 85% full or more |
| Rotary beacon on the gate | Only while a service is verified reachable from outside: it sweeps the approach and washes the road red |
| Meter on a wall | The agent that started this service has exited and it still runs; the disc turns as fast as the service is used |
| Hazard stripes | In front of a building whose port another process also holds |
| Door lamp | Warm while the service answers, guttering when long idle, out when it does not answer |
| Pipes along the roads | A service that depends on another, from the scan's own dependency list, joined to it door to door by a conduit. It carries a flow while both are in use and lies quiet otherwise. Loopback traffic between them still drives as carts |
| The harbour's mood | One state for the whole place from the machine's figures: calm, busy (CPU from 40%, 200 KB/s on the network, 20 outbound connections or 4 services in use) or under pressure (CPU 80%, memory 85%, disk 92%). The wind, the whitecaps and the drift of the smoke follow it together, and the machine panel says which and why |
| Weathering | A building that has stood for days streaks down its walls, less so one in daily use: how long it has been there, from the recorded history |
| A white survey van | portlist's own check: when it connects to a service from this machine's network address and gets in, the van comes in through the gate to that building's door, pauses and leaves |
| A count on a car's roof | One remote host carrying four or more connections |
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

## What it costs in the browser

At rest (the camera still, nobody touching it for five seconds, no tour) the
page draws at half the display's rate; everything in it moves slowly enough
that the difference cannot be seen. Measured with the GPU drawing the canvas,
1440x900 at 2x, idle: main thread 15.7% (23.1% before the half rate), script
12.9%, JS heap 5.5 MB. A screen-sized cache for the ground was tried and
dropped: with the GPU it saved no time and would have held about 20 MB. Hidden
tabs neither draw nor poll. Sounds are at most one every 150 ms, and a burst of
the same kind is one sound. A burst of closing connections empties the car
park quickly: past a five-second backlog, cars leave 0.45 s apart instead of
1.3 s. Arrow keys pan; 1 to 9 open the ports in order.

## What it costs

There is one scanner per process, always. `/api/world` reads the scan every
other view reads, cached and shared. Where a server already refreshes the scan
on demand, that refresh keeps it current (a change reaches the page in about
six seconds), and the terminal's `W` key reuses the terminal's scan. Only standalone
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

## Replay

`P`, or the clock button, opens a scrubber over the recorded opens and closes
(`~/.portlist/events.jsonl`). Dragging it rebuilds the
harbour as it stood then: `world.reconstruct()` starts from what is listening
now and walks the history back. Where the harbour's journal has a record within
twenty minutes, the past harbour also gets each service's use, owner and
connection count as the journal found them, and the banner names the time.
Otherwise it has listeners and exposure only and says so; origins read "not
recorded", never "unknown". Sessions, traffic and containers are never
recorded for the past. Live returns to now.
`/api/world?at=<unix time>` and `/api/world?timeline=1` serve it.

## The journal

The opens and closes say when things came and went. The journal says what they
were doing. Every ten minutes while the harbour is being looked at, it appends
one line to `harbour-journal.jsonl` beside the history: each listener's port,
name, activity, exposure, owner (when known) and connection count, the
machine's CPU, memory and disk, and how many hosts and containers there were.
About 380 bytes a record; two weeks are kept. No command lines, directories or
addresses. It is written from the snapshot the page already has, never from a
scan of its own.

Replay reads it back, and every service gets its **record** across days: on
how many days it was seen and what share of samples found it in use (in its
inspector). Weathering follows that record: a building that has stood for days
and is rarely used streaks down its walls; one kept in use stays clean.

## Keyboard and screen readers

Tab from the top reaches "Skip to the list of everything in the harbour": a
list of buttons, one per building, island, container, car, other machine and
landmark. Focus moves the camera there; Enter opens the same inspector a click
does. On a phone the machine panel collapses to one line: cpu, memory, disk,
time.

## Play: drama and the sandbox

`G`, or the Play button, opens a panel, everything in it off by default. **Game
mode** at the top is one switch for the full show: it turns on drama and sound
together, and off returns to the calm harbour. Stopping is never part of it.

**Drama** tells real events with more theatre. An agent that exits leaves its
toolbox at the door, and some while later the inspector cat comes to say "Boss
went home. :3000 is still on." A port two processes hold gets a brawl: two
forklifts nose to nose, a crew arguing, a red ⚔ :port ⚔ sign. A service
verified reachable from outside brings a siren by the gate, figures in coats at
the boundary and tugs lying off the causeway. Rain brings lightning over the
cranes; memory at 85% makes the yard stacks wobble. A calm score sits in the
pills and on the picture: 100, less 20 per service reachable from outside, 10
per high risk, 8 per failing, 5 per left running by an exited agent, 5 per left
over, 3 per unknown origin. The figures at the fence and the tugs are
dramatisation; nobody measured them, and the legend says so.

**Sandbox** is a simulation, labelled as one: port collision, ghost the harbour,
accidental exposure, Docker convoy, a storm (CPU at 95%), memory 92% full, a big
download (the coal train, and then the collier), and boats coming in. It copies the harbour as it is, stops
listening to the scan while it runs, and changes nothing on the machine. Every
simulated line in the log says "(simulated)", the status chip reads "sandbox",
a banner says so, and a picture taken then is stamped SIM. Back to live
restores the real harbour.

**Stopping.** A shared port's inspector has one "Settle it" button per
process. In the sandbox it stops the simulated one. Live, it copies `kill <pid>`
unless **Allow stopping from the harbour** is switched on in Play (off again on
every page load). Then each service's inspector has a Stop button: it asks
first, and `POST /api/world/stop` sends SIGTERM, only with the page key, a
same-origin request, and a fresh scan showing that pid still on that port;
never the server itself or pid 0/1. A process that ignores it is offered
`kill -9`. A server that serves this page with its own stop endpoint routes
the request through that, with its own checks.

## Memory, stories, comparison and today

**The pets remember** what the recorded opens and closes say, one line at a time
and never the same line twice: Rivet on a service that has started three or
more times today, Kelp on one that has been open to the network before, Bosun
on one that went away today and came back, Pilot on one that has stood for days
unused. Every line is a count from the history (`memory` on each service in
`/api/world`).

**Stories.** A few events in a row can mean one thing, and the harbour says so
once, in a card at the top and in the log: an agent arriving and starting a
service ("a development session came alive"), an agent leaving with its server
still running, three containers within half a minute, a service reachable from
outside minutes after it started, three restarts in three minutes, four services
stopping within twenty seconds. Never in the sandbox.

**Compare** (`C`, or the button) sets the harbour beside itself an hour ago:
what is new since then carries a star on its sign, what has gone stands as a
ghost outline on a free lot. The same button turns it off.

**Today**, a tab in the list, tells the day so far from the recorded opens and
closes and the stories told, with counts at the top.

**Families.** An agent's inspector, running or exited, lists what it started, each
service's state, and what each one leans on.

## Spotlight, sound and pictures

Whatever you click stays lit and the rest of the harbour steps back a little,
following the thing as it moves. `M` turns on sound (off by default,
remembered): the water, a chime when a service starts, a clonk when one stops,
a thud when a container is set down. It is made in the page with WebAudio, no
files, and a burst of starts is one chime. `K`, or the camera button, saves a
PNG of the harbour with a strip of its counts, for sharing: host names,
addresses and the pets' chat are left out, and nothing is uploaded.

## Getting around

The list at the top left (what needs a look, the pets, the timeline) starts open
on a wide screen and remembers how you left it. Ambient mode (`S`) hides the
controls; move the mouse and an **Exit ambient mode** button appears top right.
The machine panel ends with the network view's four counts: listening, inbound,
outbound, and to public IPs.

## Keys

`F` full screen, `S` ambient mode (tour + captions, chrome fades), `T` tour,
`/` find, `P` replay, `?` legend, `A` what needs a look, `L` light (the clock, day, dusk,
night), `M` sound, `K` picture, `G` play, `C` compare with an hour ago, arrows pan, `1`-`9` open the ports in order, `0` whole harbour, `+` `-` zoom, `Esc` close.

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
