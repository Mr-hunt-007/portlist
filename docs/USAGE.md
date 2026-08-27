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

Under each card, and in a band across the top of the table, runs the same
travelling wave. Its **amplitude and speed are the current level**, not a
history: the exposure wave rides on how much of what is listening can be reached
off the machine, the agents wave on how much of it an agent started, the band
above the table on how much is being used right now. A quiet reading ripples
slowly and shallowly, a busy one moves faster and taller. Where there is nothing
to measure, such as a container engine that did not answer, it draws a flat line
of dots instead: a wave at zero amplitude still reads as a measurement of zero.

Histories are plotted separately, in the sparklines, from real samples. The wave
is never used where a history belongs.

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

## The ten views

Every view is a different question asked of one scan. Switching views never
rescans and never moves your selection to a different service.

| key | view | what it answers |
|-----|------|-----------------|
| `0` | dashboard | everything at once, and where it opens |
| `1` | services | everything listening, with who started it |
| `2` | exposed | reachable from beyond this machine |
| `3` | attention | critical, high and medium risk |
| `4` | leftovers | looks abandoned, with the measurements behind the guess |
| `5` | agents | grouped by the agent, editor or terminal that started it, with what each one has started before |
| `6` | containers | by compose project, and the host ports they hold |
| `7` | sessions | coding-agent sessions, what they were about, context used |
| `8` | system | this machine: load, memory, disks, network, exposure |
| `9` | graph | the same graph the web dashboard draws, as layered columns |

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

## The graph

`9`. The same graph the web dashboard draws, as layered columns: **started by**,
**project**, **process**, **port**, **reachable from**, with the same edge names
(`started work in`, `runs`, `listens`, `confirmed on`). One line is one service.

A parent is printed once and carried down with a rule, so the sharing is the
thing you see first: eleven services under one agent session is a fact about
your machine that a flat list hides.

`j` and `k` walk it in graph order rather than port order, and `enter` and `O`
work on the selected row exactly as they do in the list.

The columns are dropped as the terminal narrows - the process first, because a
pid squeezed to `Python pid 681` is worse than no pid, and the detail pane has
it in full - and below 100 columns the graph is drawn as headed groups instead.

## Vibe mode

`V`, or leave it alone for thirty seconds and it arrives by itself. The list
gives way to an ambient screen worth leaving open on a second monitor. Any key
brings the list straight back, and that key is swallowed rather than acted on,
so returning never also opens, filters or moves anything.

Seven scenes rotate:

| | |
|---|---|
| **cockpit** | everything at once: meters, the services worth looking at first, and the host strip |
| **grid** | every listening service as a tile, so four services and forty look different from across a room |
| **machine** | load, memory and disk as meters, the CPU and memory waves, and what the machine adds up to |
| **network** | the host with its services around it, and a particle travelling every edge where a loopback connection was actually observed |
| **agents** | each agent, editor or terminal, and the services it started |
| **activity** | what has really happened lately, newest first, freshest pulsing |
| **room** | a plate that ships with the program, drawn as characters, with what is listening, what is off this box and how many agent sessions are open placed in its dark corners |

Inside vibe mode, four keys do not exit:

| | |
|---|---|
| `t` | theme: observatory, neon, terminal, aurora, minimal |
| `s` | speed: static, slow, medium, cinematic |
| `n` | next scene now |
| `A` | auto: whether the scene changes by itself. `n` still steps it by hand |
| `g` | the background picture: none, then each PNG in `~/.portlist/backgrounds/` as the terminal's own image and then as characters, then none again |
| `b` | how strongly a character background shows: 0, 20, 40, 60, 80, 100 |
| `B` | which end of that picture becomes ink: `auto`, `on`, `off` |

Choices are remembered in `~/.portlist/vibe.json`.

### A picture behind it

Off until you ask for it. Two ways, and the second is the one you will use
twice:

```sh
portlist --vibe-bg ~/pictures/thing.png     # name the file once, on the way in
```

or drop PNGs into `~/.portlist/backgrounds/` and press **`g`** inside vibe mode
to walk them. The footer names what is showing, so choosing is done by looking
rather than by remembering a path. Pressing `g` with nothing there creates the
folder and says so.

`g` walks **both** which picture and how it is drawn:

```
none  ->  room.png as an image  ->  room.png as characters  ->  none
```

**As an image** means the terminal is shown the file and draws it itself, behind
the text. That needs a terminal that speaks kitty's graphics protocol - kitty,
Ghostty, WezTerm and Konsole - because that protocol has a z-index, and `z=-1`
is the only arrangement where a picture sits behind the readings instead of on
top of them. iTerm2's inline images and sixel both occupy cells, so a picture
drawn that way would cover the numbers, and a screen whose numbers are hidden by
decoration is worse than one with no decoration.

On every other terminal the image steps are simply **not in the ring**, because
a state that does nothing is worse than one fewer state. You get the character
rendering, which is not a consolation prize: it is what this program was already
doing, and it works over ssh, in tmux, and on a machine with no graphics at all.
Set `PORTLIST_NO_GRAPHICS=1` to force that everywhere.

**PNG only, and that is a real limit rather than an oversight.** A PNG is `zlib`
and a few row filters, which the standard library already has; a JPEG needs a
DCT and a Huffman decoder, which is several hundred lines of the wrong kind of
code for a port tool. A JPEG is reported as unsupported rather than half-read.

`b` inside vibe mode moves it through 0, 15, 30, 45 and 60 per cent and back to
off, so it can be tuned while looking at it rather than by editing JSON. Sixty
is the ceiling on purpose: past that the picture wins and the numbers stop being
readable, and a dial should not offer a value that makes the screen worse.

"Opacity" here means **density**, not alpha. A terminal cannot half-draw a
character, so a fainter picture is a sparser stipple in the dimmest colour the
theme has. Two things follow, both deliberate:

- **It is painted into the negative space only.** The scene draws first, then
  the picture fills what is left, staying a few cells clear of anything already
  on screen. Drawn underneath, it came through the gaps between words and every
  row of text looked speckled.
- **Each scene decides how much it can carry.** The cockpit and machine scenes
  are mostly air and take it at full strength; the network scene is already
  lines and nodes on empty space, so it gets 40 per cent of whatever you set.
- **One scene is exempt.** `room` ships its own plate and draws it at the cap,
  because there is the picture and there is nothing else; a picture of yours
  decorates the other six and is ignored there. `b` and `B` do nothing in it,
  and the footer stops offering them rather than showing a dial that is inert.

A picture that is mostly light is **flipped** before it is drawn, so what shows
is the ink somebody drew rather than the paper it sits on. The first time a
paper-white plate was used as a background the terminal filled with a solid wall
of characters where the paper was and left the drawing blank. The guess reads
the picture's average brightness and is occasionally wrong about it, so `B`
cycles between `auto`, `on` and `off` while the picture is in front of you, the
same way `b` tunes the density. Both land in `vibe.json`.

It costs about half a percent of one core, measured, and nothing when it is off.

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
