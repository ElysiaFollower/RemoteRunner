# Remote Runner Domain Language

## Session

One persistent local shell hosted by one tmux pane. A Session has an immutable Session ID, a
human-readable active name, lifecycle state, and one Transcript.

## Terminal

The local tmux pane that accepts text lines and named keys and emits the bytes captured by the
Transcript. The current product has exactly one Terminal implementation.

## Transcript

The raw append-only byte stream emitted by a Session's tmux pane. It includes visible TTY echo and
program output and excludes input the TTY does not echo.

## Instance

A named bootstrap profile pointing to one inspectable hook file. An Instance changes how a Session
is prepared; it does not change Terminal semantics.

## Bootstrap

A synchronous, exclusive hook that uses the normal Session Interface to obtain a desired shell.
The hook, not Remote Runner core, owns prompt recognition, authentication sequencing, SSH, `su`,
directory changes, and environment setup.
