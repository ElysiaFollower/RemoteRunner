# Remote Runner SSH Machine Configuration Interface

## Task Contract

Make `remote-runner machine add` usable for entering real SSH machine information before real
SSH/SFTP integration testing.

The primary path is interactive CLI input. Missing fields are prompted one by one; password input is
hidden; JSON output remains machine-readable.

## Goals

- Allow `remote-runner machine add --json` to prompt for missing machine fields.
- Store password machines in `~/.remote-runner/machines.json` with existing 0600 file permissions.
- Keep JSON stdout free of prompts and credentials.
- Add explicit same-name replacement with confirmation.
- Keep current non-interactive flag workflow compatible for scripts and tests.

## Non-Goals

- Do not run real SSH/SFTP integration tests in this task.
- Do not add system keychain, SSH agent, or `~/.ssh/config` parsing.
- Do not add `machine update`; replacement is handled through `machine add --replace`.
- Do not migrate package name away from `seed_runner`.
- Do not change legacy `seed-runner` mount/session behavior.

## Implementation Sequence

1. Add interactive input helpers in the Remote Runner CLI.
2. Make `machine add` flags optional and prompt for missing fields.
3. Use hidden password input for password auth.
4. Add `--replace` and `--confirm-replace` with strict confirmation semantics.
5. Update `RemoteMachineManager.add()` to support replacement while preserving `created_at`.
6. Add focused tests for interactive input, replacement, JSON cleanliness, and key-path validation.
7. Update docs and harness evidence.

## Verification

Required commands:

```bash
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

If `git diff --check` is blocked by local Xcode license state, record that explicitly and use
available pytest/harness validation.

## Completion

Completed locally on 2026-05-08.

- Implemented interactive `remote-runner machine add` for missing machine fields.
- Kept prompts on stderr so `--json` stdout remains one JSON object.
- Used hidden password input for password auth.
- Added `--replace` and `--confirm-replace` with exact machine ID confirmation.
- Preserved `created_at` and wrote `updated_at` on replacement.
- Updated README, requirements, API contract, spec, tests, feature evidence, progress, quality, and handoff.

Validation:

- `python3 -m pytest tests/test_remote_runner_mvp.py -q` passed: 13 passed.
- `python3 -m black --check seed_runner/remote_machine.py seed_runner/remote_cli.py tests/test_remote_runner_mvp.py` passed.
- `./scripts/harness-check.sh` passed: 0 warnings.
- `python3 -m pytest -q` passed: 34 passed, 1 skipped, 68 warnings.
- Tail whitespace scan passed with no matches.
- `git diff --check` was blocked by local Xcode license state.

## Done Definition

- `remote-runner machine add` can be used interactively to enter real machine host/IP, port, user,
  auth type, password or key path, and default cwd.
- Prompt text goes to stderr; stdout is one JSON object under `--json`.
- Password values are not printed in JSON or test output.
- Same-name replacement requires explicit confirmation and preserves existing sessions/logs/transfers.
- Harness feature list, progress, and handoff are updated.
