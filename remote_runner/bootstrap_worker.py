"""Isolated bootstrap process; invoked internally by SessionManager."""

import argparse
import importlib.util
import inspect
import json
import os
from pathlib import Path
import sys
import traceback
from types import ModuleType
from typing import Any, Dict

from remote_runner.bootstrap import BootstrapSession
from remote_runner.session import SessionManager
from remote_runner.state import StateStore
from remote_runner.tmux import TmuxTerminal


def _load_module(path: Path) -> ModuleType:
    module_name = f"remote_runner_bootstrap_{os.getpid()}"
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load bootstrap file '{path}'")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_result(path: Path, value: Dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o600)
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--bootstrap-path", required=True)
    parser.add_argument("--tmux-binary", required=True)
    parser.add_argument("--tmux-socket")
    args = parser.parse_args()

    store = StateStore(Path(args.state_dir))
    result_path = store.bootstrap_result_path(args.session_id)
    if result_path.exists():
        result_path.unlink()
    try:
        module = _load_module(Path(args.bootstrap_path))
        hook = getattr(module, "bootstrap", None)
        if not callable(hook):
            raise RuntimeError("Bootstrap file must export bootstrap(session)")
        signature = inspect.signature(hook)
        if len(signature.parameters) != 1:
            raise RuntimeError("bootstrap must accept exactly one session parameter")
        manager = SessionManager(
            store=store,
            terminal=TmuxTerminal(binary=args.tmux_binary, socket_name=args.tmux_socket),
        )
        with store.writer_lock(args.session_id):
            hook(BootstrapSession(manager, args.session_id))
        _write_result(result_path, {"status": "succeeded"})
        return 0
    except BaseException as error:
        traceback.print_exc()
        _write_result(
            result_path,
            {
                "status": "failed",
                "error_type": type(error).__name__,
                "error_message": str(error),
            },
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
