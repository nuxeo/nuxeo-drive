import os
import sys
import re
import locale
import mimetypes
import psutil
from Crypto.Cipher import AES
from Crypto import Random
from nxdrive.logging_config import get_logger


log = get_logger(__name__)


WIN32_SUFFIX = os.path.join('library.zip', 'nxdrive')
OSX_SUFFIX = "Contents/Resources/lib/python2.7/site-packages.zip/nxdrive"

ENCODING = locale.getpreferredencoding()
DEFAULT_ENCODING = 'utf-8'

WIN32_PATCHED_MIME_TYPES = {
    'image/pjpeg': 'image/jpeg',
    'image/x-png': 'image/png',
    'image/bmp': 'image/x-ms-bmp',
    'audio/x-mpg': 'audio/mpeg',
    'video/x-mpeg2a': 'video/mpeg',
    'application/x-javascript': 'application/javascript',
    'application/x-mspowerpoint.12':
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}


def normalized_path(path):
    """Return absolute, normalized file path."""
    if isinstance(path, bytes):
        # Decode path with local encoding when not already decoded explicitly
        # by the caller
        path = path.decode(ENCODING)

    # XXX: we could os.path.normcase as well under Windows but it might be the
    # source of unexpected troubles so not doing it for now.
    return os.path.normpath(os.path.abspath(os.path.expanduser(path)))


def safe_long_path(path):
    """Utility to prefix path with the long path marker for Windows

    http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    """
    if sys.platform == 'win32':
        if isinstance(path, bytes):
            # Decode path with local encoding when not already decoded
            # explicitly  by the caller
            path = unicode(path.decode(ENCODING))
        path = u"\\\\?\\" + path
    return path


def find_resource_dir(directory, default_path):
    """Find the FS path of a directory in various OS binary packages"""
    import nxdrive
    nxdrive_path = os.path.dirname(nxdrive.__file__)

    app_resources = '/Contents/Resources/'
    cxfreeze_suffix = os.path.join('library.zip', 'nxdrive')

    dir_path = default_path
    if app_resources in nxdrive_path:
        # OSX frozen distribution, bundled as an app
        dir_path = re.sub(app_resources + ".*", app_resources + directory,
                             nxdrive_path)

    elif nxdrive_path.endswith(cxfreeze_suffix):
        # cx_Freeze frozen distribution of nxdrive, data is out of the zip
        dir_path = nxdrive_path.replace(cxfreeze_suffix, directory)

    if not os.path.exists(dir_path):
        log.warning("Could not find the resource directory at: %s",
                    dir_path)
        return None

    return dir_path


def find_exe_path():
    """Introspect the Python runtime to find the frozen Windows exe"""
    import nxdrive
    nxdrive_path = os.path.realpath(os.path.dirname(nxdrive.__file__))
    log.trace("nxdrive_path: %s", nxdrive_path)

    # Detect frozen win32 executable under Windows
    if nxdrive_path.endswith(WIN32_SUFFIX):
        log.trace("Detected frozen win32 executable under Windows")
        exe_path = nxdrive_path.replace(WIN32_SUFFIX, 'ndrivew.exe')
        if os.path.exists(exe_path):
            log.trace("Returning exe path: %s", exe_path)
            return exe_path

    # Detect OSX frozen app
    if nxdrive_path.endswith(OSX_SUFFIX):
        log.trace("Detected OS X frozen app")
        exe_path = nxdrive_path.replace(OSX_SUFFIX,
                                        "Contents/MacOS/ndrive")
        if os.path.exists(exe_path):
            log.trace("Returning exe path: %s", exe_path)
            return exe_path

    # Fall-back to the regular method that should work both the ndrive script
    exe_path = sys.argv[0]
    log.trace("Returning default exe path: %s", exe_path)
    return exe_path


def update_win32_reg_key(reg, path, attributes=()):
    """Helper function to create / set a key with attribute values"""
    import _winreg
    key = _winreg.CreateKey(reg, path)
    _winreg.CloseKey(key)
    key = _winreg.OpenKey(reg, path, 0, _winreg.KEY_WRITE)
    for attribute, type_, value in attributes:
        # Handle None case for app name in
        # contextual_menu.register_contextual_menu_win32
        if attribute == "None":
            attribute = None
        _winreg.SetValueEx(key, attribute, 0, type_, value)
    _winreg.CloseKey(key)


def force_decode(string, codecs=['utf8', 'cp1252']):
    for codec in codecs:
        try:
            return string.decode(codec)
        except:
            pass
    log.debug("Cannot decode string '%s' with any of the given codecs: %r",
              string, codecs)
    return ''


def encrypt(plaintext, secret, lazy=True):
    """Symetric encryption using AES"""
    secret = _lazysecret(secret) if lazy else secret
    iv = Random.new().read(AES.block_size)
    encobj = AES.new(secret, AES.MODE_CFB, iv)
    return iv + encobj.encrypt(plaintext)


def decrypt(ciphertext, secret, lazy=True):
    """Symetric decryption using AES"""
    secret = _lazysecret(secret) if lazy else secret
    iv = ciphertext[:AES.block_size]
    ciphertext = ciphertext[AES.block_size:]
    encobj = AES.new(secret, AES.MODE_CFB, iv)
    return encobj.decrypt(ciphertext)


def _lazysecret(secret, blocksize=32, padding='}'):
    """Pad secret if not legal AES block size (16, 24, 32)"""
    if len(secret) > blocksize:
        return secret[:-(len(secret) - blocksize)]
    if not len(secret) in (16, 24, 32):
        return secret + (blocksize - len(secret)) * padding
    return secret


def guess_mime_type(filename):
    mime_type, _ = mimetypes.guess_type(filename)
    if mime_type:
        if sys.platform == 'win32':
            # Patch bad Windows MIME types
            # See https://jira.nuxeo.com/browse/NXP-11660
            # and http://bugs.python.org/issue15207
            mime_type = _patch_win32_mime_type(mime_type)
        log.trace("Guessed mime type '%s' for '%s'", mime_type, filename)
        return mime_type
    else:
        log.trace("Could not guess mime type for '%s', returing"
            " 'application/octet-stream'", filename)
        return "application/octet-stream"


def _patch_win32_mime_type(mime_type):
    patched_mime_type = WIN32_PATCHED_MIME_TYPES.get(mime_type)
    return patched_mime_type if patched_mime_type else mime_type


def deprecated(func):
    """"This is a decorator which can be used to mark functions
    as deprecated. It will result in a warning being emitted
    when the function is used."""
    def new_func(*args, **kwargs):
        log.warning("Call to deprecated function {}.".format(func.__name__))
        return func(*args, **kwargs)
    new_func.__name__ = func.__name__
    new_func.__doc__ = func.__doc__
    new_func.__dict__.update(func.__dict__)
    return new_func


class PidLockFile(object):
    """ This class handle the pid lock file"""
    def __init__(self, folder, key):
        self.folder = folder
        self.key = key
        self.locked = False

    def _get_sync_pid_filepath(self, process_name=None):
        if process_name is None:
            process_name = self.key
        return os.path.join(self.folder,
                            'nxdrive_%s.pid' % process_name)

    def unlock(self):
        if not self.locked:
            return
        # Clean pid file
        pid_filepath = self._get_sync_pid_filepath()
        try:
            os.unlink(pid_filepath)
        except Exception, e:
            log.warning("Failed to remove stalled pid file: %s"
                        " for stopped process %d: %r", pid_filepath,
                        os.getpid(), e)

    def check_running(self, process_name=None):
        """Check whether another sync process is already runnning

        If nxdrive.pid file already exists and the pid points to a running
        nxdrive program then return the pid. Return None otherwise.

        """
        if process_name is None:
            process_name = self.key
        pid_filepath = self._get_sync_pid_filepath(process_name=process_name)
        if os.path.exists(pid_filepath):
            with open(safe_long_path(pid_filepath), 'rb') as f:
                pid = os.getpid()
                try:
                    pid = int(f.read().strip())
                    _ = psutil.Process(pid)
                    # TODO https://jira.nuxeo.com/browse/NXDRIVE-26: Check if
                    # we can skip the process name verif as it can be
                    # overridden
                    return pid
                except (ValueError, psutil.NoSuchProcess):
                    pass
                # This is a pid file that is empty or pointing to either a
                # stopped process or a non-nxdrive process: let's delete it if
                # possible
                try:
                    os.unlink(pid_filepath)
                    if pid is None:
                        msg = "Removed old empty pid file: %s" % pid_filepath
                    else:
                        msg = ("Removed old pid file: %s for stopped process"
                               " %d" % (pid_filepath, pid))
                    log.info(msg)
                except Exception, e:
                    if pid is None:
                        msg = ("Failed to remove empty stalled pid file: %s:"
                               " %r" % (pid_filepath, e))
                    else:
                        msg = ("Failed to remove stalled pid file: %s for"
                               " stopped process %d: %r"
                               % (pid_filepath, pid, e))
                    log.warning(msg)
        self.locked = True
        return None

    def lock(self):
        pid = self.check_running(process_name=self.key)
        if pid is not None:
            log.warning(
                    "%s process with pid %d already running.",
                    self.key, pid)
            return pid

        # Write the pid of this process
        pid_filepath = self._get_sync_pid_filepath(process_name=self.key)
        pid = os.getpid()
        with open(safe_long_path(pid_filepath), 'wb') as f:
            f.write(str(pid))
        return None


class ControllerCipher(object):
    def __init__(self, controller):
        self.controller = controller

    def encrypt(self, password):
        if password:
            return encrypt(password, self.get_secret())
        return ''

    def decrypt(self, password_in):
        password = ''
        if password_in:
            password = decrypt(password_in,
                               self.get_secret(raise_exception_if_fail=False))
        return password

    def get_secret(self, raise_exception_if_fail=True):
        # this version can not raise an exception, but future versions may
        # Encrypt password with device_id, and a constant
        dc = self.controller.get_device_config()
        secret = dc.device_id + '234380'
        return secret
