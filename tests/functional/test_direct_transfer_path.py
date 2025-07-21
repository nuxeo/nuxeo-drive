"""
Functional test case written as part of user story : https://hyland.atlassian.net/browse/NXDRIVE-3011
Covers the changes made for Direct Transfer with workspace path specified from WebUI
"""

from unittest.mock import patch

from PyQt5 import QtCore
from PyQt5.QtCore import QObject

from nxdrive.gui.application import Application

from ..markers import mac_only


class Mock_Qt:
    def __init__(self) -> None:
        self.appUpdate = self
        self.changed = self
        self.getLastFiles = self
        self.setMessage: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal
        self.setStatus = self
        self.updateAvailable: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal
        self.updateProgress: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal

    def addButton(self, *args):
        pass

    def clickedButton(self):
        pass

    def close(self):
        pass

    def connect(self, *args):
        pass

    def emit(self, *args):
        pass

    def exec_(self):
        pass

    def height(self):
        return 0

    def raise_(self):
        pass

    def rootContext(self):
        pass

    def setCheckBox(self, *args):
        pass

    def setFlags(self, *args):
        pass

    def setGeometry(self, *args):
        pass

    def setIconPixmap(self, *args):
        pass

    def setMinimumHeight(self, *args):
        pass

    def setMinimumWidth(self, *args):
        pass

    def setSource(self, *args):
        pass

    def setText(self, *args):
        pass

    def setX(self, *args):
        pass

    def setY(self, *args):
        pass

    def setWindowTitle(self, *args):
        pass

    def show(self):
        pass

    def size(self):
        return 0

    def width(self):
        return 0


@mac_only
def test_handle_nxdrive_url(manager_factory):
    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    with patch(
        "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
    ) as mock_root_objects, patch(
        "PyQt5.QtCore.QObject.findChild"
    ) as mock_find_child, patch(
        "nxdrive.gui.application.Application.init_nxdrive_listener"
    ) as mock_listener, patch(
        "nxdrive.gui.application.Application.show_metrics_acceptance"
    ) as mock_show_metrics, patch(
        "nxdrive.engine.activity.FileAction.__repr__"
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        app = Application(manager)
        mock_url = "nxdrive://direct-transfer/https/random.com/nuxeo/default-domain/UserWorkspaces"
        assert app._handle_nxdrive_url(mock_url) is True
        app.exit(0)
