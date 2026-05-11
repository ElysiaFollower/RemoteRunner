# Remote Runner Startup Commands and Windows WSL Validation

## Task Contract

Make Remote Runner machine records support ordered startup commands that run after SSH login and
before normal Linux-like command execution. This enables a Windows OpenSSH machine to enter WSL
first, then operate inside a safe WSL directory.

## Goals

- Add `startup_commands` to machine configuration.
- Prompt for startup commands during interactive `remote-runner machine add`.
- Add a way to configure startup commands for an existing machine without re-entering credentials.
- Make `session exec` and `machine doctor` honor startup commands.
- Validate the configured Windows machine by entering WSL and operating only inside
  `/mnt/c/Users/example/Desktop/SSHRunner`.

## Non-Goals

- Do not modify files outside the Windows `SSHRunner` directory.
- Do not run destructive Windows commands.
- Do not make SFTP path translation between Windows and WSL a general feature in this task.
- Do not introduce daemon, tmux, mount, or persistent remote service requirements.

## Implementation Sequence

1. Extend machine schema and redacted JSON output with `startup_commands`.
2. Add CLI support:
   - `machine add --startup-command <cmd>` repeatable.
   - interactive startup command collection.
   - `machine configure-startup <machine_id> --startup-command <cmd> --default-cwd <cwd> --json`.
3. Add backend execution path for machines with startup commands using an interactive SSH shell,
   command sentinel, and captured exit code.
4. Update doctor to use the startup-aware execution path for cwd validation.
5. Add focused tests for schema, CLI, and startup-aware backend behavior with fake channels.
6. Run local validation and then a minimal real command on the Windows machine under SSHRunner.

## Verification

Local:

```bash
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
./scripts/harness-check.sh
python3 -m black --check seed_runner/remote_machine.py seed_runner/remote_cli.py seed_runner/remote_backend.py tests/test_remote_runner_mvp.py
```

Real Windows SSHRunner validation:

```bash
python3 -m seed_runner.remote_cli machine configure-startup <machine_id> \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/example/Desktop/SSHRunner \
  --json

python3 -m seed_runner.remote_cli machine doctor <machine_id> --json
python3 -m seed_runner.remote_cli session create --machine <machine_id> --json
python3 -m seed_runner.remote_cli session exec --session <session_id> \
  --cmd "pwd && printf remote-runner-ok > rr_probe.txt && cat rr_probe.txt && rm rr_probe.txt" \
  --json
```

## Completion

Completed on 2026-05-09.

- Added persisted `startup_commands` to Remote Runner machine records.
- Added interactive and flag-based startup command collection to `machine add`.
- Added `machine configure-startup` for updating an existing machine without re-entering credentials.
- Made `machine doctor` and `session exec` use startup-aware execution when commands are configured.
- Added interactive SSH shell execution with carriage-return input for Windows OpenSSH/conhost.
- Added output cleanup for ANSI/control sequences and internal sentinel lines.
- Validated real Windows/WSL execution on machine `windows-wsl` using only `/mnt/c/Users/example/Desktop/SSHRunner`.

Validation evidence:

- `python3 -m pytest tests/test_remote_runner_mvp.py -q` passed: 15 passed.
- `python3 -m pytest -q` passed: 36 passed, 1 skipped, 73 warnings.
- `./scripts/harness-check.sh` passed: 0 warnings.
- `python3 -m black --check seed_runner/remote_machine.py seed_runner/remote_cli.py seed_runner/remote_backend.py tests/test_remote_runner_mvp.py` passed.
- `git diff --check` passed.
- Tail whitespace scan passed with no matches.
- Real `machine doctor 'windows-wsl' --json` passed after `startup_commands=["wsl"]` and `default_cwd=/mnt/c/Users/example/Desktop/SSHRunner`.
- Real `session exec` created, read, and removed `rr_probe.txt` inside SSHRunner, then a read-only `pwd && printf` command was re-run successfully.

Remaining boundary:

- Real SFTP put/get/list is not yet validated.
- Do not create, copy, or delete Windows files outside the SSHRunner directory in follow-up tests.

## Done Definition

- Startup commands are persisted and visible in redacted machine JSON.
- Existing machines can be configured with startup commands without re-entering credentials.
- Windows WSL validation succeeds without touching files outside SSHRunner.
- Harness feature evidence, progress, and handoff are updated.
