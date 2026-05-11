---
name: remote-runner
description: Use when a task should be executed on a preconfigured remote machine through Remote Runner or the current seed-runner prototype, especially when an agent must run commands, inspect logs and artifacts, iterate on failures, and clean up sessions without using raw ssh, tmux, or sshfs directly.
metadata:
  short-description: Operate remote machines through agent-friendly sessions
---

# Remote Runner

Use this skill when the work must happen on a remote machine and the environment has already been
prepared for Remote Runner or the current `seed-runner` prototype.

Do not use this skill to modify or debug the Remote Runner implementation itself. This skill is for
application-layer execution on top of the tool.

## Read First

- Read `docs/reference/REMOTE_RUNNER_API.md` for the target machine/session contract.
- Read `docs/reference/SEED_RUNNER_API.md` when using the current `seed-runner` prototype.
- Read `AGENTS.md` for system boundaries and agent expectations.
- Read the chosen task or workspace materials before running remote commands.

## Current Implementation Note

The project is being repositioned from SEEDRunner to a generic remote-machine CLI, currently called
Remote Runner. The current executable is still `seed-runner`; the target executable is
`remote-runner`.

Use the implemented CLI that exists in the current branch. Do not pretend target commands are
available until the code implements them.

## Preconditions

- Assume machine configuration has been prepared by a human unless the user explicitly asks you to configure it.
- Do not ask for passwords, key contents, or jump-host details during normal task execution.
- Do not print credentials in logs, reports, or conversation summaries.
- Prefer the tool CLI over raw `ssh`, `tmux`, `sshfs`, `scp`, or `rsync`.
- Unless the user says otherwise, create and use a dedicated workspace for task files and outputs.
- Treat the workflow as end to end: understand the task, execute it, verify the result, write any requested report or summary, and clean up in one pass.

## Target Workflow

When the target Remote Runner CLI is available:

```bash
remote-runner machine list --json
remote-runner machine doctor <machine-id> --json
remote-runner session create --machine <machine-id> --cwd <remote-dir> --json
remote-runner session exec --session <session-id> --cmd "<shell-command>" --json
remote-runner session logs --session <session-id> --json
remote-runner session destroy --session <session-id> --json
```

After each command:

- inspect `exit_code`
- read `stdout` and `stderr`
- inspect `log_file_local`
- inspect artifact paths returned by the tool
- decide whether to continue, retry, or conclude

## Prototype Workflow

When using the current `seed-runner` prototype:

1. Choose a target workspace, commonly under `runs/` for historical SEED tasks.
2. Read task materials before issuing commands.
3. Choose a mount root directory such as `./workspace`. Under it, only `artifacts/` is reserved.
4. Create a mount:

```bash
seed-runner mount create --machine <machine-id> --local-dir ./workspace
```

If the default remote path is occupied, retry once with an explicit per-task path:

```bash
seed-runner mount create \
  --machine <machine-id> \
  --local-dir ./workspace \
  --remote-dir /home/seed/seed-experiments/<experiment-name>
```

5. Create a session:

```bash
seed-runner session create --machine <machine-id> --mount-id <mount-id> --name <session-name>
```

6. Execute commands:

```bash
seed-runner session exec --session <session-id> --cmd "<shell-command>"
```

7. Read the returned `log_file_local`, normally under `<local-dir>/artifacts/logs/<session-name>/`.
8. Inspect synced outputs under `<local-dir>/artifacts/`.
9. Destroy the session and then the mount when complete.

## Command Discipline

- Send complete shell commands, not partial fragments.
- Prefer non-interactive commands.
- Use a larger `--timeout` for long-running tasks instead of assuming the default is enough.
- Do not queue many blind commands before reading evidence from the previous one.
- Treat non-zero `exit_code` as task-level evidence. Read the log and retry strategically.
- If the session is busy, inspect status/logs before retrying.
- If a platform command fails, surface the exact JSON error instead of silently falling back to raw SSH.

## Completion Rules

A task using this skill is complete only when:

- the requested remote action has been carried out or a precise blocker has been identified
- the result is supported by logs or artifacts
- any requested report or summary has been written in the workspace
- sessions and mounts are cleaned up unless the user asked to keep them

In the final answer, include key IDs, important log/artifact paths, final status, and whether the acceptance criteria were met, partially met, or blocked.
