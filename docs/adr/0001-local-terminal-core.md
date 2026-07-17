# ADR-0001: Local tmux is the only Terminal implementation

- Status: accepted
- Date: 2026-07-17

## Context

Earlier Remote Runner versions combined remote tmux over per-operation SSH, local tmux wrapping an
interactive SSH PTY, a piped Windows PowerShell agent, structured batch execution, and file transfer
under one Session interface. These implementations did not share terminal semantics, performance,
timestamps, or transcript behavior. The resulting backend branching made the public model harder to
understand than a shell.

## Decision

Remote Runner owns exactly one Terminal implementation: a local tmux pane with a recorder installed
before the real shell starts. SSH and every remote persistence mechanism are visible shell actions.
Per-target automation is an Instance bootstrap hook above the Session Interface.

V4 is intentionally incompatible. All legacy backend, machine, batch, file, run, artifact,
seed-runner, and state compatibility code is deleted.

## Consequences

- Agents and humans share the same pane and raw transcript.
- Input and observation behavior is identical for local and SSH-reached shells.
- Windows is not a host platform, but may be an SSH target.
- RR does not guarantee remote shell/process survival after SSH disconnect.
- Supporting a future second Terminal implementation requires proving identical semantics before
  introducing an Adapter seam.
