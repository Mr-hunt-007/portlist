# Changelog

Dates are the day the work landed. Versions follow [semver](https://semver.org/).

## Unreleased - 2026-09-23

### Added

- **Harbour: relationships, mood, memory and stories.** Services that depend on
  each other are joined by pipes that flow while both are in use. One mood for
  the whole harbour (calm, busy, under pressure) drives wind, whitecaps and
  smoke, and the machine panel says why. Pets remember what the history
  records: restarts today, earlier exposure, a service that came back. Chains
  of events are told once as stories. `C` compares with an hour ago (new gets a
  star, gone a ghost); a Today tab tells the day; an agent's inspector shows
  its family; buildings weather with age; a busy host carries a count.
- **Harbour: engineered details.** The coal train is a proper consist: a long
  diesel at each end and hopper wagons on two-axle bogies, backing out behind
  its rear engine. Robots walk on legs and swing their arms.
  The excavator trims the bunker while a train tips instead of waiting for a
  ship. The line ends at a buffer stop, with a signal at the staithe. The
  inbound SSH ship ties up to mooring posts clear of the rocks. The forklift
  has tyres you can see and sets pallets beside a door, not in it. Sandbox
  adds a storm, full memory, a big download and boats coming in.
- **Harbour: a port that works like one, boats by kind, and stopping.**
  Outbound connections that are not web go by sea as the vessel their port
  says: fishing boats for push, the mail boat, a ferry for chat, a launch for
  AI, tugs for databases and queues, a tender for naming. A half-full coal
  bunker brings a bulk carrier, towed in by two tugs with a pilot boat, tied up
  to the jetty and loaded by an excavator, sitting lower as it fills. Radar on
  the office, lights reflected at night. **Stopping from the harbour**: off by
  default and every reload, switched on in Play; each stop is confirmed and
  goes through `POST /api/world/stop` (key, same origin, fresh-scan check,
  SIGTERM, `kill -9` offered if ignored). The list at the top left is a clear
  button and starts open on wide screens; ambient mode has a visible Exit; the
  machine panel shows listening, inbound, outbound and public counts. The
  first-visit card no longer comes back after a quick dismiss.
- **Harbour: a coal train, CPU smoke, and Play.** A coal train is the data the
  machine is receiving: it runs in over a trestle south of the harbour while
  downloads flow, tips its wagons at the staithe and backs out the way it came
  (one wagon per ~100 KB/s, up to six). Chimney smoke follows each service's own
  CPU. `G` opens Play: **Drama** (off by default) tells real events with more
  theatre (a robot's dropped toolbox and a cat who says the boss went home, a
  brawl at a shared port, a siren with figures at the fence and tugs offshore
  when something is verified reachable, lightning in the rain, wobbling stacks
  at 85% memory, a calm score with its rule shown); **Sandbox** runs labelled
  simulations (port collision, ghost the harbour, accidental exposure, Docker
  convoy) from a copy of the harbour, touching nothing, with Back to live. A
  shared port's inspector gets "Settle it": simulated in the sandbox, a copied
  `kill <pid>` live. The harness checks all of it.
- **Harbour: what you click, what the machine feels, and a picture to share.**
  A spotlight stays on whatever you click while the rest steps back. Rain means
  the CPU has stayed above 80% (it clears below 65%, and a note says so); tape
  goes round the deck cargo at 85% memory. A rotary beacon sweeps the gate and
  washes the road red only while a service is verified reachable from outside.
  The lighthouse beam swings round and holds an arriving SSH ship. A meter turns
  on the wall of anything left running by an agent that has exited, as fast as
  it is used; hazard stripes mark a port two processes hold. Buildings get a
  pale rim and a door lamp (warm, guttering when long idle, out when not
  answering); pets and workers a faint ring in their colour; zoomed out, every
  building keeps a quiet port tag where there is room. Clicking a pet makes it
  purr. `M` turns on sound (off by default, WebAudio, no files): water, a chime
  on start, a clonk on stop, a thud when a container lands. `K` saves a PNG with
  a strip of real counts, host names, addresses and chat left out, nothing
  uploaded. The harness checks all of it (23 checks).
- **The living harbour.** `portlist --world` (also `-world`, and `W` inside the
  terminal) opens the machine as an isometric harbour in a browser, full screen
  in a Chromium app window, for a second screen. Buildings are services, shaped
  and badged by kind: a lighthouse for SSH, tanks for Postgres, MySQL and Mongo,
  a dome for local models, a mast for MCP, an onion tower for Tor. The gate opens
  only on a verified connection; a bare 0.0.0.0 bind is an amber lamp. Agents
  are robots, and one that exits leaves a bulb over what it left running.
  Coding sessions light the harbour master's windows. The ship is this machine:
  memory is its cargo, load its crane speed, a full disk clutters the yard.
- **Five pets with jobs** (guard, inspector, janitor, mechanic, courier). Each
  takes the most important fact its role cares about, walks there, observes and
  reacts, and says why with the evidence when clicked. Pets that look at the
  same thing talk about it, only in facts.
- **Events between scans**, numbered and served from one differ: started,
  stopped, restarted (identity kept), flapping, exposure opened and closed,
  stopped answering and recovered, origin found, attention created and resolved,
  shared port, agent and session arrived and left, container started, stopped
  and failed. The first snapshot produces none.
- **The lighthouse, the system quarter, the sky.** SSH gets a headland
  lighthouse that is dark when nothing listens and lit when anything does. The
  services portlist files as system were being dropped from the world entirely,
  AirPlay on all interfaces included; they now stand as small sheds, drawn and
  never counted. A horizon, stars, clouds, a distant town, the sun and a moon at
  its real phase moving with the clock, moonlight on the water, whitecaps, surf,
  buoys, ship wakes, and street lamps after dark.
- **Real logos.** 68 marks from Simple Icons (CC0) vendored into the page: the
  service's own on the wall, and chips on the sign for its runtime (read from
  the process) and framework (read from the project's package.json or
  requirements). Agents wear theirs; the ship flies the OS's. A first-visit card
  explains the harbour once.
- **Replay, other machines, keyboard access, phone panel, a real gate.** A
  scrubber rebuilds the harbour at any recorded moment (listeners and exposure
  only, and it says so). Machines that report in to a fleet store appear as harbours on
  the horizon, dark once silent. A skip link leads to a list of everything,
  keyboard-reachable, opening the same inspectors. The phone gets a one-line
  machine panel. The entrance is a two-lane checkpoint with a barrier per lane
  and an EXT OPEN/CLOSED panel; trucks queue and use their own lanes, and
  feeder ships wait for the berth.
- **Checked in a real browser, in CI.** `tools/worldcheck/run.py` drives the
  page with a scripted machine and fails on any overlap, jump, off-road vehicle,
  grounded boat, wet pet, stale entity, dead inspector or console error. The car
  park now lets same-side moves run together; only lane-crossing moves wait.
- **Highway, toll plaza, traffic light, forklift, dormant agents, clock.** The
  road off the island is a six-lane highway with a three-by-three toll plaza
  and a live gantry sign; the car park has a signalled exit and a one-car
  aisle; a forklift works where services are in use; an agent that exited
  leaves its robot, powered down, at the services it started; the machine panel
  shows the time beside the uptime. Names (`*.localhost`), stdio MCP servers
  and the scanner's own footprint now come through `/api/world` from data the
  scan already holds. In-page checks (truth, physics, burst, layout, fps) are in
  `tools/worldcheck/`.
- **Physics and a lived-in outside.** Boats shuttle to SSH and database
  islands from quay jetties on smooth curves at their own capped pace; cars
  have wheels, accelerate, brake, queue and use a two-lane car park; nothing
  drives on water or sails through a pier. A groundskeeper sweeps old
  foundations. Street lamps line the causeway and car park; trees, a bench, a
  bus shelter and a pay booth sit outside the fence. 99 real marks now (Chrome,
  Gemini, Docker, Elasticsearch, MongoDB and more) on cars, agents and islands.
  The frame rate went from 35 back to about 52 fps by caching the vignette and
  painting only the visible sea and sky.
- **SSH, both directions, and the traffic.** The lighthouse is now about
  sessions coming in: dark with no SSH server, a steady lamp while one listens,
  full beam and a big ship moored while someone is logged in. Sessions going
  out are islands on the horizon with a boat on the route, labelled at every
  zoom. Every other outbound connection is a car in a lot outside the gate. All
  three come from the scan's existing connection table and endpoint grouping.
- **Built like a harbour**: sea walls with coping and surf on every edge that
  meets water, a landward security fence with the gate as its only opening, a
  parapet on the south wall, barriers where roads end, and a causeway to the
  mainland. The **customs house** by the gate is the firewall (on, off,
  stealth), read from the host.
- **One scanner per process**: `/api/world` never adds a scan loop where one
  already runs (a server that already scans, the terminal's `W`); only
  standalone `portlist --world` keeps its own. A server with `/world` open
  measured ~3% of one core, 3 threads.
- **Attention counts places, not reasons.**
- **Outbound SSH sessions** appear as boats off the lighthouse, read from the
  ssh client process and its connection, with an event card when one opens or
  closes. An SSH client holds no listening socket, so before this a session to
  another machine was invisible in the harbour.
- **Smoother**: the corner log adds, fades and removes each row once instead of
  rebuilding every second; the inspector only redraws when its content changes;
  the machine panel updates in place. Gulls glide with occasional wing beats.
- **The machine panel**: host, chip, uptime, processes, CPU with load average,
  memory with swap, disk and network, with sparklines of the samples received.
  The ship's funnel now smokes with CPU load.
- **Cheaper to watch**: a scan costs a third less (MCP command-line matching is
  cached per command line), and the world rescans every 2 s only while things
  are changing, every 4 s otherwise. Server: ~2.6% of one core, 46 MB, 5 ms per
  answer, measured.
- **A calmer, clearer screen.** Signs in screen space with collision avoidance
  and zoom-aware detail; one event card at a time instead of toasts; pills only
  for states that have members; icon-only tools that fade when idle; a compact
  inspector that slides in and keeps its scroll; eased wheel zoom, drag inertia
  and eased focus; power-on floor by floor; pets and workers still until
  something happens. Brand look-alike emblems were removed: a service shows its
  real logo or a generic mark, never an imitation. The sea lost its long
  diagonal stroke lines for short glints and slow swells, and the lighthouse
  stands on a rocky outcrop.
- **About three seconds from a change to the page**, down from six to nine: the
  scan runs back to back while a world page is watching. Arrivals and departures
  are eased rather than switched.
- `plcore/world.py` (the semantic engine), `plcore/worldserve.py` (loopback,
  Host-checked, keyed, read-only), `plcore/data/world.html` (the renderer, no
  dependencies), `docs/WORLD.md`, and `tests/test_world.py` (19 tests).

## 1.2 - 2026-09-17

### Added

- **The sessions view answers "which of these can I close?"** Open sessions are
  grouped first, with a line saying how many there are, how many tokens they are
  carrying between them and how long the oldest has gone untouched; everything
  under them is a transcript with no process behind it. Ordering the whole list
  by recency buried the only rows that could be acted on.
- **A bar beside each context figure**, scaled to the biggest session on this
  machine and to nothing else. A transcript records the tokens a turn carried
  and never the model's limit, so no percentage of a context window is printed:
  that number would have to be invented.
- **A picture can be chosen from inside vibe mode, and so can how it is drawn.**
  Drop PNGs into `~/.portlist/backgrounds/` and `g` walks one ring covering
  both: none, each picture as the terminal's own image, then as characters, then
  none. `--vibe-bg` meant knowing a path and restarting, which is a setting
  rather than something anybody uses twice. Pressing `g` with nothing there
  creates the folder and says so.
- **The picture itself, on a terminal that can take one**, confirmed working on
  Ghostty. kitty, Ghostty,
  WezTerm and Konsole are handed the PNG and draw it behind the text at `z=-1`,
  the one arrangement where a background sits behind the readings rather than
  over them. iTerm2's inline images and sixel occupy cells and would cover the
  numbers, so they are not used. On every other terminal the image steps are not
  in the ring at all rather than being offered and doing nothing, and nothing is
  written unless the terminal has said it speaks the protocol.
- **`b` goes to 100.** It stopped at 60 on the grounds that past there the
  picture wins and the numbers stop being readable. Both true, and not the
  dial's call: this is an ambient screen.
- **One background strength for every scene.** Each scene used to scale the
  picture down by its own factor, so 60 per cent looked like four different
  things depending on which scene had come round and the quiet scenes looked
  broken beside the loud ones. The margin is what keeps the picture off the
  text, so the per-scene dimming was solving that twice and creating a new
  problem doing it.
- **The room scene shows your picture when you have set one.** It ships a plate
  so it is a scene at all, but the one scene built around a photograph was the
  one place your own photograph was ignored, which is backwards.
- **A seventh vibe scene, `room`.** It ships its own plate, drawn as characters
  by the same decoder a `--vibe-bg` picture goes through, with what is
  listening, what is reachable off this box and how many agent sessions are open
  placed where the picture is dark. It is the one scene that carries its own
  background and ignores yours, the way the grid scene carries its own tiles.
  `tools/gen_vibe_bg.py` bakes the plate down to 27 KB of 8-bit greyscale with
  `zlib` and `struct`, so the wheel gains a picture and no dependency.

### Fixed

- **Windows no longer crashes on startup.** The dashboard died on its first
  draw with `TypeError: must be real number, not NoneType`. Windows has no load
  average and the platform said so with three `None`s, but a three-element list
  is truthy, so every guard that asks "is there a load reading" passed and the
  formatting walked into a `None`. The platform now reports an empty list, and
  the dashboard, the system view and vibe mode each drop what a platform cannot
  measure, so a reading that does not exist cannot take a screen down from
  either end.

- **`A` toggles what it reads as.** It said auto and toggled whether vibe mode
  drifted in after thirty idle seconds, while the scene changing by itself was
  driven only by the speed setting and had no key at all. `A` is now auto scene
  switching, which is the thing somebody watching the screen wants to stop, and
  `n` still steps by hand. Drifting in on its own keeps its stored value, carried
  over rather than silently reassigned.
- **`A` is finally printed on the screen it belongs to.** It has always toggled
  whether vibe mode arrives on its own after thirty idle seconds, and it was in
  the key table in the docs, but the footer never listed it: a key you can only
  find by reading the source is not a key anybody has.
- **A narrow terminal gets the keys too.** The footer hint was drawn only when
  the whole sentence fit, so below about a hundred columns vibe mode showed no
  keys at all, which is the width where guessing them is hardest. It now
  shortens instead of disappearing.
- **`close it` no longer prints a `kill` it cannot stand behind.** When several
  agents share a directory the session cannot be matched to one of them from
  outside, and the detail pane was still printing `kill <first pid>`. It now
  says why it will not choose. A command that might close the wrong window is
  worse than no command.
- **One long field can no longer eat the detail pane.** A first prompt of three
  thousand words filled it and pushed out where the session actually got to,
  which is the half that decides whether to keep it. Every wrapped field now has
  a line budget and elides.
- **A failing shipped plate no longer clears a background you set.** Every
  failure path emptied `bg`, which is right for a file you named and wrong for
  the file that ships: a broken install threw away your picture instead of its
  own.

## 1.1 - 2026-08-27

### Added

- **A picture behind vibe mode**, off until asked for:
  `portlist --vibe-bg thing.png`, then `b` to tune it live through 0, 15, 30, 45
  and 60 per cent. PNG only: `plcore/imgmap.py` decodes one with `zlib` and
  `struct` and returns a density map, one value per terminal cell, with the 1:2
  aspect of a character already accounted for so a circle stays a circle. A JPEG
  is reported as unsupported rather than half-read.
  Opacity means density, not alpha, and the picture is painted into the negative
  space after the scene has drawn, keeping clear of anything already there:
  filling every empty cell put stipple in the gaps between words and made the
  text look dirty. Each scene sets how much it carries, so the network scene
  takes 40 per cent of whatever you choose and the cockpit takes all of it.
  Sixty is the ceiling because past that the picture wins.
- **The agents view shows what each session has already started**, from the
  ledger: launches that are since gone, the count on record, and how long ago
  the first and most recent were. A session that has exited still has a history,
  and that is usually the question being asked of it.
- **A light picture is flipped before it is drawn as a background.** A
  paper-white plate filled the terminal with characters where the paper was and
  left the drawing blank; `imgmap.cells` now inverts an image whose average is
  bright, so what shows is the ink, and `B` cycles that guess between `auto`,
  `on` and `off` against the picture in front of you.
- **A sixth vibe scene, `grid`**: every listening service as a tile, so a machine
  with four services and one with forty look different from across a room.

- **The graph, on `9`**, and the tenth view. Who started what, where it runs and
  what it exposes - started by, project, process, port, reachable from - drawn as
  a tree with continuous rules, because sixteen free-floating nodes in a terminal
  is not a diagram. A parent is printed once and carried down with
  a rule, so the sharing is what you see first. Columns drop as the terminal
  narrows and it becomes headed groups below 100 columns.

- **The dashboard, on `0`, and it is now where portlist opens.** Four cards
  (machine, exposure, agents, containers), the listening table, the selected
  service with its origin and its risk broken into the reasons that made it, the
  activity feed, the sparklines and a status line. The risk score is itemised
  rather than asserted, and "unknown origin" gets its own count so that nothing
  quietly inherits a label from whatever owns the port now.
- **The header, the tab bar and the footer lost their inverse-white bars.** A
  solid strip is the loudest thing a terminal can draw and it was the first
  thing your eye hit. The name is coloured, the counts carry their own tone, a
  hairline rule separates the chrome from the content, and the active tab is
  marked and underlined rather than filled in.
- **The dashboard cards are framed** in the same outline the system view uses.
  The load average rides in the machine frame's top rule rather than costing a
  row, and the table below stays unframed, because the structure is worth having
  around the summary and not around the thing you actually read.
- **A lifetime column** on wide terminals, where the space to the right of RISK
  was dead: how long each service has been listening, on one log axis shared by
  every row and normalised across the range actually on screen. A per-row wave
  of measured use was tried first and thrown away - sixteen rows rippling at
  nearly the same amplitude read as noise, and it was a third connection metric
  on a screen that already had two.
- **Ambient waves.** One travelling pattern under every card and across the top
  of the table, with **amplitude and speed taken from the metric**: exposure
  rides on the share reachable off-box, agents on the share an agent started,
  the band above the table on the share measured busy right now. Quiet ripples
  slowly and shallowly, busy moves faster and taller, and anything unmeasured
  draws a flat line of dots rather than a wave at zero, because a flat wave
  still reads as a measurement of zero. The wave is a sine, not a history, and
  is never drawn where a history belongs: the sparklines keep plotting samples.
- **Live dials on the dashboard**: three twelve-segment rings for CPU, memory
  and disk, easing round rather than jumping, with the leading segment pulsing.
  An unmeasured reading draws an empty ring instead of resting at zero.
- **`Tab` moves to the next view**, in the same order as the number keys, and
  `shift-Tab` goes back. `h` and `l` move between the dashboard's panes, and `j`
  and `k` move inside whichever has focus.
- **The dashboard animates**: dials, state dots, risk diamonds, the selected row
  and the newest event, plus a badge on any service that starts or stops
  listening while you are watching. `a` stops all of it, after which the screen
  repaints only when the data changes.
- **Vibe mode.** `V`, or leave it alone for thirty seconds and it arrives on its
  own: the list gives way to an ambient screen worth leaving open on a second
  monitor. Five scenes rotate (cockpit, machine, network, agents, activity),
  five themes,
  four speeds, all remembered in `~/.portlist/vibe.json`. Any key brings the
  list straight back, and that key is swallowed rather than acted on, so
  returning never also opens or filters something.

  Everything on it is driven by a real measurement. A service dot pulses because
  that service was measured busy in the last minute; a particle crosses an edge
  because a loopback connection between those two ports was observed. Where
  nothing has been measured the screen says so and sits still, because inventing
  motion would make the prettiest part of the program the one lying to you.
  Turning animation off with `a` also stops vibe mode arriving by itself.
  A service that starts listening while you watch is marked NEW for a few
  seconds and one that stops is reported, both from the real scan diff; the
  first frame marks nothing, because everything is new to the screen the moment
  it opens and none of it is new to the machine.
- **View 8, system.** The machine itself: load, memory and disk as meters,
  uptime, processes, the CPU and memory sparklines, the addresses this host
  answers on, the firewall and SSH state, and what those twelve listening ports
  add up to. Boxed layout that collapses to one column on a narrow terminal.
- **Animation.** Sparklines fill a sample a second, meters sweep to a new value
  instead of teleporting, and one character in the header keeps moving so a pane
  you left open an hour ago reads as live rather than frozen. `a` turns it off
  for good. It costs about half a percent of one core; the five-second scan
  dominates, not the frames.
- **Six session parsers**, up from two: Claude Code, Codex, GitHub Copilot CLI
  (its own SQLite store, opened read-only), VS Code chat, Cursor (a VS Code fork,
  so one parser covers both) and Gemini CLI. Plus which plan each tool is signed
  in under.
- **Install routes**: Homebrew tap, winget manifests, `pipx install portlist`,
  and a `curl | sh` installer that writes only to `~/.local`.
- `plcore/app.py` and `python3 -m plcore`, so a packaged install has a real
  entry point. `python3 portlist.py` still works from a clone.
- Documentation site at [mr-hunt-007.github.io/portlist](https://mr-hunt-007.github.io/portlist/).

### Fixed

- **The service column header was drawn over every view**, including the ones
  that draw their own. On the sessions view the two sets of labels interleaved
  into `PROJECTBLE  RISKCONTEXTAR`; on the new system view it left one stray
  letter between two boxes.
- **The header ran under the clock** at 80 columns and read `need atteOt22:02`.
  Clauses are now dropped whole from the right, because a truncated fact is not
  a shorter fact.
- **The footer keys collided with the status text** on a narrow terminal.
- **Eight tabs did not fit an 80-column terminal.** The counts go first, then
  the labels, down to numbers with only the current view named. Four-letter
  stubs like `Sess` and `Syst` are not names.
- The splash screen spelled the wrong name in ASCII art, left over from the
  project this was extracted from.

## 1.0 - 2026-08-26

First release: the terminal UI as a standalone program, with no web surface at
all.

- Seven views over one scan: services, exposed, attention, leftovers, agents,
  containers, sessions.
- Provenance that survives a restart, from a launch ledger written the first
  time a service is seen and never rewritten.
- Reachability checked by connecting to this machine's real address, not by
  reading a bind string.
- Use measured over time rather than inferred from uptime.
- A free-port suggestion that avoids the crowded bands and is stable per project.
- `O` opens a port in a browser. `f` suggests a free one. Nothing stops anything:
  the detail pane prints the command and you run it.
