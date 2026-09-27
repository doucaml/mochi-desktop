"""Pure domain model for Mochi's local Pocket utility."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import time
from typing import Iterable, Mapping
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4


MAX_TEXT_BYTES = 64 * 1024
DEFAULT_CAPACITY = 10


class PocketItemKind(str, Enum):
    LOCAL_FILE = "local_file"
    TEXT = "text"
    SAVED_IMAGE = "saved_image"
    URL = "url"


@dataclass(frozen=True)
class PocketItem:
    id: str
    kind: PocketItemKind
    display_name: str
    value: str
    received_at: float


@dataclass(frozen=True)
class PocketMutation:
    items: tuple[PocketItem, ...]
    evicted: tuple[PocketItem, ...] = ()
    cleanup_paths: tuple[Path, ...] = ()


def _received_at(value: float | None) -> float:
    return time.time() if value is None else float(value)


def _new_id() -> str:
    return uuid4().hex


def _normalize_path(path: str | Path) -> Path:
    raw = str(path).strip()
    if not raw:
        raise ValueError("Pocket path must not be empty")
    return Path(raw).expanduser().resolve(strict=False)


def make_local_file_item(
    path: str | Path,
    *,
    received_at: float | None = None,
) -> PocketItem:
    normalized = _normalize_path(path)
    return PocketItem(
        id=_new_id(),
        kind=PocketItemKind.LOCAL_FILE,
        display_name=normalized.name or str(normalized),
        value=str(normalized),
        received_at=_received_at(received_at),
    )


def _normalize_http_url(value: str) -> str:
    candidate = value.strip()
    parsed = urlsplit(candidate)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Pocket URL must use http or https")
    return urlunsplit((scheme, parsed.netloc.lower(), parsed.path, parsed.query, parsed.fragment))


def make_url_item(
    value: str,
    *,
    received_at: float | None = None,
) -> PocketItem:
    normalized = _normalize_http_url(value)
    host = urlsplit(normalized).hostname or normalized
    return PocketItem(
        id=_new_id(),
        kind=PocketItemKind.URL,
        display_name=host,
        value=normalized,
        received_at=_received_at(received_at),
    )


def _text_display_name(value: str) -> str:
    for line in value.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped[:80]
    raise ValueError("Pocket text must not be empty")


def make_text_item(
    value: str,
    *,
    received_at: float | None = None,
) -> PocketItem:
    if not isinstance(value, str):
        raise TypeError("Pocket text must be a string")
    display_name = _text_display_name(value)
    if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
        raise ValueError("Pocket text exceeds 64 KiB")
    return PocketItem(
        id=_new_id(),
        kind=PocketItemKind.TEXT,
        display_name=display_name,
        value=value,
        received_at=_received_at(received_at),
    )


def make_saved_image_item(
    path: str | Path,
    *,
    received_at: float | None = None,
) -> PocketItem:
    normalized = _normalize_path(path)
    return PocketItem(
        id=_new_id(),
        kind=PocketItemKind.SAVED_IMAGE,
        display_name="Dropped image",
        value=str(normalized),
        received_at=_received_at(received_at),
    )


def _dedupe_key(item: PocketItem) -> tuple[PocketItemKind, str] | None:
    if item.kind in {PocketItemKind.LOCAL_FILE, PocketItemKind.URL}:
        return (item.kind, item.value)
    return None


def apply_items(
    current: Iterable[PocketItem],
    incoming: Iterable[PocketItem],
    *,
    capacity: int = DEFAULT_CAPACITY,
) -> PocketMutation:
    if capacity < 1:
        raise ValueError("Pocket capacity must be at least one")

    merged = list(current)
    for item in incoming:
        key = _dedupe_key(item)
        if key is not None:
            merged = [existing for existing in merged if _dedupe_key(existing) != key]
        merged.append(item)

    merged.sort(key=lambda item: item.received_at, reverse=True)
    kept = merged[:capacity]
    evicted = tuple(merged[capacity:])
    cleanup_paths = tuple(
        Path(item.value) for item in evicted if item.kind is PocketItemKind.SAVED_IMAGE
    )
    return PocketMutation(tuple(kept), evicted, cleanup_paths)


def item_is_available(item: PocketItem) -> bool:
    if item.kind in {PocketItemKind.LOCAL_FILE, PocketItemKind.SAVED_IMAGE}:
        return Path(item.value).exists()
    return True


def item_to_record(item: PocketItem) -> dict[str, object]:
    return {
        "id": item.id,
        "kind": item.kind.value,
        "display_name": item.display_name,
        "value": item.value,
        "received_at": item.received_at,
    }


def item_from_record(record: Mapping[str, object]) -> PocketItem:
    item_id = record["id"]
    display_name = record["display_name"]
    value = record["value"]
    received_at = record["received_at"]
    if not isinstance(item_id, str) or not item_id:
        raise TypeError("Pocket item id must be a non-empty string")
    if not isinstance(display_name, str) or not display_name:
        raise TypeError("Pocket item display_name must be a non-empty string")
    if not isinstance(value, str):
        raise TypeError("Pocket item value must be a string")
    if isinstance(received_at, bool) or not isinstance(received_at, (int, float)):
        raise TypeError("Pocket item received_at must be numeric")

    kind = PocketItemKind(record["kind"])
    if kind in {PocketItemKind.LOCAL_FILE, PocketItemKind.SAVED_IMAGE}:
        path = Path(value)
        if not path.is_absolute():
            raise ValueError("Pocket file-backed values must be absolute paths")
    elif kind is PocketItemKind.URL:
        value = _normalize_http_url(value)
    elif kind is PocketItemKind.TEXT:
        _text_display_name(value)
        if len(value.encode("utf-8")) > MAX_TEXT_BYTES:
            raise ValueError("Pocket text exceeds 64 KiB")

    return PocketItem(
        id=item_id,
        kind=kind,
        display_name=display_name,
        value=value,
        received_at=float(received_at),
    )
