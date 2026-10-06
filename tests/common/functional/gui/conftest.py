"""Shared Qt fixtures for the functional GUI tests."""

import os

# Functional GUI tests do not require a native window-system integration.
# Select the platform before importing Qt so native windows cannot restore OS
# session state.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from nxdrive.drive.qt.imports import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Provide the single QApplication required by QWidget-based tests."""
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    yield application
    application.processEvents()
