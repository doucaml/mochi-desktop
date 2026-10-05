"""Opt-in real session-bus round trip for ``mochi-agent-signal``.

Run with MOCHI_RUN_DBUS_TESTS=1 python -m pytest tests/test_agent_dbus_integration.py,
ideally under ``dbus-run-session``. A probe application on a private name
registers the same ``agent-event`` action Mochi does; the installed Mochi and
its bus name are never touched.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from mochi import agent_signal

pytestmark = pytest.mark.skipif(
    os.environ.get("MOCHI_RUN_DBUS_TESTS") != "1",
    reason="requires opt-in access to a session bus",
)

PROBE = textwrap.dedent(
    """
    import sys

    import gi

    gi.require_version("Gio", "2.0")
    from gi.repository import Gio, GLib

    class Probe(Gio.Application):
        def __init__(self, app_id):
            super().__init__(application_id=app_id, flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            action = Gio.SimpleAction.new("agent-event", GLib.VariantType.new("(ss)"))
            action.connect("activate", self._on_event)
            self.add_action(action)

        def do_activate(self):
            self.hold()
            print("READY", flush=True)

        def _on_event(self, _action, parameter):
            event, token = parameter.unpack()
            print(f"GOT {event} {token}", flush=True)
            if event == "ended":
                self.release()
                self.quit()

    sys.exit(Probe(sys.argv[1]).run([sys.argv[0]]))
    """
)


def _pipe_with(payload: bytes):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    return os.fdopen(read_fd, "rb")


def _read_line(process: subprocess.Popen, deadline_seconds: float = 5.0) -> str:
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        line = process.stdout.readline()
        if line:
            return line.strip()
    raise AssertionError("probe produced no output in time")


def test_bridge_delivers_through_the_real_session_bus(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("gi")
    if shutil.which("gdbus") is None:
        pytest.skip("gdbus is unavailable")

    app_id = f"io.github.mochi_desktop.AgentTest.p{os.getpid()}"
    probe_path = tmp_path / "probe.py"
    probe_path.write_text(PROBE, encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, str(probe_path), app_id],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        assert _read_line(process) == "READY"
        monkeypatch.setattr(agent_signal, "APPLICATION_ID", app_id)
        monkeypatch.setattr(agent_signal, "OBJECT_PATH", "/" + app_id.replace(".", "/"))

        assert agent_signal.main(
            ["working"], stdin=_pipe_with(b'{"session_id": "bus-test", "prompt": "x"}')
        ) == 0

        token = hashlib.sha256(b"claude:bus-test").hexdigest()[:16]
        assert _read_line(process) == f"GOT working {token}"

        assert agent_signal.main(["ended"], stdin=_pipe_with(b"{}")) == 0
        assert _read_line(process).startswith("GOT ended ")
        assert process.wait(timeout=5) == 0
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_bridge_is_quiet_and_fast_when_nobody_listens(monkeypatch, capfd) -> None:
    if shutil.which("gdbus") is None:
        pytest.skip("gdbus is unavailable")
    monkeypatch.setattr(
        agent_signal, "APPLICATION_ID", f"io.github.mochi_desktop.Absent.p{os.getpid()}"
    )

    started = time.monotonic()
    assert agent_signal.main(["working"], stdin=_pipe_with(b"{}")) == 0

    assert time.monotonic() - started < 1.5
    assert capfd.readouterr() == ("", "")
