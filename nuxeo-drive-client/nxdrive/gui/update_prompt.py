"""GUI prompt to manage application update"""
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

UPDATE_DIALOG_HEIGHT = 100
BOLD_STYLE = 'font-weight: bold;'


class UpdateDialog(QDialog):
    """Dialog box to prompt about application update."""

    def __init__(self, old_version, new_version, callback):
        super(UpdateDialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PyQt4 is not installed.")
        self.setWindowTitle('Nuxeo Drive - Update')
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.resize(-1, UPDATE_DIALOG_HEIGHT)
        self.callback = callback

        # Message
        text_l = QtGui.QHBoxLayout()
        msg1_w = QtGui.QLabel('Are you sure you want to upgrade the current'
                              ' version of Nuxeo Drive')
        msg2_w = QtGui.QLabel('to the new version')
        msg3_w = QtGui.QLabel('?')
        old_version_w = QtGui.QLabel(old_version)
        old_version_w.setStyleSheet(BOLD_STYLE)
        new_version_w = QtGui.QLabel(new_version)
        new_version_w.setStyleSheet(BOLD_STYLE)
        text_l.addWidget(msg1_w)
        text_l.addWidget(old_version_w)
        text_l.addWidget(msg2_w)
        text_l.addWidget(new_version_w)
        text_l.addWidget(msg3_w)

        # Button
        button_w = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Yes
                                          | QtGui.QDialogButtonBox.No)
        button_w.accepted.connect(self.accept)
        button_w.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addLayout(text_l)
        mainLayout.addWidget(button_w)
        self.setLayout(mainLayout)

    def accept(self):
        self.callback()
        super(UpdateDialog, self).accept()


def prompt_update(old_version, new_version, updater):
    """Display a Qt dialog to prompt about application update"""
    global is_dialog_open

    if QtGui is None:
        # Qt / PyQt4 is not installed
        log.error("Qt / PyQt4 is not installed.")
        return False

    if is_dialog_open:
        # Do not reopen the dialog multiple times
        return False

    if updater is None:
        raise ValueError("updater is mandatory for update prompt dialog")

    def update():
        updater.update(new_version)

    dialog = UpdateDialog(old_version, new_version, callback=update)
    is_dialog_open = True
    try:
        dialog.exec_()
    except:
        dialog.reject()
        raise
    finally:
        is_dialog_open = False
    return dialog.result()
