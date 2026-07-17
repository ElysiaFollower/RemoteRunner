# Core Lighthouse

## Immutable Goal

```text
Agent or human -> one persistent local shell -> visible input/output -> durable raw transcript
```

Remote Runner exists to create a clear information environment, not to compensate for an allegedly
incapable Agent. Every operation must remain understandable as normal terminal use.

## Invariants

1. A Session is one local tmux pane and one real shell.
2. The transcript is the pane's raw append-only output stream and the authoritative interaction
   history.
3. The recorder is active before the real shell starts, so the initial prompt cannot be missed.
4. `send` means one UTF-8 text line plus Enter; `key` means one explicit terminal key.
5. RR never stores or returns raw input. Normal commands appear through TTY echo; passwords do not.
6. `read` and `tail` are stateless byte-range observations. No hidden reader cursor exists.
7. State contains direct facts only. RR never infers busy, prompt, completion, exit status, or remote
   process survival.
8. One Session has one current operator. Parallel work uses independent Sessions.
9. A short writer lock prevents interleaved input; bootstrap holds it for its full synchronous run.
10. Human attach is first-class. Human and Agent activity shares the same pane and transcript.
11. Destroy preserves history; purge is the only deletion operation and requires exact UUID
    confirmation.
12. A missing tmux pane or transcript recorder marks a Session lost; RR never creates a replacement
    that masquerades as the old shell.

## Responsibility Split

- The **Session Module** presents the small public Interface and owns lifecycle truth.
- The **tmux Terminal Module** hides process invocation details behind one deep local-terminal
  implementation.
- The **State Module** owns versioned durable records and file locks.
- An **Instance bootstrap Module** is user code above the Session Interface. It may automate SSH or
  login steps, but RR core does not understand them.

This shape concentrates terminal mechanics and state mutation for high Locality. No speculative
Adapter seam exists because the product has only one supported terminal implementation.

## Transparency Rules

- No hidden shell wrappers, markers, injected exit-code probes, prompt parsers, output summaries,
  automatic retries, background bootstrap input, or implicit remote tmux.
- The Session state exposes the absolute transcript path, tmux Session name, and pane ID.
- Tool failures use structured stderr errors. A command failing inside the shell remains ordinary
  transcript content.
- Input failures are not automatically retried because duplicate terminal input can execute twice.

## Platform and Persistence Boundary

The host must be macOS or Linux with tmux. A remote Linux, macOS, or Windows shell may be reached by
typing SSH into the local shell.

RR guarantees persistence across separate RR CLI invocations while the local tmux pane survives. It
does not guarantee survival across host reboot, tmux deletion, SSH disconnection, or remote machine
failure. Remote persistence mechanisms are explicit Agent decisions and belong in the Skill, not
the core.

## Rejected Designs

- separate local-tmux, remote-tmux, and Windows-pipe Session implementations;
- machine/backend enums that bundle authentication, operating system, files, and terminal behavior;
- per-operation SSH control connections as the terminal abstraction;
- automatic remote tmux creation after SSH;
- batch exec or file protocols injected into the live pane;
- compatibility aliases or legacy state migration in V4.
