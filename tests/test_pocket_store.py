from __future__ import annotations

import json
from pathlib import Path

import pytest

from mochi.pocket import make_local_file_item, make_text_item
from mochi.pocket_store import PocketStore


def test_default_path_uses_xdg_data_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    store = PocketStore()
    assert store.path == tmp_path / "mochi-desktop" / "pocket" / "pocket.json"
    assert store.images_dir == tmp_path / "mochi-desktop" / "pocket" / "images"


def test_round_trip_preserves_items(tmp_path: Path) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    current = []
    result = store.add_items(current, [make_text_item("hello", received_at=1)])
    assert list(result.items) == store.load()
    data = json.loads(store.path.read_text())
    assert data["version"] == 1
    assert data["items"][0]["value"] == "hello"


def test_malformed_records_are_skipped_while_valid_records_load(tmp_path: Path) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    good = make_text_item("valid", received_at=1)
    store.path.write_text(json.dumps({
        "version": 1,
        "items": [
            {
                "id": good.id,
                "kind": good.kind.value,
                "display_name": good.display_name,
                "value": good.value,
                "received_at": good.received_at,
            },
            {"id": "broken", "kind": "wat"},
        ],
    }))
    assert store.load() == [good]


def test_failed_atomic_replace_preserves_previous_json(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    first = store.add_items([], [make_text_item("first", received_at=1)])
    before = store.path.read_text()
    original_replace = Path.replace

    def fail_tmp_replace(self: Path, target: Path):
        if self.name.endswith(".tmp") and target == store.path:
            raise OSError("disk full")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_tmp_replace)
    with pytest.raises(OSError, match="disk full"):
        store.add_items(list(first.items), [make_text_item("second", received_at=2)])
    assert store.path.read_text() == before
    assert not store.path.with_suffix(".tmp").exists()


def test_corrupt_top_level_json_is_preserved_before_recovery_write(tmp_path: Path) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    corrupt = "{definitely not json"
    store.path.write_text(corrupt)
    assert store.load() == []

    result = store.add_items([], [make_text_item("recovered", received_at=1)])
    backups = list(tmp_path.glob("pocket.corrupt-*.json"))
    assert len(backups) == 1
    assert backups[0].read_text() == corrupt
    assert json.loads(store.path.read_text())["items"][0]["value"] == "recovered"
    assert result.items[0].value == "recovered"


def test_corrupt_backup_failure_rejects_mutation_and_keeps_original(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    corrupt = "{broken"
    store.path.write_text(corrupt)
    assert store.load() == []
    original_replace = Path.replace

    def fail_backup(self: Path, target: Path):
        if self == store.path and ".corrupt-" in target.name:
            raise OSError("cannot preserve")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_backup)
    with pytest.raises(OSError, match="cannot preserve"):
        store.add_items([], [make_text_item("nope")])
    assert store.path.read_text() == corrupt
    assert list(tmp_path.glob("pocket.corrupt-*.json")) == []


def test_failed_save_cleans_new_managed_image_and_keeps_previous_state(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    previous = store.add_items([], [make_text_item("keep", received_at=1)])
    image = store.save_raw_image(b"fake-png", received_at=2)
    image_path = Path(image.value)
    assert image_path.exists()
    before = store.path.read_text()
    original_replace = Path.replace

    def fail_metadata_replace(self: Path, target: Path):
        if self.name.endswith(".tmp") and target == store.path:
            raise OSError("metadata write failed")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_metadata_replace)
    with pytest.raises(OSError, match="metadata write failed"):
        store.add_items(list(previous.items), [image])
    assert not image_path.exists()
    assert store.path.read_text() == before


def test_capacity_cleanup_deletes_only_managed_images_after_success(tmp_path: Path) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    managed = store.save_raw_image(b"managed", received_at=0)
    external = tmp_path / "external.txt"
    external.write_text("user file")
    current = [make_text_item(f"t{i}", received_at=i + 1) for i in range(8)]
    current += [make_local_file_item(external, received_at=9), managed]
    store.add_items([], current)

    result = store.add_items(current, [make_text_item("new", received_at=20)])
    assert managed in result.evicted
    assert not Path(managed.value).exists()
    assert external.exists()


def test_remove_managed_image_deletes_image_but_remove_local_file_never_does(
    tmp_path: Path,
) -> None:
    store = PocketStore(path=tmp_path / "pocket.json", images_dir=tmp_path / "images")
    external = tmp_path / "keep.txt"
    external.write_text("keep")
    local = make_local_file_item(external, received_at=1)
    image = store.save_raw_image(b"image", received_at=2)
    current = list(store.add_items([], [local, image]).items)

    remaining = store.remove(current, image.id)
    assert Path(image.value).exists() is False
    assert external.exists()
    assert all(item.id != image.id for item in remaining)

    remaining = store.remove(remaining, local.id)
    assert external.exists()
    assert remaining == []
