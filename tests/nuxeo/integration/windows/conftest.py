"""Fixtures for Nuxeo Windows integration tests.

Re-exports the ``exe`` fixture from the common integration conftest.
"""

from tests.common.integration.windows.conftest import (  # noqa: F401
    exe,
    final_exe,
)


def pytest_addoption(parser):
    """Register --executable only if not already registered."""
    try:
        parser.addoption(
            "--executable",
            action="store",
            default="dist\\ndrive\\ndrive.exe",
            help="Path to the executable to test.",
        )
    except ValueError:
        pass
