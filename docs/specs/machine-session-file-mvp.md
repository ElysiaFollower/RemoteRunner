# Remote Runner Machine, Session, and File Transfer MVP Spec

## Goal

Define the first implementation target for Remote Runner's mount-free core:

```text
machine registry -> session in remote cwd -> command exec -> local logs/state -> explicit file transfer
```

This spec is the source of truth for the first refactor after the positioning/harness work. It is
compatible with keeping the current Python package name `seed_runner` during the migration.

## Non-Goals

- Do not remove legacy `seed-runner mount/session` behavior in this MVP.
- Do not require sshfs, FUSE, reverse SSH, or a long-running daemon.
- Do not implement profile-level research, SEED, operations, training, or benchmark workflows.
- Do not promise strong isolation from a malicious process running as the same local user.

## Global CLI Rules

- Target executable: `remote-runner`.
- Every MVP command must support `--json`.
- JSON responses must not include password values or private key contents.
- Errors must return non-zero exit status and a JSON error object when `--json` is set.
- State defaults to `~/.remote-runner/`; tests must be able to override it with an environment variable.

## State Layout

Default local state root:

```text
~/.remote-runner/
  machines.json
  sessions/
    <session_id>.json
  logs/
    <session_id>/
      cmd_001.log
  transfers/
    <session_id>.jsonl
  artifacts/
    <session_id>/
      manifest.json
  runs/
    <run_id>.json
```

State is the recovery source. A new process must be able to list machines, list sessions, inspect
command history, inspect transfer history, and inspect run manifests without relying on chat
context.

## Machine Commands

### `remote-runner machine add`

Stores a machine record. The recommended MVP path is interactive input: omitted fields are prompted
on stderr, password auth uses hidden input, and `--json` stdout remains parseable as one JSON
object. Non-interactive flags remain supported for scripts and tests, but `--password` is not the
recommended path for real credentials because shell history can leak it.

Machine records may include ordered `startup_commands`. These commands are sent after SSH login and
before the normal cwd change and user command. This covers hosts where the first usable shell is not
the SSH default shell, such as a Windows OpenSSH host that must run `wsl` before Linux commands.
They are compatibility inputs, not the direct Windows launch path for persistent sessions.

Machine records also include explicit platform/backend/shell fields. Defaults preserve existing
Linux records:

- `platform=linux`, `backend=ssh-tmux`, `shell=bash`
- `platform=windows`, `backend=windows-agent`, `shell=pwsh`
- `platform=linux|mac`, `backend=openssh-pty`, `shell=bash`, `auth_type=manual`

Direct Windows support targets Windows OpenSSH/SFTP without entering WSL. It requires Python 3 and
PowerShell 7 on the remote host.

Existing machines can update startup behavior without re-entering credentials:

```bash
remote-runner machine configure-startup <machine_id> \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/example/Desktop/SSHRunner \
  --json
```

Machines may also define explicit path mappings when command execution and file transfer see
different path namespaces. A Windows OpenSSH host that runs `wsl` may execute commands in
`/mnt/c/Users/.../SSHRunner`, while SFTP sees that directory as `C:/Users/.../SSHRunner`:

```bash
remote-runner machine configure-path-map <machine_id> \
  --command-prefix /mnt/c/Users/example/Desktop/SSHRunner \
  --file-prefix C:/Users/example/Desktop/SSHRunner \
  --json
```

This is an explicit configuration, not automatic path discovery. Path mappings are retained for
compatibility and future backend work; they do not make Windows/WSL a primary support target for the
current persistent session backend.

Existing machines can update platform behavior without re-entering credentials:

```bash
remote-runner machine configure-platform <machine_id> \
  --platform windows \
  --backend windows-agent \
  --shell pwsh \
  --json
```

Same-name machines are rejected by default. `--replace` allows overwriting an existing machine only
after exact machine ID confirmation, either through interactive prompt or
`--confirm-replace <machine_id>`. Replacement must preserve prior sessions, logs, transfers, and
artifacts.

Minimum fields:

- `machine_id`
- `host`
- `port`
- `user`
- `auth_type`: `password` or `key`
- `password` or `key_path`
- `platform`: `linux`, `windows`, or `mac`
- `backend`: `ssh-tmux`, `windows-agent`, or `openssh-pty`
- `shell`: `bash` or `pwsh`
- `startup_commands`
- `default_cwd`
- `path_mappings`

### `remote-runner machine list --json`

Returns all configured machines with credentials redacted.

### `remote-runner machine show <machine_id> --json`

Returns one machine record with credentials redacted.

### `remote-runner machine doctor <machine_id> --json`

Checks whether the machine can be reached and authenticated, and whether `default_cwd` exists or can
be entered. The result must include `reachable`, `auth_ok`, `default_cwd_ok`, `checked_at`, and
`errors`.

### `remote-runner machine remove <machine_id> --json`

Removes the machine record. It must not silently delete command logs or transfer history.

## Session Commands

### `remote-runner session create --machine <machine_id> [--cwd <remote_cwd>] --json`

Creates a recoverable session record. If `--cwd` is omitted, use the machine's `default_cwd`.

Minimum response fields:

- `session_id`
- `machine_id`
- `cwd`
- `status`
- `created_at`
- `log_dir_local`

### `remote-runner session list --json`

Lists recoverable sessions with machine ID, cwd, status, created time, command count, and log dir.

### `remote-runner session show --session <session_id> --json`

Shows one session, including last command, last exit code, command count, log dir, and transfer count.

### `remote-runner session exec --session <session_id> --cmd <command> [--cwd <remote_cwd>] [--mode wait|background] --timeout <seconds> --json`

Runs a structured command associated with the session. It must not require a mount. On `ssh-tmux`,
the command uses independent direct SSH execution; the recorded/default cwd is a batch process cwd,
not the live terminal's current directory.

Default `--mode wait` runs a bounded command and returns after completion. `--mode background`
starts a long-running command and returns after a durable `command_id` and remote state/log
references exist. In background mode, `--timeout` is the launch timeout, not the remote command
runtime limit.

`session exec` is a structured compatibility API, not the persistent terminal's input primitive.
`ssh-tmux` exec/background commands must not write wrappers, markers, or protocol traffic into the
live pane. Shell-local continuity belongs to `session send/read/tail`; upload-run-download batch
workflows belong to `run once`.

Minimum response fields:

- `session_id`
- `command_id`
- `machine_id`
- `cwd`
- `command`
- `mode`
- `status`
- `exit_code`
- `stdout`
- `stderr`
- `stdout_truncated`
- `stderr_truncated`
- `started_at`
- `ended_at`
- `duration_ms`
- `log_file_local`

Command records must be persisted even when `exit_code` is non-zero. Non-zero exit code must not
destroy the session.

Background command records must include enough references for a new CLI process to recover command
state. The first implementation stores remote status and output under:

```text
<session cwd>/.remote-runner/commands/<command_id>/
  status
  pid
  exit_code
  ended_at
  stdout.log
  stderr.log
```

Background command statuses are:

- `running`
- `exited`
- `failed`
- `timed_out`
- `stopped`

The direct Windows backend may explicitly reject background commands until durable Windows process
tracking and stop semantics are designed. Wait-mode execution must still preserve shell-local state
inside the persistent PowerShell session.

### `remote-runner session command list --session <session_id> --json`

Lists persisted command summaries for a session.

### `remote-runner session command show|result --session <session_id> --command-id <command_id> [--stdout-bytes <n>] [--stderr-bytes <n>] --json`

Shows one command result. `show` and `result` are aliases. For background commands, it refreshes
status and bounded stdout/stderr excerpts from the remote state/log files when those files are
still available. JSON excerpts are bounded; the remote stdout/stderr file references remain part of
the recoverable command record.

### `remote-runner session command wait --session <session_id> --command-id <command_id> --timeout <seconds> --json`

Polls a command until it finishes or this wait call times out. A wait timeout must not kill or
detach the remote command. Responses include `wait_timed_out`.

### `remote-runner session command stop --session <session_id> --command-id <command_id> --json`

Requests termination of a running background command. Stop must preserve command state and logs.
Destroying a session with running background commands must fail with a clear error.

### `remote-runner session logs --session <session_id> --json`

Returns ordered command log metadata and local log paths.

### `remote-runner session destroy --session <session_id> --json`

Destroys the remote backend shell while preserving local logs, transcript, command records,
transfer records, and artifacts.

## Persistent Session Shell

`session` is the public persistent shell/terminal abstraction. Backend choices such as tmux are
implementation details. A separate top-level `terminal` resource is not part of the target API.

### `remote-runner session create --machine <machine_id> [--cwd <remote_cwd>] --json`

Creates a recoverable session record and remote backend shell. If `--cwd` is omitted, use the
machine's `default_cwd`.

Minimum response fields:

- `session_id`
- `machine_id`
- `cwd`
- `backend`
- `status`
- `created_at`
- `updated_at`
- `transcript_file_local`
- `log_dir_local`

Current persistent backends are Linux/SSH + `tmux`, direct Windows OpenSSH +
`windows-agent`/PowerShell, and local `tmux` + OpenSSH PTY. Machines with `startup_commands` may be
explicitly rejected by backends that do not implement interactive startup terminal semantics. See
`docs/platform-support.md` for the current platform boundary.

### `remote-runner session exec --session <session_id> --cmd <cmd> --json`

Runs a structured command associated with the session and returns `command_id`, `exit_code`,
stdout/stderr, timestamps, duration, and log references. On `ssh-tmux`, it is an isolated direct-SSH
batch process and deliberately does not preserve terminal shell-local state. On `windows-agent`, the
agent's explicit request/result protocol provides the documented persistent PowerShell behavior.

### `remote-runner session send --session <session_id> --input <text> [--no-enter] --json`

Sends one literal line into the selected session shell. This is the normal operation whenever the
caller expects human-terminal semantics or shell-local continuity. The response is a compact
acknowledgement with input/output timestamps and transcript cursors; full session metadata belongs
to `session show`.

### `remote-runner session read --session <session_id> [--since <cursor>] [--max-bytes <n>] [--json|--plain]`

Losslessly reads the append-only transcript from an explicit UTF-8 byte cursor. Compact JSON
includes `transcript`, `start_cursor`, `next_cursor`, `last_cursor`, timestamps, idle duration, and
the compatibility aliases `since`/`cursor`. If bounded, `next_cursor` stops after the returned
bytes; it never jumps to `last_cursor`. `--plain` emits only terminal text. A new CLI process must be
able to recover and read the transcript from local state plus the remote backend.

### `remote-runner session tail --session <session_id> [--bytes <n>] [--json|--plain]`

Explicitly reads a bounded newest window from the preserved transcript. It reports the actual
start and end cursors plus whether older history exists. Tail never deletes, summarizes, compresses,
or silently substitutes for lossless read.

## File Transfer Commands

### `remote-runner file put --session <session_id> --local <path> --remote <path> --json`

Uploads a local file or directory to the remote path through SSH/SFTP or an equivalent explicit file
transfer backend.

### `remote-runner file get --session <session_id> --remote <path> --local <path> --json`

Downloads a remote file or directory to the local path.

`openssh-pty` 没有独立文件 transport，因此明确拒绝 `file get`；不得复用 session PTY 注入
分块编码、marker 或隐藏传输脚本。

### `remote-runner file list --session <session_id> --remote <path> --json`

Lists remote file metadata for the given remote path.

When the session machine has a matching `path_mappings` entry, the file transfer backend must map
the user-supplied command-side remote path to the backend file path before SFTP. Transfer records and
artifact manifests must still use the original user-supplied remote path.

Each transfer record must contain:

- `transfer_id`
- `session_id`
- `machine_id`
- `direction`: `put`, `get`, or `list`
- `source`
- `destination`
- `started_at`
- `ended_at`
- `status`
- `size_bytes` when available
- `sha256` when cheaply available
- `error` when failed

Transfer failures must be recorded in local state.

## Run Commands

### `remote-runner run once --machine <machine_id> --cmd <command> [--cwd <remote_cwd>] [--input LOCAL=REMOTE] [--artifact REMOTE=LOCAL] --json`

Runs one closed-loop remote job using the machine/session/file primitives. It must create a session,
upload all inputs, execute the command, download requested artifacts, persist a run manifest, and
destroy the created session by default.

Input and artifact flags may be repeated. `=` is the delimiter so Windows paths may still contain
colons.

Minimum run manifest fields:

- `run_id`
- `machine_id`
- `session_id`
- `cwd`
- `command`
- `status`: `running`, `succeeded`, or `failed`
- `started_at`
- `ended_at`
- `inputs`
- `command_result`
- `artifacts`
- `destroy_session`
- `destroy_session_result`
- `error` when failed before command result exists

Non-zero command exit code marks the run as failed but must preserve command logs and the manifest.

### `remote-runner run list --json`

Lists recorded run summaries.

### `remote-runner run show <run_id> --json`

Shows the full run manifest.

## Legacy Compatibility

- Existing `seed-runner mount create/status/destroy` and `seed-runner session ...` behavior remains
  legacy prototype behavior.
- Legacy tests must continue to pass during the MVP migration.
- Target docs must not describe mount as the Remote Runner core path.

## Acceptance Criteria

- Machine, session, command, log, and transfer state can be recovered by a new CLI process.
- Remote command execution works without mount setup.
- Long-running commands can be started in background mode, queried by `command_id`, waited on, or
  stopped without relying on an in-process command table.
- File put/get/list works without sshfs, FUSE, reverse SSH, or a long-running daemon.
- Run once can upload input, execute a command, download an artifact, and recover the run manifest.
- Credentials are redacted from JSON, logs, reports, and handoff files.
- `./scripts/harness-check.sh` and `python3 -m pytest -q` pass after implementation changes.
