"""Fixtures for Alfresco Windows integration tests.

Re-exports the ``exe`` fixture from the common integration conftest.
"""

from tests.common.integration.windows.conftest import (  # noqa: F401
    exe,
    final_exe,
    pytest_addoption,
)
