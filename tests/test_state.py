from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path

import pytest

from remote_runner.errors import StateError
from remote_runner.instance import InstanceManager
from remote_runner.state import STATE_PRODUCT, STATE_SCHEMA_VERSION, StateStore


def test_clean_state_is_versioned_and_private(tmp_path: Path) -> None:
    root = tmp_path / "state"
    store = StateStore(root)

    store.initialize()

    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    assert schema["product"] == STATE_PRODUCT
    assert schema["schema_version"] == STATE_SCHEMA_VERSION
    assert os.stat(root).st_mode & 0o777 == 0o700
    assert os.stat(root / "schema.json").st_mode & 0o777 == 0o600


def test_legacy_state_is_rejected_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir(mode=0o755)
    legacy = root / "machines.json"
    legacy.write_text('{"machines":{}}', encoding="utf-8")

    with pytest.raises(StateError) as caught:
        StateStore(root).initialize()

    assert caught.value.code == "incompatible_state"
    assert legacy.exists()
    assert not (root / "schema.json").exists()
    assert os.stat(root).st_mode & 0o777 == 0o755
    assert {path.name for path in root.iterdir()} == {"machines.json"}


def test_incompatible_versioned_state_is_rejected_without_mutation(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir(mode=0o755)
    schema = root / "schema.json"
    schema.write_text('{"product":"old","schema_version":99}\n', encoding="utf-8")

    with pytest.raises(StateError) as caught:
        StateStore(root).initialize()

    assert caught.value.code == "incompatible_state"
    assert os.stat(root).st_mode & 0o777 == 0o755
    assert schema.read_text(encoding="utf-8") == '{"product":"old","schema_version":99}\n'
    assert {path.name for path in root.iterdir()} == {"schema.json"}


def test_instance_is_only_a_named_bootstrap_path(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    bootstrap = tmp_path / "gpu.py"
    bootstrap.write_text("def bootstrap(session):\n    pass\n", encoding="utf-8")
    instances = InstanceManager(store)

    created = instances.add("gpu-a", str(bootstrap))

    assert created["instance_name"] == "gpu-a"
    assert created["bootstrap_path"] == str(bootstrap.resolve())
    assert set(created) == {"instance_name", "bootstrap_path", "created_at", "updated_at"}
    assert instances.list()["instances"] == [created]

    with pytest.raises(StateError) as duplicate:
        instances.add("gpu-a", str(bootstrap))
    assert duplicate.value.code == "instance_name_in_use"

    removed = instances.remove("gpu-a")
    assert removed == created
    with pytest.raises(StateError) as missing:
        instances.show("gpu-a")
    assert missing.value.code == "instance_not_found"


def test_instance_path_must_exist_and_name_is_safe(tmp_path: Path) -> None:
    instances = InstanceManager(StateStore(tmp_path / "state"))

    with pytest.raises(StateError) as bad_name:
        instances.add("bad:name", str(tmp_path / "missing.py"))
    assert bad_name.value.code == "invalid_instance_name"

    with pytest.raises(StateError) as missing:
        instances.add("good-name", str(tmp_path / "missing.py"))
    assert missing.value.code == "bootstrap_not_found"

    with pytest.raises(StateError) as unsafe_show:
        instances.show("../../outside")
    assert unsafe_show.value.code == "invalid_instance_name"


def test_concurrent_clean_state_initialization_has_one_valid_schema(tmp_path: Path) -> None:
    root = tmp_path / "state"

    with ThreadPoolExecutor(max_workers=16) as executor:
        list(executor.map(lambda _: StateStore(root).initialize(), range(128)))

    schema = json.loads((root / "schema.json").read_text(encoding="utf-8"))
    assert schema["product"] == STATE_PRODUCT
    assert schema["schema_version"] == STATE_SCHEMA_VERSION
    assert {path.name for path in root.iterdir()} == {
        ".initialize.lock",
        "diagnostics",
        "instances",
        "locks",
        "schema.json",
        "sessions",
    }


def test_incomplete_atomic_session_directory_is_not_public_state(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    store.initialize()
    incomplete = store.sessions_dir / ".sess_deadbeef.creating-crashed"
    incomplete.mkdir()
    (incomplete / "state.json").write_text('{"session_id":"not-valid"}', encoding="utf-8")

    assert store.list_sessions() == []
