<!--
Responsibility: define one completed task contract for implementation agents, making scope, acceptance, validation, and handoff executable.
Boundary: do not accumulate long-term architecture facts, raw logs, or unrelated follow-up ideas here.
-->

# Stale tmux Session Recovery

## Goal

Prevent agents from wasting effort on Remote Runner sessions or commands that are locally marked
`active`, `busy`, or `running` after the remote tmux session has already disappeared.

## Non-Goals

- Do not delete historical local logs, transfer records, or remote `.remote-runner` command state.
- Do not kill unknown remote training jobs or unrelated tmux sessions.
- Do not change the normal successful Linux/tmux persistent shell flow.
- Do not solve all timeout semantics in this slice; timed-out but still-live tmux commands may
  continue to be polled normally.

## Acceptance Criteria

- `session command show/wait` must not keep reporting `running` forever when the corresponding
  remote tmux session is gone.
- A `busy=true` session with only an `active_command` must recover to a failed command when the
  remote tmux session is gone.
- A session whose remote tmux session is gone must become `lost`, and later `session exec` must
  reject it instead of attempting to send input to a missing tmux target.
- Existing successful wait/background command paths must keep passing.
- The fix must be validated against a real stale configured Linux/tmux machine state without writing secrets or host
  details into repository files.

## Verification

```sh
python3 -m py_compile remote_runner/remote_backend.py remote_runner/remote_session.py tests/test_remote_runner_mvp.py
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<linux_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q
REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<linux_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

Real-machine evidence was collected on a configured Linux/tmux machine with historical stale
Remote Runner state:

- `command show` changed a stale `running` command to `failed` with an explanatory `error`.
- `session show` changed a stale `busy` session to `lost`, cleared `busy`, and recorded the
  reserved command as `failed`.
- A fresh pressure self-test covered large stdout truncation, silent wait, background polling/wait,
  synchronous timeout recovery, background stop, file transfer, run once, lost-session recovery,
  final exec, cleanup, and destroy.
- A second Linux/tmux machine deep self-test covered persistent shell state, timeout recovery,
  background wait, file transfer, run once, lost-session recovery, cleanup, and destroy.
- Real opt-in tests passed: `tests/test_remote_runner_real_integration.py` reported `1 passed, 1 skipped`;
  `tests/test_remote_runner_launch_suite.py` reported `3 passed`.

## Done Definition

- Code and tests implement the stale-state recovery behavior.
- `F-023` is marked `passing` with verification evidence.
- `harness/progress.md` and `harness/session-handoff.md` describe current state and next action.
