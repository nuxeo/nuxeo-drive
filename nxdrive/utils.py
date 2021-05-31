"""
We are using lazy imports (understand imports in functions) specifically here
to speed-up command line calls without loading everything at startup.

Most of functions are pure enough to be decorated with a LRU cache.
Each *maxsize* is adjusted depending of the heavy use of the decorated function.
"""
import os
import os.path
import re
import stat
import sys
from configparser import ConfigParser
from copy import deepcopy
from datetime import datetime
from functools import lru_cache
from itertools import islice
from logging import getLogger
from pathlib import Path
from threading import get_native_id
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)
from urllib.parse import parse_qsl, urlparse, urlsplit, urlunsplit

from nuxeo.utils import get_digest_algorithm, get_digest_hash

from .constants import (
    APP_NAME,
    DOC_UID_REG,
    FILE_BUFFER_SIZE,
    MAC,
    UNACCESSIBLE_HASH,
    WINDOWS,
    DigestStatus,
)
from .exceptions import (
    EncryptedSSLCertificateKey,
    InvalidSSLCertificate,
    MissingClientSSLCertificate,
    UnknownDigest,
)
from .metrics.utils import user_agent
from .options import Options

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.ciphers import Cipher

    from .client.proxy import Proxy  # noqa


DEFAULTS_CERT_DETAILS = {
    "subject": [],
    "issuer": [],
    "caIssuers": [],
    "serialNumber": "N/A",
    "notAfter": "N/A",
    "notBefore": "N/A",
}

log = getLogger(__name__)


@lru_cache(maxsize=2048)
def compute_fake_pid_from_path(path: str, /) -> int:
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
    """Return the thread identifier of the current thread. This is a nonzero integer.

    Note: this function cannot be decorated with lru_cache().
    """
    return get_native_id()


def disk_space(a_folder: str, /) -> Tuple[int, int]:
    """Retrieve the disk space used and free based on the given *a_folder*.
    Return a tuple(used, free) in bytes.
    """
    import shutil

    folder = Path(a_folder)
    for path in (folder, *folder.parents):
        try:
            data = shutil.disk_usage(path)
        except OSError:
            continue
        else:
            used = data.used
            free = data.free
            break
    else:
        used, free = 0, 0

    return used, free


def find_suitable_tmp_dir(sync_folder: Path, home_folder: Path, /) -> Path:
    """Find a suitable folder for the downloaded temporary files.

    It _must_ be on the same partition/filesystem of the local sync folder
    to prevent false FS events.

    Raise ValueError if the sync folder is at the root of the partition/filesystem.

    Note: this function cannot be decorated with lru_cache().
    """
    try:
        if WINDOWS:
            # On Windows, we need to check for the drive letter
            if str(sync_folder) == sync_folder.drive:
                # It is not allowed to use the root drive as sync folder
                raise ValueError("The local sync folder cannot be the drive itself")

            if sync_folder.drive == home_folder.drive:
                # Both folders are on the same partition, use the predefined home folder
                return home_folder
        else:
            if sync_folder.is_mount():
                # It is not allowed to use the mount point as sync folder
                raise ValueError(
                    "The local sync folder cannot be the mount point itself"
                )

            # On Unix, we check the st_dev field
            if sync_folder.stat().st_dev == home_folder.stat().st_dev:
                # Both folders are on the same mount points/filesystems, use the predefined home folder
                return home_folder

        # Folders are on different partitions/filesystem, find a suitable one based one the
        # same partition/filesystem used by the sync folder. The home folder's name is appended
        # to keep a clean tree.
        return sync_folder.parent / home_folder.name
    except FileNotFoundError:
        # Typically, the sync folder does not exist anymore
        return home_folder


@lru_cache(maxsize=1024)
def get_date_from_sqlite(d: str, /) -> Optional[datetime]:
    format_date = "%Y-%m-%d %H:%M:%S"
    try:
        return datetime.strptime(str(d.split(".")[0]), format_date)
    except Exception:
        return None


@lru_cache(maxsize=1024)
def get_timestamp_from_date(d: Optional[datetime], /) -> int:
    if not d:
        return 0

    import calendar

    return int(calendar.timegm(d.timetuple()))


def current_milli_time() -> int:
    """Return the current time in milliseconds.

    Note: this function cannot be decorated with lru_cache().
    """
    from time import time

    return int(round(time() * 1000))


def get_default_local_folder() -> Path:
    """
    Find a reasonable location for the root Nuxeo Drive folder

    This folder is user specific, typically under the home folder.

    Under Windows, try to locate My Documents as a home folder, using the
    win32com shell API if allowed, else falling back on a manual detection.

    Note: this function cannot be decorated with lru_cache().
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


def get_tree_list(path: Path, /) -> Generator[Tuple[Path, int], None, None]:
    """
    Determine local paths and their size from a given *path*.
    Each entry will yield a tuple (local_path, size).

    Note: this function cannot be decorated with lru_cache().
    """
    try:
        it = os.scandir(path)
    except OSError:
        log.warning(f"Cannot browse {path!r}")
        return

    # Check that the path can be processed
    path_lower = path.name.lower()
    if path_lower.startswith(Options.ignored_prefixes) or path_lower.endswith(
        Options.ignored_suffixes
    ):
        log.debug(f"Ignored path for Direct Transfer: {str(path)!r}")
        return

    if path.is_symlink():
        log.debug(f"Ignored symlink path for Direct Transfer: {str(path)!r}")
        return

    # First, yield the folder itself
    yield path, 0

    # Then, yield its children
    with it:
        for entry in it:
            # Check the path can be processed
            entry_lower = entry.name.lower()
            if entry_lower.startswith(Options.ignored_prefixes) or entry_lower.endswith(
                Options.ignored_suffixes
            ):
                log.debug(f"Ignored path for Direct Transfer: {entry.path!r}")
                continue

            try:
                is_dir = entry.is_dir()
            except OSError:
                log.warning(f"Error calling is_dir() on {entry.path!r}", exc_info=True)
                continue

            if entry.is_symlink():
                log.debug(f"Ignored symlink path for Direct Transfer: {entry.path!r}")
                continue

            if is_dir:
                yield from get_tree_list(Path(entry.path))
            elif entry.is_file():
                file = Path(entry.path)
                yield file, file.stat().st_size


@lru_cache(maxsize=32)
def get_value(value: str, /) -> Union[bool, float, str, Tuple[str, ...]]:
    """Get parsed value for commandline/registry input."""

    if value.lower() in ("true", "1", "on", "yes", "oui"):
        return True
    elif value.lower() in ("false", "0", "off", "no", "non"):
        return False
    elif "\n" in value:
        return tuple(sorted(value.split()))
    elif value.count(".") == 1 and re.match(r"^[\d\.]+$", value):
        # "0.1" -> 0.1
        return float(value)

    return value


def grouper(
    iterable: List[Any], count: int, /
) -> Generator[Tuple[Any, ...], None, None]:
    """grouper("ABCDEFG", 3) --> ('ABC') ('DEF') ('G',)."""
    it = iter(iterable)
    while "there are items":
        chunk = tuple(islice(it, count))
        if not chunk:
            return
        yield chunk


def increment_local_folder(basefolder: Path, name: str, /) -> Path:
    """Increment the number for a possible local folder.
    Example: "Nuxeo Drive" > "Nuxeo Drive 2" > "Nuxeo Drive 3"

    Note: this function cannot be decorated with lru_cache().
    """
    folder = basefolder / name
    num = 2
    while "checking":
        if not folder.is_dir():
            break
        folder = basefolder / f"{name} {num}"
        num += 1
    return folder


@lru_cache(maxsize=32)
def is_hexastring(value: str, /) -> bool:
    try:
        int(value, 16)
        return True
    except ValueError:
        return False


def is_generated_tmp_file(name: str, /) -> Tuple[bool, Optional[bool]]:
    """
    Try to guess temporary files generated by third party software.
    Returns a tuple to know what kind of tmp file it is to
    filter later on Processor._synchronize_locally_created().

    Note: this function cannot be decorated with lru_cache() because
    Options is used and values may change the time the app is running.

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


def path_is_unc_name(path: Path) -> bool:
    """Return True whenever the given *path* is a UNC name.
    It is a Windows specificity.
    """
    if not WINDOWS:
        return False

    path_str = str(path)

    # Fast path: it is a usual path
    if not path_str.startswith("\\\\"):
        return False

    # Pay attention to:
    #     - \\?\C:\Users\Alice\folder   (long-path prefixed usual path)
    #     - \\?\UNC\Server\Alice\folder (long-path prefixed UNC name)
    #     - \\Server\Alice\folder       (UNC name)
    # They all start with "\\" but we only want to be sure to target UNC names.
    return path_str.startswith("\\\\?\\UNC\\") or (path_str[2] != "?")


def normalized_path(path: Union[bytes, str, Path], /) -> Path:
    """Return absolute, normalized file path.

    Note: this function cannot be decorated with lru_cache().
    """
    if not isinstance(path, Path):
        path = Path(os.fsdecode(path))
    # NXDRIVE-2485: using os.path.realpath() instead of Path.resolve() and Path().absolute().
    return Path(os.path.realpath(path.expanduser()))


def normalize_and_expand_path(path: str, /) -> Path:
    """Return absolute, normalized file path with expanded environment variables.

    Note: this function cannot be decorated with lru_cache().
    """
    return normalized_path(os.path.expandvars(path))


def normalize_event_filename(
    filename: Union[str, Path], /, *, action: bool = True
) -> Path:
    """
    Normalize a file name.

    Note: we cannot decorate the function with lru_cache() because it as
    several side effects. We need to find a way to decouple the normalization
    and actions to do on the OS.

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
    normalized = normalized.with_name(safe_filename(normalized.name))

    if WINDOWS and path.exists():
        path = normalized_path(path).with_name(path.name)

    if not MAC and action and path != normalized and path.exists():
        log.info(f"Forcing normalization: {path!r} -> {normalized!r}")
        safe_rename(path, normalized)

    return normalized


def if_frozen(func, /) -> Callable:  # type: ignore
    """
    Decorator to enable the call of a function/method
    only if the application is frozen.

    Note: this function must not be decorated with lru_cache().
    """

    def wrapper(*args: Any, **kwargs: Any) -> Union[bool, Callable]:
        """Inner function to do the check and abort the call
        if the application not frozen."""
        if not Options.is_frozen:
            return False
        return func(*args, **kwargs)  # type: ignore

    return wrapper


@lru_cache(maxsize=4096)
def safe_filename(name: str, /, *, replacement: str = "-") -> str:
    """Replace forbidden characters (at the OS and Nuxeo levels) for a given *name*.
    See benchmarks/test_safe_filename.py for the best implementation.
    """
    return (
        # Windows doesn't allow whitespace at the end of filenames
        (name.rstrip() if WINDOWS else name)
        .replace("/", replacement)
        .replace(":", replacement)
        .replace('"', replacement)
        .replace("|", replacement)
        .replace("*", replacement)
        .replace("<", replacement)
        .replace(">", replacement)
        .replace("?", replacement)
        .replace("\\", replacement)
    )


def safe_long_path(path: Path, /) -> Path:
    """
    Utility to prefix path with the long path marker for Windows
    Source: http://msdn.microsoft.com/en-us/library/aa365247.aspx#maxpath

    We also need to normalize the path as described here:
        https://bugs.python.org/issue18199#msg260122
    """
    if WINDOWS:
        if path.parts[0].startswith("\\\\"):
            # Only checking for "\\" to cover UNC paths and already long-path-protected paths
            # because UNC paths must no have the long-path prefix.
            path = normalized_path(path)
        else:
            path = Path(f"\\\\?\\{normalized_path(path)}")
    return path


def safe_rename(src: Path, dst: Path, /) -> None:
    """
    Safely rename files on Windows.

    Note: this function cannot be decorated with lru_cache().

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


@lru_cache(maxsize=16)
def find_resource(folder: str, /, *, file: str = "") -> Path:
    """Find the FS path of a directory in various OS binary packages."""
    return normalized_path(Options.res_dir) / folder / file


@lru_cache(maxsize=16)
def find_icon(icon: str, /) -> Path:
    return find_resource("icons", file=icon)


@lru_cache(maxsize=4096, typed=True)
def force_decode(string: Union[bytes, str], /) -> str:
    if isinstance(string, bytes):
        string = string.decode("utf-8")
    return string


@lru_cache(maxsize=4096, typed=True)
def force_encode(data: Union[bytes, str]) -> bytes:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return data


@lru_cache(maxsize=4)
def retrieve_ssl_certificate(hostname: str, /, *, port: int = 443) -> str:
    """Retrieve the SSL certificate from a given hostname."""

    import ssl

    with ssl.create_connection((hostname, port)) as conn:  # type: ignore
        with ssl.SSLContext().wrap_socket(conn, server_hostname=hostname) as sock:
            cert_data: bytes = sock.getpeercert(binary_form=True)  # type: ignore
            return ssl.DER_cert_to_PEM_cert(cert_data)


def client_certificate() -> Optional[Tuple[str, str]]:
    """
    Fetch the paths to the certification file and it's key from the option.
    Return None if one of them is missing.
    """
    client_certificate = (Options.cert_file, Options.cert_key_file)
    if not all(client_certificate):
        return None
    return client_certificate


@lru_cache(maxsize=4)
def get_certificate_details(
    *, hostname: str = "", cert_data: str = ""
) -> Dict[str, Any]:
    """
    Get SSL certificate details from a given certificate content or hostname.

    Note: This function uses a undocumented method of the _ssl module.
          It is continuously tested in our CI to ensure it still
          available after any Python upgrade.
          Certified working as of Python 3.8.6.
    """

    import ssl

    defaults = deepcopy(DEFAULTS_CERT_DETAILS)
    cert_file = Path("c.crt")

    try:
        certificate = cert_data or retrieve_ssl_certificate(hostname)
        cert_file.write_text(certificate, encoding="utf-8")
        try:
            # Taken from https://stackoverflow.com/a/50072461/1117028
            # pylint: disable=protected-access
            details = ssl._ssl._test_decode_cert(cert_file)  # type: ignore
            defaults.update(details)
        finally:
            cert_file.unlink()
    except Exception:
        log.warning("Error while retrieving the SSL certificate", exc_info=True)

    return defaults


def _cryptor(key: bytes, iv: bytes) -> "Cipher":
    """Instantiate a new AES (de|en)cryptor."""
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    return Cipher(algorithms.AES(key), mode=modes.CFB8(iv))


def encrypt(plaintext: Union[bytes, str], key: Union[bytes, str]) -> bytes:
    """Chiper *plaintext* using AES with the given *key*."""
    import base64

    plaintext = force_encode(plaintext)
    key = _pad_secret(force_encode(key))
    iv = os.urandom(16)
    encryptor = _cryptor(key, iv).encryptor()  # type: ignore
    return base64.b64encode(iv + encryptor.update(plaintext) + encryptor.finalize())


def decrypt(secure_data: Union[bytes, str], key: Union[bytes, str]) -> Optional[bytes]:
    """Dechiper AES *secure_data* with the given *key*."""
    import base64

    try:
        key = _pad_secret(force_encode(key))
        data = base64.b64decode(force_encode(secure_data))
        iv = data[:16]
        ciphertext = data[16:]
        decryptor = _cryptor(key, iv).decryptor()  # type: ignore
        res: bytes = decryptor.update(ciphertext) + decryptor.finalize()
        return res
    except Exception:
        return None


def _pad_secret(key: bytes) -> bytes:
    """Pad secret for AES block size (32 bits)."""
    length = len(key)
    if length == 32:
        return key
    size = 32 - length
    if length > 32:
        return key[:size]
    return key + bytes([size]) * size


@lru_cache(maxsize=4)
def simplify_url(url: str, /) -> str:
    """Simplify port if possible and trim trailing slashes."""

    parts = urlsplit(url)
    new_parts = [parts.scheme, parts.netloc, parts.path, parts.query, parts.fragment]

    if parts.scheme == "http" and parts.netloc.endswith(":80"):
        new_parts[1] = parts.netloc[:-3]
    elif parts.scheme == "https" and parts.netloc.endswith(":443"):
        new_parts[1] = parts.netloc[:-4]

    return urlunsplit(new_parts).rstrip("/")


@lru_cache(maxsize=16)
def parse_protocol_url(url_string: str, /) -> Optional[Dict[str, str]]:
    """
    Parse URL for which Drive is registered as a protocol handler.

    Return None if `url_string` is not a supported URL pattern or raise a
    ValueError is the URL structure is invalid.
    """

    if not url_string.startswith("nxdrive://"):
        return None

    if url_string == "nxdrive://trigger-watch":
        log.warning(
            f"Outdated FinderSync extension is running. Skipping {url_string!r}."
        )
        return None

    # Commands that need a path to work with
    path_cmds = ("access-online", "copy-share-link", "direct-transfer", "edit-metadata")

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
        #     - Direct Transfer
        # And event from macOS to sync the document status (FinderSync)
        r"nxdrive://(?P<cmd>({}))/(?P<path>.*)".format("|".join(path_cmds)),
        # Event to acquire the login token from the server
        (
            r"nxdrive://(?P<cmd>token)/"
            fr"(?P<token>{DOC_UID_REG})/"
            r"user/(?P<username>.*)"
        ),
        # Event to continue the OAuth2 login flow
        # authorize?code=EAhJq9aZau&state=uuIwrlQy810Ra49DhDIaH2tXDYYowA
        # authorize/?code=EAhJq9aZau&state=uuIwrlQy810Ra49DhDIaH2tXDYYowA
        r"nxdrive://(?P<cmd>authorize)/?\?(?P<query>.+)",
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
        return {
            "command": cmd,
            "token": parsed_url["token"],
            "username": parsed_url["username"],
        }
    elif cmd == "authorize":
        # Details are passed as URL params (?param=value&param2=value2),
        # let's convert to a simple dict
        full_query = urlparse(parsed_url["query"]).path
        query = dict(parse_qsl(full_query))
        return {"command": cmd, **query}
    return {"command": cmd, "filepath": parsed_url["path"]}


def parse_edit_protocol(
    parsed_url: Dict[str, str], url_string: str, /
) -> Dict[str, str]:
    """
    Parse a `nxdrive://edit` URL for quick editing of Nuxeo documents.

    Note: no need to decorate the function with lru_cache() as the caller
    already is.
    """

    scheme = parsed_url["scheme"]
    if scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid command {url_string}: scheme should be http or https"
        )

    server_url = f"{scheme}://{parsed_url.get('server')}"

    return {
        "command": "download_edit",
        "server_url": server_url,
        "user": parsed_url["username"],
        "repo": parsed_url["repo"],
        "doc_id": parsed_url["docid"],
        "filename": parsed_url["filename"],
        "download_url": parsed_url["download"],
    }


def set_path_readonly(path: Path, /) -> None:
    if path.is_dir():
        # Need to add
        right = stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IRUSR
    else:
        # Already in read only
        right = stat.S_IRGRP | stat.S_IRUSR

    if path.stat().st_mode & ~right != 0:
        path.chmod(right)


def unset_path_readonly(path: Path, /) -> None:
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


def unlock_path(path: Path, /, *, unlock_parent: bool = True) -> int:
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


def lock_path(path: Path, locker: int, /) -> None:
    if locker == 0:
        return

    if locker & 1 == 1:
        set_path_readonly(path)

    if locker & 2 == 2:
        set_path_readonly(path.parent)


@lru_cache(maxsize=4096)
def sizeof_fmt(num: Union[float, int], /, *, suffix: str = "B") -> str:
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


@lru_cache(maxsize=32, typed=True)
def short_name(name: Union[bytes, str], /) -> str:
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
    """This class handle the pid lock file"""

    def __init__(self, folder: Path, key: str, /) -> None:
        self.key = key
        self.locked = False
        self.pid_filepath = safe_long_path(folder / f"nxdrive_{key}.pid")

    def unlock(self) -> None:
        if not self.locked:
            return

        # Clean pid file
        try:
            self.pid_filepath.unlink(missing_ok=True)
        except OSError:
            log.warning(
                f"Failed to remove stalled PID file: {self.pid_filepath!r} "
                f"for stopped process {os.getpid()}",
                exc_info=True,
            )

    def check_running(self) -> Optional[int]:
        """Check whether another sync process is already running

        If the lock file already exists and the pid points to a running
        nxdrive program then return the pid. Return None otherwise.
        """
        if self.pid_filepath.is_file():
            try:
                pid: Optional[int] = int(
                    self.pid_filepath.read_text(encoding="utf-8").strip()
                )
            except ValueError:
                log.warning("The PID file has invalid data", exc_info=True)
                pid = None
            else:
                from contextlib import suppress

                import psutil

                with suppress(ValueError, psutil.NoSuchProcess):
                    # If process has been created after the lock file.
                    # Changed from getctime() to getmtime() because of Windows
                    # file system tunneling.
                    if (
                        psutil.Process(pid).create_time()
                        > self.pid_filepath.stat().st_mtime
                    ):
                        raise ValueError()

                    return pid

            # This is a pid file that is empty or pointing to either a
            # stopped process or a non-nxdrive process: let's delete it if
            # possible
            try:
                self.pid_filepath.unlink(missing_ok=True)
            except OSError:
                if pid is not None:
                    msg = (
                        f"Failed to remove stalled PID file: {self.pid_filepath!r} "
                        f"for stopped process {pid}"
                    )
                    log.warning(msg, exc_info=True)
                    return pid

                msg = f"Failed to remove empty stalled PID file {self.pid_filepath!r}"
                log.warning(msg, exc_info=True)
            else:
                if pid is None:
                    msg = f"Removed old empty PID file {self.pid_filepath!r}"
                else:
                    msg = f"Removed old PID file {self.pid_filepath!r} for stopped process {pid}"
                log.info(msg)

        self.locked = True
        return None

    def lock(self) -> Optional[int]:
        pid = self.check_running()
        if pid is not None:
            log.warning(f"{self.key} process with PID {pid} already running")
            return pid

        # Write the pid of this process
        pid = os.getpid()
        if not isinstance(pid, int):
            raise RuntimeError(f"Invalid PID: {pid!r}")

        self.pid_filepath.write_text(str(pid), encoding="utf-8")
        return None


def compute_digest(
    path: Path, digest_func: str, /, *, callback: Callable = None
) -> str:
    """Lazy computation of the digest.

    Note: this function must not be decorated with lru_cache().
    """
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

    return str(h.hexdigest())


def digest_status(digest: str) -> DigestStatus:
    """Determine the given *digest* status. It will be use to know when a document can be synced."""
    if not digest:
        return DigestStatus.REMOTE_HASH_EMPTY

    # Likely a crafted digest to tell us it will be computed async (NXDRIVE-2140)
    if "-" in digest:
        return DigestStatus.REMOTE_HASH_ASYNC

    # The digest seems good
    if get_digest_algorithm(digest):
        return DigestStatus.OK

    # The digest will not be locally computable (likely a Live Connect document)
    return DigestStatus.REMOTE_HASH_EXOTIC


def config_paths() -> Tuple[Tuple[Path, ...], Path]:
    """Return the list of possible local configuration paths and the default one."""
    conf_name = "config.ini"
    paths = (
        Path(sys.executable).parent / conf_name,
        Path(Options.nxdrive_home) / conf_name,
        Path(conf_name),
    )
    return paths, paths[1]


def get_config_path() -> Path:
    """Return the configuration file path."""
    paths, default_path = config_paths()
    res = [conf_file for conf_file in paths if conf_file.is_file()]
    return res[0] if res else default_path


def save_config(config_dump: Dict[str, Any], /) -> Path:
    """Update the configuration file with passed config dump."""
    conf_path = get_config_path()
    config = ConfigParser()

    #  Check if config file already exist, if not then use nxdrive home folder
    if not conf_path.is_file():
        # Craft a new config file
        config["DEFAULT"] = {"env": "features"}  # Set saved section as DEFAULT env
        config["features"] = config_dump
    else:
        # Update the config file
        config.read(conf_path)
        if "DEFAULT" not in config or "env" not in config["DEFAULT"]:
            # Missing DEFAULT section or env
            config["DEFAULT"] = {"env": "features"}
        section = config["DEFAULT"]["env"]
        if section not in config:
            # Saved section doesn't already exist
            config[section] = config_dump
        else:
            # Update existing section with config dump datas
            for key, value in config_dump.items():
                config[section][key] = str(value)

    # Save back the modified config file and return its path
    with open(conf_path, "w") as output:
        config.write(output)
    return conf_path


def test_url(
    url: str,
    /,
    *,
    login_page: str = Options.startup_page,
    proxy: "Proxy" = None,
    timeout: int = 5,
) -> str:
    """Try to request the login page to see if the URL is valid."""
    import requests
    from requests.exceptions import SSLError
    from urllib3.util.url import parse_url

    kwargs: Dict[str, Any] = {
        "timeout": timeout,
        "verify": Options.ca_bundle or not Options.ssl_no_verify,
        "cert": client_certificate(),
        "headers": {"User-Agent": user_agent()},
    }
    try:
        parse_url(url)
        log.debug(f"Testing URL {url!r}")
        full_url = f"{url}/{login_page}"
        if proxy:
            kwargs["proxies"] = proxy.settings(url=full_url)
        with requests.get(full_url, **kwargs) as resp:
            resp.raise_for_status()
            if resp.status_code == 200:  # Happens when JSF is installed
                log.debug(f"Valid URL: {url}")
                return ""
    except SSLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" in str(exc):
            raise InvalidSSLCertificate()
        elif "CERTIFICATE_REQUIRED" in str(exc):
            raise MissingClientSSLCertificate()
        elif "password is required" in str(exc):
            raise EncryptedSSLCertificateKey()

    except requests.HTTPError as exc:
        if exc.response.status_code in (401, 403):
            # When there is only Web-UI installed, the code is 401.
            log.debug(f"Valid URL: {url}")
            return ""
    return "CONNECTION_ERROR"


def today_is_special() -> bool:
    """This beautiful day is special, isn't it? As all other days, right? :)"""
    return (
        os.getenv("I_LOVE_XMAS", "0") == "1"
        or int(datetime.utcnow().strftime("%j")) >= 354
    )


def get_current_locale() -> str:
    """Detect and return the OS default language."""

    # Guess the encoding
    if MAC:
        # Always UTF-8 on macOS
        encoding = "UTF-8"
    else:
        import locale

        encoding = locale.getdefaultlocale()[1] or ""

    # Guess the current locale name
    if WINDOWS:
        import ctypes

        l10n_code = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        l10n = locale.windows_locale[l10n_code]
    elif MAC:
        from CoreServices import NSLocale

        l10n_code = NSLocale.currentLocale()
        l10n = NSLocale.localeIdentifier(l10n_code)
    else:
        l10n = locale.getdefaultlocale()[0] or ""

    return ".".join([l10n, encoding])
