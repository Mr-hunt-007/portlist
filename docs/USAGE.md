# Usage

```sh
portlist
```

That is the whole command line. Everything else is keys.

## The dashboard

`0`, and where portlist opens: four cards (machine, exposure, agents,
containers), the listening table, the selected service with its origin and the
risk broken into the reasons that made it, the activity feed, the CPU and memory
sparklines, and a status line.

**Tab** moves to the next view and **shift-Tab** goes back, in the same order as
the number keys. **`h`** and **`l`**, or the left and right arrows, move between
the dashboard's two panes, and `j`/`k` move inside whichever has focus, so the
same keys scroll the table or the activity feed depending on where you are.

The machine is drawn as three live dials when the terminal is at least 118
columns wide, and as meters below that. Each ring is twelve segments, the
leading one pulses, and the ring eases round when a reading changes rather than
jumping. A value that cannot be measured draws an empty ring rather than a
zero.

Two numbers there are worth reading carefully. **NEEDS WORK** counts critical and
high risk, and every point is itemised in the pane below. **UNKNOWN ORIGIN**
counts services that were already listening before portlist first looked: their
origin is not guessed, and they are counted separately so a stale process does
not inherit a repository label from whatever owns the port now.

## The nine views

Every view is a different question asked of one scan. Switching views never
rescans and never moves your selection to a different service.

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

Views 5 and 6 group rather than filter, so their headers are not selectable.

## Keys

| | |
|---|---|
| `j` `k`, arrows | move |
| `enter`, `o` | detail pane |
| `O` | open the port in a browser |
| `/` | search, `enter` keeps it, `esc` clears it |
| `f` | suggest a port that is free |
| `a` | animation on the system view |
| `V` | vibe mode |
| `tab` `shift-tab` | the next view, in the same order as the number keys |
| `h` `l`, left, right | move between the dashboard's panes |
| `r` | rescan now |
| `?` | keys |
| `q` | quit |

`ctrl+enter` opens a port too, where the terminal sends it. macOS never delivers
`cmd+enter` to a terminal program - the terminal app keeps it - so `O` is the
binding that always works.

## The columns

**PORT** the port, and the bind scope behind it. Two processes can hold the same
port number with different scopes, so a row is a service on a port, not a port.

**SERVICE** what it is, named from the command, the port and the project rather
than from the port number alone.

**PROJECT** the git root the process was started from, never a directory
inherited from whatever owns the port now.

**REACHABLE** checked by connecting to this machine's real address, not by
reading a bind string. `Localhost only`, `All interfaces`, or what was actually
found.

**RISK** a score and a band. The detail pane shows every reason that fed it.

**STARTED BY** the agent, editor, terminal, service manager or container that
started it, and how long ago. `unattributed` when portlist cannot tell, which is
a state it renders rather than a blank it hides.

## The detail pane

`enter` opens it. It carries the full command line, the working directory, the
project, the launch record, what the risk score was made of, what uses this
service and what it uses, and the command to stop it.

It prints that command. It does not run it. There is no kill key.

## The system view

`8`. Load, memory and disk as meters; uptime and process count; sparklines for
CPU and memory filled one sample a second; the addresses this host answers on;
the firewall and SSH state; and what the listening ports add up to.

The sparklines leave a gap where nothing was measured rather than drawing a
zero, and a rate that needs two samples says `no rate yet` until it has them.

`a` turns the animation off if you would rather it sat still. It costs about
half a percent of one core.

## Vibe mode

`V`, or leave it alone for thirty seconds and it arrives by itself. The list
gives way to an ambient screen worth leaving open on a second monitor. Any key
brings the list straight back, and that key is swallowed rather than acted on,
so returning never also opens, filters or moves anything.

Five scenes rotate:

| | |
|---|---|
| **cockpit** | everything at once: meters, the services worth looking at first, and the host strip |
| **machine** | load, memory and disk as meters, the CPU and memory waves, and what the machine adds up to |
| **network** | the host with its services around it, and a particle travelling every edge where a loopback connection was actually observed |
| **agents** | each agent, editor or terminal, and the services it started |
| **activity** | what has really happened lately, newest first, freshest pulsing |

Inside vibe mode, four keys do not exit:

| | |
|---|---|
| `t` | theme: observatory, neon, terminal, aurora, minimal |
| `s` | speed: static, slow, medium, cinematic |
| `n` | next scene now |
| `A` | whether it may arrive on its own after thirty idle seconds |

Choices are remembered in `~/.portlist/vibe.json`.

When a service really appears while you are watching, it is marked **NEW** for
a few seconds; when one stops listening, that is reported too. The first frame
marks nothing at all, because everything is new to the screen the moment it
opens and none of it is new to the machine.

**Nothing on this screen moves unless something was measured.** A service dot
pulses because that service was measured busy in the last minute, not because
pulsing looks good. A particle crosses an edge because a connection between
those two local ports was observed. Where nothing has been measured yet, the
screen says so and sits still: "no connections observed between them yet" is a
real answer, and inventing motion there would make the prettiest part of the
program the one lying to you.

Turning animation off with `a` also stops vibe mode arriving on its own. Asking
for a still screen and then being given a moving one is not a feature.

The whole program sits near two percent of one core with vibe running, most of
which is the five-second scan it does anyway.

## Searching

`/` filters on port, service, command, project, directory and starter at once.
It is a filter over the scan, so it works the same in every view.

## Data and privacy

`~/.portlist/` holds the launch ledger, use history and recipe book. Override
with `--data-dir` or `PORTLIST_DATA`.

Session transcripts are read from your agents' own local stores and never leave
the machine. portlist has no network code beyond connecting to this host.
