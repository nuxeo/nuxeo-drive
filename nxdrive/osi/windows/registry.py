# coding: utf-8
import winreg
from logging import getLogger
from typing import Dict, Optional, Union

__all__ = ("read", "delete")

log = getLogger(__name__)

HKCU = winreg.HKEY_CURRENT_USER


def create(key: str) -> bool:
    """
    Create the specified key in the Current User registry.

    Return `True` if the creation was successful, `False` otherwise.
    """
    try:
        with winreg.CreateKey(HKCU, key):
            log.debug(f"Created {key} registry key")
    except OSError:
        log.exception(f"Couldn't create {key} registry key")
        return False
    return True


def delete(key: str) -> bool:
    """
    Delete the specified key from the Current User registry.

    Return `True` if the deletion was successful, `False` otherwise.
    """
    try:
        with winreg.OpenKey(HKCU, key, 0, winreg.KEY_ALL_ACCESS) as handle:
            while "key has subkeys":
                try:
                    subkey = winreg.EnumKey(handle, 0)
                except OSError:
                    break
                else:
                    delete(f"{key}\\{subkey}")
            winreg.DeleteKey(HKCU, key)
            log.debug(f"Deleted {key} registry key")
    except OSError:
        log.exception(f"Couldn't delete {key} registry key")
        return False
    return True


def delete_value(key: str, value: str) -> bool:
    """
    Delete the specified value from the specified key in the Current User registry.

    Return `True` if the deletion was successful, `False` otherwise.
    """
    try:
        with winreg.OpenKey(HKCU, key, 0, winreg.KEY_SET_VALUE) as handle:
            winreg.DeleteValue(handle, value)
            log.debug(f"Deleted {value} value from {key} registry key")
    except OSError:
        log.exception(f"Couldn't delete {value} value from {key} registry key")
        return False
    return True


def read(key: str) -> Optional[Dict[str, str]]:
    """
    Read the values in the specified key in the Current User registry.

    Return `None` if the read failed.
    """
    values = {}
    try:
        with winreg.OpenKey(HKCU, key, 0, winreg.KEY_READ) as handle:
            for i in range(winreg.QueryInfoKey(handle)[1]):
                value = winreg.EnumValue(handle, i)
                values[value[0]] = value[1]
    except OSError:
        log.exception(f"Couldn't read {key} registry key values")
        return None
    return values


def write(key: str, content: Union[str, Dict[Optional[str], str]]) -> bool:
    """
    Write the specified key in the Current User registry.

    If `content` is a string, it will be set as the default value
    of the registry key.
    If `content` is a dictionary, each key/value in `content`
    will be a value name/value data in the key.
    If the dictionary key is `None`, the data will be set as
    the default value of the registry key.

    Return `True` if the write was successful, `False` otherwise.
    """
    if isinstance(content, str):
        content = {None: content}
    try:
        with winreg.CreateKeyEx(HKCU, key) as handle:
            for name, data in content.items():
                winreg.SetValueEx(handle, name, 0, winreg.REG_SZ, data)
            log.debug(f"Wrote in {key} registry key: {content}")
    except OSError:
        log.exception(f"Couldn't write {key} registry key")
        return False
    return True
