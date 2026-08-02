"""Cleanup old test users and workspaces.

Thin wrapper that delegates to the Nuxeo-specific cleanup module.
Kept at ``tests/cleanup.py`` for backward compatibility with
``tox -e clean``.
"""

import sys
from pathlib import Path

# When invoked as ``python tests/cleanup.py``, Python prepends the script's
# directory (tests/) to sys.path.  This causes ``tests/nuxeo/`` to shadow the
# third-party ``nuxeo`` package.  Fix by replacing that entry with the project
# root so both ``tests`` (as a package) and ``nuxeo`` (third-party) resolve
# correctly.
_root = str(Path(__file__).resolve().parent.parent)
_tests_dir = str(Path(__file__).resolve().parent)
if sys.path and sys.path[0] == _tests_dir:
    sys.path[0] = _root
elif _root not in sys.path:
    sys.path.insert(0, _root)

import runpy

runpy.run_path(_tests_dir + "/nuxeo/cleanup.py", run_name="__main__")
