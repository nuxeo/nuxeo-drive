"""GUI dialog to notify about application update"""
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger


log = get_logger(__name__)

# Keep Qt an optional dependency for now
QtGui, QDialog = None, object
try:
    from PyQt4 import QtGui
    QDialog = QtGui.QDialog
    log.debug("Qt / PyQt4 successfully imported")
except ImportError:
    log.warning("Qt / PyQt4 is not installed: GUI is disabled")
    pass

is_dialog_open = False

BOLD_STYLE = 'font-weight: bold;'


class UpdatedDialog(QDialog):
    """Dialog box to notify about application update."""

    def __init__(self, version):
        super(UpdatedDialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PyQt4 is not installed.")
        self.setWindowTitle('Nuxeo Drive - Update status')
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.resize(-1, 100)

        # Message
        text_l = QtGui.QHBoxLayout()
        msg_w = QtGui.QLabel('Nuxeo Drive successfully updated to version')
        version_w = QtGui.QLabel(version)
        version_w.setStyleSheet(BOLD_STYLE)
        text_l.addWidget(msg_w)
        text_l.addWidget(version_w)

        # Button
        button_w = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok)
        button_w.accepted.connect(self.accept)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(text_l)
        mainLayout.addWidget(button_w)
        self.setLayout(mainLayout)


def notify_updated(version):
    """Display a Qt dialog to notify about application update"""
    global is_dialog_open

    if QtGui is None:
        # Qt / PyQt4 is not installed
        log.error("Qt / PyQt4 is not installed.")
        return False

    if is_dialog_open:
        # Do not reopen the dialog multiple times
        return False

    dialog = UpdatedDialog(version)
    is_dialog_open = True
    try:
        dialog.exec_()
    except:
        dialog.reject()
        raise
    finally:
        is_dialog_open = False
    return dialog.result()
