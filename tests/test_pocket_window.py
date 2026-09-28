"""Pocket management window and safe action coverage."""

from __future__ import annotations

from pathlib import Path

from mochi.pocket import (
    make_local_file_item,
    make_text_item,
    make_url_item,
)
from mochi.pocket_window import PocketTextWindow, PocketWindow


class _Controller:
    def __init__(self, items=()) -> None:
        self._items = tuple(items)
        self.removed = []

    @property
    def items(self):
        return self._items

    def remove(self, item_id: str) -> bool:
        self.removed.append(item_id)
        self._items = tuple(item for item in self._items if item.id != item_id)
        return True


def test_empty_pocket_shows_drag_explanation() -> None:
    window = PocketWindow(_Controller())

    assert window.empty_visible is True
    assert window.rows == {}
    assert "drag" in window.empty_text.lower()


def test_list_rows_show_available_and_missing_file_states(tmp_path: Path) -> None:
    available_path = tmp_path / "available.txt"
    available_path.write_text("hello", encoding="utf-8")
    available = make_local_file_item(available_path, received_at=2)
    missing = make_local_file_item(tmp_path / "missing.txt", received_at=1)

    window = PocketWindow(_Controller((available, missing)))

    assert window.empty_visible is False
    assert window.rows[available.id].model.available is True
    assert window.rows[available.id].open_button.get_sensitive() is True
    assert window.rows[missing.id].model.available is False
    assert window.rows[missing.id].open_button.get_sensitive() is False
    assert "Unavailable" in window.rows[missing.id].model.subtitle


def test_open_file_and_url_use_validated_uris(tmp_path: Path) -> None:
    path = tmp_path / "note with spaces.txt"
    path.write_text("hello", encoding="utf-8")
    file_item = make_local_file_item(path)
    url_item = make_url_item("https://example.com/page")
    launched = []
    window = PocketWindow(
        _Controller((file_item, url_item)),
        launcher=launched.append,
    )

    window.open_item(file_item.id)
    window.open_item(url_item.id)

    assert launched == [path.as_uri(), "https://example.com/page"]


def test_text_opens_in_a_read_only_detail_window() -> None:
    item = make_text_item("full\ntext")
    window = PocketWindow(_Controller((item,)))

    assert window.open_item(item.id) is True

    detail = window.detail_windows[-1]
    assert isinstance(detail, PocketTextWindow)
    assert detail.text_view.get_editable() is False
    assert detail.text_view.get_cursor_visible() is False
    start, end = detail.text_view.get_buffer().get_bounds()
    assert detail.text_view.get_buffer().get_text(start, end, True) == "full\ntext"


def test_remove_dispatches_to_controller_and_refreshes_rows() -> None:
    item = make_text_item("remove me")
    controller = _Controller((item,))
    window = PocketWindow(controller)

    window.rows[item.id].remove_button.emit("clicked")

    assert controller.removed == [item.id]
    assert window.rows == {}
    assert window.empty_visible is True


def test_launch_failure_preserves_item_and_shows_feedback() -> None:
    item = make_url_item("https://example.com")
    controller = _Controller((item,))

    def fail(_uri: str) -> None:
        raise OSError("no handler")

    window = PocketWindow(controller, launcher=fail)

    assert window.open_item(item.id) is False

    assert controller.items == (item,)
    assert controller.removed == []
    assert "couldn't open" in window.error_text.lower()
