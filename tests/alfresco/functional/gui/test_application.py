"""Functional smoke tests for the Alfresco Application entry point.

These tests require a display / Qt event loop and a live Alfresco
server; they are auto-skipped when the environment cannot support
them (via the parent ``conftest.py``'s ``pytest_collection_modifyitems``
hook, plus explicit ``pytest.importorskip`` for Qt).
"""

import pytest

qt = pytest.importorskip("PySide6.QtCore", reason="PySide6 not available")


class TestApplicationStartup:
    def test_manager_boots_with_alfresco_engine(self, manager_factory) -> None:
        """Basic smoke test: build a Manager bound to Alfresco and confirm
        it can enumerate engines without exceptions.
        """
        manager = manager_factory(with_engine=True)
        # The engine must be registered but not started (so no Qt loop is
        # required in this smoke test).
        assert list(manager.engines.values())
