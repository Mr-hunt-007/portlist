# Changelog

Dates are the day the work landed. Versions follow [semver](https://semver.org/).

## 1.1 - 2026-08-27

### Added

- **Vibe mode.** `V`, or leave it alone for thirty seconds and it arrives on its
  own: the list gives way to an ambient screen worth leaving open on a second
  monitor. Four scenes rotate (machine, network, agents, activity), five themes,
  four speeds, all remembered in `~/.portlist/vibe.json`. Any key brings the
  list straight back, and that key is swallowed rather than acted on, so
  returning never also opens or filters something.

  Everything on it is driven by a real measurement. A service dot pulses because
  that service was measured busy in the last minute; a particle crosses an edge
  because a loopback connection between those two ports was observed. Where
  nothing has been measured the screen says so and sits still, because inventing
  motion would make the prettiest part of the program the one lying to you.
  Turning animation off with `a` also stops vibe mode arriving by itself.
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
- The splash screen in portlist spelled `PORTBOARD` in ASCII art, left over from
  the copy it was made from.

## 1.0 - 2026-08-26

First release: the terminal UI, extracted from Portboard as a standalone program
with no web surface at all.

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
