"""The console entry point must survive the 0.4.0a1 updater's environment."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tomllib
from types import SimpleNamespace

from mochi_launcher import drop_updater_workspace


ROOT = Path(__file__).resolve().parents[1]
SOURCE_TREE = ROOT / "src"


def _stub_workspace(tmp_path: Path) -> Path:
    """Recreate the bootstrap workspace: a ``mochi`` package with only ``update``."""
    workspace = tmp_path / "update-bootstrap" / "update-abc"
    (workspace / "mochi" / "update").mkdir(parents=True)
    (workspace / "mochi" / "__init__.py").write_text("", encoding="utf-8")
    (workspace / "mochi" / "update" / "__init__.py").write_text("", encoding="utf-8")
    return workspace


def test_console_script_uses_the_unshadowable_launcher() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert project["project"]["scripts"]["mochi"] == "mochi_launcher:main"
    assert "mochi_launcher" in project["tool"]["setuptools"]["py-modules"]


def test_workspace_paths_modules_and_variables_are_removed(tmp_path: Path) -> None:
    workspace = _stub_workspace(tmp_path)
    environ = {
        "MOCHI_UPDATER_WORKSPACE": str(workspace),
        "MOCHI_UPDATER_ASSET_ROOT": str(workspace / "assets" / "mochi"),
        "PYTHONPATH": os.pathsep.join([str(workspace), "/home/me/dev"]),
        "HOME": "/home/me",
    }
    path = ["/venv/bin", str(workspace), "/venv/lib/site-packages"]
    modules = {
        "mochi": SimpleNamespace(__file__=str(workspace / "mochi" / "__init__.py")),
        "mochi.update": SimpleNamespace(
            __file__=str(workspace / "mochi" / "update" / "__init__.py")
        ),
        "mochi_other": SimpleNamespace(__file__="/elsewhere/mochi_other.py"),
    }

    assert drop_updater_workspace(environ, path, modules) is True

    assert path == ["/venv/bin", "/venv/lib/site-packages"]
    assert environ == {"PYTHONPATH": "/home/me/dev", "HOME": "/home/me"}
    assert list(modules) == ["mochi_other"]


def test_ordinary_launch_is_left_alone() -> None:
    environ = {
        "PYTHONPATH": "/home/me/dev",
        # A developer pointing the in-app updater window at local art.
        "MOCHI_UPDATER_ASSET_ROOT": "/home/me/art",
    }
    path = ["/venv/bin", "/home/me/dev"]

    assert drop_updater_workspace(environ, path, {}) is False

    assert environ == {
        "PYTHONPATH": "/home/me/dev",
        "MOCHI_UPDATER_ASSET_ROOT": "/home/me/art",
    }
    assert path == ["/venv/bin", "/home/me/dev"]


def _launch(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    script = "import sys; sys.argv = ['mochi', '--help']; import mochi_launcher; mochi_launcher.main()"
    return subprocess.run(
        [sys.executable, "-c", script],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_launcher_starts_mochi_under_the_leaked_updater_environment(
    tmp_path: Path,
) -> None:
    workspace = _stub_workspace(tmp_path)
    environment = os.environ.copy()
    # The stub precedes the real package, exactly as in a 0.4.0a1 relaunch.
    environment["PYTHONPATH"] = os.pathsep.join([str(workspace), str(SOURCE_TREE)])
    environment["MOCHI_UPDATER_WORKSPACE"] = str(workspace)

    completed = _launch(environment)

    assert completed.returncode == 0, completed.stderr
    assert "A tiny friend for your desktop." in completed.stdout


def test_without_the_launcher_the_stub_shadows_mochi(tmp_path: Path) -> None:
    """Documents the 0.4.0a1 failure the launcher exists to prevent."""
    workspace = _stub_workspace(tmp_path)
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join([str(workspace), str(SOURCE_TREE)])

    completed = subprocess.run(
        [sys.executable, "-c", "from mochi.main import main"],
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "No module named 'mochi.main'" in completed.stderr
