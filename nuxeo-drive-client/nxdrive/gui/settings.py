"""GUI prompt to manage settings"""
from nxdrive.client import Unauthorized
from nxdrive.gui.resources import find_icon
from nxdrive.logging_config import get_logger
from nxdrive.controller import ServerBindingSettings
from nxdrive.controller import ProxySettings
from nxdrive.controller import MissingToken
from nxdrive.client.base_automation_client import get_proxies_for_handler
from nxdrive.client.base_automation_client import get_proxy_handler
import urllib2
import socket

WindowsError = None
try:
    from exceptions import WindowsError
except ImportError:
    pass  # this will never be raised under unix

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
PROXY_TEST_HOST = 'www.google.com'
DEFAULT_FIELD_WIDGET_WIDTH = 250

LICENSE_LINK = (
    '<a href ="http://github.com/nuxeo/nuxeo-drive/blob/master/LICENSE.txt">'
    'LICENSE.txt</a>')
SOURCE_LINK = ('<a href ="http://github.com/nuxeo/nuxeo-drive">'
               'http://github.com/nuxeo/nuxeo-drive</a>')

BOLD_STYLE = 'font-weight: bold;'


class Dialog(QDialog):
    """Tabbed dialog box to manage settings

    Available tabs for now: Accounts (server bindings), Proxy settings
    """

    def __init__(self, sb_field_spec, proxy_field_spec, version,
                 title=None, callback=None):
        super(Dialog, self).__init__()
        if QtGui is None:
            raise RuntimeError("PyQt4 is not installed.")
        if title is not None:
            self.setWindowTitle(title)
        icon = find_icon('nuxeo_drive_icon_64.png')
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))
        self.resize(500, -1)
        self.accepted = False
        self.callback = callback

        # Fields
        self.sb_fields = {}
        self.proxy_fields = {}

        # Style sheet
        self.setStyleSheet('QGroupBox {border: none;}')

        # Tabs
        account_box = self.get_account_box(sb_field_spec)
        proxy_box = self.get_proxy_box(proxy_field_spec)
        about_box = self.get_about_box(version)
        self.tabs = QtGui.QTabWidget()
        self.tabs.addTab(account_box, 'Accounts')
        self.tabs.addTab(proxy_box, 'Proxy settings')
        self.tabs.addTab(about_box, 'About')

        # Message
        self.message_area = QtGui.QLabel()
        self.message_area.setWordWrap(True)

        # Buttons
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok
                                           | QtGui.QDialogButtonBox.Cancel)
        buttonBox.accepted.connect(self.accept)
        buttonBox.rejected.connect(self.reject)

        mainLayout = QtGui.QVBoxLayout()
        mainLayout.addWidget(self.tabs)
        mainLayout.addWidget(self.message_area)
        mainLayout.addWidget(buttonBox)
        self.setLayout(mainLayout)

    def get_account_box(self, field_spec):
        box = QtGui.QGroupBox()
        box.setFixedHeight(200)
        layout = QtGui.QGridLayout()
        for i, spec in enumerate(field_spec):
            field_id = spec['id']
            value = spec.get('value')
            if field_id == 'update_password':
                if spec.get('display'):
                    field = QtGui.QCheckBox(spec['label'])
                    # Set listener to enable / disable password field
                    field.stateChanged.connect(self.enable_password)
                    layout.addWidget(field, i + 1, 1)
                    self.sb_fields[field_id] = field
            else:
                label = QtGui.QLabel(spec['label'])
                line_edit = QtGui.QLineEdit()
                if value is not None:
                    line_edit.setText(str(value))
                if spec.get('secret', False):
                    line_edit.setEchoMode(QtGui.QLineEdit.Password)
                enabled = spec.get('enabled', True)
                line_edit.setEnabled(enabled)
                line_edit.textChanged.connect(self.clear_message)
                if field_id != 'initialized':
                    layout.addWidget(label, i + 1, 0)
                    layout.addWidget(line_edit, i + 1, 1)
                self.sb_fields[field_id] = line_edit
        box.setLayout(layout)
        return box

    def enable_password(self):
        enabled = self.sender().isChecked()
        self.sb_fields['password'].setEnabled(enabled)

    def clear_message(self, *args, **kwargs):
        self.message_area.clear()

    def get_proxy_box(self, field_spec):
        box = QtGui.QGroupBox()
        layout = QtGui.QGridLayout()
        for i, spec in enumerate(field_spec):
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
                if field_id == 'proxy_config':
                    field.currentIndexChanged.connect(
                            self.enable_manual_settings)
            elif field_id == 'proxy_authenticated':
                # Checkbox
                field = QtGui.QCheckBox(spec['label'])
                if value is not None:
                    field.setChecked(value)
                # Set listener to enable / disable fields depending on
                # authentication
                if field_id == 'proxy_authenticated':
                    field.stateChanged.connect(
                            self.enable_credentials)
            else:
                # Text input
                if field_id == 'proxy_exceptions':
                    field = QtGui.QTextEdit()
                else:
                    field = QtGui.QLineEdit()
                if value is not None:
                    field.setText(value)
                if field_id == 'proxy_password':
                    field.setEchoMode(QtGui.QLineEdit.Password)
            enabled = spec.get('enabled', True)
            field.setEnabled(enabled)
            width = spec.get('width', DEFAULT_FIELD_WIDGET_WIDTH)
            field.setFixedWidth(width)
            if field_id != 'proxy_authenticated':
                layout.addWidget(label, i + 1, 0, QtCore.Qt.AlignRight)
            layout.addWidget(field, i + 1, 1)
            self.proxy_fields[field_id] = field
        box.setLayout(layout)
        return box

    def enable_manual_settings(self):
        enabled = self.sender().currentText() == 'Manual'
        for field in self.proxy_fields:
            if field in ('proxy_username', 'proxy_password'):
                authenticated = (self.proxy_fields['proxy_authenticated']
                                 .isChecked())
                self.proxy_fields[field].setEnabled(enabled and authenticated)
            elif field != 'proxy_config':
                self.proxy_fields[field].setEnabled(enabled)

    def enable_credentials(self):
        enabled = self.sender().isChecked()
        self.proxy_fields['proxy_username'].setEnabled(enabled)
        self.proxy_fields['proxy_password'].setEnabled(enabled)

    def show_message(self, message, tab_index=0):
        self.tabs.setCurrentIndex(tab_index)
        self.message_area.setText(message)

    def get_about_box(self, version_number):
        box = QtGui.QGroupBox()
        layout = QtGui.QVBoxLayout()

        # Version
        version_label = QtGui.QLabel('Version')
        version_label.setStyleSheet(BOLD_STYLE)
        layout.addWidget(version_label)
        version_widget = QtGui.QLabel('Nuxeo Drive v' + version_number)
        version_widget.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(version_widget)

        # License
        license_label = QtGui.QLabel('License')
        license_label.setStyleSheet(BOLD_STYLE)
        license_label.setContentsMargins(0, 20, 0, 0)
        layout.addWidget(license_label)
        license_widget = QtGui.QLabel(LICENSE_LINK)
        license_widget.setOpenExternalLinks(True)
        license_widget.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(license_widget)

        # Source code
        source_label = QtGui.QLabel('Source code')
        source_label.setStyleSheet(BOLD_STYLE)
        source_label.setContentsMargins(0, 20, 0, 0)
        layout.addWidget(source_label)
        source_widget = QtGui.QLabel(SOURCE_LINK)
        source_widget.setOpenExternalLinks(True)
        source_widget.setContentsMargins(20, 0, 0, 0)
        layout.addWidget(source_widget)

        layout.setAlignment(QtCore.Qt.AlignTop)
        box.setLayout(layout)
        return box

    def accept(self):
        if self.callback is not None:
            values = dict()
            self.read_field_values(self.sb_fields, values)
            self.read_field_values(self.proxy_fields, values)
            if not self.callback(values, self):
                return
        self.accepted = True
        super(Dialog, self).accept()

    def read_field_values(self, fields, values):
        for id_, widget in fields.items():
            if isinstance(widget, QtGui.QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QtGui.QCheckBox):
                value = widget.isChecked()
            elif isinstance(widget, QtGui.QTextEdit):
                value = widget.toPlainText()
            else:
                value = widget.text()
            values[id_] = value

    def reject(self):
        for id_, widget in self.sb_fields.items():
            if id_ == 'update_password':
                widget.stateChanged.disconnect(self.enable_password)
        super(Dialog, self).reject()


def prompt_settings(controller, sb_settings, proxy_settings, version,
                    app=None):
    """Prompt a Qt dialog to manage settings"""
    global is_dialog_open

    timeout_msg = ("Connection timed out, please check"
                   " your Internet connection and retry.")

    if QtGui is None:
        # Qt / PyQt4 is not installed
        log.error("Qt / PyQt4 is not installed:"
                  " use commandline options for binding a server.")
        return False

    if is_dialog_open:
        # Do not reopen the dialog multiple times
        return False

    # TODO: learn how to use Qt i18n support to handle translation of labels
    # Server binding fields
    sb_field_spec = [
        {
            'id': 'url',
            'label': 'Nuxeo server URL:',
            'value': sb_settings.server_url,
            'enabled': not sb_settings.initialized,
        },
        {
            'id': 'username',
            'label': 'Username:',
            'value': sb_settings.username,
            'enabled': (not sb_settings.initialized
                        or sb_settings.pwd_update_required),
        },
        {
            'id': 'update_password',
            'label': 'Update password',
            'value': False,
            'display': (sb_settings.initialized
                        and not sb_settings.pwd_update_required),
        },
        {
            'id': 'password',
            'label': 'Password:',
            'secret': True,
            'enabled': (not sb_settings.initialized
                        or sb_settings.pwd_update_required),
        },
        {
            'id': 'initialized',
            'label': '',
            'value': sb_settings.initialized,
        },
    ]

    # Proxy fields
    manual_proxy = proxy_settings.config == 'Manual'
    proxy_field_spec = [
        {
            'id': 'proxy_config',
            'label': 'Proxy settings:',
            'value': proxy_settings.config,
            'items': PROXY_CONFIGS,
            'width': 80,
        },
        {
            'id': 'proxy_type',
            'label': 'Proxy type:',
            'value': proxy_settings.proxy_type,
            'items': PROXY_TYPES,
            'enabled': manual_proxy,
            'width': 80,
        },
        {
            'id': 'proxy_server',
            'label': 'Server:',
            'value': proxy_settings.server,
            'enabled': manual_proxy,
        },
        {
            'id': 'proxy_port',
            'label': 'Port:',
            'value': proxy_settings.port,
            'enabled': manual_proxy,
        },
        {
            'id': 'proxy_authenticated',
            'label': 'Proxy server requires a password',
            'value': proxy_settings.authenticated,
            'enabled': manual_proxy,
        },
        {
            'id': 'proxy_username',
            'label': 'Username:',
            'value': proxy_settings.username,
            'enabled': manual_proxy and proxy_settings.authenticated,
        },
        {
            'id': 'proxy_password',
            'label': 'Password:',
            'value': proxy_settings.password,
            'enabled': manual_proxy and proxy_settings.authenticated,
        },
        {
            'id': 'proxy_exceptions',
            'label': 'No proxy for:',
            'value': proxy_settings.exceptions,
            'enabled': manual_proxy,
        },
    ]

    def validate(values, dialog):
        proxy_settings = get_proxy_settings(values)
        if not check_proxy_settings(proxy_settings, dialog):
            return False
        if not bind_server(values, proxy_settings, dialog):
            return False
        try:
            controller.set_proxy_settings(proxy_settings)
            return True
        except MissingToken as e:
            dialog.show_message(e.message)
            return False

    def check_proxy_settings(proxy_settings, dialog):
        if proxy_settings.config == 'None':
            return True
        try:
            proxies, _ = get_proxies_for_handler(proxy_settings)
            proxy_handler = get_proxy_handler(proxies)
            if proxy_handler.proxies:
                # System or manual proxy set, try a GET on test URL
                opener = urllib2.build_opener(proxy_handler)
                protocol = proxy_handler.proxies.iterkeys().next()
                test_url = protocol + '://' + PROXY_TEST_HOST
                opener.open(urllib2.Request(test_url))
            return True
        except socket.timeout:
            return handle_error(timeout_msg, dialog, tab_index=1)
        except urllib2.HTTPError as e:
            msg = "HTTP error %d" % e.code
            if hasattr(e, 'msg'):
                msg = msg + ": " + e.msg
            return handle_error(msg, dialog, tab_index=1)
        except Exception as e:
            if hasattr(e, 'msg'):
                msg = e.msg
            else:
                msg = "Unable to connect to proxy server."
            return handle_error(msg, dialog, tab_index=1)

    def get_proxy_settings(values):
        return ProxySettings(config=str(values['proxy_config']),
                             proxy_type=str(values['proxy_type']),
                             server=str(values['proxy_server']),
                             port=str(values['proxy_port']),
                             authenticated=values['proxy_authenticated'],
                             username=str(values['proxy_username']),
                             password=str(values['proxy_password']),
                             exceptions=str(values['proxy_exceptions']))

    def bind_server(values, proxy_settings, dialog):
        initialized = values.get('initialized')
        update_password = values.get('update_password')
        if (initialized == 'True' and update_password is False):
            return True
        url = values['url']
        if not url:
            dialog.show_message("The Nuxeo server URL is required.")
            return False
        url = str(url)
        if (not url.startswith("http://")
            and not url.startswith('https://')):
            dialog.show_message("Not a valid HTTP url.")
            return False
        username = values['username']
        if not username:
            dialog.show_message("A user name is required")
            return False
        username = str(username)
        password = str(values['password'])
        dialog.show_message("Connecting to %s ..." % url)
        try:
            controller.refresh_proxies(proxy_settings)
            controller.bind_server(sb_settings.local_folder, url, username,
                                   password)
            return True
        except Unauthorized:
            return handle_error("Invalid credentials.", dialog, exc_info=False)
        except socket.timeout:
            return handle_error(timeout_msg, dialog)
        except (OSError, WindowsError) as e:
            # This error case will make more sense when local folder
            # configuration becomes available in the Settings dialog box.
            # See https://jira.nuxeo.com/browse/NXP-12657
            return handle_error("Unable to create local folder %s, please"
                                " check this is a valid location and current"
                                " user has the appropriate permission." %
                                sb_settings.local_folder, dialog)
        except Exception as e:
            if hasattr(e, 'msg'):
                msg = e.msg
            else:
                msg = "Unable to connect to " + url
            return handle_error(msg, dialog)

    def handle_error(msg, dialog, tab_index=0, exc_info=True):
        log.debug(msg, exc_info=exc_info)
        dialog.show_message(msg, tab_index=tab_index)
        return False

    if app is None:
        log.debug("Launching Qt prompt to manage settings.")
        QtGui.QApplication([])
    dialog = Dialog(sb_field_spec, proxy_field_spec, version,
                    title="Nuxeo Drive - Settings",
                    callback=validate)
    is_dialog_open = True
    try:
        dialog.exec_()
    except:
        dialog.reject()
        raise
    finally:
        is_dialog_open = False
    return dialog.accepted

if __name__ == '__main__':
    from nxdrive.controller import Controller
    from nxdrive.controller import default_nuxeo_drive_folder
    ctl = Controller('/tmp')
    sb_settings = ServerBindingSettings(
                                    server_url='http://localhost:8080/nuxeo',
                                    username='Administrator',
                                    local_folder=default_nuxeo_drive_folder())
    proxy_settings = ProxySettings()
    version = ctl.get_version()
    print prompt_settings(ctl, sb_settings, proxy_settings, version)
    ctl.dispose()
