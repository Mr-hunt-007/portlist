# Security

## What portlist reads

Process tables, listening sockets, `/proc` or `ps`, the container engine if one
answers, and the transcript stores your coding agents already write. All of it
on this machine, all of it as you.

## What portlist sends

Nothing. There is no server, no telemetry, no update check and no network code
beyond two local operations, both worth being exact about:

- it connects **outward** to ports on this machine to see what answers;
- it binds a candidate port for a moment to confirm it is free, then closes it.

Neither calls `listen()`. portlist has no port of its own, so a tool for
watching what is listening never adds to the list.

## Session transcripts

Views 7 reads what Claude Code, Codex, Copilot CLI, VS Code, Cursor and Gemini
write locally. Prompts stay on the machine: there is nowhere for them to go.
Account details are narrower than the file they come from - the plan and the
organisation, never the address or the account id, and values are scrubbed as
well as field names, because an organisation name can itself contain an address.

## What portlist will not do

It never stops, kills or restarts anything. The detail pane prints the command
and you run it. That is deliberate: a tool that both guesses which process is
abandoned and can end it will eventually end the wrong one.

## Reporting a vulnerability

Open an issue at https://github.com/Mr-hunt-007/portlist/issues. If it is
sensitive, say so in the issue without the detail and it can move somewhere
private from there.
