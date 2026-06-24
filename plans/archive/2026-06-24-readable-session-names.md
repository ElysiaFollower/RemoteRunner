<!--
Responsibility: define one completed task contract for implementation agents, making scope, acceptance, validation, and handoff executable.
Boundary: do not accumulate long-term architecture facts, raw logs, or unrelated follow-up ideas here.
-->

# Readable Session Names

## Goal

Resolve the local `docs/issues/` item by adding optional human-readable names to Remote Runner
sessions while keeping `session_id` as the immutable primary key.

## Non-Goals

- Do not replace `session_id` or change log directory naming.
- Do not add tags, aliases, automatic naming, UI behavior, or machine-scoped session selectors.
- Do not change remote tmux or Windows agent resource names exposed by backends.
- Do not run real-machine opt-in tests unless local behavior suggests backend risk.

## Acceptance Criteria

- `remote-runner session create --name <name>` persists and returns `name`.
- `session show/exec/command list/show/wait/stop/send/read/logs/destroy` accept either a
  `session_id` or a unique session name through the existing `--session` parameter.
- `file put/get/list` accept either a `session_id` or a unique session name.
- Names are optional and validated as short CLI-safe labels using letters, digits, `.`, `_`, and `-`.
- Names beginning with `sess_` are rejected so they cannot be confused with generated IDs.
- Duplicate non-destroyed names on the same machine are rejected; destroyed sessions do not block reuse.
- Ambiguous name resolution fails with a clear error and does not execute the requested operation.
- Existing sessions without `name` continue to work by `session_id`.
- The local issue file is removed after the feature is represented in code, tests, docs, and harness.

## Verification

```sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m remote_runner.cli session create --help
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

Evidence collected on 2026-06-24:

- `tests/test_remote_runner_mvp.py`: `45 passed`
- `remote_runner.cli session create --help`: includes `--name`
- `tests/test_remote_runner_launch_suite.py`: `2 passed, 1 skipped`
- `tests/test_remote_runner_real_integration.py`: `2 skipped`
- Full test suite: `68 passed, 4 skipped`
- Harness check: `0 warnings`
- `git diff --check`: passed
- `docs/issues/`: no remaining files

## Done Definition

- Code and tests implement readable session names across session and file commands.
- API docs, requirements, getting-started, skill, feature list, progress, and handoff are synchronized.
- `docs/issues/` no longer contains the resolved temporary issue.
