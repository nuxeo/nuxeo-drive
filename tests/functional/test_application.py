"""
Functional tests for nxdrive/gui/application.py
"""

from unittest.mock import patch

from PyQt5.QtCore import QObject

from nxdrive.gui.application import Application
from tests.functional.mocked_classes import Mock_Qt


def test_exit_app(manager_factory):
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    with patch(
        "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
    ) as mock_root_objects, patch("PyQt5.QtCore.QObject.findChild") as mock_find_child:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        app = Application(manager)
        assert app.exit_app() is None
