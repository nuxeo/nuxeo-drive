"""GUI prompt to manage application update"""
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger
from nxdrive.updater import version_compare


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

UPDATE_DIALOG_HEIGHT = 120


class UpdateDialog(QDialog):
    """Dialog box to prompt about application update."""

    def __init__(self, update_required, old_version, new_version, auto_update,
                 callback):
        super(UpdateDialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PyQt4 is not installed.")
        self.setWindowTitle('Nuxeo Drive - Update')
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.resize(-1, UPDATE_DIALOG_HEIGHT)
        self.callback = callback

        mainLayout = QtGui.QVBoxLayout()
        # Message
        if update_required:
            update_type = (
                'upgrade' if version_compare(new_version, old_version) > 0
                else 'downgrade')
            article = 'an' if update_type == 'upgrade' else 'a'
            line1_w = QtGui.QLabel('The current version of Nuxeo Drive is not'
                                   ' compatible with the Nuxeo server version,'
                                   ' %s %s is required.' % (
                                                        article, update_type))
            mainLayout.addWidget(line1_w)
            msg = 'Do you want to %s' % update_type
        else:
            msg = 'Are you sure you want to upgrade'
        msg += ' the current version of Nuxeo Drive %s to version %s ?' % (
                                                    old_version, new_version)
        line2_w = QtGui.QLabel(msg)
        mainLayout.addWidget(line2_w)

        # Auto-update
        self.auto_update_w = QtGui.QCheckBox('Automatically update Nuxeo Drive'
                                             ' next time?')
        if auto_update:
            self.auto_update_w.setChecked(True)
        mainLayout.addWidget(self.auto_update_w)

        # Button
        button_w = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Yes
                                          | QtGui.QDialogButtonBox.No)
        button_w.accepted.connect(self.accept)
        button_w.rejected.connect(self.reject)
        mainLayout.addWidget(button_w)

        self.setLayout(mainLayout)

    def accept(self):
        auto_update = self.auto_update_w.isChecked()
        self.callback(auto_update)
        super(UpdateDialog, self).accept()


def prompt_update(controller, update_required, old_version, new_version,
                  updater):
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

    def update(auto_update):
        controller.set_auto_update(auto_update)
        updater.update(new_version)

    dialog = UpdateDialog(update_required, old_version, new_version,
                          controller.is_auto_update(), callback=update)
    is_dialog_open = True
    try:
        dialog.exec_()
    except:
        dialog.reject()
        raise
    finally:
        is_dialog_open = False
    return dialog.result()
