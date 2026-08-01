"""Cleanup old test users and workspaces.

Thin wrapper that delegates to the Nuxeo-specific cleanup module.
Kept at ``tests/cleanup.py`` for backward compatibility with
``tox -e clean``.
"""

import runpy

runpy.run_module("tests.nuxeo.cleanup", run_name="__main__")
