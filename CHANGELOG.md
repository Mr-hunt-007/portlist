# Changelog

Dates are the day the work landed. Versions follow [semver](https://semver.org/).

## 1.1 - 2026-08-27

### Added

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
