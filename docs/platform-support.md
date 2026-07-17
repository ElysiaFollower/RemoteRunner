# Platform Support

## Supported host

Remote Runner runs on macOS and Linux with local tmux and Python 3.10+.

## Unsupported host

Windows is not a Remote Runner host platform. The former PowerShell pipe agent and all Windows
backend branches were deleted because they did not provide the same PTY/terminal semantics.

## Remote targets

Remote Runner does not classify remote platforms. An Agent may type `ssh`, `mosh`, a cloud CLI, or
another connector into the local shell. A Windows OpenSSH target therefore remains usable through
normal terminal interaction without any Windows-specific RR implementation.

## Persistence

RR guarantees the local tmux shell while the local pane survives. An SSH connection can time out or
drop. Remote process persistence, reconnection, remote tmux, Slurm, `nohup`, and similar mechanisms
are explicit operator choices and are documented in the usage Skill rather than automated by core.
