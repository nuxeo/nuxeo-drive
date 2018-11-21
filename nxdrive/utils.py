# coding: utf-8
"""
We are using lazy imports (understand imports in functions) specifically here
to speed-up command line calls without loading everything at startup.
"""
import os
import re
import stat
from logging import getLogger
from sys import platform
from typing import Any, Callable, Dict, Optional, Pattern, Tuple, TYPE_CHECKING, Union
from urllib.parse import urlsplit, urlunsplit

from .constants import APP_NAME, WINDOWS
from .options import Options

if TYPE_CHECKING:
    from .proxy import Proxy  # noqa

__all__ = (
    "PidLockFile",
    "current_milli_time",
    "copy_to_clipboard",
    "decrypt",
    "encrypt",
    "find_icon",
    "find_resource",
    "force_decode",
    "force_encode",
    "get_device",
    "guess_server_url",
    "if_frozen",
    "is_generated_tmp_file",
    "lock_path",
    "normalize_event_filename",
    "normalized_path",
    "parse_edit_protocol",
    "parse_protocol_url",
    "path_join",
    "safe_filename",
    "safe_long_path",
    "set_path_readonly",
    "short_name",
    "simplify_url",
    "unlock_path",
    "unset_path_readonly",
    "version_le",
)

DEVICE_DESCRIPTIONS = {"darwin": "macOS", "linux": "GNU/Linux", "win32": "Windows"}
WIN32_PATCHED_MIME_TYPES = {
    "image/pjpeg": "image/jpeg",
    "image/x-png": "image/png",
    "image/bmp": "image/x-ms-bmp",
    "audio/x-mpg": "audio/mpeg",
    "video/x-mpeg2a": "video/mpeg",
    "application/x-javascript": "application/javascript",
    "application/x-msexcel": "application/vnd.ms-excel",
    "application/x-mspowerpoint": "application/vnd.ms-powerpoint",
    "application/x-mspowerpoint.12": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

log = getLogger(__name__)


def cmp(a: Any, b: Any) -> int:
    """
    cmp() does not exist anymore in Python 3.
    `a` and `b` can be None, str or StrictVersion.
    """
    if a is None:
        if b is None:
            return 0
        return -1
    if b is None:
        return 1
    return (a > b) - (a < b)


def copy_to_clipboard(text: str) -> None:
    """ Copy the given text to the clipboard. """

    if WINDOWS:
        import win32clipboard

        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
    else:
        from PyQt5.QtWidgets import QApplication

        cb = QApplication.clipboard()
        cb.clear(mode=cb.Clipboard)
        cb.setText(text, mode=cb.Clipboard)


def current_milli_time() -> int:
    from time import time

    return int(round(time() * 1000))


def get_device() -> str:
    """ Retrieve the device type. """

    device = DEVICE_DESCRIPTIONS.get(platform)
    if not device:
        device = platform.replace(" ", "")
    return device


def get_default_nuxeo_drive_folder() -> str:
    """
    Find a reasonable location for the root Nuxeo Drive folder

    This folder is user specific, typically under the home folder.

    Under Windows, try to locate My Documents as a home folder, using the
    win32com shell API if allowed, else falling back on a manual detection.
    """

    folder = Options.home
    if WINDOWS:
        from win32com.shell import shell, shellcon

        try:
            folder = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
        except:
            """
            In some cases (not really sure how this happens) the current user
            is not allowed to access its 'My Documents' folder path through
            the win32com shell API, which raises the following error:
            com_error: (-2147024891, 'Access is denied.', None, None)
            We noticed that in this case the 'Location' tab is missing in the
            Properties window of 'My Documents' accessed through the
            Explorer.
            So let's fall back on a manual (and poor) detection.
            WARNING: it's important to check 'Documents' first as under
            Windows 7 there also exists a 'My Documents' folder invisible in
            the Explorer and cmd / powershell but visible from Python.
            First try regular location for documents under Windows 7 and up
            """
            log.error(
                "Access denied to the API SHGetFolderPath,"
                " falling back on manual detection"
            )
            folder = os.path.join(Options.home, "Documents")

    folder = increment_local_folder(folder, APP_NAME)
    return force_decode(folder)


def increment_local_folder(basefolder: str, name: str) -> str:
    """Increment the number for a possible local folder.
    Example: "Nuxeo Drive" > "Nuxeo Drive 2" > "Nuxeo Drive 3"
    """
    folder = os.path.join(basefolder, name)
    for num in range(2, 42):
        if not os.path.isdir(folder):
            break
        folder = os.path.join(basefolder, f"{name} {num}")
    else:
        folder = ""
    return folder


def is_hexastring(value: str) -> bool:
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def is_generated_tmp_file(name: str) -> Tuple[bool, Optional[bool]]:
    """
    Try to guess temporary files generated by tierce softwares.
    Returns a tuple to know what kind of tmp file it is to
    filter later on Processor._synchronize_locally_created().

    :return tuple: (bool: is tmp file, bool: need to recheck later)
    """

    ignore, do_not_ignore = True, False
    delay, do_not_delay, no_delay_effect = True, False, None

    name = force_decode(name)

    # Default ignored suffixes already handle .bak, .tmp, etc..
    if name.endswith(Options.ignored_suffixes):
        return ignore, do_not_delay

    # MS Office temporary file
    if len(name) == 8 and is_hexastring(name):
        # Permit to recheck later, else we have to ban all file names
        # that are only hexadecimal characters.
        return ignore, delay

    # Emacs auto save file
    # http://www.emacswiki.org/emacs/AutoSave
    if name.startswith("#") and name.endswith("#"):
        return ignore, do_not_delay

    # See https://stackoverflow.com/a/10591106/1117028 for benchmark
    reg = re.compile(r"|".join("(?:%s)" % p for p in Options.ignored_files))
    if reg.match(name.lower()):
        return ignore, do_not_delay

    return do_not_ignore, no_delay_effect


def version_compare(x: str, y: str) -> int:
    """
    Compare version numbers using the usual x.y.z pattern.

    For instance, will result in:
        - 5.9.3 > 5.9.2
        - 5.9.3 > 5.8
        - 5.8 > 5.6.0
        - 5.10 > 5.1.2
        - 1.3.0524 > 1.3.0424
        - 1.4 > 1.3.0524
        - ...

    Also handles snapshots and hotfixes:
        - 5.9.4-SNAPSHOT > 5.9.3-SNAPSHOT
        - 5.9.4-SNAPSHOT > 5.9.3
        - 5.9.4-SNAPSHOT < 5.9.4
        - 5.9.4-SNAPSHOT < 5.9.5
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

    # Handle None values
    if not all((x, y)):
        return cmp(x, y)

    ret = (-1, 1)

    x_numbers = x.split(".")
    y_numbers = y.split(".")
    while x_numbers and y_numbers:
        x_part = x_numbers.pop(0)
        y_part = y_numbers.pop(0)

        # Handle hotfixes
        if "HF" in x_part:
            hf = x_part.replace("-HF", ".").split(".", 1)
            x_part = hf[0]
            x_numbers.append(hf[1])
        if "HF" in y_part:
            hf = y_part.replace("-HF", ".").split(".", 1)
            y_part = hf[0]
            y_numbers.append(hf[1])

        # Handle snapshots
        x_snapshot = "SNAPSHOT" in x_part
        y_snapshot = "SNAPSHOT" in y_part
        if not x_snapshot and y_snapshot:
            # y is snapshot, x is not
            x_number = int(x_part)
            y_number = int(y_part.replace("-SNAPSHOT", ""))
            return ret[y_number <= x_number]
        elif not y_snapshot and x_snapshot:
            # x is snapshot, y is not
            x_number = int(x_part.replace("-SNAPSHOT", ""))
            y_number = int(y_part)
            return ret[x_number > y_number]

        x_number = int(x_part.replace("-SNAPSHOT", ""))
        y_number = int(y_part.replace("-SNAPSHOT", ""))
        if x_number != y_number:
            return ret[x_number - y_number > 0]

    if x_numbers:
        return 1
    if y_numbers:
        return -1

    return 0


def version_compare_client(x: str, y: str) -> int:
    """ Try to compare SemVer and fallback to version_compare on error. """

    from distutils.version import StrictVersion

    # Ignore date based versions, they will be treated as normal versions
    if x and "-I" in x:
        x = x.split("-")[0]
    if y and "-I" in y:
        y = y.split("-")[0]

    try:
        return cmp(StrictVersion(x), StrictVersion(y))
    except (AttributeError, ValueError):
        return version_compare(x, y)


def version_le(x: str, y: str) -> bool:
    """ x <= y """
    return version_compare_client(x, y) <= 0


def version_lt(x: str, y: str) -> bool:
    """ x < y """
    return version_compare_client(x, y) < 0


def normalized_path(path: str) -> str:
    """ Return absolute, normalized file path. """
    return os.path.realpath(os.path.normpath(os.path.abspath(force_decode(path))))


def normalize_event_filename(filename: str, action: bool = True) -> str:
    """
    Normalize a file name.

    :param unicode filename: The file name to normalize.
    :param bool action: Apply changes on the file system.
    :return unicode: The normalized file name.
    """

    import unicodedata

    # NXDRIVE-688: Ensure the name is stripped for a file
    stripped = filename.strip()
    if WINDOWS:
        # Windows does not allow files/folders ending with space(s)
        filename = stripped
    elif (
        action
        and filename != stripped
        and os.path.exists(filename)
        and not os.path.isdir(filename)
    ):
        # We can have folders ending with spaces
        log.debug(f"Forcing space normalization: {filename!r} -> {stripped!r}")
        os.rename(filename, stripped)
        filename = stripped

    # NXDRIVE-188: Normalize name on the file system, if needed
    normalized = unicodedata.normalize("NFC", str(filename))
    normalized = os.path.join(
        os.path.dirname(normalized), safe_os_filename(os.path.basename(normalized))
    )

    if WINDOWS and os.path.exists(filename):
        """
        If `filename` exists, and as Windows is case insensitive,
        the result of Get(Full|Long|Short)PathName() could be unexpected
        because it will return the path of the existant `filename`.

        Check this simplified code session (the file "ABC.txt" exists):

            >>> win32api.GetLongPathName('abc.txt')
            'ABC.txt'
            >>> win32api.GetLongPathName('ABC.TXT')
            'ABC.txt'
            >>> win32api.GetLongPathName('ABC.txt')
            'ABC.txt'

        So, to counter that behavior, we save the actual file name
        and restore it in the full path.
        """
        import win32api

        long_path = win32api.GetLongPathNameW(filename)
        filename = os.path.join(os.path.dirname(long_path), os.path.basename(filename))

    if action and filename != normalized and os.path.exists(filename):
        log.debug(f"Forcing normalization: {filename!r} -> {normalized!r}")
        os.rename(filename, normalized)

    return normalized


def if_frozen(func) -> Callable:
    """Decorator to enable the call of a function/method
    only if the application is frozen."""

    def wrapper(*args: Any, **kwargs: Any) -> Union[bool, Callable]:
        """Inner function to do the check and abort the call
        if the application not frozen."""
        if not Options.is_frozen:
            return False
        return func(*args, **kwargs)

    return wrapper


def safe_filename(
    name: str, replacement: str = "-", pattern: Pattern = re.compile(r'(["|*/:<>?\\])')
) -> str:
    """ Replace invalid characters in target filename. """
    return re.sub(pattern, replacement, name)


def safe_os_filename(name: str) -> str:
    """
    Replace characters that are forbidden in file or folder names by the OS.

    On Windows, they are  " | * / : < > ? \\
    On Unix, they are  / :
    """
    if WINDOWS:
        return safe_filename(name)
    else:
        return safe_filename(name, pattern=re.compile(r"([/:])"))


def safe_long_path(path: str) -> str:
    """
    Utility to prefix path with the long path marker for Windows
    Source: http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    We also need to normalize the path as described here:
        https://bugs.python.org/issue18199#msg260122
    """
    path = force_decode(path)

    if WINDOWS and not path.startswith("\\\\?\\"):
        path = f"\\\\?\\{normalized_path(path)}"

    return path


def path_join(parent: str, child: str) -> str:
    if parent == "/":
        return "/" + child
    return parent + "/" + child


def find_resource(folder: str, filename: str = "") -> str:
    """ Find the FS path of a directory in various OS binary packages. """
    return os.path.join(Options.res_dir, folder, filename)


def find_icon(icon: str) -> str:
    return find_resource("icons", icon)


def force_decode(string: Union[bytes, str]) -> str:
    if isinstance(string, bytes):
        string = string.decode("utf-8")
    return string


def force_encode(data: Union[bytes, str]) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data


def encrypt(
    plaintext: Union[bytes, str], secret: Union[bytes, str], lazy: bool = True
) -> bytes:
    """ Symetric encryption using AES. """

    import base64
    from Cryptodome.Random import get_random_bytes
    from Cryptodome.Cipher import AES

    plaintext = force_encode(plaintext)
    secret = force_encode(secret)
    secret = _lazysecret(secret) if lazy else secret
    iv = get_random_bytes(AES.block_size)
    encobj = AES.new(secret, AES.MODE_CFB, iv)
    return base64.b64encode(iv + encobj.encrypt(plaintext))


def decrypt(
    ciphertext: Union[bytes, str], secret: Union[bytes, str], lazy: bool = True
) -> Optional[bytes]:
    """ Symetric decryption using AES. """

    import base64
    from Cryptodome.Cipher import AES

    ciphertext = force_encode(ciphertext)
    secret = force_encode(secret)
    secret = _lazysecret(secret) if lazy else secret
    ciphertext = base64.b64decode(ciphertext)
    iv = ciphertext[: AES.block_size]
    ciphertext = ciphertext[AES.block_size :]

    # Don't fail on decrypt
    try:
        encobj = AES.new(secret, AES.MODE_CFB, iv)
        return encobj.decrypt(ciphertext)
    except:
        return None


def _lazysecret(secret: bytes, blocksize: int = 32, padding: bytes = b"}") -> bytes:
    """Pad secret if not legal AES block size (16, 24, 32)"""
    if len(secret) > blocksize:
        return secret[: -(len(secret) - blocksize)]
    if not len(secret) in (16, 24, 32):
        return secret + (blocksize - len(secret)) * padding
    return secret


def guess_server_url(
    url: str,
    login_page: str = Options.startup_page,
    proxy: "Proxy" = None,
    timeout: int = 5,
) -> Optional[str]:
    """
    Guess the complete server URL given an URL (either an IP address,
    a simple domain name or an already complete URL).

    :param url: The server URL (IP, domain name, full URL).
    :param login_page: The Drive login page.
    :param int timeout: Timeout for each and every request.
    :return: The complete URL.
    """

    import requests
    import rfc3987

    parts = urlsplit(url)

    # IP address or domain name only
    if parts.scheme:
        """
        Handle that kind of `url`:

        >>> urlsplit('192.168.0.42:8080/nuxeo')
        SplitResult(scheme='192.168.0.42', netloc='', path='8080/nuxeo', ...)
        """
        domain = ":".join([parts.scheme, parts.path.strip("/")])
    else:
        domain = parts.path.strip("/")

    # URLs to test
    urls = [
        # First, test the given URL
        parts,
        # URL/nuxeo
        (
            parts.scheme,
            parts.netloc,
            parts.path + "/nuxeo",
            parts.query,
            parts.fragment,
        ),
        # URL:8080/nuxeo
        (
            parts.scheme,
            parts.netloc + ":8080",
            parts.path + "/nuxeo",
            parts.query,
            parts.fragment,
        ),
        # https://domain.com/nuxeo
        ("https", domain, "nuxeo", "", ""),
        ("https", domain + ":8080", "nuxeo", "", ""),
        # https://domain.com
        ("https", domain, "", "", ""),
        # https://domain.com:8080/nuxeo
        # http://domain.com/nuxeo
        ("http", domain, "nuxeo", "", ""),
        # http://domain.com:8080/nuxeo
        ("http", domain + ":8080", "nuxeo", "", ""),
        # http://domain.com
        ("http", domain, "", "", ""),
    ]

    kwargs = {"timeout": timeout, "verify": not Options.ssl_no_verify}
    for new_url_parts in urls:
        new_url = urlunsplit(new_url_parts).rstrip("/")
        try:
            rfc3987.parse(new_url, rule="URI")
            log.trace(f"Testing URL {new_url!r}")
            full_url = f"{new_url}/{login_page}"
            if proxy:
                kwargs["proxies"] = proxy.settings(url=full_url)
            with requests.get(full_url, **kwargs) as resp:
                resp.raise_for_status()
                if resp.status_code == 200:
                    return new_url
        except requests.HTTPError as exc:
            if exc.response.status_code == 401:
                # When there is only Web-UI installed, the code is 401.
                return new_url
        except (ValueError, requests.RequestException):
            pass

    if not url.lower().startswith("http"):
        return None
    return url


def simplify_url(url: str) -> str:
    """ Simplify port if possible and trim trailing slashes. """

    parts = urlsplit(url)
    new_parts = [parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment]

    if parts.scheme == "http" and parts.netloc.endswith(":80"):
        new_parts[1] = parts.netloc[:-3]
    elif parts.scheme == "https" and parts.netloc.endswith(":443"):
        new_parts[1] = parts.netloc[:-4]

    return urlunsplit(new_parts).rstrip("/")


def parse_protocol_url(url_string: str) -> Optional[Dict[str, str]]:
    """
    Parse URL for which Drive is registered as a protocol handler.

    Return None if `url_string` is not a supported URL pattern or raise a
    ValueError is the URL structure is invalid.
    """

    if not url_string.startswith("nxdrive://"):
        return None

    # Commands that need a path to work with
    path_cmds = ("access-online", "copy-share-link", "edit-metadata")

    protocol_regex = (
        # Direct Edit stuff
        (
            r"nxdrive://(?P<cmd>edit)/(?P<scheme>\w*)/(?P<server>.*)/"
            r"user/(?P<username>.*)/repo/(?P<repo>.*)/"
            r"nxdocid/(?P<docid>(\d|[a-f]|-)*)/filename/(?P<filename>[^/]*)"
            r"(/downloadUrl/(?P<download>.*)|)"
        ),
        # Events from context menu:
        #     - Access online
        #     - Copy share-link
        #     - Edit metadata
        # And event from macOS to sync the document status (FinderSync)
        r"nxdrive://(?P<cmd>({}))/(?P<path>.*)".format("|".join(path_cmds)),
        # Event to acquire the login token from the server
        (
            r"nxdrive://(?P<cmd>token)/"
            r"(?P<token>[0-F]{8}-[0-F]{4}-[0-F]{4}-[0-F]{4}-[0-F]{12})/"
            r"user/(?P<username>.*)"
        ),
    )

    match_res = None
    for regex in protocol_regex:
        match_res = re.match(regex, url_string, re.I)
        if match_res:
            break

    if not match_res:
        raise ValueError(f"Unsupported command {url_string!r} in protocol handler")

    parsed_url: Dict[str, str] = match_res.groupdict()
    cmd = parsed_url["cmd"]
    if cmd == "edit":
        return parse_edit_protocol(parsed_url, url_string)
    elif cmd == "token":
        return dict(
            command=cmd, token=parsed_url["token"], username=parsed_url["username"]
        )
    elif cmd in path_cmds:
        return dict(command=cmd, filepath=parsed_url["path"])
    return dict(command=cmd)


def parse_edit_protocol(parsed_url: Dict[str, str], url_string: str) -> Dict[str, str]:
    """ Parse a `nxdrive://edit` URL for quick editing of Nuxeo documents. """
    scheme = parsed_url["scheme"]
    if scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid command {url_string}: scheme should be http or https"
        )

    server_url = f"{scheme}://{parsed_url.get('server')}"

    return dict(
        command="download_edit",
        server_url=server_url,
        user=parsed_url["username"],
        repo=parsed_url["repo"],
        doc_id=parsed_url["docid"],
        filename=parsed_url["filename"],
        download_url=parsed_url["download"],
    )


def set_path_readonly(path: str) -> None:
    current = os.stat(path).st_mode
    if os.path.isdir(path):
        # Need to add
        right = stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IRUSR
        if current & ~right != 0:
            os.chmod(path, right)
    else:
        # Already in read only
        right = stat.S_IRGRP | stat.S_IRUSR
        if current & ~right != 0:
            os.chmod(path, right)


def unset_path_readonly(path: str) -> None:
    current = os.stat(path).st_mode
    if os.path.isdir(path):
        right = (
            stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IRUSR
            | stat.S_IWGRP
            | stat.S_IWUSR
        )
        if current & right != right:
            os.chmod(path, right)
    else:
        right = stat.S_IRGRP | stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR
        if current & right != right:
            os.chmod(path, right)


def unlock_path(path: str, unlock_parent: bool = True) -> int:
    result = 0
    if unlock_parent:
        parent_path = os.path.dirname(path)
        if os.path.exists(parent_path) and not os.access(parent_path, os.W_OK):
            unset_path_readonly(parent_path)
            result |= 2
    if os.path.exists(path) and not os.access(path, os.W_OK):
        unset_path_readonly(path)
        result |= 1
    return result


def lock_path(path: str, locker: int) -> None:
    if locker == 0:
        return
    if locker & 1 == 1:
        set_path_readonly(path)
    if locker & 2 == 2:
        parent = os.path.dirname(path)
        set_path_readonly(parent)


def short_name(name: Union[bytes, str]) -> str:
    """
    Shortening a given `name` for notifications, as the text is limited to 200 characters on Windows:
    https://msdn.microsoft.com/en-us/library/windows/desktop/ee330740(v=vs.85).aspx
    This is related to Windows, but we apply the truncation everywhere.
    """
    name = force_decode(name)
    if len(name) > 70:
        name = f"{name[:30]}…{name[-40:]}"
    return name


class PidLockFile:
    """ This class handle the pid lock file"""

    def __init__(self, folder: str, key: str) -> None:
        self.folder = folder
        self.key = key
        self.locked = False

    def _get_sync_pid_filepath(self, process_name: str = None) -> str:
        if process_name is None:
            process_name = self.key
        return os.path.join(self.folder, f"nxdrive_{process_name}.pid")

    def unlock(self) -> None:
        if not self.locked:
            return
        # Clean pid file
        pid_filepath = self._get_sync_pid_filepath()
        try:
            os.unlink(pid_filepath)
        except Exception as e:
            log.warning(
                f"Failed to remove stalled PID file: {pid_filepath!r} "
                f"for stopped process {os.getpid()}: {e!r}"
            )

    def check_running(self, process_name: str = None) -> Optional[int]:
        """Check whether another sync process is already runnning

        If nxdrive.pid file already exists and the pid points to a running
        nxdrive program then return the pid. Return None otherwise.
        """

        from contextlib import suppress
        import psutil

        if process_name is None:
            process_name = self.key
        pid_filepath = self._get_sync_pid_filepath(process_name=process_name)
        if os.path.exists(pid_filepath):
            with open(safe_long_path(pid_filepath), "rb") as f:
                with suppress(ValueError, psutil.NoSuchProcess):
                    pid = int(f.read().strip())
                    p = psutil.Process(pid)
                    # If process has been created after the lock file
                    # Changed from getctime() to getmtime() because of Windows
                    # file system tunneling
                    if p.create_time() > os.path.getmtime(pid_filepath):
                        raise ValueError
                    return pid
                pid = os.getpid()
            # This is a pid file that is empty or pointing to either a
            # stopped process or a non-nxdrive process: let's delete it if
            # possible
            try:
                os.unlink(pid_filepath)
                if pid is None:
                    msg = f"Removed old empty PID file {pid_filepath!r}"
                else:
                    msg = f"Removed old PID file {pid_filepath!r} for stopped process {pid}"
                log.info(msg)
            except Exception as e:
                if pid is not None:
                    msg = (
                        f"Failed to remove stalled PID file: {pid_filepath!r} "
                        f"for stopped process {pid}: {e!r}"
                    )
                    log.warning(msg)
                    return pid
                msg = (
                    f"Failed to remove empty stalled PID file {pid_filepath!r}: "
                    f"{e!r}"
                )
                log.warning(msg)
        self.locked = True
        return None

    def lock(self) -> Optional[int]:
        pid = self.check_running(process_name=self.key)
        if pid is not None:
            log.warning(f"{self.key} process with PID {pid} already running")
            return pid

        # Write the pid of this process
        pid_filepath = self._get_sync_pid_filepath(process_name=self.key)
        pid = os.getpid()
        with open(safe_long_path(pid_filepath), "w") as f:
            f.write(str(pid))
        return None
