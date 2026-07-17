# Remote Runner Local Terminal V4 Requirements

## 1. Product Goal

Remote Runner must let an Agent use and observe a persistent shell exactly as a human would: send
visible terminal input, receive continuing output, inspect state when needed, and collaborate with a
human attached to the same tmux pane.

The tool must remain transparent. It does not understand shell commands, SSH, remote operating
systems, prompts, jobs, or command completion.

## 2. Supported Environment

- Host platform: macOS or Linux.
- Required host dependency: tmux.
- Runtime: Python 3.10+.
- Remote targets: unrestricted; the Agent may type SSH or another connector into the local shell.
- Windows host execution and Windows-specific Session implementation: unsupported.

## 3. Session Requirements

### 3.1 Identity

- Every Session receives a never-reused `session_id` UUID.
- Every live Session has a readable `session_name`, unique across active/lost Sessions.
- Name lookup is for active/lost use; historical lookup uses exact ID.
- Destroy releases the name. A new Session may reuse it but receives a different ID and storage.
- The tmux Session name must be readable, unique, and returned by `session show`.

### 3.2 Creation and capture

- `session create` creates one local tmux pane and starts the chosen login shell.
- `pipe-pane` must write to a private append-only transcript before the real shell emits its first
  byte.
- State and transcript files must default to user-only permissions.
- The Session must persist across independent RR CLI invocations while tmux remains alive.

### 3.3 Input

- `session send` accepts exactly one UTF-8 line, pastes it into the pane, and sends Enter.
- It returns only `session_name` and the transcript byte position immediately before input.
- Raw input must not be returned or persisted. RR must avoid putting bootstrap secrets in process
  arguments.
- `session key` sends one documented tmux key such as `C-c`, `C-d`, `Tab`, arrow, or Enter.
- No `interrupt` compatibility alias exists.
- RR never retries a failed input automatically. If delivery is uncertain, the error tells the
  caller to inspect the transcript.

### 3.4 Observation

- The transcript stores raw pane bytes without ANSI cleaning, screen reconstruction, compression,
  rotation, summarization, or completion inference.
- `read --from N --max-bytes M` performs one bounded range read from a single file-size snapshot.
- `tail --bytes M` performs one bounded newest-range read from a single snapshot.
- Neither operation stores a hidden reader cursor.
- Raw bytes are the default CLI output. `--json` adds only the output text and cursor values required
  by that operation.
- `session show` is the only Session state query and includes the absolute transcript path.

### 3.5 State

Lifecycle values are:

```text
active / lost / destroyed
```

State must include:

- identity: `session_id`, `session_name`;
- lifecycle: `session_status`, `created_at`, `lost_at`, `destroyed_at`;
- terminal location: `tmux_session_name`, `tmux_pane_id`, `initial_cwd`, `local_shell_path`;
- bootstrap provenance: `instance_name`, `bootstrap_status` and timestamps when applicable;
- observation: `last_rr_input_at`, `time_since_last_rr_input_ms`, `last_output_at`,
  `time_since_last_output_ms`, `transcript_path`, `transcript_end_cursor`.

The names must describe facts directly. No `busy`, `idle`, `command_elapsed`, prompt, completion, or
exit-code field is permitted.

### 3.6 Attach and lifecycle

- A human may attach directly to the returned tmux Session.
- Human input that the TTY echoes and resulting output must enter the same transcript.
- Human input must not update `last_rr_input_at`; that field explicitly means RR-mediated input.
- If the stored pane or its transcript recorder disappears, `show` marks the Session lost.
  `send/key/attach` return
  `session_lost`; `read/tail` remain available.
- `destroy` kills an existing tmux Session if present, marks history destroyed, and is idempotent for
  already-missing tmux.
- `purge` accepts only a destroyed exact Session ID and requires the same ID as confirmation.

## 4. Instance/bootstrap Requirements

- An Instance record contains only a safe name, absolute bootstrap path, and timestamps.
- The bootstrap file exports `bootstrap(session)` with exactly one parameter.
- The hook receives normal `send/key/read/tail/show` operations; it has no direct state mutation
  privilege through the supplied object.
- The hook decides when prompts have appeared and what to send next. RR provides no prompt DSL or
  SSH state machine.
- `session create --instance` runs bootstrap synchronously in an isolated process under the Session
  writer lock.
- Completion, exception, or timeout ends that process before `create` returns.
- Failure and timeout leave the Session active, preserve transcript, mark bootstrap state, and return
  a private diagnostic path.
- A hook may read passwords from environment or local configuration. Normal TTY no-echo controls
  transcript visibility.

## 5. Concurrency

- A Session is single-operator by contract.
- `send/key` hold a per-Session writer lock only during one input operation.
- Bootstrap holds the writer lock for its full run.
- `read/tail/show` do not acquire the writer lock.
- Parallel Agent work uses separate Sessions.

## 6. Error Contract

- RR success exits zero.
- RR usage failure exits 2; operational/internal failure exits nonzero.
- RR errors write one compact JSON object to stderr with stable `error.code` and actionable
  `error.message`; stdout remains empty.
- Known recovery facts may accompany the error. Unavailable fields are omitted, not filled with
  misleading nulls.
- Unexpected RR exceptions use `internal_error` and, when possible, a private diagnostic path.
- A command failing inside the shell is not an RR error and appears only in the transcript.

## 7. State Compatibility

- State has an explicit product marker and schema version.
- A nonempty directory without the V4 schema, or a different schema version, is rejected without
  mutation.
- No old Remote Runner or seed-runner Session, machine, backend, command, file, run, or artifact
  migration is implemented.

## 8. Acceptance

- Default tests use an isolated tmux server socket and temporary state; no default/business tmux is
  created, locked, typed into, or destroyed.
- Real tmux tests cover initial-byte capture, state continuity, raw ANSI/CR bytes, RR input, external
  human input, no-echo secret input, Ctrl-C via `key`, lost/destroy/reuse/purge, and large bounded
  reads.
- Bootstrap tests cover success, failure, timeout, diagnostic preservation, and no post-return
  background input.
- CLI tests cover raw/JSON output, exact response keys, structured stderr errors, help, and absence of
  every legacy command.
