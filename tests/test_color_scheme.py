"""Mochi follows the desktop's light/dark preference through the XDG portal."""

from __future__ import annotations

from types import SimpleNamespace

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

from mochi.color_scheme import SystemColorSchemeSync  # noqa: E402


NO_PREFERENCE, PREFER_DARK, PREFER_LIGHT = 0, 1, 2


def _settings(*, prefer_dark: bool = False, native_color_scheme: bool = False):
    return SimpleNamespace(
        props=SimpleNamespace(gtk_application_prefer_dark_theme=prefer_dark),
        find_property=lambda name: (
            object()
            if native_color_scheme and name == "gtk-interface-color-scheme"
            else None
        ),
    )


def _unknown_method() -> GLib.Error:
    return GLib.Error.new_literal(
        Gio.dbus_error_quark(), "no such method", Gio.DBusError.UNKNOWN_METHOD
    )


class _FakePortal:
    def __init__(self, scheme: int | None = None, *, read_one: bool = True) -> None:
        self.scheme = scheme
        self.read_one = read_one
        self.calls: list[str] = []
        self._signal_handler = None

    def connect(self, signal: str, handler):
        assert signal == "g-signal"
        self._signal_handler = handler
        return 1

    def call(self, method, parameters, flags, timeout, cancellable, callback):
        self.calls.append(method)
        assert parameters.unpack() == ("org.freedesktop.appearance", "color-scheme")
        callback(self, method)

    def call_finish(self, method):
        if self.scheme is None or (method == "ReadOne" and not self.read_one):
            raise _unknown_method()
        if method == "ReadOne":
            return GLib.Variant("(v)", (GLib.Variant("u", self.scheme),))
        # Settings portal version 1 wraps Read's value in an extra variant.
        return GLib.Variant(
            "(v)", (GLib.Variant("v", GLib.Variant("u", self.scheme)),)
        )

    def emit_setting_changed(self, namespace: str, key: str, value: int) -> None:
        parameters = GLib.Variant("(ssv)", (namespace, key, GLib.Variant("u", value)))
        self._signal_handler(self, ":1.2", "SettingChanged", parameters)


def _sync(settings, portal: _FakePortal) -> SystemColorSchemeSync:
    return SystemColorSchemeSync(settings, portal_factory=lambda: portal)


def test_starts_in_dark_mode_when_the_desktop_prefers_dark() -> None:
    settings = _settings()

    assert _sync(settings, _FakePortal(PREFER_DARK)).start() is True

    assert settings.props.gtk_application_prefer_dark_theme is True


def test_light_preference_overrides_a_dark_gtk_default() -> None:
    settings = _settings(prefer_dark=True)

    _sync(settings, _FakePortal(PREFER_LIGHT)).start()

    assert settings.props.gtk_application_prefer_dark_theme is False


def test_switching_live_from_dark_to_gnome_default_returns_to_light() -> None:
    # GNOME reports its normal light style as "no preference", so leaving dark
    # mode must restore GTK's own setting rather than staying dark.
    settings = _settings(prefer_dark=False)
    portal = _FakePortal(PREFER_DARK)
    _sync(settings, portal).start()
    assert settings.props.gtk_application_prefer_dark_theme is True

    portal.emit_setting_changed("org.freedesktop.appearance", "color-scheme", NO_PREFERENCE)

    assert settings.props.gtk_application_prefer_dark_theme is False


def test_no_preference_keeps_the_users_own_gtk_setting() -> None:
    settings = _settings(prefer_dark=True)

    _sync(settings, _FakePortal(NO_PREFERENCE)).start()

    assert settings.props.gtk_application_prefer_dark_theme is True


def test_unrelated_setting_changes_are_ignored() -> None:
    settings = _settings()
    portal = _FakePortal(PREFER_LIGHT)
    _sync(settings, portal).start()

    portal.emit_setting_changed("org.freedesktop.appearance", "accent-color", PREFER_DARK)
    portal.emit_setting_changed("org.gnome.desktop.interface", "color-scheme", PREFER_DARK)

    assert settings.props.gtk_application_prefer_dark_theme is False


def test_older_portals_without_read_one_fall_back_to_read() -> None:
    settings = _settings()
    portal = _FakePortal(PREFER_DARK, read_one=False)

    _sync(settings, portal).start()

    assert portal.calls == ["ReadOne", "Read"]
    assert settings.props.gtk_application_prefer_dark_theme is True


def test_unreadable_preference_leaves_gtk_alone() -> None:
    settings = _settings(prefer_dark=True)

    _sync(settings, _FakePortal(None)).start()

    assert settings.props.gtk_application_prefer_dark_theme is True


def test_missing_portal_is_not_an_error() -> None:
    settings = _settings()

    def no_portal():
        raise GLib.Error("no session bus")

    sync = SystemColorSchemeSync(settings, portal_factory=no_portal)

    assert sync.start() is False
    assert settings.props.gtk_application_prefer_dark_theme is False


def test_gtk_that_follows_the_portal_itself_is_left_to_do_so() -> None:
    settings = _settings(native_color_scheme=True)

    def unexpected_portal():
        raise AssertionError("should not open the portal")

    sync = SystemColorSchemeSync(settings, portal_factory=unexpected_portal)

    assert sync.start() is False


def test_mochi_follows_the_desktop_before_its_first_window_appears() -> None:
    import inspect

    from mochi.app import MochiApplication

    source = inspect.getsource(MochiApplication.do_activate)

    assert "SystemColorSchemeSync(" in source
    assert source.index(".start()") < source.index("window.present()")
