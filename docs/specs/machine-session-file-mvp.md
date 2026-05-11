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

This is an explicit configuration, not automatic path discovery.

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

### `remote-runner session exec --session <session_id> --cmd <command> [--cwd <remote_cwd>] --timeout <seconds> --json`

Executes the command directly in the remote cwd. It must not require a mount.

Minimum response fields:

- `session_id`
- `machine_id`
- `cwd`
- `command`
- `exit_code`
- `stdout`
- `stderr`
- `started_at`
- `ended_at`
- `duration_ms`
- `log_file_local`

Command records must be persisted even when `exit_code` is non-zero. Non-zero exit code must not
destroy the session.

### `remote-runner session logs --session <session_id> --json`

Returns ordered command log metadata and local log paths.

### `remote-runner session destroy --session <session_id> --json`

Marks or removes the active session from the active list while preserving local logs, command
records, transfer records, and artifacts.

## File Transfer Commands

### `remote-runner file put --session <session_id> --local <path> --remote <path> --json`

Uploads a local file or directory to the remote path through SSH/SFTP or an equivalent explicit file
transfer backend.

### `remote-runner file get --session <session_id> --remote <path> --local <path> --json`

Downloads a remote file or directory to the local path.

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
- File put/get/list works without sshfs, FUSE, reverse SSH, or a long-running daemon.
- Run once can upload input, execute a command, download an artifact, and recover the run manifest.
- Credentials are redacted from JSON, logs, reports, and handoff files.
- `./scripts/harness-check.sh` and `python3 -m pytest -q` pass after documentation-only preparation.
