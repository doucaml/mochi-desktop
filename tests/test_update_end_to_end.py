"""Real install → real update → real relaunch, in a sandboxed home.

The unit tests in test_update_worker.py replace downloads, commands, and the
relaunch with fakes. Mochi 0.4.0a1 shipped an updater whose relaunch crashed in
every real update because of an environment leak those fakes could not see.
This test runs the real installer, the real worker, and the real relaunched
Mochi; only the download is replaced by a local archive of this checkout.

It needs a display, git history, dbus-run-session, and network access (the
private venv may fetch setuptools>=69), and takes about a minute, so it is
opt-in: set MOCHI_RUN_UPDATE_E2E=1. CI enables it.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tarfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
# The updater users already have installed: Release v0.4.0-alpha.1.
RELEASED_UPDATER_COMMIT = "a50626988962354fc48e718328a654fd8a6cacdd"
TARGET_COMMIT = "e2e0" * 10

pytestmark = pytest.mark.skipif(
    os.environ.get("MOCHI_RUN_UPDATE_E2E") != "1",
    reason="set MOCHI_RUN_UPDATE_E2E=1 to run the real install/update/relaunch test",
)


# Mirrors the bootstrap runner, with the download pointed at a local archive and
# launched processes recorded so the test can stop them.
DRIVER_SOURCE = """\
import shutil
import subprocess
import sys
from pathlib import Path

workspace = Path(__file__).resolve().parent
sys.path.insert(0, str(workspace))

from mochi.update.model import UpdateMetadata, UpdateTarget
from mochi.update.worker import UpdateWorker

archive, launch_log, pid_file, commit = sys.argv[1:5]


def download(_url, destination, on_bytes):
    shutil.copy(archive, destination)
    on_bytes(1, 1)


def launch(args, *, env=None):
    process = subprocess.Popen(
        [str(value) for value in args],
        env=env,
        start_new_session=True,
        stdout=open(launch_log, "ab"),
        stderr=subprocess.STDOUT,
    )
    with open(pid_file, "a", encoding="utf-8") as pids:
        pids.write(f"{process.pid}\\n")
    return process


def report(progress):
    print(f"{progress.stage.value}: {progress.message}", flush=True)


worker = UpdateWorker(download_archive=download, launch_command=launch)
target = UpdateTarget(commit=commit, metadata=UpdateMetadata("e2e", "main", ()))
raise SystemExit(worker.run(target, wait_pid=None, on_progress=report))
"""


def _require(condition: bool, reason: str) -> None:
    if not condition:
        pytest.skip(reason)


def _sandbox_environment(tmp_path: Path) -> dict[str, str]:
    home = tmp_path / "home"
    for name in ("config", "data", "state", "cache"):
        (home / name).mkdir(parents=True)
    tools = tmp_path / "tools"
    tools.mkdir()
    # install.sh resolves python3 from PATH; use the interpreter that has GTK.
    (tools / "python3").symlink_to(Path(getattr(sys, "_base_executable", None) or sys.executable))

    environment = os.environ.copy()
    for name in ("PYTHONPATH", "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DESKTOP_SESSION"):
        environment.pop(name, None)
    environment.update(
        HOME=str(home),
        XDG_CONFIG_HOME=str(home / "config"),
        XDG_DATA_HOME=str(home / "data"),
        XDG_STATE_HOME=str(home / "state"),
        XDG_CACHE_HOME=str(home / "cache"),
        PATH=f"{tools}{os.pathsep}{environment.get('PATH', '')}",
        NO_COLOR="1",
        GTK_A11Y="none",
    )
    return environment


def _archive_checkout(destination: Path) -> None:
    listed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    with tarfile.open(destination, "w:gz") as archive:
        for raw_name in filter(None, listed):
            name = raw_name.decode()
            path = ROOT / name
            if path.is_file() and not path.is_symlink():
                archive.add(path, arcname=f"mochi-desktop-{TARGET_COMMIT}/{name}")


def _released_workspace(tmp_path: Path, environment: dict[str, str]) -> Path:
    """Recreate the 0.4.0a1 bootstrap: its updater code and its environment."""
    workspace = tmp_path / "released-workspace"
    (workspace / "mochi").mkdir(parents=True)
    (workspace / "mochi" / "__init__.py").write_text("", encoding="utf-8")
    exported = subprocess.run(
        ["git", "-C", str(ROOT), "archive", RELEASED_UPDATER_COMMIT, "src/mochi/update"],
        check=True,
        capture_output=True,
    ).stdout
    unpacked = tmp_path / "released-source"
    unpacked.mkdir()
    subprocess.run(["tar", "-x", "-C", str(unpacked)], input=exported, check=True)
    shutil.copytree(unpacked / "src" / "mochi" / "update", workspace / "mochi" / "update")
    # Exactly what the released bootstrap exported to the worker.
    environment["PYTHONPATH"] = str(workspace)
    environment["MOCHI_UPDATER_WORKSPACE"] = str(workspace)
    environment["MOCHI_UPDATER_ASSET_ROOT"] = str(workspace / "assets" / "mochi")
    return workspace


def _current_workspace(tmp_path: Path, environment: dict[str, str]) -> Path:
    """Create the workspace with this checkout's real bootstrap_updater."""
    from mochi.update.bootstrap import bootstrap_updater
    from mochi.update.model import UpdateMetadata, UpdateTarget

    captured: dict[str, dict[str, str]] = {}

    def capture(_args, *, env):
        captured["env"] = dict(env)
        return None

    app_home = Path(environment["XDG_DATA_HOME"]) / "mochi-desktop"
    original = os.environ.copy()
    os.environ.clear()
    os.environ.update(environment)
    try:
        bootstrap_updater(
            UpdateTarget(TARGET_COMMIT, UpdateMetadata("e2e", "main", ())),
            gui=False,
            app_home=app_home,
            source_package=ROOT / "src" / "mochi" / "update",
            asset_root=ROOT / "assets" / "mochi",
            popen=capture,
        )
    finally:
        os.environ.clear()
        os.environ.update(original)
    environment.clear()
    environment.update(captured["env"])
    return next((app_home / "update-bootstrap").iterdir())


def _stop_launched(pid_file: Path) -> None:
    if not pid_file.exists():
        return
    for line in pid_file.read_text(encoding="utf-8").split():
        try:
            os.killpg(int(line), signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass


@pytest.mark.parametrize(
    "make_workspace",
    [_released_workspace, _current_workspace],
    ids=["released-0.4.0a1-updater", "this-checkout-updater"],
)
def test_update_installs_this_checkout_and_relaunches_mochi(
    tmp_path: Path,
    make_workspace,
) -> None:
    _require(bool(os.environ.get("DISPLAY")), "needs a display (run under xvfb-run)")
    _require(shutil.which("dbus-run-session") is not None, "needs dbus-run-session")
    _require(shutil.which("git") is not None, "needs git")
    has_release = subprocess.run(
        ["git", "-C", str(ROOT), "cat-file", "-e", f"{RELEASED_UPDATER_COMMIT}^{{commit}}"],
        capture_output=True,
    ).returncode == 0
    _require(has_release, "needs git history containing the v0.4.0-alpha.1 release")

    environment = _sandbox_environment(tmp_path)
    installed = subprocess.run(
        [str(ROOT / "install.sh")],
        env=environment,
        text=True,
        capture_output=True,
        timeout=300,
    )
    assert installed.returncode == 0, installed.stdout + installed.stderr

    archive = tmp_path / "target.tar.gz"
    _archive_checkout(archive)
    workspace = make_workspace(tmp_path, environment)
    driver = workspace / "e2e_driver.py"
    driver.write_text(DRIVER_SOURCE, encoding="utf-8")
    launch_log = tmp_path / "launch.log"
    pid_file = tmp_path / "launched.pids"

    try:
        # A private session bus keeps the relaunched Mochi from finding (and
        # deferring to) a Mochi the developer is running.
        updated = subprocess.run(
            [
                "dbus-run-session",
                "--",
                sys.executable,
                str(driver),
                str(archive),
                str(launch_log),
                str(pid_file),
                TARGET_COMMIT,
            ],
            env=environment,
            text=True,
            capture_output=True,
            timeout=300,
        )
    finally:
        _stop_launched(pid_file)

    relaunch_output = launch_log.read_text(errors="replace") if launch_log.exists() else ""
    diagnostics = f"{updated.stdout}\n{updated.stderr}\n--- relaunched Mochi ---\n{relaunch_output}"
    assert updated.returncode == 0, diagnostics
    assert "success: All updated!" in updated.stdout, diagnostics
    assert "No module named 'mochi.main'" not in relaunch_output

    app_home = Path(environment["XDG_DATA_HOME"]) / "mochi-desktop"
    install_record = json.loads((app_home / "install.json").read_text(encoding="utf-8"))
    assert install_record["commit"] == TARGET_COMMIT
    assert not (app_home / "venv.backup").exists()
    assert "mochi_launcher" in (app_home / "venv" / "bin" / "mochi").read_text(encoding="utf-8")
