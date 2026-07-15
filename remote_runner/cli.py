"""CLI entry point for the mount-free Remote Runner target API."""

import argparse
import getpass
import sys
from typing import Any, Dict, List, Optional

from remote_runner.remote_backend import get_remote_backend
from remote_runner.remote_file import get_remote_file_manager
from remote_runner.remote_machine import get_remote_machine_manager
from remote_runner.remote_run import get_remote_run_manager
from remote_runner.remote_session import get_remote_session_manager
from remote_runner.utils import json_response


def _print(payload: Dict[str, Any]) -> None:
    print(json_response(payload))


def _handle_error(error: Exception) -> None:
    _print({"error": str(error)})
    sys.exit(1)


def _prompt(label: str, default: Optional[str] = None) -> str:
    suffix = f" [{default}]" if default is not None else ""
    print(f"{label}{suffix}: ", end="", file=sys.stderr, flush=True)
    value = sys.stdin.readline()
    if value == "":
        if default is not None:
            return default
        raise RuntimeError(f"{label} is required")
    value = value.rstrip("\n")
    if value == "" and default is not None:
        return default
    return value


def _prompt_required(label: str) -> str:
    while True:
        value = _prompt(label).strip()
        if value:
            return value
        print(f"{label} is required", file=sys.stderr)


def _prompt_port(default: int = 22) -> int:
    while True:
        value = _prompt("SSH port", str(default)).strip()
        try:
            return int(value)
        except ValueError:
            print("SSH port must be an integer", file=sys.stderr)


def _prompt_auth_type() -> str:
    while True:
        value = _prompt("Auth type (password/key)", "key").strip().lower()
        if value in {"password", "key"}:
            return value
        print("Auth type must be 'password' or 'key'", file=sys.stderr)


def _prompt_platform() -> str:
    while True:
        value = _prompt("Remote platform (linux/windows/mac)", "linux").strip().lower()
        if value in {"linux", "windows", "mac"}:
            return value
        print("Remote platform must be 'linux', 'windows', or 'mac'", file=sys.stderr)


def _prompt_password() -> str:
    password = getpass.getpass("SSH password: ", stream=sys.stderr)
    if not password:
        raise RuntimeError("SSH password is required")
    return password


def _prompt_startup_commands(existing: Optional[List[str]] = None) -> List[str]:
    commands = list(existing or [])
    if commands:
        print("Existing startup commands:", file=sys.stderr)
        for index, command in enumerate(commands, start=1):
            print(f"  {index}. {command}", file=sys.stderr)
    print(
        "Startup commands after SSH login, one per line. Blank line ends.",
        file=sys.stderr,
    )
    commands = []
    while True:
        command = _prompt("startup>").strip()
        if not command:
            return commands
        commands.append(command)


def _has_interactive_missing_fields(args: argparse.Namespace) -> bool:
    if args.backend == "openssh-pty" or getattr(args, "ssh_alias", None):
        return any(
            value in {None, ""}
            for value in (
                args.machine_id,
                getattr(args, "ssh_alias", None),
            )
        )
    return any(
        value in {None, ""}
        for value in (
            args.machine_id,
            args.host,
            args.user,
            args.auth_type,
        )
    )


def _machine_exists(machine_id: str) -> bool:
    try:
        get_remote_machine_manager().get(machine_id)
        return True
    except KeyError:
        return False


def _collect_machine_add_args(args: argparse.Namespace) -> Dict[str, Any]:
    interactive = _has_interactive_missing_fields(args)
    machine_id = args.machine_id or _prompt_required("Machine ID")
    backend = args.backend
    default_cwd = args.default_cwd
    ssh_alias = args.ssh_alias

    if backend is None and ssh_alias:
        backend = "openssh-pty"
    if backend == "openssh-pty":
        platform = args.platform or (_prompt_platform() if interactive else "linux")
        shell = args.shell or "bash"
        ssh_alias = ssh_alias or _prompt_required("SSH alias")
        host = args.host or "localhost"
        port = args.port if args.port is not None else 0
        user = args.user or ""
        auth_type = args.auth_type or "manual"
        password = None
        key_path = None
        startup_commands = args.startup_command or []
        if default_cwd in {None, ""}:
            default_cwd = _prompt("Default cwd after login", "~") if interactive else "~"
        confirm_replace = args.confirm_replace
        if args.replace and not confirm_replace and interactive and _machine_exists(machine_id):
            print(
                f"Machine '{machine_id}' already exists and will be replaced.",
                file=sys.stderr,
            )
            confirm_replace = _prompt_required(
                f"Type machine ID '{machine_id}' to confirm replacement"
            )
        return {
            "machine_id": machine_id,
            "host": host,
            "port": port,
            "user": user,
            "auth_type": auth_type,
            "password": password,
            "key_path": key_path,
            "ssh_alias": ssh_alias,
            "default_cwd": default_cwd,
            "startup_commands": startup_commands,
            "platform": platform,
            "backend": backend,
            "shell": shell,
            "replace": args.replace,
            "confirm_replace": confirm_replace,
        }

    host = args.host or _prompt_required("Host/IP")
    port = args.port if args.port is not None else (_prompt_port() if interactive else 22)
    user = args.user or _prompt_required("SSH user")
    auth_type = args.auth_type or _prompt_auth_type()
    platform = args.platform or (_prompt_platform() if interactive else "linux")
    if backend is None:
        backend = "windows-agent" if platform == "windows" else "ssh-tmux"
    shell = args.shell or ("pwsh" if backend == "windows-agent" else "bash")

    password = args.password
    key_path = args.key_path
    if auth_type == "password" and not password:
        password = _prompt_password()
    if auth_type == "key" and not key_path:
        key_path = _prompt_required("SSH key path")

    startup_commands = args.startup_command
    if startup_commands is None and interactive:
        startup_commands = _prompt_startup_commands()
    startup_commands = startup_commands or []

    if default_cwd in {None, ""}:
        default_cwd = _prompt("Default cwd after startup commands", "~") if interactive else "~"

    confirm_replace = args.confirm_replace
    if args.replace and not confirm_replace and interactive and _machine_exists(machine_id):
        print(
            f"Machine '{machine_id}' already exists and will be replaced.",
            file=sys.stderr,
        )
        confirm_replace = _prompt_required(f"Type machine ID '{machine_id}' to confirm replacement")

    return {
        "machine_id": machine_id,
        "host": host,
        "port": port,
        "user": user,
        "auth_type": auth_type,
        "password": password,
        "key_path": key_path,
        "ssh_alias": ssh_alias,
        "default_cwd": default_cwd,
        "startup_commands": startup_commands,
        "platform": platform,
        "backend": backend,
        "shell": shell,
        "replace": args.replace,
        "confirm_replace": confirm_replace,
    }


def _parse_path_pair(spec: str, left_name: str, right_name: str) -> Dict[str, str]:
    if "=" not in spec:
        raise ValueError(f"{left_name}={right_name} is required: {spec}")
    left, right = spec.split("=", 1)
    if not left or not right:
        raise ValueError(f"{left_name} and {right_name} are required: {spec}")
    return {left_name: left, right_name: right}


def cmd_machine_add(args: argparse.Namespace) -> None:
    manager = get_remote_machine_manager()
    machine_args = _collect_machine_add_args(args)
    result = manager.add(**machine_args)
    _print(result)


def cmd_machine_list(args: argparse.Namespace) -> None:
    _print(get_remote_machine_manager().list())


def cmd_machine_show(args: argparse.Namespace) -> None:
    _print(get_remote_machine_manager().show(args.machine_id))


def cmd_machine_doctor(args: argparse.Namespace) -> None:
    _print(get_remote_machine_manager().doctor(args.machine_id, get_remote_backend()))


def cmd_machine_restart_tmux_server(args: argparse.Namespace) -> None:
    _print(
        get_remote_machine_manager().restart_tmux_server(
            args.machine_id,
            get_remote_backend(),
        )
    )


def cmd_machine_remove(args: argparse.Namespace) -> None:
    _print(get_remote_machine_manager().remove(args.machine_id))


def cmd_machine_configure_startup(args: argparse.Namespace) -> None:
    startup_commands = args.startup_command
    if startup_commands is None:
        machine = get_remote_machine_manager().get(args.machine_id)
        startup_commands = _prompt_startup_commands(machine.startup_commands)
    default_cwd = args.default_cwd
    if default_cwd in {None, ""} and args.interactive:
        machine = get_remote_machine_manager().get(args.machine_id)
        default_cwd = _prompt("Default cwd after startup commands", machine.default_cwd)
    _print(
        get_remote_machine_manager().configure_startup(
            machine_id=args.machine_id,
            startup_commands=startup_commands,
            default_cwd=default_cwd,
        )
    )


def cmd_machine_configure_path_map(args: argparse.Namespace) -> None:
    _print(
        get_remote_machine_manager().configure_path_map(
            machine_id=args.machine_id,
            command_prefix=args.command_prefix,
            file_prefix=args.file_prefix,
        )
    )


def cmd_machine_configure_platform(args: argparse.Namespace) -> None:
    _print(
        get_remote_machine_manager().configure_platform(
            machine_id=args.machine_id,
            platform=args.platform,
            backend=args.backend,
            shell=args.shell,
        )
    )


def cmd_session_create(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().create(
            machine_id=args.machine,
            cwd=args.cwd,
            name=args.name,
        )
    )


def cmd_session_list(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().list())


def cmd_session_show(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().show(args.session))


def cmd_session_exec(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().exec(
            session_id=args.session,
            command=args.cmd,
            cwd=args.cwd,
            timeout=args.timeout,
            mode=args.mode,
        )
    )


def cmd_session_command_list(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().command_list(args.session))


def cmd_session_command_show(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().command_show(
            session_id=args.session,
            command_id=args.command_id,
            stdout_limit=args.stdout_bytes,
            stderr_limit=args.stderr_bytes,
        )
    )


def cmd_session_command_wait(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().command_wait(
            session_id=args.session,
            command_id=args.command_id,
            timeout=args.timeout,
            stdout_limit=args.stdout_bytes,
            stderr_limit=args.stderr_bytes,
        )
    )


def cmd_session_command_stop(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().command_stop(
            session_id=args.session,
            command_id=args.command_id,
        )
    )


def cmd_session_send(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().send(
            session_id=args.session,
            input_text=args.input,
            enter=not args.no_enter,
        )
    )


def cmd_session_interrupt(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().interrupt(args.session))


def cmd_session_attach(args: argparse.Namespace) -> None:
    result = get_remote_session_manager().attach(args.session)
    if args.json:
        _print(result)


def cmd_session_read(args: argparse.Namespace) -> None:
    _print(
        get_remote_session_manager().read(
            session_id=args.session,
            since=args.since,
            max_chars=args.max_chars,
        )
    )


def cmd_session_logs(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().logs(args.session))


def cmd_session_destroy(args: argparse.Namespace) -> None:
    _print(get_remote_session_manager().destroy(args.session))


def cmd_file_put(args: argparse.Namespace) -> None:
    _print(get_remote_file_manager().put(args.session, args.local, args.remote))


def cmd_file_get(args: argparse.Namespace) -> None:
    _print(get_remote_file_manager().get(args.session, args.remote, args.local))


def cmd_file_list(args: argparse.Namespace) -> None:
    _print(get_remote_file_manager().list(args.session, args.remote))


def cmd_run_once(args: argparse.Namespace) -> None:
    inputs = [_parse_path_pair(spec, "local_path", "remote_path") for spec in args.input or []]
    artifacts = [
        _parse_path_pair(spec, "remote_path", "local_path") for spec in args.artifact or []
    ]
    _print(
        get_remote_run_manager().once(
            machine_id=args.machine,
            command=args.cmd,
            cwd=args.cwd,
            inputs=inputs,
            artifacts=artifacts,
            timeout=args.timeout,
            destroy_session=not args.keep_session,
        )
    )


def cmd_run_list(args: argparse.Namespace) -> None:
    _print(get_remote_run_manager().list())


def cmd_run_show(args: argparse.Namespace) -> None:
    _print(get_remote_run_manager().show(args.run_id))


def add_json_flag(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true", help="Emit JSON output")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="remote-runner: local CLI for controlling remote machines",
    )
    subparsers = parser.add_subparsers(dest="command")

    machine = subparsers.add_parser("machine", help="Machine management")
    machine_sub = machine.add_subparsers(dest="machine_command")

    machine_add = machine_sub.add_parser("add", help="Add a machine")
    machine_add.add_argument("--machine-id")
    machine_add.add_argument("--host")
    machine_add.add_argument("--port", type=int)
    machine_add.add_argument("--user")
    machine_add.add_argument("--auth-type", choices=["key", "password", "manual"])
    machine_add.add_argument("--platform", choices=["linux", "windows", "mac"])
    machine_add.add_argument("--backend", choices=["ssh-tmux", "windows-agent", "openssh-pty"])
    machine_add.add_argument("--shell")
    machine_add.add_argument("--password", help="Password auth value; prefer interactive input")
    machine_add.add_argument("--key-path")
    machine_add.add_argument("--ssh-alias", help="OpenSSH Host alias for openssh-pty backend")
    machine_add.add_argument("--default-cwd")
    machine_add.add_argument(
        "--startup-command",
        action="append",
        help="Command to run after SSH login; repeat to preserve order",
    )
    machine_add.add_argument("--replace", action="store_true")
    machine_add.add_argument("--confirm-replace")
    add_json_flag(machine_add)
    machine_add.set_defaults(func=cmd_machine_add)

    machine_list = machine_sub.add_parser("list", help="List machines")
    add_json_flag(machine_list)
    machine_list.set_defaults(func=cmd_machine_list)

    machine_show = machine_sub.add_parser("show", help="Show a machine")
    machine_show.add_argument("machine_id")
    add_json_flag(machine_show)
    machine_show.set_defaults(func=cmd_machine_show)

    machine_doctor = machine_sub.add_parser("doctor", help="Diagnose machine connectivity")
    machine_doctor.add_argument("machine_id")
    add_json_flag(machine_doctor)
    machine_doctor.set_defaults(func=cmd_machine_doctor)

    machine_restart_tmux = machine_sub.add_parser(
        "restart-tmux-server",
        help="Restart the remote user's tmux server after safety checks",
    )
    machine_restart_tmux.add_argument("machine_id")
    add_json_flag(machine_restart_tmux)
    machine_restart_tmux.set_defaults(func=cmd_machine_restart_tmux_server)

    machine_remove = machine_sub.add_parser("remove", help="Remove a machine")
    machine_remove.add_argument("machine_id")
    add_json_flag(machine_remove)
    machine_remove.set_defaults(func=cmd_machine_remove)

    machine_startup = machine_sub.add_parser(
        "configure-startup",
        help="Configure startup commands for an existing machine",
    )
    machine_startup.add_argument("machine_id")
    machine_startup.add_argument(
        "--startup-command",
        action="append",
        help="Command to run after SSH login; repeat to preserve order",
    )
    machine_startup.add_argument("--default-cwd")
    machine_startup.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for missing startup/default cwd fields",
    )
    add_json_flag(machine_startup)
    machine_startup.set_defaults(func=cmd_machine_configure_startup)

    machine_path_map = machine_sub.add_parser(
        "configure-path-map",
        help="Configure command-path to SFTP-path mapping for an existing machine",
    )
    machine_path_map.add_argument("machine_id")
    machine_path_map.add_argument("--command-prefix", required=True)
    machine_path_map.add_argument("--file-prefix", required=True)
    add_json_flag(machine_path_map)
    machine_path_map.set_defaults(func=cmd_machine_configure_path_map)

    machine_platform = machine_sub.add_parser(
        "configure-platform",
        help="Configure remote platform and session backend for an existing machine",
    )
    machine_platform.add_argument("machine_id")
    machine_platform.add_argument("--platform", required=True, choices=["linux", "windows", "mac"])
    machine_platform.add_argument("--backend", choices=["ssh-tmux", "windows-agent", "openssh-pty"])
    machine_platform.add_argument("--shell")
    add_json_flag(machine_platform)
    machine_platform.set_defaults(func=cmd_machine_configure_platform)

    session = subparsers.add_parser("session", help="Session management")
    session_sub = session.add_subparsers(dest="session_command")

    session_create = session_sub.add_parser("create", help="Create a session")
    session_create.add_argument("--machine", required=True)
    session_create.add_argument("--cwd")
    session_create.add_argument("--name", help="Optional readable session name")
    add_json_flag(session_create)
    session_create.set_defaults(func=cmd_session_create)

    session_list = session_sub.add_parser("list", help="List sessions")
    add_json_flag(session_list)
    session_list.set_defaults(func=cmd_session_list)

    session_show = session_sub.add_parser("show", help="Show a session")
    session_show.add_argument("--session", required=True)
    add_json_flag(session_show)
    session_show.set_defaults(func=cmd_session_show)

    session_exec = session_sub.add_parser(
        "exec",
        help="Run a structured command associated with a session",
    )
    session_exec.add_argument("--session", required=True)
    session_exec.add_argument("--cmd", required=True)
    session_exec.add_argument("--cwd")
    session_exec.add_argument("--timeout", type=int, default=300)
    session_exec.add_argument(
        "--mode",
        choices=["wait", "background"],
        default="wait",
        help="wait for command completion or start it in the background",
    )
    add_json_flag(session_exec)
    session_exec.set_defaults(func=cmd_session_exec)

    session_command = session_sub.add_parser("command", help="Inspect background session commands")
    session_command_sub = session_command.add_subparsers(dest="session_command_action")

    session_command_list = session_command_sub.add_parser("list", help="List session commands")
    session_command_list.add_argument("--session", required=True)
    add_json_flag(session_command_list)
    session_command_list.set_defaults(func=cmd_session_command_list)

    session_command_show = session_command_sub.add_parser("show", help="Show a session command")
    session_command_show.add_argument("--session", required=True)
    session_command_show.add_argument("--command-id", required=True)
    session_command_show.add_argument("--stdout-bytes", type=int, default=8192)
    session_command_show.add_argument("--stderr-bytes", type=int, default=8192)
    add_json_flag(session_command_show)
    session_command_show.set_defaults(func=cmd_session_command_show)

    session_command_result = session_command_sub.add_parser(
        "result",
        help="Show a session command result",
    )
    session_command_result.add_argument("--session", required=True)
    session_command_result.add_argument("--command-id", required=True)
    session_command_result.add_argument("--stdout-bytes", type=int, default=8192)
    session_command_result.add_argument("--stderr-bytes", type=int, default=8192)
    add_json_flag(session_command_result)
    session_command_result.set_defaults(func=cmd_session_command_show)

    session_command_wait = session_command_sub.add_parser("wait", help="Wait for a session command")
    session_command_wait.add_argument("--session", required=True)
    session_command_wait.add_argument("--command-id", required=True)
    session_command_wait.add_argument("--timeout", type=int, default=30)
    session_command_wait.add_argument("--stdout-bytes", type=int, default=8192)
    session_command_wait.add_argument("--stderr-bytes", type=int, default=8192)
    add_json_flag(session_command_wait)
    session_command_wait.set_defaults(func=cmd_session_command_wait)

    session_command_stop = session_command_sub.add_parser("stop", help="Stop a session command")
    session_command_stop.add_argument("--session", required=True)
    session_command_stop.add_argument("--command-id", required=True)
    add_json_flag(session_command_stop)
    session_command_stop.set_defaults(func=cmd_session_command_stop)

    session_send = session_sub.add_parser("send", help="Send raw input to a session shell")
    session_send.add_argument("--session", required=True)
    session_send.add_argument("--input", required=True)
    session_send.add_argument(
        "--no-enter",
        action="store_true",
        help="Send input without pressing Enter",
    )
    add_json_flag(session_send)
    session_send.set_defaults(func=cmd_session_send)

    session_interrupt = session_sub.add_parser(
        "interrupt",
        help="Send Ctrl-C to the session's foreground process",
    )
    session_interrupt.add_argument("--session", required=True)
    add_json_flag(session_interrupt)
    session_interrupt.set_defaults(func=cmd_session_interrupt)

    session_attach = session_sub.add_parser(
        "attach",
        help="Attach to a session's interactive local terminal",
    )
    session_attach.add_argument("--session", required=True)
    add_json_flag(session_attach)
    session_attach.set_defaults(func=cmd_session_attach)

    session_read = session_sub.add_parser("read", help="Read session shell transcript")
    session_read.add_argument("--session", required=True)
    session_read.add_argument("--since", type=int)
    session_read.add_argument("--max-chars", type=int)
    add_json_flag(session_read)
    session_read.set_defaults(func=cmd_session_read)

    session_logs = session_sub.add_parser("logs", help="List session logs")
    session_logs.add_argument("--session", required=True)
    add_json_flag(session_logs)
    session_logs.set_defaults(func=cmd_session_logs)

    session_destroy = session_sub.add_parser("destroy", help="Destroy a session")
    session_destroy.add_argument("--session", required=True)
    add_json_flag(session_destroy)
    session_destroy.set_defaults(func=cmd_session_destroy)

    file_parser = subparsers.add_parser("file", help="File transfer")
    file_sub = file_parser.add_subparsers(dest="file_command")

    file_put = file_sub.add_parser("put", help="Upload a file or directory")
    file_put.add_argument("--session", required=True)
    file_put.add_argument("--local", required=True)
    file_put.add_argument("--remote", required=True)
    add_json_flag(file_put)
    file_put.set_defaults(func=cmd_file_put)

    file_get = file_sub.add_parser("get", help="Download a file or directory")
    file_get.add_argument("--session", required=True)
    file_get.add_argument("--remote", required=True)
    file_get.add_argument("--local", required=True)
    add_json_flag(file_get)
    file_get.set_defaults(func=cmd_file_get)

    file_list = file_sub.add_parser("list", help="List remote files")
    file_list.add_argument("--session", required=True)
    file_list.add_argument("--remote", required=True)
    add_json_flag(file_list)
    file_list.set_defaults(func=cmd_file_list)

    run_parser = subparsers.add_parser("run", help="Closed-loop run orchestration")
    run_sub = run_parser.add_subparsers(dest="run_command")

    run_once = run_sub.add_parser("once", help="Run one remote command with inputs/artifacts")
    run_once.add_argument("--machine", required=True)
    run_once.add_argument("--cmd", required=True)
    run_once.add_argument("--cwd")
    run_once.add_argument(
        "--input",
        action="append",
        help="Input mapping LOCAL=REMOTE; repeat for multiple inputs",
    )
    run_once.add_argument(
        "--artifact",
        action="append",
        help="Artifact mapping REMOTE=LOCAL; repeat for multiple artifacts",
    )
    run_once.add_argument("--timeout", type=int, default=300)
    run_once.add_argument(
        "--keep-session",
        action="store_true",
        help="Keep the created session active after the run",
    )
    add_json_flag(run_once)
    run_once.set_defaults(func=cmd_run_once)

    run_list = run_sub.add_parser("list", help="List recorded runs")
    add_json_flag(run_list)
    run_list.set_defaults(func=cmd_run_list)

    run_show = run_sub.add_parser("show", help="Show a recorded run")
    run_show.add_argument("run_id")
    add_json_flag(run_show)
    run_show.set_defaults(func=cmd_run_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except Exception as exc:
        _handle_error(exc)


if __name__ == "__main__":
    main()
