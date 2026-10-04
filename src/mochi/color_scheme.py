"""Follow the desktop's light/dark preference in Mochi's GTK theme.

Mochi uses plain GTK 4 without libadwaita. Before GTK 4.20, plain GTK does not
track GNOME's (or KDE's) dark-style switch, so Mochi's windows stayed in
whichever theme GTK started with. This reads the desktop-neutral XDG Settings
portal, the same source libadwaita uses, and mirrors it into
``gtk-application-prefer-dark-theme``, including live changes.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib


PORTAL_BUS_NAME = "org.freedesktop.portal.Desktop"
PORTAL_OBJECT_PATH = "/org/freedesktop/portal/desktop"
PORTAL_INTERFACE = "org.freedesktop.portal.Settings"
APPEARANCE_NAMESPACE = "org.freedesktop.appearance"
COLOR_SCHEME_KEY = "color-scheme"
PORTAL_TIMEOUT_MS = 2_000

# org.freedesktop.appearance color-scheme values.
NO_PREFERENCE = 0
PREFER_DARK = 1
PREFER_LIGHT = 2


def _open_portal() -> Gio.DBusProxy:
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION,
        Gio.DBusProxyFlags.DO_NOT_LOAD_PROPERTIES,
        None,
        PORTAL_BUS_NAME,
        PORTAL_OBJECT_PATH,
        PORTAL_INTERFACE,
        None,
    )


class SystemColorSchemeSync:
    def __init__(
        self,
        settings,
        *,
        portal_factory: Callable[[], Gio.DBusProxy] = _open_portal,
    ) -> None:
        self._settings = settings
        self._portal_factory = portal_factory
        self._portal = None
        # GNOME reports its normal light style as "no preference"; returning to
        # it must restore what GTK had before Mochi changed anything.
        self._gtk_default = bool(settings.props.gtk_application_prefer_dark_theme)
        self._logger = logging.getLogger(__name__)

    def start(self) -> bool:
        """Begin following the desktop; return False when there is nothing to do."""
        if self._settings.find_property("gtk-interface-color-scheme") is not None:
            # GTK 4.20+ reads this portal setting itself.
            return False
        try:
            self._portal = self._portal_factory()
        except GLib.Error as error:
            self._logger.debug("Settings portal unavailable: %s", error.message)
            return False

        self._portal.connect("g-signal", self._on_portal_signal)
        self._read("ReadOne", self._on_read_one_finished)
        return True

    def _read(self, method: str, callback) -> None:
        self._portal.call(
            method,
            GLib.Variant("(ss)", (APPEARANCE_NAMESPACE, COLOR_SCHEME_KEY)),
            Gio.DBusCallFlags.NONE,
            PORTAL_TIMEOUT_MS,
            None,
            callback,
        )

    def _on_read_one_finished(self, portal, result) -> None:
        try:
            reply = portal.call_finish(result)
        except GLib.Error as error:
            if error.matches(Gio.dbus_error_quark(), Gio.DBusError.UNKNOWN_METHOD):
                # Settings portal version 1 only has the deprecated Read.
                self._read("Read", self._on_read_finished)
            else:
                self._logger.debug("Could not read color scheme: %s", error.message)
            return
        self._apply(reply.unpack()[0])

    def _on_read_finished(self, portal, result) -> None:
        try:
            reply = portal.call_finish(result)
        except GLib.Error as error:
            self._logger.debug("Could not read color scheme: %s", error.message)
            return
        # Read wraps the value in an extra variant; unpack() removes both.
        self._apply(reply.unpack()[0])

    def _on_portal_signal(self, _portal, _sender, signal_name, parameters) -> None:
        if signal_name != "SettingChanged":
            return
        namespace, key, value = parameters.unpack()
        if namespace == APPEARANCE_NAMESPACE and key == COLOR_SCHEME_KEY:
            self._apply(value)

    def _apply(self, scheme) -> None:
        if scheme == PREFER_DARK:
            prefer_dark = True
        elif scheme == PREFER_LIGHT:
            prefer_dark = False
        else:
            prefer_dark = self._gtk_default
        self._settings.props.gtk_application_prefer_dark_theme = prefer_dark
