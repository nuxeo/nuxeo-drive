"""Qt fixtures shared by GUI unit tests."""

import os
import sys

import pytest

# Unit tests run without a display on Linux CI. The platform plugin is selected
# when QApplication is created, so setting this before importing it is enough
# even though other PyQt modules may already have been imported.
if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
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
