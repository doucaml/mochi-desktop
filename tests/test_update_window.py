"""Polished Mochi updater window state tests."""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import cairo
import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gtk  # noqa: E402

from mochi.update.model import InstalledBuild, UpdateMetadata, UpdateTarget
from mochi.update.window import MOCHI_GREEN, UPDATE_WINDOW_CSS, UpdateWindow, UpdaterSprite
from mochi.update.worker import UpdateProgress, UpdateStage


def _installed() -> InstalledBuild:
    return InstalledBuild(
        version="0.3.0a1",
        commit="old123456789",
        channel="main",
        installed_at="2026-09-26T12:00:00+00:00",
    )


def _target() -> UpdateTarget:
    return UpdateTarget(
        commit="new987654321",
        metadata=UpdateMetadata(
            version="0.4.0a1",
            channel="main",
            highlights=("First", "Second", "Third", "Fourth"),
        ),
    )


def _window(tmp_path: Path) -> UpdateWindow:
    calls: list[str] = []
    return UpdateWindow(
        on_later=lambda: calls.append("later"),
        on_update_restart=lambda: calls.append("update"),
        on_retry=lambda: calls.append("retry"),
        on_close=lambda: calls.append("close"),
        asset_root=tmp_path,
    )


def test_available_state_shows_versions_three_highlights_and_actions(
    tmp_path: Path,
) -> None:
    window = _window(tmp_path)

    window.show_available(_installed(), _target())

    assert window.state_name == "available"
    assert "0.3.0a1" in window.version_text
    assert "0.4.0a1" in window.version_text
    assert window.highlight_texts == ("First", "Second", "Third")
    assert window.visible_actions == ("Later", "Update & Restart")


def test_downloading_uses_real_byte_fraction(tmp_path: Path) -> None:
    window = _window(tmp_path)

    window.show_progress(
        UpdateProgress(
            stage=UpdateStage.DOWNLOADING,
            message="Getting the newest Mochi…",
            downloaded=25,
            total=100,
        )
    )

    assert window.state_name == "downloading"
    assert window.progress_fraction == 0.25
    assert window.progress_is_indeterminate is False


def test_install_stages_do_not_invent_numeric_progress(tmp_path: Path) -> None:
    window = _window(tmp_path)

    for stage in (
        UpdateStage.INSTALLING,
        UpdateStage.SWAPPING,
        UpdateStage.REFRESHING,
        UpdateStage.RESTARTING,
    ):
        window.show_progress(UpdateProgress(stage=stage, message=stage.value))
        assert window.progress_is_indeterminate is True
        assert window.progress_fraction is None

    assert "Cancel" not in window.visible_actions


def test_failure_state_is_friendly_and_exposes_details(tmp_path: Path) -> None:
    window = _window(tmp_path)

    window.show_failure(
        "Hmm... something went wrong.",
        "stage=install target=new9876",
    )

    assert window.state_name == "failure"
    assert "current Mochi is still safe" in window.body_text
    assert window.visible_actions == ("Try Again", "Close", "Show Details")
    assert "target=new9876" in window.details_text


def test_success_state_is_small_and_positive(tmp_path: Path) -> None:
    window = _window(tmp_path)

    window.show_success()

    assert window.state_name == "success"
    assert "All updated" in window.title_text


def test_updater_css_respects_theme_and_uses_mochi_green() -> None:
    assert "@theme_bg_color" in UPDATE_WINDOW_CSS
    assert "@theme_fg_color" in UPDATE_WINDOW_CSS
    assert MOCHI_GREEN == "#79c98b"
    assert "#79c98b" in UPDATE_WINDOW_CSS


def test_sprite_renderer_explicitly_uses_nearest_neighbor() -> None:
    source = inspect.getsource(UpdaterSprite)
    assert "FILTER_NEAREST" in source
    assert issubclass(UpdaterSprite, Gtk.DrawingArea)


def test_sprite_renderer_slices_manifest_spritesheet_into_frames(
    tmp_path: Path,
) -> None:
    wave_dir = tmp_path / "wave"
    wave_dir.mkdir()
    manifest = {
        "animations": {
            "wave": {
                "spritesheet": "wave/wave.png",
                "frame_count": 3,
                "source_cell_size": [2, 2],
            }
        }
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    sheet = cairo.ImageSurface(cairo.FORMAT_ARGB32, 6, 2)
    context = cairo.Context(sheet)
    for index, intensity in enumerate((0.2, 0.5, 0.8)):
        context.set_source_rgba(intensity, 1.0 - intensity, 0.3, 1.0)
        context.rectangle(index * 2, 0, 2, 2)
        context.fill()
    sheet.write_to_png(str(wave_dir / "wave.png"))

    sprite = UpdaterSprite(asset_root=tmp_path, animation="wave")

    assert len(sprite._frames) == 3
    assert {
        (frame.get_width(), frame.get_height())
        for frame in sprite._frames
    } == {(2, 2)}
    assert len({bytes(frame.get_data()) for frame in sprite._frames}) == 3


def test_safe_pre_swap_stages_offer_cancel_when_external_callback_exists(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    window = UpdateWindow(
        on_later=lambda: None,
        on_update_restart=lambda: None,
        on_retry=lambda: None,
        on_close=lambda: None,
        on_cancel=lambda: calls.append("cancel"),
        asset_root=tmp_path,
    )

    for stage in (
        UpdateStage.DOWNLOADING,
        UpdateStage.VERIFYING,
    ):
        window.show_progress(UpdateProgress(stage=stage, message=stage.value))
        assert window.visible_actions == ("Cancel",)

    for stage in (
        UpdateStage.SWAPPING,
        UpdateStage.INSTALLING,
        UpdateStage.REFRESHING,
        UpdateStage.RESTARTING,
    ):
        window.show_progress(UpdateProgress(stage=stage, message=stage.value))
        assert "Cancel" not in window.visible_actions
