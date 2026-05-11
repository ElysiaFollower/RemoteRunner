# ADR 0001: Remote Runner Core Must Not Depend on Mounts

## Status

Accepted for the machine/session/file-transfer MVP.

## Context

The current `seed-runner` prototype uses a mount-first workflow built around sshfs, reverse SSH
reachability, tmux, and a synced local directory. That validated the need for a tool-managed remote
execution layer, but it is not a reliable product boundary for Remote Runner.

Many real remote machines are inconvenient or impossible to mount from a local workstation:

- FUSE or sshfs may be unavailable or disallowed.
- The remote machine may not be able to connect back to the local machine.
- Lab, enterprise, or cluster machines often restrict mount permissions.
- Long-lived mounts are brittle across network changes and sleep/resume cycles.
- Mount semantics obscure the true source of state when debugging command output and artifacts.

Remote Runner's core value is a stable local CLI for operating remote machines, not a transparent
filesystem illusion.

## Decision

Remote Runner's target architecture will not use mounting as a core abstraction.

The core MVP will use:

- local state under `~/.remote-runner/`
- explicit machine configuration and connection diagnostics
- explicit session records with remote working directories
- direct remote command execution through SSH or an equivalent backend
- explicit file transfer commands for put/get/list
- local manifests for commands, logs, transfers, and artifacts

The `seed-runner mount/session` workflow remains a legacy compatibility path for the current
prototype. It should not be expanded as the target Remote Runner API.

## Consequences

- `remote-runner session exec` must run in a remote `cwd` without requiring a mounted local tree.
- File movement must be explicit through `remote-runner file put/get/list`.
- Logs and command results must be written to local state regardless of mount availability.
- The implementation may use SFTP first; `rsync` can be added later as an optional backend.
- Existing `seed-runner` tests should keep passing while the new core is introduced.

## Non-Goals

- This ADR does not require deleting legacy mount code in the first MVP.
- This ADR does not forbid optional mount backends in the future.
- This ADR does not decide the final project/package rename strategy.
