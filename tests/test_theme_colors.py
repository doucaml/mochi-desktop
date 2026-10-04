"""Mochi's overlay CSS must follow the GTK theme in light and dark mode.

Mochi is a plain GTK 4 app (no libadwaita), so libadwaita-only named colors
such as ``@window_bg_color`` do not exist. GTK silently drops a declaration
that names an unknown color, which once left the nameplate as white text with
no background: invisible on light desktops.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk  # noqa: E402

from mochi.presence.nameplate import Nameplate  # noqa: E402


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src" / "mochi"
NAMED_COLOR = re.compile(r"@([a-z_]+_color)\b")

requires_display = pytest.mark.skipif(
    Gdk.Display.get_default() is None, reason="needs a display (run under xvfb-run)"
)


def _rooted_label(*css_classes: str) -> Gtk.Label:
    window = Gtk.Window()
    label = Gtk.Label(label="Mochi")
    for css_class in css_classes:
        label.add_css_class(css_class)
    window.set_child(label)
    return label


def _theme_color(widget: Gtk.Widget, name: str) -> Gdk.RGBA | None:
    found, color = widget.get_style_context().lookup_color(name)
    return color if found else None


@pytest.fixture
def dark_mode():
    settings = Gtk.Settings.get_default()
    original = settings.props.gtk_application_prefer_dark_theme

    def set_dark(enabled: bool) -> None:
        settings.props.gtk_application_prefer_dark_theme = enabled

    yield set_dark
    settings.props.gtk_application_prefer_dark_theme = original


@requires_display
def test_css_only_names_colors_the_gtk_theme_defines() -> None:
    label = _rooted_label()
    used: dict[str, set[str]] = {}
    for path in SOURCE_ROOT.rglob("*.py"):
        for name in NAMED_COLOR.findall(path.read_text(encoding="utf-8")):
            used.setdefault(name, set()).add(str(path.relative_to(SOURCE_ROOT)))

    assert used, "expected Mochi CSS to use GTK theme colors"
    undefined = {
        name: sorted(files)
        for name, files in used.items()
        if _theme_color(label, name) is None
    }
    assert undefined == {}, f"CSS names colors GTK does not define: {undefined}"


@requires_display
@pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])
def test_nameplate_text_follows_the_theme(dark_mode, dark: bool) -> None:
    dark_mode(dark)
    Nameplate._install_css(Gdk.Display.get_default())
    label = _rooted_label("mochi-nameplate-text")

    expected = _theme_color(label, "theme_fg_color")

    assert expected is not None
    assert label.get_color().equal(expected), (
        f"nameplate text is {label.get_color().to_string()}, "
        f"theme text is {expected.to_string()}"
    )
