"""GUI prompt to manage application update"""
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger
from nxdrive.updater import version_compare
from nxdrive.updater import UpdateError
from nxdrive.updater import RootPrivilegeRequired


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

        # Message
        self.message_area = QtGui.QLabel()
        self.message_area.setWordWrap(True)
        mainLayout.addWidget(self.message_area)

        self.setLayout(mainLayout)

    def accept(self):
        auto_update = self.auto_update_w.isChecked()
        if not self.callback(auto_update, self):
            return
        super(UpdateDialog, self).accept()

    def show_message(self, message):
        self.message_area.setText(message)


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

    def update(auto_update, dialog):
        try:
            updated = updater.update(new_version)
            controller.set_auto_update(auto_update)
            return updated
        except RootPrivilegeRequired as e:
            return handle_error("Please accept the User Access Control dialog"
                                " to update Nuxeo Drive.", dialog)
        except UpdateError as e:
            if hasattr(e, 'msg'):
                msg = e.msg
            else:
                msg = "Unable to process update."
            return handle_error(msg, dialog)

    def handle_error(msg, dialog, exc_info=True):
        log.debug(msg, exc_info=exc_info)
        dialog.show_message(msg)
        return False

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
