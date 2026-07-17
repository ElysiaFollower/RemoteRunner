"""Command-line interface for transparent local persistent terminals."""

import argparse
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Dict, List, NoReturn, Optional

from remote_runner.errors import RemoteRunnerError, UsageError
from remote_runner.instance import InstanceManager
from remote_runner.session import ReadResult, SessionManager, TailResult
from remote_runner.state import StateStore
from remote_runner.tmux import TmuxTerminal


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


def _write_json(payload: Dict[str, Any], *, stream: Any = sys.stdout) -> None:
    stream.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    stream.flush()


def _add_session_ref(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--session", required=True, help="Active Session name or exact Session ID")


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="remote-runner")
    parser.add_argument(
        "--state-dir",
        help="Local state directory (default: REMOTE_RUNNER_STATE_DIR or ~/.remote-runner)",
    )
    groups = parser.add_subparsers(dest="resource", required=True)

    instance = groups.add_parser("instance", help="Manage optional bootstrap profiles")
    instance_commands = instance.add_subparsers(dest="instance_command", required=True)

    instance_add = instance_commands.add_parser("add", help="Register a bootstrap hook")
    instance_add.add_argument("--name", required=True)
    instance_add.add_argument("--bootstrap", required=True)
    instance_add.add_argument("--replace", action="store_true")
    instance_add.set_defaults(handler=_instance_add)

    instance_list = instance_commands.add_parser("list", help="List bootstrap profiles")
    instance_list.set_defaults(handler=_instance_list)

    instance_show = instance_commands.add_parser("show", help="Show one bootstrap profile")
    instance_show.add_argument("--instance", required=True)
    instance_show.set_defaults(handler=_instance_show)

    instance_remove = instance_commands.add_parser("remove", help="Remove a bootstrap profile")
    instance_remove.add_argument("--instance", required=True)
    instance_remove.set_defaults(handler=_instance_remove)

    session = groups.add_parser("session", help="Operate persistent local terminal Sessions")
    session_commands = session.add_subparsers(dest="session_command", required=True)

    session_create = session_commands.add_parser("create", help="Create a local tmux shell")
    session_create.add_argument("--name")
    session_create.add_argument("--cwd")
    session_create.add_argument("--shell")
    session_create.add_argument("--instance")
    session_create.add_argument("--bootstrap-timeout", type=float, default=60.0)
    session_create.set_defaults(handler=_session_create)

    session_list = session_commands.add_parser("list", help="List Sessions")
    session_list.add_argument("--all", action="store_true", help="Include destroyed Sessions")
    session_list.set_defaults(handler=_session_list)

    session_show = session_commands.add_parser("show", help="Show Session state")
    _add_session_ref(session_show)
    session_show.set_defaults(handler=_session_show)

    session_send = session_commands.add_parser("send", help="Send one text line and Enter")
    _add_session_ref(session_send)
    send_input = session_send.add_mutually_exclusive_group(required=True)
    send_input.add_argument("--input", help="One line of terminal input")
    send_input.add_argument(
        "--stdin",
        action="store_true",
        help="Read the one input line from stdin instead of process arguments",
    )
    session_send.set_defaults(handler=_session_send)

    session_key = session_commands.add_parser("key", help="Send one named terminal key")
    _add_session_ref(session_key)
    session_key.add_argument("key", help="For example C-c, C-d, Tab, Up or Enter")
    session_key.set_defaults(handler=_session_key)

    session_read = session_commands.add_parser("read", help="Read a transcript byte range")
    _add_session_ref(session_read)
    session_read.add_argument("--from", dest="from_cursor", type=int, default=0)
    session_read.add_argument("--max-bytes", type=int, default=65536)
    session_read.add_argument("--json", action="store_true")
    session_read.set_defaults(handler=_session_read)

    session_tail = session_commands.add_parser("tail", help="Read the newest transcript bytes")
    _add_session_ref(session_tail)
    session_tail.add_argument("--bytes", dest="max_bytes", type=int, default=8192)
    session_tail.add_argument("--json", action="store_true")
    session_tail.set_defaults(handler=_session_tail)

    session_attach = session_commands.add_parser("attach", help="Attach this terminal to tmux")
    _add_session_ref(session_attach)
    session_attach.set_defaults(handler=_session_attach)

    session_destroy = session_commands.add_parser("destroy", help="Stop tmux and preserve history")
    _add_session_ref(session_destroy)
    session_destroy.set_defaults(handler=_session_destroy)

    session_purge = session_commands.add_parser("purge", help="Delete destroyed Session history")
    session_purge.add_argument("--session-id", required=True)
    session_purge.add_argument("--confirm", required=True)
    session_purge.set_defaults(handler=_session_purge)

    return parser


def _instance_add(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.instances.add(args.name, args.bootstrap, replace=args.replace)


def _instance_list(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.instances.list()


def _instance_show(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.instances.show(args.instance)


def _instance_remove(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.instances.remove(args.instance)


def _session_create(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.create(
        name=args.name,
        cwd=args.cwd,
        shell=args.shell,
        instance_name=args.instance,
        bootstrap_timeout=args.bootstrap_timeout,
    )


def _session_list(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.list(include_destroyed=args.all)


def _session_show(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.show(args.session)


def _session_send(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    if args.stdin:
        raw = sys.stdin.buffer.read()
        if raw.endswith(b"\n"):
            raw = raw[:-1]
            if raw.endswith(b"\r"):
                raw = raw[:-1]
        try:
            line = raw.decode("utf-8")
        except UnicodeDecodeError as error:
            raise UsageError("stdin input must be valid UTF-8") from error
    else:
        line = args.input
    return context.sessions.send(args.session, line)


def _session_key(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.key(args.session, args.key)


def _session_read(args: argparse.Namespace, context: "CliContext") -> Any:
    result = context.sessions.read(
        args.session,
        from_cursor=args.from_cursor,
        max_bytes=args.max_bytes,
    )
    if args.json:
        return _read_json(result)
    return result.output


def _session_tail(args: argparse.Namespace, context: "CliContext") -> Any:
    result = context.sessions.tail(args.session, max_bytes=args.max_bytes)
    if args.json:
        return _tail_json(result)
    return result.output


def _session_attach(args: argparse.Namespace, context: "CliContext") -> "AttachAction":
    return AttachAction(context.sessions.attach_argv(args.session))


def _session_destroy(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.destroy(args.session)


def _session_purge(args: argparse.Namespace, context: "CliContext") -> Dict[str, Any]:
    return context.sessions.purge(args.session_id, confirm=args.confirm)


def _read_json(result: ReadResult) -> Dict[str, Any]:
    return {
        "output": result.output.decode("utf-8", errors="replace"),
        "next_read_cursor": result.next_read_cursor,
        "transcript_end_cursor": result.transcript_end_cursor,
    }


def _tail_json(result: TailResult) -> Dict[str, Any]:
    return {
        "output": result.output.decode("utf-8", errors="replace"),
        "output_start_cursor": result.output_start_cursor,
        "transcript_end_cursor": result.transcript_end_cursor,
    }


class AttachAction:
    def __init__(self, argv: List[str]) -> None:
        self.argv = argv


class CliContext:
    def __init__(self, *, state_dir: Optional[str] = None) -> None:
        store = StateStore(Path(state_dir)) if state_dir else StateStore()
        terminal = TmuxTerminal()
        self.sessions = SessionManager(store=store, terminal=terminal)
        self.instances = InstanceManager(store)
        self.store = store


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    context: Optional[CliContext] = None
    try:
        args = parser.parse_args(argv)
        context = CliContext(state_dir=args.state_dir)
        result = args.handler(args, context)
        if isinstance(result, AttachAction):
            os.execvp(result.argv[0], result.argv)
        if isinstance(result, bytes):
            sys.stdout.buffer.write(result)
            sys.stdout.buffer.flush()
        else:
            _write_json(result)
        return 0
    except RemoteRunnerError as error:
        _write_json(error.payload(), stream=sys.stderr)
        return error.exit_code
    except KeyboardInterrupt:
        interrupt_error = RemoteRunnerError(
            "interrupted", "Remote Runner was interrupted", exit_code=130
        )
        _write_json(interrupt_error.payload(), stream=sys.stderr)
        return interrupt_error.exit_code
    except Exception:
        diagnostic_path = None
        if context is not None:
            diagnostic_path = context.store.write_diagnostic(traceback.format_exc())
        payload: Dict[str, Any] = {
            "error": {
                "code": "internal_error",
                "message": "Remote Runner encountered an unexpected internal error",
            }
        }
        if diagnostic_path is not None:
            payload["diagnostic_path"] = str(diagnostic_path)
        _write_json(payload, stream=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
