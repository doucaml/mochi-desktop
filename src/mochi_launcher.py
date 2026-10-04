"""Console entry point that survives Mochi 0.4.0a1's updater environment.

The 0.4.0a1 updater relaunched the freshly installed runtime with PYTHONPATH
pointing at its bootstrap workspace. That workspace holds a stub ``mochi``
package containing only ``mochi.update``, so it shadowed the real package and
``from mochi.main import main`` failed before any new code could run.

This module deliberately lives outside the ``mochi`` package so the stub cannot
shadow it. It removes the updater workspace from the import path before Mochi
is imported, which lets an already-installed 0.4.0a1 updater deliver a fixed
release. Ordinary launches are unaffected: without the updater's marker
variable this only returns ``mochi.main.main()``.
"""

from __future__ import annotations

from collections.abc import MutableMapping
import os
from pathlib import Path
import sys


UPDATER_ENVIRONMENT_PREFIX = "MOCHI_UPDATER_"
UPDATER_WORKSPACE_VARIABLE = "MOCHI_UPDATER_WORKSPACE"


def _is_within(path: str, root: Path) -> bool:
    try:
        resolved = Path(path).resolve()
    except (OSError, RuntimeError):
        return False
    return resolved == root or root in resolved.parents


def drop_updater_workspace(
    environ: MutableMapping[str, str] | None = None,
    path: list[str] | None = None,
    modules: MutableMapping[str, object] | None = None,
) -> bool:
    """Forget an updater bootstrap workspace leaked into this process.

    Returns True when a workspace was found and removed.
    """
    environ = os.environ if environ is None else environ
    path = sys.path if path is None else path
    modules = sys.modules if modules is None else modules

    workspace_value = environ.get(UPDATER_WORKSPACE_VARIABLE)
    if not workspace_value:
        return False
    # The bootstrap's private variables (asset root, workspace) describe a
    # temporary directory that is deleted when the updater exits.
    for name in [key for key in environ if key.startswith(UPDATER_ENVIRONMENT_PREFIX)]:
        del environ[name]

    workspace = Path(workspace_value).resolve()
    path[:] = [entry for entry in path if not _is_within(entry or os.getcwd(), workspace)]

    remaining = [
        entry
        for entry in environ.get("PYTHONPATH", "").split(os.pathsep)
        if entry and not _is_within(entry, workspace)
    ]
    if remaining:
        environ["PYTHONPATH"] = os.pathsep.join(remaining)
    else:
        environ.pop("PYTHONPATH", None)

    for name in [key for key in modules if key == "mochi" or key.startswith("mochi.")]:
        module_file = getattr(modules[name], "__file__", None)
        if module_file is None or _is_within(module_file, workspace):
            del modules[name]
    return True


def main() -> int:
    drop_updater_workspace()
    from mochi.main import main as mochi_main

    return mochi_main()


if __name__ == "__main__":
    raise SystemExit(main())
