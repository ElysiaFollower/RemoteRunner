# Remote Runner Machine, Session, and File Transfer MVP

## Task Contract

Prepare and then implement the first mount-free Remote Runner core:

```text
machine registry -> session in remote cwd -> command exec -> local logs/state -> explicit file transfer
```

This active plan covers the first implementation phase after the positioning and harness reset.

## Goals

- Add a target `remote-runner` CLI surface for machine, session, exec, logs, and file transfer.
- Move target state to `~/.remote-runner/`.
- Make local state the source of recovery for machines, sessions, commands, transfers, and artifacts.
- Remove mount from the target architecture while preserving legacy `seed-runner` behavior.
- Prefer SSH/SFTP for MVP command execution and file movement.

## Non-Goals

- Do not delete legacy mount code in this phase.
- Do not complete package-wide rename from `seed_runner`.
- Do not build research, SEED, operations, training, or benchmark profiles.
- Do not add a daemon, GUI, MCP server, or enterprise credential integration.

## Implementation Sequence

1. State and config foundation
   - Add Remote Runner state root resolution.
   - Add machine records with credential redaction.
   - Add session, command, transfer, and artifact manifest persistence.
2. Machine CLI
   - Implement `machine add/list/show/doctor/remove --json`.
   - Ensure `doctor` checks auth and remote cwd without printing credentials.
3. Session and exec CLI
   - Implement `session create/list/show/exec/logs/destroy --json`.
   - Execute commands directly in remote cwd and persist command result plus local log.
4. File transfer CLI
   - Implement `file put/get/list --json` through SSH/SFTP.
   - Persist transfer records including failure records.
5. Compatibility and documentation
   - Keep legacy `seed-runner` tests green.
   - Update public docs and harness evidence when behavior lands.

## Verification

During implementation, add tests for:

- machine config add/list/show redaction and doctor success/failure
- session create/list/show/exec/logs/destroy without mount
- non-zero exit code preserving logs and session
- file put/get/list success, missing path, permission failure, and state persistence
- legacy `seed-runner` tests still passing

Standard commands:

```bash
./scripts/harness-check.sh
python3 -m pytest tests/test_config.py tests/test_workflow_state.py -q
python3 -m pytest -q
```

Run real VM tests only when a machine is explicitly configured:

```bash
SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q
```

## Completion

Completed locally on 2026-05-08.

- Implemented target `remote-runner` console script while keeping package name `seed_runner`.
- Added mount-free Remote Runner state, machine, SSH/SFTP backend, session, file transfer, and CLI modules.
- Persisted machines, sessions, command logs, transfer JSONL, and artifact manifest under `~/.remote-runner/`.
- Added busy protection for concurrent exec on the same session.
- Kept legacy `seed-runner` tests passing.

Validation:

- `python3 -m pytest tests/test_remote_runner_mvp.py -q` passed: 6 passed.
- `python3 -m black --check seed_runner/remote_state.py seed_runner/remote_machine.py seed_runner/remote_backend.py seed_runner/remote_session.py seed_runner/remote_file.py seed_runner/remote_cli.py tests/test_remote_runner_mvp.py` passed.
- `python3 -m pytest -q` passed: 27 passed, 1 skipped, 59 warnings.
- `./scripts/harness-check.sh` passed: 0 warnings.
- `git diff --check` passed.

Remaining boundary:

- Real remote SSH/SFTP integration was not run in this session.
- `remote-runner machine add` still needs an interactive or credential-reference path before password auth should be recommended.

## Risks

- CLI rename can expand scope; keep package rename separate unless it becomes necessary for the
  script entry point.
- Password auth support can leak via shell history if implemented only through flags; prefer
  interactive entry or config-file editing in MVP docs.
- SFTP directory transfer behavior needs careful test coverage; start with clear recursive semantics
  or explicitly document file-only MVP before widening.
- Existing mount/session state shape may conflict with new session state; keep legacy and target
  state keys separated.

## Done Definition

- `remote-runner` target commands exist and return JSON.
- Mount is not required for machine/session/file MVP.
- Local state records machines, sessions, commands, logs, transfers, and artifacts.
- Credentials are redacted from JSON and logs.
- New tests and legacy tests pass.
- Harness feature evidence and session handoff are updated.
