import os

def normalized_path(path):
    """Return absolute, normalized file path"""
    # XXX: we could os.path.normcase as well under Windows but it might be the
    # source of unexpected troubles so no doing it for now.

    # We do not expand the user folder marker `~` as we expect the OS shell to
    # do it automatically when using the commandline or we do it explicitly
    # where appropriate
    return os.path.normpath(os.path.abspath(path))

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

def update_win32_reg_key(reg, path, attributes=()):
    """Helper function to create / set a key with attribute values"""
    import _winreg
    key = _winreg.CreateKey(reg, path)
    _winreg.CloseKey(key)
    key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE)
    for attribute, type_, value in attributes:
        _winreg.SetValueEx(key, attribute, 0, type_, value)
    _winreg.CloseKey(key)