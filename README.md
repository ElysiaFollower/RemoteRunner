# Remote Runner

Remote Runner gives agents and humans the same persistent local shell.

Each Session is one local tmux pane. Remote Runner installs `pipe-pane` before starting the shell,
writes the pane's raw output to an append-only transcript, and exposes a small interface for text,
keys, ranges, state, attach, and lifecycle. SSH is an ordinary command typed into that shell; Remote
Runner does not hide remote login, create remote tmux sessions, infer prompts, or run batch protocols
through the terminal.

## Requirements

- macOS or Linux
- Python 3.10+
- tmux

Windows can be an SSH target, but Remote Runner does not run on Windows and has no Windows-specific
backend.

## Install

```bash
python3 -m pip install -e ".[dev]"
remote-runner --help
```

This V4 design is intentionally incompatible with every earlier Remote Runner/seed-runner state,
Session, command, and backend. Archive the old state directory before first use; the new tool refuses
to read or mutate it.

When replacing an editable prototype installation named `seed-runner`, uninstall that old package
metadata before installing V4 so stale console scripts are not left behind:

```bash
python3 -m pip uninstall seed-runner
python3 -m pip install -e ".[dev]"
```

## First Session

```bash
remote-runner session create --name project
remote-runner session show --session project
remote-runner session tail --session project
remote-runner session send --session project --input 'pwd'
remote-runner session tail --session project
remote-runner session key --session project C-c
```

`tail` and `read` write raw terminal bytes by default. Add `--json` only when cursor metadata is
needed:

```bash
remote-runner session read --session project --from 0 --max-bytes 65536 --json
```

To connect elsewhere, use the terminal normally:

```bash
remote-runner session send --session project --input 'ssh gpu-a'
```

Remote Runner only promises that the local shell persists while its tmux pane exists. SSH keepalive,
reconnection, remote tmux, Slurm, `nohup`, and remote process survival remain explicit operator
decisions.

## Human Collaboration

`session show` returns `tmux_session_name` and `transcript_path`. A human can attach directly:

```bash
tmux attach-session -t <tmux_session_name>
```

Normal echoed human input and all pane output enter the same transcript. Passwords and other
no-echo input do not, matching what the terminal displays.

## Instance Bootstrap

An Instance is only a name pointing at an inspectable Python hook:

```python
def bootstrap(session):
    session.send("ssh gpu-a")
    # This hook owns prompt waiting and login decisions through read/tail.
```

```bash
remote-runner instance add --name gpu-a --bootstrap ~/.config/rr/gpu_a.py
remote-runner session create --name training --instance gpu-a
```

Bootstrap runs synchronously under the Session's writer lock. Failure or timeout leaves the shell,
transcript, and diagnostic log intact for an agent or human to take over.

See [Getting Started](docs/getting-started.md), the
[CLI contract](docs/reference/REMOTE_RUNNER_API.md), and the
[core lighthouse](docs/architecture/core-lighthouse.md).
