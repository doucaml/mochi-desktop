from __future__ import annotations

from pathlib import Path

import pytest

from mochi.pocket import (
    MAX_TEXT_BYTES,
    PocketItemKind,
    apply_items,
    item_from_record,
    item_is_available,
    item_to_record,
    make_local_file_item,
    make_saved_image_item,
    make_text_item,
    make_url_item,
)


def test_local_file_item_normalizes_to_absolute_path(tmp_path: Path) -> None:
    item = make_local_file_item(tmp_path / "folder" / ".." / "note.txt", received_at=10)
    assert item.kind is PocketItemKind.LOCAL_FILE
    assert Path(item.value).is_absolute()
    assert item.value == str((tmp_path / "note.txt").resolve(strict=False))
    assert item.display_name == "note.txt"
    assert item.received_at == 10


def test_url_item_accepts_only_http_and_https_and_normalizes_host() -> None:
    item = make_url_item("  HTTPS://Example.COM/path?q=1  ", received_at=2)
    assert item.kind is PocketItemKind.URL
    assert item.value == "https://example.com/path?q=1"
    with pytest.raises(ValueError):
        make_url_item("file:///tmp/nope")
    with pytest.raises(ValueError):
        make_url_item("javascript:alert(1)")


def test_text_item_preserves_path_like_text_as_text() -> None:
    item = make_text_item("/tmp/example.txt", received_at=3)
    assert item.kind is PocketItemKind.TEXT
    assert item.value == "/tmp/example.txt"


def test_text_item_rejects_empty_and_over_64_kib() -> None:
    with pytest.raises(ValueError):
        make_text_item("   \n\t")
    make_text_item("x" * MAX_TEXT_BYTES)
    with pytest.raises(ValueError):
        make_text_item("x" * (MAX_TEXT_BYTES + 1))


def test_duplicate_file_refreshes_to_top_without_duplicate(tmp_path: Path) -> None:
    first = make_local_file_item(tmp_path / "same.txt", received_at=1)
    other = make_text_item("note", received_at=2)
    again = make_local_file_item(tmp_path / "same.txt", received_at=5)
    result = apply_items([other, first], [again])
    assert [item.kind for item in result.items] == [PocketItemKind.LOCAL_FILE, PocketItemKind.TEXT]
    assert result.items[0].received_at == 5
    assert len(result.items) == 2
    assert result.evicted == ()


def test_duplicate_url_refreshes_but_duplicate_text_is_retained() -> None:
    url1 = make_url_item("https://example.com", received_at=1)
    text1 = make_text_item("same", received_at=2)
    url2 = make_url_item("HTTPS://EXAMPLE.COM", received_at=3)
    text2 = make_text_item("same", received_at=4)
    result = apply_items([text1, url1], [url2, text2])
    assert [item.kind for item in result.items] == [
        PocketItemKind.TEXT,
        PocketItemKind.URL,
        PocketItemKind.TEXT,
    ]
    assert result.items[1].received_at == 3


def test_capacity_evicts_oldest_and_marks_only_managed_images_for_cleanup(tmp_path: Path) -> None:
    old_image = make_saved_image_item(tmp_path / "managed.png", received_at=0)
    current = [make_text_item(f"item {i}", received_at=i + 1) for i in range(9)] + [old_image]
    incoming = make_text_item("newest", received_at=20)
    result = apply_items(current, [incoming], capacity=10)
    assert len(result.items) == 10
    assert result.items[0].value == "newest"
    assert old_image in result.evicted
    assert result.cleanup_paths == (Path(old_image.value),)


def test_duplicate_refresh_inside_full_pocket_does_not_evict_refreshed_entry(tmp_path: Path) -> None:
    repeated = make_local_file_item(tmp_path / "keep.txt", received_at=1)
    current = [make_text_item(f"t{i}", received_at=i + 2) for i in range(9)] + [repeated]
    refreshed = make_local_file_item(tmp_path / "keep.txt", received_at=99)
    result = apply_items(current, [refreshed], capacity=10)
    assert len(result.items) == 10
    assert result.items[0].value == repeated.value
    assert all(item.value != repeated.value for item in result.evicted)


def test_item_serialization_round_trips_and_malformed_record_is_rejected(tmp_path: Path) -> None:
    item = make_saved_image_item(tmp_path / "drop.png", received_at=123.5)
    restored = item_from_record(item_to_record(item))
    assert restored == item
    with pytest.raises((TypeError, ValueError, KeyError)):
        item_from_record({"id": "broken", "kind": "wat"})


def test_item_availability_only_checks_file_backed_items(tmp_path: Path) -> None:
    missing = make_local_file_item(tmp_path / "missing.txt")
    existing_path = tmp_path / "exists.png"
    existing_path.write_bytes(b"png")
    image = make_saved_image_item(existing_path)
    text = make_text_item("hello")
    url = make_url_item("https://example.com")
    assert item_is_available(missing) is False
    assert item_is_available(image) is True
    assert item_is_available(text) is True
    assert item_is_available(url) is True
