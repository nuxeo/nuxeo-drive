import os
from nxdrive.logging_config import get_logger
log = get_logger(__name__)


def find_exe_path():
    """Introspect the Python runtime to find the frozen Windows exe"""
    import nxdrive
    nxdrive_path = os.path.dirname(nxdrive.__file__)
    frozen_suffix = os.path.join('library.zip', 'nxdrive')
    if nxdrive_path.endswith(frozen_suffix):
        exe_path = nxdrive_path.replace(frozen_suffix, 'ndrivew.exe')
        if os.path.exists(exe_path):
            return exe_path
    # TODO: handle the python.exe + python script as sys.argv[0] case as well
    return None


def update_key(reg, path, attributes=()):
    """Helper function to create / set a key with attribute values"""
    import _winreg
    key = _winreg.CreateKey(reg, path)
    _winreg.CloseKey(key)
    key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE)
    for attribute, type_, value in attributes:
        _winreg.SetValueEx(key, attribute, 0, type_, value)
    _winreg.CloseKey(key)


def register_protocol_handlers(controller):
    """Register ndrive as a protocol handler in the Registry"""
    import _winreg

    exe_path = find_exe_path()
    if exe_path is None:
        log.warning('Not a frozen windows exe: '
                 'skipping protocol handler registration')
        return

    log.debug("Registering 'nxdrive' protocol handler to: %s", exe_path)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)

    # Register Nuxeo Drive as a software as a protocol command provider
    command = '"' + exe_path + '" "%1"'
    update_key(
        reg, 'Software\\Nuxeo Drive',
        [('', _winreg.REG_SZ, 'Nuxeo Drive')],
    )
    # TODO: add an icon for Nuxeo Drive too
    update_key(
        reg, 'Software\\Nuxeo Drive\\Protocols\\nxdrive',
        [('URL Protocol', _winreg.REG_SZ, '')],
    )
    # TODO: add an icon for the nxdrive protocol too
    update_key(
        reg,
        'Software\\Nuxeo Drive\\Protocols\\nxdrive\\shell\\open\\command',
        [('', _winreg.REG_SZ, command)],
    )
    # Create the nxdrive protocol key
    nxdrive_class_path = 'Software\\Classes\\nxdrive'
    update_key(
        reg, nxdrive_class_path,
        [
            ('EditFlags', _winreg.REG_DWORD, 2),
            ('', _winreg.REG_SZ, 'URL:nxdrive Protocol'),
            ('URL Protocol', _winreg.REG_SZ, ''),
        ],
    )
    # Create the nxdrive command key
    command_path = nxdrive_class_path + '\\shell\\open\\command'
    update_key(
        reg, command_path,
        [('', _winreg.REG_SZ, command)],
    )
