<!--
Responsibility: define one active task contract for implementation agents, making scope, acceptance, validation, and handoff executable.
Boundary: do not accumulate long-term architecture facts, raw logs, or unrelated follow-up ideas here.
-->

# Windows Agent PowerShell Backend

## Goal

Make direct Windows OpenSSH machines usable for the core Remote Runner session workflow by adding a Windows agent-backed backend that can create a persistent PowerShell session, execute commands in that same shell context, read transcript output, destroy the session, and support `run once` without breaking the existing Linux/tmux backend.

## Non-Goals

- Do not replace or refactor the existing Linux/SSH + tmux backend beyond the routing needed to select the Windows backend.
- Do not require administrator privileges, Windows Service installation, WSL, tmux, or a third-party Windows terminal multiplexer for the first P0 slice.
- Do not make `cmd.exe` a first-class target shell in this task; Windows P0 targets PowerShell 7 (`pwsh`).
- Do not add a GUI, daemon manager, profile layer, or full production installer in this task.

## Current Repo Facts

- Entry rules: `AGENTS.md`
- Bootstrap contract: `harness/bootstrap-contract.md`
- Current feature item: `F-022`
- Relevant files/modules: `remote_runner/remote_backend.py`, `remote_runner/remote_machine.py`, `remote_runner/remote_session.py`, `remote_runner/remote_run.py`, `remote_runner/cli.py`, `tests/test_remote_runner_mvp.py`, `tests/test_remote_runner_real_integration.py`, `docs/platform-support.md`, `docs/reference/REMOTE_RUNNER_API.md`
- Known constraints: current public `session` API is already the persistent shell abstraction; Linux uses tmux; a direct Windows OpenSSH test target has OpenSSH, SFTP, Python 3, and PowerShell 7 available.

## Allowed Changes

- Add machine capability fields such as platform/backend/shell while preserving old machine records.
- Add a Windows agent script/module and backend selection inside Remote Runner.
- Add CLI/config affordances needed to configure a Windows PowerShell agent backend.
- Add unit/fake tests and an opt-in real Windows integration path that only writes inside the configured test cwd.
- Update requirements/API/platform docs and harness state for the new support boundary.

## Forbidden Changes

- Do not remove or weaken existing Linux/tmux tests, behavior, or documentation.
- Do not persist passwords, keys, real hostnames, or private remote paths in docs, tests, handoff, logs, or feature evidence.
- Do not run real Windows tests outside `REMOTE_RUNNER_REAL_TEST_CWD`.
- Do not require admin-only install steps unless the user explicitly approves a later task.

## Acceptance Criteria

- A machine configured for direct Windows OpenSSH with `backend=windows-agent` and `shell=pwsh` can create a Remote Runner session.
- Repeated `session exec` calls on that Windows session preserve shell-local state, demonstrated with a cwd or environment variable set in one command and observed in a later command.
- `session read` returns a recoverable transcript/cursor for the Windows session.
- `session destroy` stops the remote agent/session state and preserves local session logs/transcript.
- `run once` works on the Windows backend for a simple command and default cleanup path.
- Existing Linux/tmux fake-backed tests continue to pass.

## Key Anchors

Matching check file: `plans/archive/2026-06-13-windows-agent-pwsh-backend.check.json`

- Windows agent implementation: proves the task does not rely on tmux, WSL, or transient one-shot SSH commands for Windows persistence.
- Backend routing/config: proves users can select Windows PowerShell behavior without forking the product API.
- Persistent shell test evidence: proves the same Windows session keeps state across multiple CLI commands.
- Documentation boundary: proves Windows is now a supported P0 backend path with explicit prerequisites and limits.

## Verification Commands

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_PLATFORM=windows REMOTE_RUNNER_REAL_MACHINE=<windows_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<windows_test_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q
git diff --check
```

## Evidence Recording

After verification passes, write the command, result, key output summary, or artifact path into `harness/feature_list.json` under `F-022.evidence`.

## Done Definition

- Requested Windows session behavior is implemented and verified locally.
- Non-goals remain untouched; Linux/tmux behavior remains passing.
- Key anchors are satisfied; if an anchor became invalid because the plan changed, the active plan and `.check.json` were updated first with the reason recorded.
- Verification commands above have run; commands not run are explained.
- `harness/feature_list.json` status and evidence are updated.
- Docs, tests, and harness files are updated for the new backend support boundary.
- `harness/session-handoff.md` names current state, risks, and next action.
- Clean-state checks are covered.

## Blockers

- Stop if the configured direct Windows test target loses SSH/SFTP access or cannot run PowerShell 7/Python, because real persistent-shell verification is part of the acceptance criteria.

## Next Best Action

1. Implement the smallest Windows agent protocol that can create, exec, read, and destroy a persistent `pwsh` session through SSH/SFTP.
