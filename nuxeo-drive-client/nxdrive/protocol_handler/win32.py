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
        log.warn('Not a frozen windows exe: '
                 'skipping protocol handler registration')
        return

    log.debug("Registering 'nxdrive' protocol handler to: %s", exe_path)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)

    # Create the nxdrive protocol key
    nxdrive_class_path = 'Software\\Classes\\nxdrive'
    nxdrive_class_attributes = (
        ('EditFlags', _winreg.REG_DWORD, 2),
        ('', _winreg.REG_SZ, 'URL:nxdrive Protocol'),
        ('URL Protocol', _winreg.REG_SZ, ''),
    )
    update_key(reg, nxdrive_class_path, nxdrive_class_attributes)

    # Create the nxdrive command key
    command = '"' + exe_path + '" "%1"'
    command_path = nxdrive_class_path + '\\shell\\open\\command'
    command_attributes = (
        ('', _winreg.REG_SZ, command)
    )
    update_key(reg, command_path, command_attributes)
