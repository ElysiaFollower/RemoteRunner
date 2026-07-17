# Getting Started

## 1. Verify the host

```bash
python3 --version
tmux -V
remote-runner --help
```

Remote Runner runs only on macOS/Linux with local tmux.

## 2. Start a named shell

```bash
remote-runner session create --name work
remote-runner session show --session work
```

Use a name another person can understand. `show` returns the exact tmux name and transcript path.

## 3. Observe before typing

```bash
remote-runner session tail --session work
```

Confirm the visible prompt before sending a new shell command. RR intentionally has no busy or
completion guess.

## 4. Use the terminal

```bash
remote-runner session send --session work --input 'pwd'
remote-runner session tail --session work
remote-runner session key --session work C-c
```

To work remotely, type SSH normally:

```bash
remote-runner session send --session work --input 'ssh my-host'
```

If SSH requests a password, wait until the prompt is visible and send it. The TTY disables echo, so
the password does not enter the transcript; RR also does not store or return sent input.

## 5. Read exact ranges

For normal observation, use `tail`. When every byte matters:

```bash
remote-runner session read --session work --from 0 --max-bytes 65536 --json
```

Continue from `next_read_cursor`. Read and tail never advance a hidden cursor.

## 6. Work with a human

Give the human `tmux_session_name` from `session show`:

```bash
tmux attach-session -t <tmux_session_name>
```

Both operators see the same shell. Do not type concurrently. Normal human input/output appears in
the same transcript.

## 7. Optional bootstrap

Create one inspectable hook per target Instance, register it, and create a Session:

```bash
remote-runner instance add --name gpu-a --bootstrap ~/.config/rr/gpu_a.py
remote-runner session create --name gpu-work --instance gpu-a
```

Bootstrap is synchronous. If it fails, inspect the returned Session and diagnostic path, then take
over through normal terminal operations.

## 8. Finish without deleting history

```bash
remote-runner session destroy --session work
```

Only use `session purge` with the exact destroyed UUID when the transcript and state should truly be
deleted.
