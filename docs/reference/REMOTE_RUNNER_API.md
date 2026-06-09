# Remote Runner API Contract v0

This document describes the current target user- and agent-facing CLI contract for
`remote-runner`. The repository still contains the legacy `seed-runner` prototype; see
`SEED_RUNNER_API.md` for that older API.

## Design Goals

- Local CLI first.
- Non-interactive use by default, so humans, scripts, and agents can share the same interface.
- JSON output for every resource/query/action command.
- No credentials in stdout, stderr, logs, reports, or JSON payloads.
- Recoverable state: machines, sessions, commands, logs, transfers, and artifacts can be queried after an interruption.
- Backend flexibility: SSH, tmux, rsync, SFTP, Slurm, Docker, or other mechanisms are implementation details.

## Platform Support

The current MVP is Linux-first. The actively supported persistent session path targets Linux
machines reachable over SSH/SFTP with `tmux` available on the remote host.

Windows OpenSSH + WSL is not the current primary support target. `startup_commands` and
`path_mappings` remain in the machine schema because they are useful for compatibility and future
backend work, but machines that require startup commands may be explicitly rejected by the current
persistent session backend. See [Platform Support](../platform-support.md).

## Global Options

All commands should eventually support:

```bash
--json
--timeout <seconds>
--state-dir <path>
```

When `--json` is present, stdout must contain one JSON object. Errors should return non-zero exit
status and write one JSON object to stderr.

## Machine Commands

### Add Machine

```bash
remote-runner machine add --json
```

Default MVP behavior is interactive when fields are omitted. The user supplies machine ID, host or
IP, port, user, authentication method, credential reference or password, and default working
directory. The user may also supply ordered startup commands that run immediately after SSH login
and before the default cwd/user command. Prompts are written to stderr so `--json` stdout remains
one JSON object.

Non-interactive flags remain available, but password values should not be encouraged as command-line
flags because shell history is easy to leak. The recommended password path is hidden interactive
input.

Same-name replacement is explicit:

```bash
remote-runner machine add --replace --confirm-replace lab-gpu-01 --json
```

Interactive replacement warns on stderr when the machine already exists and requires typing the
exact machine ID before overwriting the machine record. Replacement preserves prior sessions, logs,
transfers, and artifacts.

Minimum stored fields:

```json
{
  "machine_id": "lab-gpu-01",
  "host": "192.0.2.10",
  "port": 22,
  "user": "ely",
  "auth_type": "key",
  "key_path": "~/.ssh/id_ed25519",
  "default_cwd": "/home/ely",
  "startup_commands": [],
  "path_mappings": []
}
```

For a future or compatibility Windows OpenSSH machine that should enter WSL before Linux commands:

```bash
remote-runner machine configure-startup lab-win-01 \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/example/Desktop/SSHRunner \
  --json
```

`configure-startup` updates only startup commands and the optional default cwd. It must preserve
credentials and existing sessions, logs, transfers, and artifacts.

Some machines expose different path namespaces for command execution and SFTP. For example, a
Windows OpenSSH host may enter WSL for commands, where the working directory is
`/mnt/c/Users/.../SSHRunner`, while SFTP sees the same directory as
`C:/Users/.../SSHRunner`. Configure an explicit prefix mapping:

```bash
remote-runner machine configure-path-map lab-win-01 \
  --command-prefix /mnt/c/Users/example/Desktop/SSHRunner \
  --file-prefix C:/Users/example/Desktop/SSHRunner \
  --json
```

`file put/get/list` apply this mapping before SFTP. Transfer records and artifact manifests keep
the original user-supplied remote path, not the backend-specific path. This compatibility path is
not the current primary persistent-session support target.

### List Machines

```bash
remote-runner machine list --json
```

```json
{
  "machines": [
    {
      "machine_id": "lab-gpu-01",
      "host": "192.0.2.10",
      "port": 22,
      "user": "ely",
      "auth_type": "key",
      "default_cwd": "/home/ely",
      "startup_commands": [],
      "path_mappings": []
    }
  ],
  "summary": {
    "machine_count": 1
  }
}
```

Credentials must be redacted.

### Show Machine

```bash
remote-runner machine show lab-gpu-01 --json
```

Returns one machine record with credential fields redacted or represented as references.

### Doctor Machine

```bash
remote-runner machine doctor lab-gpu-01 --json
```

```json
{
  "machine_id": "lab-gpu-01",
  "reachable": true,
  "auth_ok": true,
  "default_cwd_ok": true,
  "checked_at": "2026-05-07T10:00:00Z",
  "errors": []
}
```

Diagnostics should be clear enough for a human to fix config quickly, while avoiding credential leaks.

### Remove Machine

```bash
remote-runner machine remove lab-gpu-01 --json
```

Returns the removed machine ID and whether related inactive sessions were retained or deleted.

### Restart Tmux Server

```bash
remote-runner machine restart-tmux-server lab-gpu-01 --json
```

Current Linux/tmux backend maintenance command. This command uses direct SSH against the machine; it
does not run inside a Remote Runner session, because killing the tmux server from inside its own
tmux-backed session prevents the command from completing cleanly.

The command must be conservative:

- Refuse when local state contains active Remote Runner tmux sessions for that machine. The user
  must destroy those sessions explicitly first.
- Refuse when remote `tmux list-sessions` reports any remaining tmux session, including sessions
  not managed by Remote Runner. This avoids killing unrelated user workloads.
- Run `tmux kill-server` only when no active Remote Runner tmux session and no remote tmux session
  remain.
- Return `not_running` as a successful no-op when no remote tmux server exists.

Example response:

```json
{
  "machine_id": "lab-gpu-01",
  "backend": "tmux",
  "checked_active_session_count": 0,
  "tmux_server_status": "restarted",
  "old_tmux_server_pid": "1205436"
}
```

## Session Commands

### Create Session

```bash
remote-runner session create \
  --machine lab-gpu-01 \
  --cwd /home/ely/project \
  --json
```

```json
{
  "session_id": "sess_abc123",
  "machine_id": "lab-gpu-01",
  "cwd": "/home/ely/project",
  "status": "active",
  "backend": "tmux",
  "created_at": "2026-05-07T10:00:00Z",
  "log_dir_local": "/Users/ely/.remote-runner/logs/sess_abc123",
  "transcript_file_local": "/Users/ely/.remote-runner/logs/sess_abc123/transcript.txt"
}
```

If `--cwd` is omitted, use the machine's `default_cwd`. A session is the persistent remote shell
context for this work area; backend details such as tmux are implementation details, not a separate
top-level resource. In the current MVP, this persistent backend is Linux/SSH + tmux.

Current Linux/tmux implementation note: `session create` opens a remote tmux-backed shell through
SSH, and later `session exec/send/read/destroy` calls use fresh SSH operations to control that
backend shell. It does not persistently log in a user account in Remote Runner itself, but the
remote shell inherits the Unix identity, supplementary groups, environment, and tmux server context
available to the process that ultimately spawns it. `tmux new-session` creates a new tmux session,
but if the user's tmux server already exists, the new shell may be forked by that existing tmux
server rather than directly by the fresh SSH login process. If server-side group membership or login
policy changes, `session destroy && session create` is the public Remote Runner restart path, but it
is not a guaranteed authorization refresh while an existing tmux server with old process credentials
continues serving new tmux sessions.

### List Sessions

```bash
remote-runner session list --json
```

Returns active and recoverable sessions with machine ID, cwd, status, creation time, command count,
and log directory.

### Show Session

```bash
remote-runner session show --session sess_abc123 --json
```

Returns the session record, last command, last exit code, command count, and log locations.

### Execute Command

```bash
remote-runner session exec \
  --session sess_abc123 \
  --cmd "pytest -q" \
  --timeout 300 \
  --json
```

This is the default synchronous path. `--mode wait` runs the command inside the persistent session
shell and returns only after the command finishes. Shell-local state such as `cd`, exported
variables, aliases, and shell functions remains available to later commands in the same session.

Optional cwd override. This changes the persistent shell's current directory before running the
command:

```bash
remote-runner session exec \
  --session sess_abc123 \
  --cwd /home/ely/project/subdir \
  --cmd "make test" \
  --json
```

Return shape:

```json
{
  "session_id": "sess_abc123",
  "command_id": "cmd_abc123",
  "machine_id": "lab-gpu-01",
  "cwd": "/home/ely/project",
  "command": "pytest -q",
  "mode": "wait",
  "status": "completed",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "stdout_truncated": false,
  "stderr_truncated": false,
  "started_at": "2026-05-07T10:00:00Z",
  "ended_at": "2026-05-07T10:00:08Z",
  "duration_ms": 8123,
  "log_file_local": "/Users/ely/.remote-runner/logs/sess_abc123/cmd_001.log"
}
```

Behavior requirements:

- Preserve logs even when `exit_code` is non-zero.
- Do not destroy the session on command failure.
- Return a clear busy/timeout state when a command cannot be accepted.
- Allow stdout/stderr truncation in JSON only if the full content is available through
  `log_file_local` or a recoverable remote log reference.
- Do not require sshfs, FUSE, reverse SSH, or mount setup.
- `session exec` defaults to synchronous wait mode; long-running jobs should use
  `--mode background`.
- `session exec` runs in the session shell. It must keep command boundaries and exit codes through
  Remote Runner command wrappers and state files, not by relying on chat memory.

### Background Command Start

```bash
remote-runner session exec \
  --session sess_abc123 \
  --cmd "docker compose up" \
  --mode background \
  --json
```

Background start returns immediately after the command is accepted in the session shell. The
response includes `command_id`, `status=running`, `remote_state_dir`, remote log/status file
references, timestamps, and `log_file_local` for the local summary record.

Background commands persist their own remote state under the session cwd in
`.remote-runner/commands/<command_id>/`. The CLI can be restarted later and still recover the
command state from local session records plus those remote files.

### Session Commands

```bash
remote-runner session command list --session sess_abc123 --json
remote-runner session command show --session sess_abc123 --command-id cmd_abc123 --json
remote-runner session command result --session sess_abc123 --command-id cmd_abc123 --json
remote-runner session command wait --session sess_abc123 --command-id cmd_abc123 --timeout 20 --json
remote-runner session command stop --session sess_abc123 --command-id cmd_abc123 --json
```

`show` and `result` are aliases. They return the current command status, bounded stdout/stderr
excerpts, truncation flags, exit code when available, timestamps, local log path, and remote state
references when the command was started in background mode.

`wait` only limits the wait call itself. It does not kill the remote command on timeout. The
returned JSON includes `wait_timed_out` so callers can distinguish "still running" from
"finished".

`stop` sends a stop request for a background command. Repeating `stop` on a finished command must
return a clear result without losing logs or state.

### Session Input and Transcript

```bash
remote-runner session send \
  --session sess_abc123 \
  --input "python" \
  --json

remote-runner session read --session sess_abc123 --json
remote-runner session read --session sess_abc123 --since 1200 --json
```

`session send` sends raw input to the same session shell and presses Enter by default; use
`--no-enter` for partial input. This is for shell-panel and interactive workflows. For normal agent
automation, prefer `session exec` because it also records command boundaries, stdout/stderr,
exit code, timestamps, and logs.

`session read` returns captured transcript text, a `cursor`, and the requested `since` offset.
Callers can store the cursor and later request only the new transcript region. The local transcript
file is preserved in Remote Runner state for recovery.

### Logs

```bash
remote-runner session logs --session sess_abc123 --json
```

Returns ordered command log metadata and paths. A future text mode may print combined logs.

### Destroy Session

```bash
remote-runner session destroy --session sess_abc123 --json
```

Returns final status and preserved log/transcript locations. Destroying a session stops the remote
backend shell but preserves local session records, command logs, transfer records, artifacts, and
transcript path.

There is currently no separate `session restart` or `session refresh-auth` command. Restart is
modeled as explicit `session destroy` followed by `session create`.

## File Transfer Commands

### Put

```bash
remote-runner file put --session sess_abc123 --local ./input.txt --remote /home/ely/project/input.txt --json
```

Uploads a local file or directory to the remote path through SSH/SFTP or another explicit transfer
backend. It must not require a mount.

### Get

```bash
remote-runner file get --session sess_abc123 --remote /home/ely/project/output.txt --local ./output.txt --json
```

Downloads a remote file or directory to the local path.

### List

```bash
remote-runner file list --session sess_abc123 --remote /home/ely/project --json
```

Lists remote file metadata for the path.

Transfer responses and persisted records should include direction, source, destination, timestamps,
status, size/hash when available, and error details when failed.

## Local State

Default MVP state root:

```text
~/.remote-runner/
  machines.json
  sessions/
  logs/
  transfers/
  artifacts/
  runs/
```

The storage implementation can later move to SQLite or a daemon. The CLI contract must remain the
source of truth for humans, scripts, and agents.

## Run Commands

`run` commands sit above machine/session/file and provide a generic closed loop. They are not tied
to research, SEED, operations, training, or any other profile.

### Run Once

```bash
remote-runner run once \
  --machine lab-gpu-01 \
  --cwd /home/ely/project \
  --input ./input.json=/home/ely/project/input.json \
  --cmd "python train.py --input input.json --output output.txt" \
  --artifact /home/ely/project/output.txt=./output.txt \
  --json
```

`--input` uses `LOCAL=REMOTE`; `--artifact` uses `REMOTE=LOCAL`. Both flags may be repeated. The
delimiter is `=` so Windows-style paths can still contain `:`.

Default behavior creates a session, uploads inputs, executes the command, downloads artifacts, saves
a run manifest, destroys the session, and preserves logs/state. Use `--keep-session` to leave the
created session active.

Minimum run manifest fields:

```json
{
  "run_id": "run_abc123",
  "machine_id": "lab-gpu-01",
  "session_id": "sess_abc123",
  "cwd": "/home/ely/project",
  "command": "python train.py",
  "status": "succeeded",
  "started_at": "2026-05-11T10:00:00Z",
  "ended_at": "2026-05-11T10:00:08Z",
  "inputs": [],
  "command_result": {},
  "artifacts": [],
  "destroy_session_result": {}
}
```

Non-zero command exit codes mark the run as `failed` but must preserve command logs and the run
manifest.

### List Runs

```bash
remote-runner run list --json
```

Returns recoverable run summaries with run ID, machine ID, session ID, cwd, command, status,
timestamps, exit code, input count, and artifact count.

### Show Run

```bash
remote-runner run show run_abc123 --json
```

Returns the full run manifest.

## Future Profile Layer

Profile commands are intentionally above the generic run layer. Future commands may include:

```bash
remote-runner run verify
remote-runner artifact push
remote-runner artifact pull
remote-runner report evidence
```

These may support operations, SEED, research, training, benchmark, or other workflows. They should
not redefine the machine/session/file/run primitives.
