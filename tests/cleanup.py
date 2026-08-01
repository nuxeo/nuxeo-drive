"""Cleanup old test users and workspaces.

Thin wrapper that delegates to the Nuxeo-specific cleanup module.
Kept at ``tests/cleanup.py`` for backward compatibility with
``tox -e clean``.
"""

import sys
from pathlib import Path

# Ensure the project root is on sys.path so that "tests" is importable
# as a package even when running via ``python tests/cleanup.py``.
_root = str(Path(__file__).resolve().parent.parent)
if _root not in sys.path:
    sys.path.insert(0, _root)

import runpy

runpy.run_module("tests.nuxeo.cleanup", run_name="__main__")
