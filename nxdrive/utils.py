# coding: utf-8
"""
We are using lazy imports (understand imports in functions) specifically here
to speed-up command line calls without loading everything at startup.
"""
import os
import os.path
import re
import stat
from copy import deepcopy
from datetime import datetime
from logging import getLogger
from pathlib import Path
from threading import get_ident
from typing import (
    Any,
    Callable,
    Dict,
    Iterator,
    Optional,
    Pattern,
    Tuple,
    TYPE_CHECKING,
    Union,
)
from urllib.parse import urlsplit, urlunsplit

from nuxeo.utils import get_digest_hash

from .constants import (
    APP_NAME,
    DOC_UID_REG,
    FILE_BUFFER_SIZE,
    MAC,
    UNACCESSIBLE_HASH,
    WINDOWS,
)
from .exceptions import InvalidSSLCertificate, UnknownDigest
from .options import Options

if TYPE_CHECKING:
    from .proxy import Proxy  # noqa

__all__ = (
    "PidLockFile",
    "compute_digest",
    "compute_fake_pid_from_path",
    "compute_urls",
    "current_milli_time",
    "current_thread_id",
    "decrypt",
    "encrypt",
    "find_icon",
    "find_resource",
    "find_suitable_tmp_dir",
    "force_decode",
    "force_encode",
    "get_arch",
    "get_certificate_details",
    "get_current_os",
    "get_current_os_full",
    "get_date_from_sqlite",
    "get_device",
    "get_timestamp_from_date",
    "guess_server_url",
    "if_frozen",
    "is_generated_tmp_file",
    "lock_path",
    "normalize_event_filename",
    "normalized_path",
    "normalize_and_expand_path",
    "parse_edit_protocol",
    "parse_protocol_url",
    "retrieve_ssl_certificate",
    "safe_filename",
    "safe_long_path",
    "set_path_readonly",
    "sizeof_fmt",
    "short_name",
    "simplify_url",
    "unlock_path",
    "unset_path_readonly",
    "version_le",
)

DEFAULTS_CERT_DETAILS = {
    "subject": [],
    "issuer": [],
    "caIssuers": [],
    "serialNumber": "N/A",
    "notAfter": "N/A",
    "notBefore": "N/A",
}

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


def compute_fake_pid_from_path(path: str) -> int:
    """
    We have no way to find the PID of the apps using the opened file.
    This is a limitation (or a feature) of COM objects and AppleScript.
    To bypass this, we compute a "unique" ID for a given path.
    """
    from binascii import crc32
    from sys import getdefaultencoding

    if isinstance(path, bytes):
        path_b = path
    else:
        path_b = path.encode(getdefaultencoding() or "utf-8", errors="ignore")

    return crc32(path_b)


def current_thread_id() -> int:
    """Return the thread identifier of the current thread. This is a nonzero integer."""
    # TODO: use get_native_id() in Python 3.8 (XXX_PYTHON)
    return get_ident()


def find_suitable_tmp_dir(sync_folder: Path, home_folder: Path) -> Path:
    """Find a suitable folder for the downloaded temporary files.
    It _must_ be on the same partition of the local sync folder
    to prevent false FS events.
    """
    if WINDOWS:
        # On Windows, we need to check for the drive letter
        if sync_folder.drive == home_folder.drive:
            # Both folders are on the same partition, use the predefined home folder
            return home_folder

    # On Unix, we check the st_dev field
    elif sync_folder.stat().st_dev == home_folder.stat().st_dev:
        # Both folders are on the same partition, use the predefined home folder
        return home_folder

    # Folders are on different partitions, try to find a suitable one based one the same
    # partition used by the *sync_folder*.
    return sync_folder.parent


def get_date_from_sqlite(d: str) -> Optional[datetime]:
    format_date = "%Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(str(d.split(".")[0]), format_date)
    except Exception:
        return None


def get_timestamp_from_date(d: datetime = None) -> int:
    if not d:
        return 0

    import calendar

    return int(calendar.timegm(d.timetuple()))


def current_milli_time() -> int:
    from time import time

    return int(round(time() * 1000))


def get_arch() -> str:
    """ Detect the OS architecture. """

    from struct import calcsize

    return f"{calcsize('P') * 8}-bit"


def get_current_os() -> Tuple[str, str]:
    """ Detect the OS version. """

    device = get_device()

    if device == "macOS":
        from platform import mac_ver

        # Ex: macOS 10.12.6
        version = mac_ver()[0]
    elif device == "GNU/Linux":
        import distro

        # Ex: Debian GNU/Linux testing buster
        details = distro.linux_distribution()
        device = details[0]
        version = " ".join(details[1:])
    else:
        from platform import win32_ver

        # Ex: Windows 7
        version = win32_ver()[0]

    return (device, version.strip())


def get_current_os_full() -> Tuple[Any, ...]:
    """ Detect the full OS version for log debugging. """

    device = get_device()

    if device == "macOS":
        from platform import mac_ver

        return mac_ver()
    elif device == "GNU/Linux":
        import distro

        return distro.linux_distribution()
    else:
        from platform import win32_ver

        return win32_ver()


def get_device() -> str:
    """ Retrieve the device type. """

    from sys import platform

    device = DEVICE_DESCRIPTIONS.get(platform)
    if not device:
        device = platform.replace(" ", "")
    return device


def get_default_local_folder() -> Path:
    """
    Find a reasonable location for the root Nuxeo Drive folder

    This folder is user specific, typically under the home folder.

    Under Windows, try to locate My Documents as a home folder, using the
    win32com shell API if allowed, else falling back on a manual detection.
    """

    if WINDOWS:
        from win32com.shell import shell, shellcon

        try:
            folder = normalized_path(
                shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
            )
        except Exception:
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
            log.warning(
                "Access denied to the API SHGetFolderPath,"
                " falling back on manual detection",
                exc_info=True,
            )
            folder = normalized_path(Options.home) / "Documents"
    else:
        folder = normalized_path(Options.home)

    return increment_local_folder(folder, APP_NAME)


def get_value(value: str) -> Union[bool, str, Tuple[str, ...]]:
    """ Get parsed value for commandline/registry input. """

    if value.lower() in {"true", "1", "on", "yes", "oui"}:
        return True
    elif value.lower() in {"false", "0", "off", "no", "non"}:
        return False
    elif "\n" in value:
        return tuple(sorted(value.split()))

    return value


def increment_local_folder(basefolder: Path, name: str) -> Path:
    """Increment the number for a possible local folder.
    Example: "Nuxeo Drive" > "Nuxeo Drive 2" > "Nuxeo Drive 3"
    """
    folder = basefolder / name
    num = 2
    while "checking":
        if not folder.is_dir():
            break
        folder = basefolder / f"{name} {num}"
        num += 1
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


def normalized_path(path: Union[bytes, str, Path], cls: Callable = Path) -> Path:
    """Return absolute, normalized file path.
    The *cls* argument is used in tests, it must be a class or subclass of Path.
    """
    if not isinstance(path, Path):
        path = force_decode(path)
    expanded = cls(path).expanduser()
    try:
        return expanded.resolve()
    except PermissionError:
        # On Windows, we can get a PermissionError when the file is being
        # opened in another software, fallback on .absolute() then.
        return expanded.absolute()


def normalize_and_expand_path(path: str) -> Path:
    """ Return absolute, normalized file path with expanded environment variables. """
    return normalized_path(os.path.expandvars(path))


def normalize_event_filename(filename: Union[str, Path], action: bool = True) -> Path:
    """
    Normalize a file name.

    :param unicode filename: The file name to normalize.
    :param bool action: Apply changes on the file system.
    :return Path: The normalized file name.
    """

    import unicodedata

    path = Path(filename)

    # NXDRIVE-688: Ensure the name is stripped for a file
    stripped = Path(str(path).strip())
    if all(
        [
            not WINDOWS,  # Windows does not allow files/folders ending with space(s)
            action,
            path != stripped,
            path.exists(),
            not path.is_dir(),
        ]
    ):
        # We can have folders ending with spaces
        log.info(f"Forcing space normalization: {path!r} -> {stripped!r}")
        path.rename(stripped)
        path = stripped

    # NXDRIVE-188: Normalize name on the file system, if needed
    normalized = Path(unicodedata.normalize("NFC", str(path)))
    normalized = normalized.with_name(safe_os_filename(normalized.name))

    if WINDOWS and path.exists():
        path = normalized_path(path).with_name(path.name)

    if not MAC and action and path != normalized and path.exists():
        log.info(f"Forcing normalization: {path!r} -> {normalized!r}")
        safe_rename(path, normalized)

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
    if WINDOWS:
        # Windows doesn't allow whitespace at the end of filenames
        name = name.rstrip()
    return re.sub(pattern, replacement, name)


def safe_os_filename(name: str, pattern: Pattern = re.compile(r"([/:])")) -> str:
    """
    Replace characters that are forbidden in file or folder names by the OS.

    On Windows, they are:
        " | * / : < > ? \\
    On Unix, they are:
        / :
    """
    if WINDOWS:
        return safe_filename(name)
    else:
        return safe_filename(name, pattern=pattern)


def safe_long_path(path: Path) -> Path:
    """
    Utility to prefix path with the long path marker for Windows
    Source: http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    We also need to normalize the path as described here:
        https://bugs.python.org/issue18199#msg260122
    """
    if WINDOWS:
        path = Path(f"\\\\?\\{normalized_path(path)}")
    return path


def safe_rename(src: Path, dst: Path) -> None:
    """
    Safely rename files on Windows.

    As said here https://docs.python.org/3/library/pathlib.html#pathlib.Path.rename
    Unix systems will silently replace the destination if it is an existing file,
    if the user has permissions.
    This function is here to ensure Windows keeps the same behavior as the other OSes.
    In case the user doesn't have the fitting permissions to delete the destination or
    rename the file after deletion, we let the error raise.
    """
    try:
        src.rename(dst)
    except FileExistsError:
        if dst.is_file():
            log.info(f"Deleting {dst} to rename {src} in its place")
            dst.unlink()
            src.rename(dst)
        else:
            raise


def find_resource(folder: str, filename: str = "") -> Path:
    """ Find the FS path of a directory in various OS binary packages. """
    return normalized_path(Options.res_dir) / folder / filename


def find_icon(icon: str) -> Path:
    return find_resource("icons", icon)


def force_decode(string: Union[bytes, str]) -> str:
    if isinstance(string, bytes):
        string = string.decode("utf-8")
    return string


def force_encode(data: Union[bytes, str]) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data


def retrieve_ssl_certificate(hostname: str, port: int = 443) -> str:
    """Retreive the SSL certificate from a given hostname."""

    import ssl

    with ssl.create_connection((hostname, port)) as conn:  # type: ignore
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        with context.wrap_socket(conn, server_hostname=hostname) as sock:
            cert_data: bytes = sock.getpeercert(binary_form=True)  # type: ignore
            return ssl.DER_cert_to_PEM_cert(cert_data)


def get_certificate_details(hostname: str = "", cert_data: str = "") -> Dict[str, Any]:
    """
    Get SSL certificate details from a given certificate content or hostname.

    Note: This function uses a undocumented method of the _ssl module.
          It is continuously tested in our CI to ensure it still
          available after any Python upgrade.
          Certified working as of Python 3.6.7.
    """

    import ssl

    defaults = deepcopy(DEFAULTS_CERT_DETAILS)
    cert_file = Path("c.crt")

    try:
        certificate = cert_data or retrieve_ssl_certificate(hostname)
        cert_file.write_text(certificate, encoding="utf-8")
        try:
            # Taken from https://stackoverflow.com/a/50072461/1117028
            details = ssl._ssl._test_decode_cert(cert_file)  # type: ignore
            defaults.update(details)
        finally:
            cert_file.unlink()
    except Exception:
        log.warning("Error while retreiving the SSL certificate", exc_info=True)

    return defaults


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
    except Exception:
        return None


def _lazysecret(secret: bytes, blocksize: int = 32, padding: bytes = b"}") -> bytes:
    """Pad secret if not legal AES block size (16, 24, 32)"""
    length = len(secret)
    if length > blocksize:
        return secret[: -(length - blocksize)]
    if length not in (16, 24, 32):
        return secret + (blocksize - length) * padding
    return secret


def compute_urls(url: str) -> Iterator[str]:
    """
    Compute several predefined URLs for a given URL.
    Each URL is sanitized and yield'ed.
    """
    import re

    # Remove any whitespace character
    # (space, tab, carriage return, new line, vertical tab, form feed)
    url = re.sub(r"\s+", "", url)

    parts = urlsplit(url)

    # IP address or domain name only
    if parts.scheme:
        """
        Handle that kind of `url`:

        >>> urlsplit('192.168.0.42:8080/nuxeo')
        SplitResult(scheme='', netloc='', path='192.168.0.42:8080/nuxeo', ...)
        """
        domain = parts.netloc
        path = parts.path
    else:
        if "/" in parts.path:
            domain, path = parts.path.split("/", 1)
        else:
            domain = parts.path
            path = ""

    urls = []
    for scheme, port in (("https", 443), ("http", 8080)):
        urls.extend(
            [
                # scheme://URL/nuxeo
                (scheme, domain, path, parts.query, parts.fragment),
                # scheme://URL:port/nuxeo
                (scheme, f"{domain}:{port}", path, parts.query, parts.fragment),
                # scheme://domain.com/nuxeo
                (scheme, domain, "nuxeo", "", ""),
                (scheme, f"{domain}:{port}", "nuxeo", "", ""),
                (scheme, domain, path, "", ""),
                (scheme, f"{domain}:{port}", path, "", ""),
                # scheme://domain.com
                (scheme, domain, "", "", ""),
            ]
        )

    for new_url_parts in urls:
        # Join and remove trailing slash(es)
        new_url = urlunsplit(new_url_parts)
        # Remove any double slashes but ones from the protocol
        scheme, url = new_url.split("://")
        yield f'{scheme}://{re.sub(r"(/{2,})", "/", url.strip("/"))}'


def guess_server_url(
    url: str,
    login_page: str = Options.startup_page,
    proxy: "Proxy" = None,
    timeout: int = 5,
) -> str:
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

    from requests.exceptions import SSLError

    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        "verify": Options.ca_bundle or not Options.ssl_no_verify,
    }
    for new_url in compute_urls(url):
        try:
            rfc3987.parse(new_url, rule="URI")
            log.debug(f"Testing URL {new_url!r}")
            full_url = f"{new_url}/{login_page}"
            if proxy:
                kwargs["proxies"] = proxy.settings(url=full_url)
            with requests.get(full_url, **kwargs) as resp:
                resp.raise_for_status()
                if resp.status_code == 200:  # Happens when JSF is installed
                    log.debug(f"Found URL: {new_url}")
                    return new_url
        except SSLError as exc:
            if "CERTIFICATE_VERIFY_FAILED" in str(exc):
                raise InvalidSSLCertificate()
        except requests.HTTPError as exc:
            if exc.response.status_code in (401, 403):
                # When there is only Web-UI installed, the code is 401.
                log.debug(f"Found URL: {new_url}")
                return new_url
        except (ValueError, requests.RequestException):
            log.debug(f"Bad URL: {new_url}")
        except Exception:
            log.exception("Unhandled error")

    if not url.lower().startswith("http"):
        return ""
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
            r"nxdocid/(?P<docid>[0-9a-fA-F\-]*)/filename/(?P<filename>[^/]*)"
            r"/downloadUrl/(?P<download>.*)"
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
            fr"(?P<token>{DOC_UID_REG})/"
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
    return dict(command=cmd, filepath=parsed_url["path"])


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


def set_path_readonly(path: Path) -> None:
    if path.is_dir():
        # Need to add
        right = stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IRUSR
    else:
        # Already in read only
        right = stat.S_IRGRP | stat.S_IRUSR

    if path.stat().st_mode & ~right != 0:
        path.chmod(right)


def unset_path_readonly(path: Path) -> None:
    if path.is_dir():
        right = (
            stat.S_IXUSR
            | stat.S_IRGRP
            | stat.S_IXGRP
            | stat.S_IRUSR
            | stat.S_IWGRP
            | stat.S_IWUSR
        )
    else:
        right = stat.S_IRGRP | stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR

    if path.stat().st_mode & right != right:
        path.chmod(right)


def unlock_path(path: Path, unlock_parent: bool = True) -> int:
    result = 0

    if unlock_parent:
        parent_path = path.parent
        if parent_path.exists() and not os.access(parent_path, os.W_OK):
            unset_path_readonly(parent_path)
            result |= 2

    if path.exists() and not os.access(path, os.W_OK):
        unset_path_readonly(path)
        result |= 1

    return result


def lock_path(path: Path, locker: int) -> None:
    if locker == 0:
        return

    if locker & 1 == 1:
        set_path_readonly(path)

    if locker & 2 == 2:
        set_path_readonly(path.parent)


def sizeof_fmt(num: Union[float, int], suffix: str = "B") -> str:
    """
    Human readable version of file size.
    Supports:
        - all currently known binary prefixes (https://en.wikipedia.org/wiki/Binary_prefix)
        - negative and positive numbers
        - numbers larger than 1,000 Yobibytes
        - arbitrary units

    Examples:

        >>> sizeof_fmt(168963795964)
        "157.4 GiB"
        >>> sizeof_fmt(168963795964, suffix="o")
        "157.4 Gio"

    Source: https://stackoverflow.com/a/1094933/1117028
    """
    val = float(num)
    for unit in ("", "Ki", "Mi", "Gi", "Ti", "Pi", "Ei", "Zi"):
        if abs(val) < 1024.0:
            return f"{val:3.1f} {unit}{suffix}"
        val /= 1024.0
    return f"{val:,.1f} Yi{suffix}"


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

    def __init__(self, folder: Path, key: str) -> None:
        self.folder = folder
        self.key = key
        self.locked = False

    def _get_sync_pid_filepath(self, process_name: str = None) -> Path:
        if process_name is None:
            process_name = self.key
        return safe_long_path(self.folder / f"nxdrive_{process_name}.pid")

    def unlock(self) -> None:
        if not self.locked:
            return

        # Clean pid file
        pid_filepath = self._get_sync_pid_filepath()
        try:
            pid_filepath.unlink()
        except OSError as e:
            log.warning(
                f"Failed to remove stalled PID file: {pid_filepath!r} "
                f"for stopped process {os.getpid()}: {e!r}"
            )

    def check_running(self, process_name: str = None) -> Optional[int]:
        """Check whether another sync process is already runnning

        If the lock file already exists and the pid points to a running
        nxdrive program then return the pid. Return None otherwise.
        """

        from contextlib import suppress
        import psutil

        if process_name is None:
            process_name = self.key

        pid_filepath = self._get_sync_pid_filepath(process_name=process_name)

        if pid_filepath.is_file():
            try:
                pid: Optional[int] = int(
                    pid_filepath.read_text(encoding="utf-8").strip()
                )
            except ValueError as exc:
                log.warning(f"The PID file has invalid data: {exc}")
                pid = None
            else:
                with suppress(ValueError, psutil.NoSuchProcess):
                    # If process has been created after the lock file.
                    # Changed from getctime() to getmtime() because of Windows
                    # file system tunneling.
                    if psutil.Process(pid).create_time() > pid_filepath.stat().st_mtime:
                        raise ValueError()

                    return pid

            # This is a pid file that is empty or pointing to either a
            # stopped process or a non-nxdrive process: let's delete it if
            # possible
            try:
                pid_filepath.unlink()
            except OSError as e:
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
            else:
                if pid is None:
                    msg = f"Removed old empty PID file {pid_filepath!r}"
                else:
                    msg = f"Removed old PID file {pid_filepath!r} for stopped process {pid}"
                log.info(msg)

        self.locked = True
        return None

    def lock(self) -> Optional[int]:
        pid = self.check_running(process_name=self.key)
        if pid is not None:
            log.warning(f"{self.key} process with PID {pid} already running")
            return pid

        # Write the pid of this process
        pid = os.getpid()
        if not isinstance(pid, int):
            raise RuntimeError(f"Invalid PID: {pid!r}")

        pid_filepath = self._get_sync_pid_filepath(process_name=self.key)
        pid_filepath.write_text(str(pid), encoding="utf-8")

        return None


def compute_digest(path: Path, digest_func: str, callback: Callable = None) -> str:
    """ Lazy computation of the digest. """
    h = get_digest_hash(digest_func)
    if not h:
        raise UnknownDigest(digest_func)

    try:
        with safe_long_path(path).open(mode="rb") as f:
            while "computing":
                if callable(callback):
                    callback(path)
                buf = f.read(FILE_BUFFER_SIZE)
                if not buf:
                    break
                h.update(buf)
    except (OSError, MemoryError):
        # MemoryError happens randomly, dunno why but this is
        # not an issue as the hash will be recomputed later
        return UNACCESSIBLE_HASH

    return h.hexdigest()
