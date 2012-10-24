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
    return None


def register_protocol_handlers(controller):
    """Register ndrive as a protocol handler in the Registry"""
    import _winreg

    exe_path = find_exe_path()
    if exe_path is None:
        log.warn('Not a frozen windows exe: '
                 'skipping protocol handler registration')
        return

    command = '"' + exe_path + '" "%1"'
    log.debug("Registering 'nxdrive' protocol handler command: %s", command)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    try:
        # Create the nxdrive key if missing:
        nxdrive = _winreg.CreateKey(reg, 'nxdrive')
        _winreg.CloseKey(nxdrive)
    except _winreg.EnvironmentError:
        # Already existing key
        pass

    nxdrive = _winreg.OpenKey(reg, 'nxdrive', 0, _winreg.KEY_WRITE)
    _winreg.SetValueEx(nxdrive,'EditFlags', 0, _winreg.REG_DWORD, 2)
    _winreg.SetValueEx(nxdrive,'', 0, _winreg.REG_SZ, 'URL:nxdrive Protocol')
    _winreg.SetValueEx(nxdrive,'URL Protocol', 0, _winreg.REG_SZ, '')
    _winreg.CloseKey(nxdrive)

    comm = _winreg.CreateKey(reg, 'nxdrive\\shell\\open\\command')
    _winreg.CloseKey(comm)

    comm = _winreg.OpenKey(reg, 'nxdrive\\shell\\open\\command', 0, _winreg.KEY_WRITE)
    _winreg.SetValueEx(comm,'', 0, _winreg.REG_SZ, command)
    _winreg.CloseKey(comm)
