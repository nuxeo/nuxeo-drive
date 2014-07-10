import os
import sys
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path
from nxdrive.utils import update_win32_reg_key

log = get_logger(__name__)

REG_KEY = 'Software\\Classes\\*\\shell\\Nuxeo drive\\command'


def register_contextual_menu():
    if sys.platform == 'win32':
        register_contextual_menu_win32()


def register_contextual_menu_win32():
    """Register ndrive as a windows explorer contextual menu"""
    import _winreg

    app_name = "None"
    args = " metadata --file \"%1\""
    exe_path = find_exe_path() + args
    if exe_path is None:
        log.warning('Not a frozen windows exe: '
                    'skipping startup application registration')
        return

    log.debug("Registering '%s' application %s to registry key %s",
              app_name, exe_path, REG_KEY)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CURRENT_USER)
    update_win32_reg_key(
        reg, REG_KEY,
        [(app_name, _winreg.REG_SZ, exe_path)],
    )
