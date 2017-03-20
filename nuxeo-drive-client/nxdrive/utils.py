import os
import sys
import re
import locale
import mimetypes
import psutil
import time
import base64
from Crypto.Cipher import AES
from Crypto import Random
from nxdrive.logging_config import get_logger


NUXEO_DRIVE_FOLDER_NAME = 'Nuxeo Drive'
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
    'application/x-msexcel': 'application/vnd.ms-excel',
    'application/x-mspowerpoint': 'application/vnd.ms-powerpoint',
    'application/x-mspowerpoint.12':
    'application/vnd.openxmlformats-officedocument.presentationml.presentation',
}

DEVICE_DESCRIPTIONS = {
    'linux2': 'GNU/Linux Desktop',
    'darwin': 'Mac OSX Desktop',
    'cygwin': 'Windows Desktop',
    'win32': 'Windows Desktop',
}

TOKEN_PERMISSION = 'ReadWrite'


def current_milli_time():
    return int(round(time.time() * 1000))


def is_hexastring(value):
    for c in value:
        if c not in "0123456789ABCDEF":
            return False
    return True


def is_office_temp_file(name):
    if name.startswith('~') and name.endswith(".tmp"):
        return True
    if len(name) == 8 and "." not in name:
        return is_hexastring(name)
        # for each car in "0123456789ABCDEF"
    elif name.endswith(".tmp") and name.startswith("ppt") and len(name) > 7:
        # Name is pptABCD.tmp, ppt123.tmp, etc.
        # Check if the part between ppt & .tmp is hexadecimal string
        return is_hexastring(name[3:-4])
    elif  10 <= len(name) <= 12 and name.endswith(".tmp"):
        # name like 813DEFA7.tmp, C199633.tmp
        # 6-8 hexadecimal characters in name part with extension .tmp
        return is_hexastring(name[0:-4])
    return False


def version_compare(x, y):
    """Compare version numbers using the usual x.y.z pattern.

    For instance, will result in:
        - 5.9.3 > 5.9.2
        - 5.9.3 > 5.8
        - 5.8 > 5.6.0
        - 5.10 > 5.1.2
        - 1.3.0524 > 1.3.0424
        - 1.4 > 1.3.0524
        - ...

    Also handles date-based releases, snapshots and hotfixes:
        - 5.9.4-I20140515_0120 > 5.9.4-I20140415_0120
        - 5.9.4-I20140415_0120 > 5.9.3
        - 5.9.4-I20140415_0120 < 5.9.4
        - 5.9.4-I20140415_0120 < 5.9.5
        - 5.9.4-SNAPSHOT > 5.9.3-SNAPSHOT
        - 5.9.4-SNAPSHOT > 5.9.3
        - 5.9.4-SNAPSHOT < 5.9.4
        - 5.9.4-SNAPSHOT < 5.9.5
        - 5.9.4-I20140415_0120 > 5.9.3-SNAPSHOT
        - 5.9.4-I20140415_0120 < 5.9.5-SNAPSHOT
        - 5.9.4-I20140415_0120 = 5.9.4-SNAPSHOT (can't decide,
                                                 consider as equal)
        - 5.8.0-HF15 > 5.8
        - 5.8.0-HF15 > 5.7.1-SNAPSHOT
        - 5.8.0-HF15 < 5.9.1
        - 5.8.0-HF15 > 5.8.0-HF14
        - 5.8.0-HF15 > 5.6.0-HF35
        - 5.8.0-HF15 < 5.10.0-HF01
        - 5.8.0-HF15-SNAPSHOT > 5.8
        - 5.8.0-HF15-SNAPSHOT > 5.8.0-HF14-SNAPSHOT
        - 5.8.0-HF15-SNAPSHOT > 5.8.0-HF14
        - 5.8.0-HF15-SNAPSHOT < 5.8.0-HF15
        - 5.8.0-HF15-SNAPSHOT < 5.8.0-HF16-SNAPSHOT
    """

    x_numbers = x.split('.')
    y_numbers = y.split('.')
    while (x_numbers and y_numbers):
        x_number = x_numbers.pop(0)
        y_number = y_numbers.pop(0)
        # Handle hotfixes
        if 'HF' in x_number:
            hf = re.sub(ur'-HF', '.', x_number).split('.', 1)
            x_number = hf[0]
            x_numbers.append(hf[1])
        if 'HF' in y_number:
            hf = re.sub(ur'-HF', '.', y_number).split('.', 1)
            y_number = hf[0]
            y_numbers.append(hf[1])
        # Handle date-based and snapshots
        x_date_based = 'I' in x_number
        y_date_based = 'I' in y_number
        x_snapshot = 'SNAPSHOT' in x_number
        y_snapshot = 'SNAPSHOT' in y_number
        if (not x_date_based and not x_snapshot and (y_date_based or y_snapshot)):
            # y is date-based or snapshot, x is not
            x_number = int(x_number)
            y_number = int(re.sub(ur'-(I.*|SNAPSHOT)', '', y_number))
            if y_number <= x_number:
                return 1
            else:
                return -1
        elif (not y_date_based and not y_snapshot
              and (x_date_based or x_snapshot)):
            # x is date-based or snapshot, y is not
            x_number = int(re.sub(ur'-(I.*|SNAPSHOT)', '', x_number))
            y_number = int(y_number)
            if x_number <= y_number:
                return -1
            else:
                return 1
        else:
            if x_date_based and y_date_based:
                # x and y are date-based
                x_number = int(re.sub(ur'(I|-|_)', '', x_number))
                y_number = int(re.sub(ur'(I|-|_)', '', y_number))
            elif x_snapshot and y_snapshot:
                # x and y are snapshots
                x_number = int(re.sub(ur'-SNAPSHOT', '', x_number))
                y_number = int(re.sub(ur'-SNAPSHOT', '', y_number))
            elif x_date_based and y_snapshot:
                # x is date-based, y is snapshot
                x_number = int(re.sub(ur'-I.*', '', x_number))
                y_number = int(re.sub(ur'-SNAPSHOT', '', y_number))
                if x_number == y_number:
                    return 0
            elif x_snapshot and y_date_based:
                # x is snapshot, y is date-based
                x_number = int(re.sub(ur'-SNAPSHOT', '', x_number))
                y_number = int(re.sub(ur'-I.*', '', y_number))
                if x_number == y_number:
                    return 0
            else:
                # x and y are not date-based
                x_number = int(x_number)
                y_number = int(y_number)
        if x_number != y_number:
            diff = x_number - y_number
            if diff > 0:
                return 1
            else:
                return -1
    if x_numbers:
        return 1
    if y_numbers:
        return -1
    return 0


def normalized_path(path):
    """ Return absolute, normalized file path. """
    if isinstance(path, bytes):
        # Decode path with local encoding when not already decoded explicitly
        # by the caller
        path = path.decode(ENCODING)

    return os.path.realpath(
        os.path.normpath(os.path.abspath(os.path.expanduser(path))))


def safe_long_path(path):
    """
    Utility to prefix path with the long path marker for Windows
    Source: http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    We also need to normalize the path as described here:
        https://bugs.python.org/issue18199#msg260122
    """
    if sys.platform == 'win32':
        if isinstance(path, bytes):
            # Decode path with local encoding when not already decoded
            # explicitly by the caller
            path = unicode(path.decode(ENCODING))

        if not path.startswith(u'\\\\?\\'):
            path = u'\\\\?\\' + normalized_path(path)

    return path


def path_join(parent, child):
    if parent == '/':
        return '/' + child
    return parent + '/' + child


def default_nuxeo_drive_folder():
    # TODO: Factorize with manager.get_default_nuxeo_drive_folder
    """Find a reasonable location for the root Nuxeo Drive folder

    This folder is user specific, typically under the home folder.

    Under Windows, try to locate My Documents as a home folder, using the
    win32com shell API if allowed, else falling back on a manual detection.

    Note that we need to decode the path returned by os.path.expanduser with
    the local encoding because the value of the HOME environment variable is
    read as a byte string. Using os.path.expanduser(u'~') fails if the home
    path contains non ASCII characters since Unicode coercion attempts to
    decode the byte string as an ASCII string.
    """
    if sys.platform == "win32":
        from win32com.shell import shell, shellcon
        try:
            my_documents = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL,
                                                 None, 0)
        except:
            # In some cases (not really sure how this happens) the current user
            # is not allowed to access its 'My Documents' folder path through
            # the win32com shell API, which raises the following error:
            # com_error: (-2147024891, 'Access is denied.', None, None)
            # We noticed that in this case the 'Location' tab is missing in the
            # Properties window of 'My Documents' accessed through the
            # Explorer.
            # So let's fall back on a manual (and poor) detection.
            # WARNING: it's important to check 'Documents' first as under
            # Windows 7 there also exists a 'My Documents' folder invisible in
            # the Explorer and cmd / powershell but visible from Python.
            # First try regular location for documents under Windows 7 and up
            log.debug("Access denied to win32com shell API: SHGetFolderPath,"
                      " falling back on manual detection of My Documents")
            my_documents = os.path.expanduser(r'~\Documents')
            my_documents = unicode(my_documents.decode(ENCODING))
            if not os.path.exists(my_documents):
                # Compatibility for Windows XP
                my_documents = os.path.expanduser(r'~\My Documents')
                my_documents = unicode(my_documents.decode(ENCODING))

        if os.path.exists(my_documents):
            nuxeo_drive_folder = os.path.join(my_documents,
                                              NUXEO_DRIVE_FOLDER_NAME)
            log.debug("Will use '%s' as default Nuxeo Drive folder location under Windows", nuxeo_drive_folder)
            return nuxeo_drive_folder

    # Fall back on home folder otherwise
    user_home = os.path.expanduser('~')
    user_home = unicode(user_home.decode(ENCODING))
    nuxeo_drive_folder = os.path.join(user_home, NUXEO_DRIVE_FOLDER_NAME)
    log.debug("Will use '%s' as default Nuxeo Drive folder location", nuxeo_drive_folder)
    return nuxeo_drive_folder


def find_resource_dir(directory, default_path):
    """Find the FS path of a directory in various OS binary packages"""
    import nxdrive
    nxdrive_path = os.path.dirname(nxdrive.__file__)

    app_resources = '/Contents/Resources/'
    cxfreeze_suffix = os.path.join('library.zip', 'nxdrive')

    dir_path = default_path
    if app_resources in nxdrive_path:
        # OSX frozen distribution, bundled as an app
        dir_path = re.sub(app_resources + ".*", app_resources + directory, nxdrive_path)

    elif nxdrive_path.endswith(cxfreeze_suffix):
        # cx_Freeze frozen distribution of nxdrive, data is out of the zip
        dir_path = nxdrive_path.replace(cxfreeze_suffix, directory)

    if not os.path.exists(dir_path):
        log.warning("Could not find the resource directory at: %s",
                    dir_path)
        return None

    return dir_path


def force_decode(string, codecs=('utf-8', 'cp1252')):
    if isinstance(string, unicode):
        string = string.encode('utf-8')
    for codec in codecs:
        try:
            return string.decode(codec)
        except UnicodeDecodeError:
            pass
    log.debug("Cannot decode string '%s' with any of the given codecs: %r",
              string, codecs)


def encrypt(plaintext, secret, lazy=True):
    """Symetric encryption using AES"""
    secret = _lazysecret(secret) if lazy else secret
    iv = Random.new().read(AES.block_size)
    encobj = AES.new(secret, AES.MODE_CFB, iv)
    return base64.b64encode(iv + encobj.encrypt(plaintext))


def decrypt(ciphertext, secret, lazy=True):
    """Symetric decryption using AES"""
    secret = _lazysecret(secret) if lazy else secret
    ciphertext = base64.b64decode(ciphertext)
    iv = ciphertext[:AES.block_size]
    ciphertext = ciphertext[AES.block_size:]
    # Dont fail on decrypt
    try:
        encobj = AES.new(secret, AES.MODE_CFB, iv)
        return encobj.decrypt(ciphertext)
    except:
        return None


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
        log.trace("Could not guess mime type for '%s', returing 'application/octet-stream'", filename)
        return "application/octet-stream"


def guess_digest_algorithm(digest):
    # For now only md5 and sha1 are supported
    if digest is None or len(digest) == 32:
        return 'md5'
    elif len(digest) == 40:
        return 'sha1'
    else:
        raise Exception('Unknown digest algorithm for %s' % digest)


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


class ServerLoader(object):
    def __init__(self, remote_client, local_client):
        self._remote_client = remote_client
        self._local_client = local_client

    def sync(self, remote_uid, local):
        childs = self._local_client.get_children_info(local)
        rchilds = self._remote_client.get_children_info(remote_uid)
        existing_childs = dict()
        for child in rchilds:
            path = os.path.join(local, child.name)
            existing_childs[path] = child
        for child in childs:
            child_uid = None
            if child.path not in existing_childs:
                if child.folderish:
                    print "Making folder: %s" % child.path
                    child_uid = self._remote_client.make_folder(remote_uid, child.name)
                else:
                    print "Making file: %s" % child.path
                    self._remote_client.stream_file(remote_uid, self._local_client._abspath(child.path))
            else:
                child_uid = existing_childs[child.path].uid
            if child.folderish:
                self.sync(child_uid, child.path)


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
            pid = None
            with open(safe_long_path(pid_filepath), 'rb') as f:
                pid = os.getpid()
                try:
                    pid = int(f.read().strip())
                    p = psutil.Process(pid)
                    # If process has been created after the lock file
                    # Changed from getctime() to getmtime() because of Windows' 'file system tunneling'
                    if p.create_time() > os.path.getmtime(pid_filepath):
                        raise ValueError
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
                    return pid
                log.warning(msg)
        self.locked = True
        return None

    def lock(self):
        pid = self.check_running(process_name=self.key)
        if pid is not None:
            log.warning("%s process with pid %d already running.", self.key, pid)
            return pid

        # Write the pid of this process
        pid_filepath = self._get_sync_pid_filepath(process_name=self.key)
        pid = os.getpid()
        with open(safe_long_path(pid_filepath), 'wb') as f:
            f.write(str(pid))
        return None
