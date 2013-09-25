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

PROXY_CONFIGS = ['none', 'system', 'manual']
PROXY_TYPES = ['http', 'https']


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
            field_id = spec['id']
            label = QtGui.QLabel(spec['label'])
            value = spec.get('value')
            items = spec.get('items')
            # Combo box
            if items is not None:
                field = QtGui.QComboBox()
                field.addItems(items)
                if value is not None:
                    field.setCurrentIndex(items.index(value))
                # Set listener to enable / disable fields depending on
                # proxy config
                if field_id == 'config':
                    field.currentIndexChanged.connect(
                            self.enable_manual_settings)
            else:
                # Text input
                field = QtGui.QLineEdit()
                if value is not None:
                    field.setText(value)
                if spec.get('is_password', False):
                    field.setEchoMode(QtGui.QLineEdit.Password)
            enabled = spec.get('enabled', True)
            field.setEnabled(enabled)
            width = spec.get('width')
            if width is not None:
                field.setFixedWidth(width)
            layout.addWidget(label, i + 1, 0)
            layout.addWidget(field, i + 1, 1)
            self.fields[field_id] = field

        self.proxy_settings_group_box.setLayout(layout)

    def enable_manual_settings(self):
        enabled = self.sender().currentText() == 'manual'
        for field in self.fields:
            if field != 'config':
                self.fields[field].setEnabled(enabled)

    def accept(self):
        if self.callback is not None:
            values = dict((id_,
                           (w.currentText() if isinstance(w, QtGui.QComboBox)
                            else w.text()))
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
    manual_proxy = config == 'manual'
    fields_spec = [
        {
            'id': 'config',
            'label': 'Proxy settings:',
            'value': config,
            'items': PROXY_CONFIGS,
            'width': 80,
        },
        {
            'id': 'proxy_type',
            'label': 'Proxy type:',
            'value': proxy_type,
            'items': PROXY_TYPES,
            'enabled': manual_proxy,
            'width': 80,
        },
        {
            'id': 'server',
            'label': 'Server:',
            'value': server,
            'enabled': manual_proxy,
        },
        {
            'id': 'port',
            'label': 'Port:',
            'value': port,
            'enabled': manual_proxy,
        },
    ]

    def set_proxy_settings(values, dialog):
        # TODO: handle  validations
        config = str(values['config'])
        proxy_type = str(values['proxy_type'])
        server = str(values['server'])
        port = str(values['port'])
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
