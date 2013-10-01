"""GUI prompt to manage HTTP proxy settings"""
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger

log = get_logger(__name__)

# Keep Qt an optional dependency for now
QtGui, QDialog = None, object
try:
    from PyQt4 import QtGui
    from PyQt4 import QtCore
    QDialog = QtGui.QDialog
    log.debug("Qt / PyQt4 successfully imported")
except ImportError:
    log.warning("Qt / PyQt4 is not installed: GUI is disabled")
    pass


is_dialog_open = False

PROXY_CONFIGS = ['None', 'System', 'Manual']
PROXY_TYPES = ['http', 'https']
DEFAULT_FIELD_WIDGET_WIDTH = 250


class Dialog(QDialog):
    """Dialog box to manage the HTTP proxy settings"""

    def __init__(self, fields_spec, title=None, fields_title=None,
                 callback=None):
        super(Dialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PyQt4 is not installed.")
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
        self.resize(450, -1)
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
            elif field_id == 'authenticated':
                # Checkbox
                field = QtGui.QCheckBox(spec['label'])
                if value is not None:
                    field.setChecked(value)
                # Set listener to enable / disable fields depending on
                # authentication
                if field_id == 'authenticated':
                    field.stateChanged.connect(
                            self.enable_credentials)
            else:
                # Text input
                field = QtGui.QLineEdit()
                if value is not None:
                    field.setText(value)
                if field_id == 'password':
                    field.setEchoMode(QtGui.QLineEdit.Password)
            enabled = spec.get('enabled', True)
            field.setEnabled(enabled)
            width = spec.get('width', DEFAULT_FIELD_WIDGET_WIDTH)
            field.setFixedWidth(width)
            if field_id != 'authenticated':
                layout.addWidget(label, i + 1, 0, QtCore.Qt.AlignRight)
            layout.addWidget(field, i + 1, 1)
            self.fields[field_id] = field

        self.proxy_settings_group_box.setLayout(layout)

    def enable_manual_settings(self):
        enabled = self.sender().currentText() == 'Manual'
        for field in self.fields:
            if field in ('username', 'password'):
                authenticated = self.fields['authenticated'].isChecked()
                self.fields[field].setEnabled(enabled and authenticated)
            elif field != 'config':
                self.fields[field].setEnabled(enabled)

    def enable_credentials(self):
        enabled = self.sender().isChecked()
        self.fields['username'].setEnabled(enabled)
        self.fields['password'].setEnabled(enabled)

    def accept(self):
        if self.callback is not None:
            values = dict()
            for id_, widget in self.fields.items():
                if isinstance(widget, QtGui.QComboBox):
                    value = widget.currentText()
                elif isinstance(widget, QtGui.QCheckBox):
                    value = widget.isChecked()
                else:
                    value = widget.text()
                values[id_] = value
            if not self.callback(values, self):
                return
        self.accepted = True
        super(Dialog, self).accept()

    def reject(self):
        super(Dialog, self).reject()


def prompt_proxy_settings(controller, app=None, config='System',
                         proxy_type=None, server=None, port=None,
                         authenticated=False, username=None, password=None,
                         exceptions=None):
    """Prompt a Qt dialog to manage HTTP proxy settings"""
    global is_dialog_open

    if QtGui is None:
        # Qt / PyQt4 is not installed
        log.error("Qt / PyQt4 is not installed:"
                  " use commandline options for binding a server.")
        return False

    if is_dialog_open:
        # Do not reopen the dialog multiple times
        return False

    # TODO: learn how to use Qt i18n support to handle translation of labels
    manual_proxy = config == 'Manual'
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
        {
            'id': 'authenticated',
            'label': 'Proxy server requires a password',
            'value': authenticated,
            'enabled': manual_proxy,
        },
        {
            'id': 'username',
            'label': 'Username:',
            'value': username,
            'enabled': manual_proxy and authenticated,
        },
        {
            'id': 'password',
            'label': 'Password:',
            'value': password,
            'enabled': manual_proxy and authenticated,
        },
    ]

    def set_proxy_settings(values, dialog):
        # TODO: handle  validations
        config = str(values['config'])
        proxy_type = str(values['proxy_type'])
        server = str(values['server'])
        port = str(values['port'])
        authenticated = values['authenticated']
        username = str(values['username'])
        password = str(values['password'])
        exceptions = None
        controller.set_proxy_settings(config, proxy_type=proxy_type,
                                      server=server, port=port,
                                      authenticated=authenticated,
                                      username=username, password=password,
                                      exceptions=exceptions)
        return True

    if app is None:
        # TODO: ?
        log.debug("Launching Qt prompt for HTTP proxy settings.")
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
