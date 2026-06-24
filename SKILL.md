---
name: remote-runner
description: Use when a task should be executed on a preconfigured remote machine through the remote-runner CLI, especially when an agent must run commands, transfer files, collect structured stdout/stderr/exit codes, inspect logs/artifacts, iterate on failures, and clean up sessions without using raw ssh, scp, rsync, tmux, sshfs, or mounted folders directly.
metadata:
  short-description: Operate remote machines through Remote Runner
---

# Remote Runner

Use this skill when work must happen on a remote machine through the `remote-runner` CLI. This skill is for application-layer execution on top of Remote Runner, not for changing Remote Runner's implementation.

## Core Rule

Use `remote-runner` as the stable interface:

- machine registry and diagnostics: `machine list/show/doctor`
- remote command context: `session create/exec`, `session command list/show/wait/stop`,
  `session send/read/logs/destroy`
- explicit file movement: `file put/get/list`
- one-shot closed loop: `run once`

Do not use raw `ssh`, `scp`, `rsync`, `tmux`, `sshfs`, or mount workflows unless the user explicitly asks you to debug the platform itself. Remote Runner no longer uses mounted folders as its core abstraction.

## Platform Boundary

For normal work, choose an explicitly configured machine whose `platform`, `backend`, and `shell`
match the target OS:

- Linux/mac-style work: SSH/SFTP machine with `backend=ssh-tmux`, `shell=bash`, and `tmux`
  available.
- Direct Windows work: Windows OpenSSH/SFTP machine with `backend=windows-agent`, `shell=pwsh`,
  Python 3, and PowerShell 7 available.

Windows OpenSSH + WSL records that depend on `startup_commands` and `path_mappings` are
compatibility inputs, not the primary direct Windows path.

## Environment

The normal local environment is the `seedrunner` conda environment.

```bash
conda activate seedrunner
remote-runner --help
```

If the shell is not activated:

```bash
conda run -n seedrunner remote-runner --help
```

If `remote-runner` is missing, install the tool from the Remote Runner repo:

```bash
cd /Users/ely/workspace/research/old/agent/SEEDRunner
conda run -n seedrunner python -m pip install -e .
```

## Start Workflow

1. List machines:

```bash
remote-runner machine list --json
```

2. Diagnose the chosen machine before doing work:

```bash
remote-runner machine doctor <machine-id> --json
```

Do not continue if `reachable`, `auth_ok`, or `default_cwd_ok` is false. Report the machine-level blocker.

3. Choose an explicit remote working directory. It must be safe and writable for this task. Do not assume `/home/ely/tmp` is writable; verify it first or use a known-good directory such as `/tmp` for probes.

4. Create a session:

```bash
remote-runner session create --machine <machine-id> --cwd <remote-dir> --name <session-name> --json
```

`session create` opens the persistent remote shell context for this work area. `machine doctor` and
the first `session exec` are still the practical connectivity checks. `--name` is optional, but use
a readable name for non-temporary sessions. Later `--session` arguments accept either the generated
`session_id` or a unique readable name.

5. Run bounded commands through the session:

```bash
remote-runner session exec \
  --session <session-ref> \
  --cmd 'pwd && whoami' \
  --mode wait \
  --json
```

Inspect `exit_code`, `stdout`, `stderr`, and `log_file_local` after every command.
Commands in the same session share shell-local state: a prior `cd`, `export`, or alias can affect
later `session exec` calls.

For long-running or persistent commands on the Linux/tmux backend, do not compensate by using very
large synchronous timeouts. Start the command in background mode and keep the returned `command_id`:

```bash
remote-runner session exec \
  --session <session-ref> \
  --cmd '<long-running-command>' \
  --mode background \
  --json
```

Then inspect or wait explicitly:

```bash
remote-runner session command show \
  --session <session-ref> \
  --command-id <command-id> \
  --json

remote-runner session command wait \
  --session <session-ref> \
  --command-id <command-id> \
  --timeout 30 \
  --json
```

Use `session command stop` when a running background command should be terminated. A session with
running background commands cannot be destroyed until those commands finish or are stopped. The
direct Windows backend currently supports persistent wait-mode execution and raw send/read, but
rejects background commands with a clear error.

6. Clean up when finished:

```bash
remote-runner session destroy --session <session-ref> --json
```

## Persistent Session Transcript

Use `session send/read` when the task needs raw shell-panel behavior in the existing session. Do
not create a separate top-level terminal resource.

```bash
remote-runner session send \
  --session <session-ref> \
  --input 'cd src' \
  --json

remote-runner session read \
  --session <session-ref> \
  --json
```

`session read` returns transcript text and a cursor for incremental reads. `session destroy` stops
the remote backend shell and preserves local command logs and transcript state.

## File Transfer

Use explicit Remote Runner file commands:

```bash
remote-runner file put \
  --session <session-ref> \
  --local ./input.txt \
  --remote <remote-dir>/input.txt \
  --json

remote-runner file list \
  --session <session-ref> \
  --remote <remote-dir> \
  --json

remote-runner file get \
  --session <session-ref> \
  --remote <remote-dir>/output.txt \
  --local ./output.txt \
  --json
```

File transfer is built into Remote Runner through SSH/SFTP. It does not require mounted folders, sshfs, rsync, or scp.

If file transfer fails, classify before retrying:

- `machine doctor` fails: machine auth/connectivity problem.
- `session exec` fails similarly: not an SFTP-only issue.
- `session exec` succeeds but `file put` fails with permission denied: remote path permissions problem.
- `session exec` succeeds but SFTP cannot open paths: check SFTP subsystem and path mappings.
- Windows OpenSSH + WSL path mismatch on a compatibility backend: use `machine configure-path-map`.

## Run Once

Use `run once` when the task is one closed loop: upload inputs, run one command, pull artifacts, preserve manifest/logs, destroy the temporary session.

```bash
remote-runner run once \
  --machine <machine-id> \
  --cwd <remote-dir> \
  --input ./input.txt=<remote-dir>/input.txt \
  --cmd 'cp input.txt output.txt' \
  --artifact <remote-dir>/output.txt=./output.txt \
  --json
```

Use `run list` and `run show` to recover run state:

```bash
remote-runner run list --json
remote-runner run show <run-id> --json
```

## Machine Configuration

Only configure machines when the user explicitly asks. Never print passwords, key contents, host-sensitive details, or private paths in reports or handoffs.

Password-auth Linux machine:

```bash
remote-runner machine add \
  --machine-id <machine-id> \
  --host <host-or-ip> \
  --user <user> \
  --auth-type password \
  --default-cwd /home/<user> \
  --json
```

To update a stale machine record:

```bash
remote-runner machine add \
  --machine-id <machine-id> \
  --host <host-or-ip> \
  --user <user> \
  --auth-type password \
  --default-cwd /home/<user> \
  --replace \
  --confirm-replace <machine-id> \
  --json
```

Direct Windows OpenSSH machine:

```bash
remote-runner machine add \
  --machine-id <machine-id> \
  --host <host-or-ip> \
  --user <user> \
  --auth-type password \
  --platform windows \
  --backend windows-agent \
  --shell pwsh \
  --default-cwd C:/Users/<user> \
  --json
```

Windows OpenSSH that must enter WSL first, for compatibility backend work:

```bash
remote-runner machine configure-startup <machine-id> \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/<user>/Desktop/SSHRunner \
  --json

remote-runner machine configure-path-map <machine-id> \
  --command-prefix /mnt/c/Users/<user>/Desktop/SSHRunner \
  --file-prefix C:/Users/<user>/Desktop/SSHRunner \
  --json
```

Do not choose this Windows/WSL path for normal direct Windows persistent session work unless the
user explicitly asks to test that compatibility boundary.

## Failure Handling

- Always surface the exact JSON error.
- Do not continue after failed `doctor` unless the user asks to debug configuration.
- Non-zero command exit codes are task evidence, not necessarily platform failure. Read logs before retrying.
- A busy session means another command is active; inspect logs/state before retrying.
- If a session was created during a failed task, destroy it unless the user asks to keep it.
- If credentials are stale, update the machine record; do not work around it with raw SSH.

## Completion

A remote task is complete only when:

- the requested action ran or a precise blocker was identified
- result evidence is captured from JSON output, logs, transfer records, or artifacts
- created remote probe files are cleaned up unless intentionally retained
- sessions are destroyed unless the user asked to keep them

Final answers should include the machine id, session id or run id when useful, key log/artifact paths, final status, and any residual risk. Do not include secrets.
