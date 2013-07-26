"""GUI prompt to manage HTTP proxy settings"""
from nxdrive.client import Unauthorized
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger
import socket

log = get_logger(__name__)

# Keep QT an optional dependency for now
QtGui, QDialog = None, object
try:
    from PySide import QtGui
    QDialog = QtGui.QDialog
    log.debug("QT / PySide successfully imported")
except ImportError:
    log.warning("QT / PySide is not installed: GUI is disabled")
    pass


is_dialog_open = False


class Dialog(QDialog):
    """Dialog box to manage the HTTP proxy settings"""

    def __init__(self, fields_spec, title=None, fields_title=None,
                 callback=None):
        super(Dialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PySide is not installed.")
        self.create_proxy_settings_box(fields_spec)
        self.callback = callback
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok
                                           | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.proxy_settings_group_box)
        self.message_area = QtGui.QLabel()
        self.message_area.setWordWrap(True)
        mainLayout.addWidget(self.message_area)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)
        if title is not None:
            self.setWindowTitle(title)
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.resize(600, -1)
        self.accepted = False

    def create_proxy_settings_box(self, fields_spec):
        self.proxy_settings_group_box = QtGui.QGroupBox()
        layout = QtGui.QGridLayout()
        self.fields = {}
        for i, spec in enumerate(fields_spec):
            label = QtGui.QLabel(spec['label'])
            line_edit = QtGui.QLineEdit()
            value = spec.get('value')
            if value is not None:
                line_edit.setText(value)
            if spec.get('is_password', False):
                line_edit.setEchoMode(QtGui.QLineEdit.Password)
            line_edit.textChanged.connect(self.clear_message)
            layout.addWidget(label, i + 1, 0)
            layout.addWidget(line_edit, i + 1, 1)
            self.fields[spec['id']] = line_edit

        self.proxy_settings_group_box.setLayout(layout)

    def clear_message(self, *args, **kwargs):
        self.message_area.setText(None)

    def show_message(self, message):
        self.message_area.setText(message)

    def accept(self):
        if self.callback is not None:
            values = dict((id_, w.text())
                               for id_, w in self.fields.items())
            if not self.callback(values, self):
                return
        self.accepted = True
        super(Dialog, self).accept()

    def reject(self):
        super(Dialog, self).reject()


def prompt_proxy_settings(controller, app=None, config='system',
                         proxy_type=None, server=None, port=None,
                         authenticated=None, username=None, password=None,
                         exceptions=None):
    """Prompt a QT dialog to manage HTTP proxy settings"""
    global is_dialog_open

    if QtGui is None:
        # Qt / PySide is not installed
        log.error("QT / PySide is not installed:"
                  " use commandline options for binding a server.")
        return False

    if is_dialog_open:
        # Do not reopen the dialog multiple times
        return False

    # TODO: learn how to use QT i18n support to handle translation of labels
    fields_spec = [
        {
            'id': 'config',
            'label': 'Proxy settings:',
            'value': config,
        },
        {
            'id': 'proxy_type',
            'label': 'Proxy type:',
            'value': proxy_type,
        },
        {
            'id': 'server',
            'label': 'Server:',
            'value': server,
        },
        {
            'id': 'port',
            'label': 'Port:',
            'value': port,
        },
    ]

    def set_proxy_settings(values, dialog):
        # TODO: handle  validations
        config = values['config']
        if config != 'manual':
            controller.set_proxy_settings(config)
        else:
            proxy_type = values['proxy_type']
            server = values['server']
            port = values['port']
            authenticated = False
            username = None
            password = None
            exceptions = None
            controller.set_proxy_settings(config, proxy_type=proxy_type,
                                          server=server, port=port,
                                          authenticated=authenticated,
                                          username=username, password=password,
                                          exceptions=exceptions)
        return True

    if app is None:
        # TODO: ?
        log.debug("Launching QT prompt for HTTP proxy settings.")
        QtGui.QApplication([])
    dialog = Dialog(fields_spec, title="Nuxeo Drive - Proxy settings",
                    callback=set_proxy_settings)
    is_dialog_open = True
    try:
        dialog.exec_()
    except:
        dialog.reject()
        raise
    finally:
        is_dialog_open = False
    return dialog.accepted
