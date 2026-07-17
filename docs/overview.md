# Remote Runner Overview

## Definition

Remote Runner is a local persistent-terminal CLI for agents and humans.

```text
local tmux pane -> real shell -> raw append-only transcript -> explicit operation/query interface
```

It solves one problem: give an Agent the same clear shell environment a human understands. The
Agent sends a line or key, observes terminal output, reads state when needed, and decides what to do
next. Remote Runner does not interpret commands or pretend terminal interaction is batch RPC.

## Product Boundary

Remote Runner owns:

- local tmux Session creation and lifecycle;
- exact line and named-key input;
- raw `pipe-pane` transcript capture;
- byte-range `read`, bounded `tail`, and transparent state;
- human attach coordinates;
- optional per-Instance bootstrap hooks using the same terminal Interface.

Remote Runner does not own:

- SSH semantics, remote OS detection, prompt parsing, busy/completion inference, exit codes, jobs,
  file transfer, artifacts, remote tmux, schedulers, or remote process persistence;
- Windows as a host platform;
- old Remote Runner/seed-runner state or compatibility behavior.

SSH, `su`, `cd`, environment setup, remote tmux, Slurm, `nohup`, `scp`, and similar actions are
ordinary visible shell operations chosen by the Agent or by an inspectable bootstrap hook.

## Domain Terms

- **Session**: one persistent local shell hosted by one tmux pane. It has an immutable UUID, an
  active human-readable name, lifecycle state, and one transcript.
- **Session name**: the public active/lost lookup key. It is unique while reserved and reusable after
  destroy.
- **Session ID**: an immutable UUID used for state and historical lookup. It is never reused.
- **Terminal**: the local tmux pane implementing line/key input, attach, existence, and destruction.
- **Transcript**: raw append-only bytes emitted by the pane. It records visible echo and output, not
  no-echo input or a reconstructed screen.
- **Instance**: a named bootstrap profile pointing to one inspectable Python hook. It is not a
  backend or remote machine object.
- **Bootstrap**: synchronous, exclusive terminal automation that obtains a desired shell through the
  normal Session Interface. The hook owns all prompt and login decisions.

## Modules

1. **Session Module**: identity, lifecycle, name resolution, bootstrap orchestration, and the public
   Interface.
2. **tmux Terminal Module**: one local tmux implementation for creating a pane, sending input,
   attaching, probing existence, and destroying it.
3. **State Module**: versioned JSON state, UUID-keyed history, locks, transcript paths, and direct
   observations.

There is deliberately no backend seam: only one Terminal implementation exists. Introducing a
second implementation requires first proving that it can satisfy the same terminal semantics.

## Status and Observation

Session lifecycle is limited to facts RR can know:

```text
active / lost / destroyed
```

RR does not expose `busy`, `command_completed`, or `prompt_ready`. In a local tmux pane running SSH,
tmux only sees the `ssh` process and cannot know the remote shell state. The Agent inspects the raw
tail for the visible prompt, just as a human does.

`session show` reports direct facts such as the last RR-mediated input time, last transcript write
time, elapsed milliseconds since each, transcript end cursor, path, and tmux name. `read` and `tail`
remain focused on transcript bytes and cursor positions.

## Compatibility Decision

Local Terminal V4 is a deliberate break. It removes machine, remote-tmux, interactive-SSH backend,
Windows agent, structured exec/background, file, run, artifact, and seed-runner surfaces. Old state
is detected and rejected without mutation. Git history is the migration record; runtime
compatibility code is not retained.
