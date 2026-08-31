"""Qt fixtures shared by GUI unit tests."""

import os

import pytest

# GUI unit tests do not require a native window-system integration. Select the
# platform before importing Qt so native windows cannot restore OS session state.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from nxdrive.drive.qt.imports import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """Provide the single QApplication required by QWidget-based tests.

    QApplication is also a QCoreApplication, so the repository-wide ``app``
    fixture will safely reuse this instance if it is requested later.
    """
    application = QApplication.instance()
    if application is None:
        application = QApplication([])
    yield application
    application.processEvents()
