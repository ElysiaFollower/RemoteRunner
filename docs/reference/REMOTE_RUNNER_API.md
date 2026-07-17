# Remote Runner CLI Contract V4

All commands except `session read`, `session tail`, and interactive `session attach` return one
compact JSON object on stdout. RR failures write one compact JSON object to stderr and exit nonzero.

## State directory

The default is `~/.remote-runner`. Override it with `REMOTE_RUNNER_STATE_DIR` or the global option:

```bash
remote-runner --state-dir /path/to/state session list
```

The directory must be empty or contain the exact V4 schema. Legacy state is rejected without
mutation.

## Instance

### Add

```bash
remote-runner instance add --name gpu-a --bootstrap ~/.config/rr/gpu_a.py
```

```json
{"instance_name":"gpu-a","bootstrap_path":"/abs/gpu_a.py","created_at":"...","updated_at":"..."}
```

Use `--replace` to point an existing Instance at a different hook explicitly.

### List/show/remove

```bash
remote-runner instance list
remote-runner instance show --instance gpu-a
remote-runner instance remove --instance gpu-a
```

An Instance is a bootstrap profile only. It contains no host, backend, platform, shell, or hidden
transport.

## Session create

```bash
remote-runner session create \
  --name project \
  --cwd /path/to/project \
  --shell /bin/zsh
```

Optional bootstrap:

```bash
remote-runner session create \
  --name gpu-work \
  --instance gpu-a \
  --bootstrap-timeout 60
```

If `--name` is omitted, RR generates a short `shell-xxxxxx` name. Names start with a letter or number,
contain at most 64 letters, numbers, `.`, `_`, or `-`, and are unique across active/lost Sessions.

Success returns the same state shape as `session show`. Bootstrap failure or timeout is an RR error,
but its payload includes the preserved Session name, ID, and diagnostic path.

## Session show/list

```bash
remote-runner session show --session project
remote-runner session list
remote-runner session list --all
```

`--session` resolves an exact ID first, otherwise an active/lost name. Destroyed history is queried
by exact ID. `--all` includes destroyed Sessions.

State fields:

```json
{
  "session_id":"sess_<uuid>",
  "session_name":"project",
  "session_status":"active",
  "tmux_session_name":"rr-project-<short-id>",
  "tmux_pane_id":"%1",
  "initial_cwd":"/path/to/project",
  "local_shell_path":"/bin/zsh",
  "instance_name":null,
  "bootstrap_status":"not_requested",
  "created_at":"...",
  "lost_at":null,
  "destroyed_at":null,
  "last_rr_input_at":"...",
  "time_since_last_rr_input_ms":123,
  "last_output_at":"...",
  "time_since_last_output_ms":45,
  "transcript_path":"/absolute/path/transcript.log",
  "transcript_end_cursor":8192
}
```

Bootstrap Sessions additionally contain `bootstrap_started_at`, `bootstrap_ended_at`, and
`bootstrap_log_path`.

`initial_cwd` and `local_shell_path` describe how RR created the local terminal. They deliberately
do not claim to be the shell's current directory or the program currently running in the pane.

## Session send

```bash
remote-runner session send --session project --input 'pwd'
```

```json
{"session_name":"project","read_from_cursor":8192}
```

The cursor is the transcript end observed immediately before input. RR sends the exact UTF-8 text,
then Enter. Newline or carriage return inside the input is rejected.

For input that must not appear in process arguments:

```bash
printf %s "$VALUE" | remote-runner session send --session project --stdin
```

`--stdin` accepts one optional trailing LF or CRLF as the line delimiter; any other newline is
rejected. RR never returns or stores the input. Whether it appears in the transcript is controlled
by normal TTY echo.

## Session key

```bash
remote-runner session key --session project C-c
remote-runner session key --session project C-d
remote-runner session key --session project Tab
```

The response has the same two fields as `send`. Supported key names are ordinary alphanumeric keys,
`C-`/`M-`/`S-` variants, Space, Tab, Enter, Escape, BSpace, DC, Home, End, arrows, PageUp/PageDown, and
F1-F12. There is no separate `interrupt` command.

## Session read

Raw default:

```bash
remote-runner session read --session project --from 8192 --max-bytes 65536
```

Structured range:

```bash
remote-runner session read --session project --from 8192 --max-bytes 65536 --json
```

```json
{"output":"...","next_read_cursor":9000,"transcript_end_cursor":12000}
```

`output` is a UTF-8 replacement view in JSON. Cursor values always address raw bytes; the raw default
and `transcript_path` preserve exact bytes.

## Session tail

```bash
remote-runner session tail --session project --bytes 8192
remote-runner session tail --session project --bytes 8192 --json
```

```json
{"output":"...","output_start_cursor":3810,"transcript_end_cursor":12002}
```

Neither read nor tail changes hidden state, waits, cleans output, or interprets the prompt.

## Session attach

```bash
remote-runner session attach --session project
```

This process becomes `tmux attach-session`. Detach with the normal tmux key binding. A human may also
read `tmux_session_name` from `show` and attach directly.

## Session destroy/purge

```bash
remote-runner session destroy --session project
```

Destroy kills tmux if present, marks history destroyed, and releases the public name. It preserves
state and transcript.

```bash
remote-runner session purge \
  --session-id sess_<uuid> \
  --confirm sess_<uuid>
```

Purge only accepts a destroyed exact ID. On success it returns the purged ID.

## Bootstrap hook Interface

```python
import os
import time

def bootstrap(session):
    anchor = session.send("ssh gpu-a")["read_from_cursor"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        observed = session.read(anchor, 65536)
        if b"password:" in observed.output:
            session.send(os.environ["GPU_PASSWORD"])
            return
        time.sleep(0.1)
    raise RuntimeError("SSH password prompt did not appear")
```

The object exposes `session_id`, `session_name`, `send`, `key`, `read`, `tail`, and `show`. It does not
provide prompt matching or SSH semantics.

## RR error shape

```json
{"error":{"code":"session_lost","message":"..."},"session_name":"project","session_id":"..."}
```

Stable codes cover usage, state, tmux, Session lifecycle, input uncertainty, transcript access, and
bootstrap failures. An unexpected internal error uses `internal_error` and may include a private
`diagnostic_path`. A shell command's exit status is never an RR error.
