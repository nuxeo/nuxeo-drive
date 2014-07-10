import os
import sys
from nxdrive.logging_config import get_logger
from nxdrive.utils import find_exe_path
from nxdrive.utils import update_win32_reg_key

log = get_logger(__name__)


def register_contextual_menu():
    if sys.platform == 'win32':
        register_contextual_menu_win32()


def register_contextual_menu_win32():
    """Register ndrive as a windows explorer contextual menu"""
    import _winreg

    reg_key = '*\\shell\\nuxeo drive\\command'
    app_name = 'Nuxeo Drive'
    exe_path = find_exe_path()
    if exe_path is None:
        log.warning('Not a frozen windows exe: '
                    'skipping startup application registration')
        return

    exe_path += " metadata --file %1"

    log.debug("Registering '%s' application %s to registry key %s",
              app_name, exe_path, reg_key)
    reg = _winreg.ConnectRegistry(None, _winreg.HKEY_CLASSES_ROOT)
    update_win32_reg_key(
        reg, reg_key,
        [(app_name, _winreg.REG_SZ, exe_path)],
    )
