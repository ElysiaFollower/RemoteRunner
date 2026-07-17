---
name: remote-runner
description: Use when an agent should work through a persistent local shell managed by Remote Runner, including transparent SSH login, long terminal tasks, transcript inspection, or human tmux collaboration.
metadata:
  short-description: Use a transparent persistent shell
---

# Remote Runner

Remote Runner provides one real local shell per Session. Treat it exactly like a human terminal.
The tool does not understand commands, infer busy/completion, create remote tmux automatically, or
run hidden batch/file protocols.

## Start

List current Sessions and choose a readable name:

```bash
remote-runner session list
remote-runner session create --name <readable-name>
```

For a configured login profile:

```bash
remote-runner instance list
remote-runner session create --name <readable-name> --instance <instance-name>
```

An Instance only runs an inspectable bootstrap hook through the same terminal Interface. If it
fails, use the returned Session ID, transcript, and diagnostic path to take over manually.

## Normal terminal loop

1. Query state separately:

```bash
remote-runner session show --session <name>
```

Check `session_status`, `time_since_last_rr_input_ms`, `time_since_last_output_ms`,
`transcript_end_cursor`, and `transcript_path`. These are direct facts, not command status.

2. Inspect the newest raw terminal output:

```bash
remote-runner session tail --session <name> --bytes 8192
```

Before sending a new shell command, confirm that the visible shell prompt has returned. If a
foreground program is asking for a password, confirmation, debugger command, or REPL input, answer
that program instead. Never treat a fixed sleep or quiet output as completion.

3. Send exactly one line:

```bash
remote-runner session send --session <name> --input '<one line>'
```

Then return to `tail`. `send` returns a `read_from_cursor` anchor but never returns or stores the
input itself.

4. Send terminal keys explicitly:

```bash
remote-runner session key --session <name> C-c
remote-runner session key --session <name> C-d
remote-runner session key --session <name> Tab
```

Use `C-c` to interrupt a foreground process, then inspect the tail until the prompt is visible.

## Exact history

`tail` is an explicit newest-window view. When every byte in a range matters:

```bash
remote-runner session read \
  --session <name-or-id> \
  --from <cursor> \
  --max-bytes 65536 \
  --json
```

Continue from `next_read_cursor`. RR never stores a hidden reader cursor, skips output, compresses
history, or summarizes the transcript. If the CLI view is inconvenient, read the absolute
`transcript_path` from `session show` with ordinary local tools.

## SSH and remote persistence

SSH is ordinary visible terminal input:

```bash
remote-runner session send --session <name> --input 'ssh <host-or-alias>'
```

Wait for and answer login prompts exactly as a human would. Password input is not terminal-echoed;
RR also does not persist sent input. Long-idle SSH connections may disconnect. RR guarantees only
the local tmux shell, not remote-shell or remote-process survival. When remote persistence matters,
choose remote tmux, Slurm, `nohup`, or another mechanism explicitly in the shell.

## Single operator and parallel work

One Session has one current operator. Never let multiple Agents send into the same Session. Create
one readable Session per parallel task. Reads may happen concurrently, but terminal input must have
one owner.

## Human collaboration

`session show` returns `tmux_session_name`. Tell the human:

```bash
tmux attach-session -t <tmux_session_name>
```

Do not type concurrently. Human-visible input and output enter the same transcript, so the Agent can
observe the result after control returns.

## Lost and cleanup

If state is `lost`, the tmux pane no longer exists. RR will not fabricate a replacement. Historical
`read/tail` still works by Session ID. Finish the lifecycle and create a new shell:

```bash
remote-runner session destroy --session <name-or-id>
remote-runner session create --name <name>
```

Destroy preserves history and releases the name. Purge only when permanent deletion is explicitly
required and the exact destroyed Session ID is available.
