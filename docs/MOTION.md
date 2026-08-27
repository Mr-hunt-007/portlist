# Motion

A design language for the dashboard, written before the code that implements it.

The dashboard is a living map of one machine. Everything that moves on it is a
measurement, and the shape of the movement tells you which kind of measurement
it is. That is the whole idea: **the data makes the art, and the art is legible
because each kind of data moves in its own way.**

This document is the plan. Some of it is built; the last section says which.

## The rule that constrains every choice below

Motion may be ornament in *shape* but never in *substance*. A thing moves
because something was measured; if nothing was measured, it goes still and says
so. A flat line means "nothing to report" and an empty ring means "not
measured", and neither of those is allowed to look like a reading of zero.

The consequence worth stating plainly: **when the machine is quiet, the
dashboard becomes calm.** It does not invent traffic to look busy. A quiet
machine that looks quiet is the product working.

## The vocabulary

Five primitives. Each one owns a kind of meaning, and nothing else uses it.

### 1. Breath - ambient life, made of density

The idle language. Density oscillates; height never changes. Very low ink, slow
enough that you notice it only when you look for it.

```
      ·····           ····
      ····           ·····
     ·····           ·····
     ·····           ····
     ····           ·····
    ·····           ····
```

Glyph ramp ` ·:∙•`. Amplitude is the reading, and at rest it is barely there.
This is what runs when nothing is happening, everywhere, forever.

### 2. Wave - magnitude, made of height

For quantities that have a level: CPU, memory, disk, the share of services
reachable off-box. Amplitude *and* speed are the reading, so a busy machine is
both taller and faster.

```
  ▃▅▆▇▆▅▃▁  ▁▃▄▆▇▇▅▄▂  ▁▂▄▅▇▇▆▄▃      busy
  ▁▁▁▁▁▁      ▁▁▁▁▁▁     ▁▁▁▁▁▁       quiet
```

It is a sine, not a history. Histories are sparklines, plotted from samples, and
the wave must never be drawn where one belongs.

### 3. Flow - an observed relationship

Particles travelling a path, and **only** where a connection was actually seen
between two local ports. No observation, no particle: the line sits still.

```
  •────────·────────·───────────
  ─•────────·────────·──────────
  ──•────────·────────·─────────

  ──────────────────────────────    nothing observed, so nothing moves
```

Direction carries meaning: the particle travels from the caller to the callee.

### 4. Ripple - a discrete event

Fires once, expands, and is gone. Started, stopped, became reachable, became
exposed, container restarted, a new relationship observed.

```
             ◦
            ◦·◦
           ◦· ·◦
          ◦·   ·◦
         ◦·     ·◦
        ◦·       ·◦
```

Then back to ambient. An event that keeps flashing stops being an event.

### 5. Scan - attention

A slow sweep across one element, and the cheapest primitive here: one cell
changes per frame. It marks the focused pane, and nothing else.

```
  ▏│┆
   ▏│┆
    ▏│┆
```

### And a set of state glyphs

Not motion so much as vocabulary. One character, one state.

| | | |
|---|---|---|
| `◦○◉●◉○` | active | measured busy inside the last minute |
| `○` | idle | watched long enough to know, and not busy |
| `●` | running | listening; not watched long enough to say |
| `◇◆` | critical | scored critical, and the only thing that pulses red |
| `⊗` | stopped | it was here and it is not now |
| `?` | unknown | cannot be read at all |

## What moves how

| what | primitive | what drives it |
|---|---|---|
| CPU, memory, disk | dial + wave | the reading; leading segment pulses |
| services being used | wave, above the table | share measured busy right now |
| reachable off-box | wave, under the card | share of listening that is reachable |
| agent-started work | wave, under the card | share of listening an agent started |
| containers | wave, or flat | count, or flat when the engine did not answer |
| a single service | pulse glyph | its measured state |
| a critical service | slow diamond pulse | its risk band |
| a local dependency | flow | an observed loopback connection |
| an agent and its ports | flow | the ledger's record of what it started |
| something started or stopped | ripple, once | the scan diff |
| the focused pane | scan | where you are |
| a row's lifetime | static bar, per row | how long it has been listening, on one log axis |
| the whole screen, at rest | breath | nothing at all, gently |

## The rules by state

**Idle.** Breath only, everywhere. Amplitude near its floor, period around four
seconds. The screen must never look frozen and must never look busy.

**Active.** The element with the measurement moves; the rest keeps breathing. A
wave's speed rises with its own amplitude, so activity reads as urgency without
anything else changing.

**Transition.** An event ripples once, at most eight frames, then the element
returns to its ambient state within two seconds. No element holds an alarm
state longer than the fact behind it.

**Warning.** Colour changes first, motion second: amber, and the wave keeps its
own amplitude. Nothing new starts moving.

**Critical.** The risk diamond pulses, slowly, on that row only. The rest of the
screen does not react. A dashboard where everything flashes red teaches you to
ignore red.

**Unknown.** Flat. Dots rather than a wave, an empty ring rather than an empty
bar, and the word if there is room. This is the state most systems get wrong by
drawing zero.

**Stopped.** `⊗`, one ripple, and the row leaves on the next scan. It is
reported for as long as the scan diff remembers it, and then it is gone.

## Rhythm

| | |
|---|---|
| breath | one cycle per 4 seconds |
| wave | 0.35 to 2.1 cells per frame, from its own amplitude |
| flow | one cell per frame, so a particle crosses a 30-cell link in a second |
| ripple | 8 frames, once |
| pulse | one step per 3 frames |
| scan | one cell per frame |
| frames | 0.12s while something moves, and nothing at all when it does not |

The frame budget is the honest constraint: curses paints only changed cells, so
the cost of this whole language is a few hundred bytes of terminal writes per
second. `a` stops all of it, and then the screen repaints only when the data
changes.

## Terminal constraints

**60 columns.** Breath and pulses only. Waves are dropped before they become
four cells of noise; the dials become meters.

**80 columns.** Meters, waves under the cards, the band above the table.

**120 columns and up.** Dials, the full card row, flow between services.

**No Unicode.** Every glyph has an ASCII twin: the ramp becomes `.:*#`, the
blocks become `#` and `.`, the ring becomes `o` and `.`. A mojibake frame is
worse than an ASCII one, so the terminal is asked rather than assumed.

**Limited colour.** Motion carries the meaning; colour only reinforces it. Every
state is distinguishable in monochrome, which is also why the state glyphs
differ in shape and not only in hue.

## Screenshot test

Any single frame has to look deliberate. That rules out primitives whose
mid-animation frames are ugly: a wave caught mid-sweep is fine, a spinner caught
between glyphs is not. It is also why breath uses density rather than height -
a still frame of it reads as texture, not as an interrupted animation.

## The wide-terminal column

Past about 150 columns the space to the right of RISK is dead. It carries how
long each service has been listening, on one log axis shared by every row and
normalised across the range actually on screen.

```
UPTIME   minutes ━━━━▸ weeks   (log)
━                                         1h
━━━━━━━━━━                                7h
━━━━━━━━━━━━━━━━━━                        23h
━━━━━━━━━━━━━━━━━━━━━━━━━                 2d
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 29d
```

Two attempts got this wrong, and both failures are instructive. The first drew a
per-row wave of measured use: every row rippled at nearly the same amplitude, so
sixteen rows of near-identical dashes read as noise rather than as data, and it
was a third connection metric on a screen that already had two. The second used
a log axis anchored at zero, where an hour already fills half the bar and
everything from two days to a month lands in the same four cells.

What works is a different question from the rest of the table, on an axis that
spans what is present: the columns to the left say what a service is and how
exposed it is, and this says whether it has been up for weeks or arrived while
you were making coffee. It does not move. Not everything should.

## The backdrop

A picture can sit behind the vibe scenes. It is the one thing on screen that is
**not** a measurement, which is why it is off until asked for, capped at 60 per
cent, and confined to vibe mode. The list views are columns you read; the vibe
scenes are a thing you glance at from across a desk.

Three rules keep it from costing you data:

1. **Density, not alpha.** A terminal cannot half-draw a glyph, so fainter means
   sparser, in the dimmest colour the theme has.
2. **Negative space only.** The scene draws first; the picture fills what is
   left and stays clear of anything already there.
3. **Per scene.** The cockpit is mostly air and takes it whole. The network
   scene is lines on emptiness and takes 40 per cent, because a background
   competes with the thing you are meant to be looking at.

## Chrome

The chrome follows the same restraint as the motion. No inverse-video bars: the
name is coloured, the counts carry their own tone, and a hairline rule separates
the header from the content. The active tab is marked with `▌` and underlined
rather than filled in, because a block of solid colour behind text is hard to
read and harder to screenshot.

The dashboard's summary cards are framed in the same outline the system view
uses. The table below them is not, and that asymmetry is the point: structure
around the summary, nothing in the way of the thing you actually read.

## Built, and not yet built

**Built.** Dials with easing and a pulsing leading segment; waves under every
card and across the table; pulse glyphs per service; the critical diamond; the
scan-diff badges for started and stopped; sparklines from real samples; `a` to
stop everything.

**Not yet built, in the order worth doing it.**

1. **Breath as the ambient layer.** Today the waves carry both the ambient and
   the magnitude job, which is why a quiet machine still shows a row of `▁`.
   Breath separates them: density for life, height for level.
2. **Flow between services**, from `depends_on` and `used_by`. It exists in
   vibe's network scene and belongs on the dashboard.
3. **Ripple on events**, replacing the current `NEW` badge with something that
   fires and settles.
4. **Scan on the focused pane**, replacing the static header highlight.

None of these change what the dashboard says. They change how clearly it says it.
