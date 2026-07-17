"""Inspectable bootstrap profiles layered above the terminal core."""

from pathlib import Path
import re
from typing import Any, Dict

from remote_runner.errors import StateError
from remote_runner.state import StateStore, utc_now

INSTANCE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class InstanceManager:
    """Manage names that point to independent bootstrap hook files."""

    def __init__(self, store: StateStore) -> None:
        self.store = store

    def add(self, name: str, bootstrap_path: str, *, replace: bool = False) -> Dict[str, Any]:
        self._validate_name(name)
        path = Path(bootstrap_path).expanduser().resolve()
        if not path.is_file():
            raise StateError(
                "bootstrap_not_found",
                f"Bootstrap file '{path}' was not found",
                context={"bootstrap_path": str(path)},
            )
        now = utc_now()
        with self.store.state_lock():
            existing = None
            try:
                existing = self.store.load_instance(name)
            except StateError as error:
                if error.code != "instance_not_found":
                    raise
            if existing is not None and not replace:
                raise StateError(
                    "instance_name_in_use",
                    f"Instance '{name}' already exists; use --replace explicitly",
                    context={"instance_name": name},
                )
            instance = {
                "instance_name": name,
                "bootstrap_path": str(path),
                "created_at": existing.get("created_at", now) if existing else now,
                "updated_at": now,
            }
            self.store.save_instance(instance)
        return instance

    def show(self, name: str) -> Dict[str, Any]:
        self._validate_name(name)
        return self.store.load_instance(name)

    def list(self) -> Dict[str, Any]:
        return {"instances": self.store.list_instances()}

    def remove(self, name: str) -> Dict[str, Any]:
        self._validate_name(name)
        with self.store.state_lock():
            instance = self.store.load_instance(name)
            self.store.delete_instance(name)
        return instance

    @staticmethod
    def _validate_name(name: str) -> None:
        if not INSTANCE_NAME_PATTERN.fullmatch(name):
            raise StateError(
                "invalid_instance_name",
                (
                    "Instance name must start with a letter or number and contain at most 64 "
                    "letters, numbers, '.', '_' or '-'"
                ),
                context={"instance_name": name},
            )
