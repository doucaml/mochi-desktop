"""Transactional local persistence for Mochi's Pocket."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
import time
from typing import Iterable
from uuid import uuid4

from mochi.pocket import (
    PocketItem,
    PocketItemKind,
    PocketMutation,
    apply_items,
    item_from_record,
    item_to_record,
    make_saved_image_item,
)


class PocketStore:
    FORMAT_VERSION = 1

    def __init__(
        self,
        path: Path | None = None,
        images_dir: Path | None = None,
    ) -> None:
        data_home = Path(
            os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
        )
        root = data_home / "mochi-desktop" / "pocket"
        self.path = path or root / "pocket.json"
        self.images_dir = images_dir or root / "images"
        self._logger = logging.getLogger(__name__)
        self._corrupt_loaded = False

    def load(self) -> list[PocketItem]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self._corrupt_loaded = False
            return []
        except json.JSONDecodeError as error:
            self._logger.warning("Pocket data is corrupt at %s: %s", self.path, error)
            self._corrupt_loaded = True
            return []

        if not isinstance(payload, dict) or payload.get("version") != self.FORMAT_VERSION:
            self._logger.warning("Pocket data has an invalid top-level format at %s", self.path)
            self._corrupt_loaded = True
            return []
        records = payload.get("items")
        if not isinstance(records, list):
            self._logger.warning("Pocket data has an invalid item list at %s", self.path)
            self._corrupt_loaded = True
            return []

        items: list[PocketItem] = []
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                self._logger.warning("Ignoring malformed Pocket record %d", index)
                continue
            try:
                items.append(item_from_record(record))
            except (KeyError, TypeError, ValueError) as error:
                self._logger.warning(
                    "Ignoring malformed Pocket record %d: %s", index, error
                )
        self._corrupt_loaded = False
        return items

    def add_items(
        self,
        current: Iterable[PocketItem],
        incoming: Iterable[PocketItem],
    ) -> PocketMutation:
        current_items = list(current)
        incoming_items = list(incoming)
        mutation = apply_items(current_items, incoming_items)
        try:
            self._save_items(mutation.items)
        except OSError:
            self._cleanup_new_managed_images(current_items, incoming_items)
            raise
        for path in mutation.cleanup_paths:
            self._delete_managed_image(path)
        return mutation

    def remove(
        self,
        current: Iterable[PocketItem],
        item_id: str,
    ) -> list[PocketItem]:
        current_items = list(current)
        target = next((item for item in current_items if item.id == item_id), None)
        if target is None:
            return current_items
        remaining = [item for item in current_items if item.id != item_id]
        self._save_items(remaining)
        if target.kind is PocketItemKind.SAVED_IMAGE:
            self._delete_managed_image(Path(target.value))
        return remaining

    def save_raw_image(
        self,
        png_bytes: bytes,
        *,
        received_at: float | None = None,
    ) -> PocketItem:
        if not isinstance(png_bytes, bytes) or not png_bytes:
            raise ValueError("Pocket image data must be non-empty bytes")
        self.images_dir.mkdir(parents=True, exist_ok=True)
        stem = uuid4().hex
        final_path = self.images_dir / f"{stem}.png"
        temp_path = self.images_dir / f".{stem}.tmp"
        try:
            temp_path.write_bytes(png_bytes)
            temp_path.replace(final_path)
        finally:
            temp_path.unlink(missing_ok=True)
        return make_saved_image_item(final_path, received_at=received_at)

    def _save_items(self, items: Iterable[PocketItem]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self._corrupt_loaded and self.path.exists():
            backup = self.path.with_name(
                f"{self.path.stem}.corrupt-{time.time_ns()}{self.path.suffix}"
            )
            self.path.replace(backup)
            self._logger.warning("Preserved corrupt Pocket data at %s", backup)

        temporary_path = self.path.with_suffix(".tmp")
        payload = {
            "version": self.FORMAT_VERSION,
            "items": [item_to_record(item) for item in items],
        }
        try:
            temporary_path.write_text(
                json.dumps(payload, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary_path.replace(self.path)
        finally:
            temporary_path.unlink(missing_ok=True)
        self._corrupt_loaded = False

    def _cleanup_new_managed_images(
        self,
        current: Iterable[PocketItem],
        incoming: Iterable[PocketItem],
    ) -> None:
        existing_values = {
            item.value
            for item in current
            if item.kind is PocketItemKind.SAVED_IMAGE
        }
        for item in incoming:
            if (
                item.kind is PocketItemKind.SAVED_IMAGE
                and item.value not in existing_values
            ):
                self._delete_managed_image(Path(item.value))

    def _delete_managed_image(self, path: Path) -> None:
        if not self._is_managed_image(path):
            self._logger.warning("Refusing to delete unmanaged Pocket image path %s", path)
            return
        try:
            path.unlink(missing_ok=True)
        except OSError as error:
            self._logger.warning("Could not delete managed Pocket image %s: %s", path, error)

    def _is_managed_image(self, path: Path) -> bool:
        managed_root = self.images_dir.resolve(strict=False)
        candidate = path.resolve(strict=False)
        try:
            candidate.relative_to(managed_root)
        except ValueError:
            return False
        return candidate != managed_root
