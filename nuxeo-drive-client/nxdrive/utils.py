import os
import sys


WIN32_SUFFIX = os.path.join('library.zip', 'nxdrive')
OSX_SUFFIX = "Contents/Resources/lib/python2.7/site-packages.zip/nxdrive"


def normalized_path(path):
    """Return absolute, normalized file path."""
    if isinstance(path, bytes):
        # Assume that the path (e.g. a command line argument) is encoded in
        # utf-8 when not already decoded explicitly by the caller
        path = path.decode('utf-8')

    # XXX: we could os.path.normcase as well under Windows but it might be the
    # source of unexpected troubles so no doing it for now.
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def safe_long_path(path):
    """Utility to prefix path with the long path marker for Windows

    http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    """
    if sys.platform == 'win32':
        path = u"\\\\?\\" + path
    return path


def find_exe_path():
    """Introspect the Python runtime to find the frozen Windows exe"""
    import nxdrive
    nxdrive_path = os.path.realpath(os.path.dirname(nxdrive.__file__))

    # Detect frozen win32 executable under Windows
    if nxdrive_path.endswith(WIN32_SUFFIX):
        exe_path = nxdrive_path.replace(WIN32_SUFFIX, 'ndrivew.exe')
        if os.path.exists(exe_path):
            return exe_path

    # Detect OSX frozen app
    if nxdrive_path.endswith(OSX_SUFFIX):
        exe_path = nxdrive_path.replace(OSX_SUFFIX, "Contents/MacOS/Nuxeo Drive")
        if os.path.exists(exe_path):
            return exe_path

    # Fall-back to the regular method that should work both the ndrive script
    return sys.argv[0]


def update_win32_reg_key(reg, path, attributes=()):
    """Helper function to create / set a key with attribute values"""
    import _winreg
    key = _winreg.CreateKey(reg, path)
    _winreg.CloseKey(key)
    key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE)
    for attribute, type_, value in attributes:
        _winreg.SetValueEx(key, attribute, 0, type_, value)
    _winreg.CloseKey(key)
