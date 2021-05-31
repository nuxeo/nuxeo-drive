import configparser
import os
from collections import namedtuple
from datetime import datetime
from math import pow
from pathlib import Path, _posix_flavour, _windows_flavour
from time import sleep
from unittest.mock import patch

import pytest

import nxdrive.utils
from nxdrive.constants import APP_NAME, WINDOWS, DigestStatus
from nxdrive.options import Options

from ..markers import not_windows, windows_only

BAD_HOSTNAMES = [
    "expired.badssl.com",
    "wrong.host.badssl.com",
    "self-signed.badssl.com",
    "untrusted-root.badssl.com",
    "revoked.badssl.com",
    "pinning-test.badssl.com",
    "no-common-name.badssl.com",
    "no-subject.badssl.com",
    "incomplete-chain.badssl.com",
    "sha1-intermediate.badssl.com",
    "client-cert-missing.badssl.com",
    "invalid-expected-sct.badssl.com",
]

Stat = namedtuple("Stat", "st_size")


class MockedPath(Path):
    """Simple way to test Path methods.
    Using mock did not make it.
    """

    _flavour = _windows_flavour if WINDOWS else _posix_flavour

    def resolve(self, *_, **__):
        """Raise a PermissionError."""
        raise PermissionError("Boom!")


@pytest.mark.parametrize(
    "size, digest_func, result",
    [
        (0, "md5", "d41d8cd98f00b204e9800998ecf8427e"),  # 0b
        (1, "md5", "cfcd208495d565ef66e7dff9f98764da"),
        (10, "md5", "f1b708bba17f1ce948dc979f4d7092bc"),
        (100, "md5", "c88a1ec806fc879d1dcc0a666a8d7e36"),
        (1000, "md5", "88bb69a5d5e02ec7af5f68d82feb1f1d"),
        (1_000_000, "md5", "2f54d66538c094bf229e89ed0667b6fd"),  # 1Mb
        (50_000_000, "md5", "863f3ed728e4ef9afa7de307f09f1bd1"),  # 50Mb
    ],
)
def test_compute_digest(tmp, size, digest_func, result):
    func = nxdrive.utils.compute_digest

    folder = tmp()
    folder.mkdir()

    file = folder / f"{size}.bin"
    file.touch()
    file.write_bytes(b"0" * size)

    assert func(file, digest_func) == result


def test_compute_digest_with_callback(tmp):
    from nxdrive.constants import FILE_BUFFER_SIZE

    folder = tmp()
    folder.mkdir()

    file = folder / "file.bin"
    file.touch()
    file.write_bytes(b"0" * 4 * FILE_BUFFER_SIZE)

    def callback(*_):
        nonlocal called
        called += 1

    called = 0
    nxdrive.utils.compute_digest(file, "md5", callback=callback)
    assert called == 5


def test_compute_digest_unknown():
    from nxdrive.exceptions import UnknownDigest

    with pytest.raises(UnknownDigest):
        nxdrive.utils.compute_digest("no_file", "unknown_digest_func")


def test_compute_digest_error(tmp):
    from nxdrive.constants import UNACCESSIBLE_HASH

    folder = tmp()
    folder.mkdir()

    digest = nxdrive.utils.compute_digest(folder / "ghost file.secret", "md5")
    assert digest == UNACCESSIBLE_HASH


@pytest.mark.parametrize(
    "path, pid",
    [
        ("/Users/Bob/Documents/Sans%20titre-1.psd", 1_868_982_964),
        (b"/Users/Bob/Documents/Sans%20titre-1.psd", 1_868_982_964),
        ("C:\\Users\\Alice\\tests\\test.psd", 3_523_690_320),
        (r"C:\Users\Alice\tests\test.psd", 3_523_690_320),
        (br"C:\Users\Alice\tests\test.psd", 3_523_690_320),
        ("", 0),
        (b"", 0),
    ],
)
def test_compute_fake_pid_from_path(path, pid):
    func = nxdrive.utils.compute_fake_pid_from_path
    assert func(path) == pid


def test_current_thread_id():
    thread_id = nxdrive.utils.current_thread_id()
    assert isinstance(thread_id, int)
    assert thread_id > 0


@pytest.mark.parametrize(
    "digest, expected_status",
    [
        ("", DigestStatus.REMOTE_HASH_EMPTY),
        ("0" * 32, DigestStatus.OK),
        ("0" * 32 + "-0", DigestStatus.REMOTE_HASH_ASYNC),
        ('"MTYxMTIyODA1ODUzNA"', DigestStatus.REMOTE_HASH_EXOTIC),
        ("z" * 32, DigestStatus.REMOTE_HASH_EXOTIC),
    ],
)
def test_digest_status(digest, expected_status):
    assert nxdrive.utils.digest_status(digest) is expected_status


@pytest.mark.parametrize(
    "key",
    [
        "12345678-acbd-1234-cdef-1234567890ab",
        "12345678-acbd-1234-cdef-1234567890ab",
        "12345678-acbd-1234-cdef-12345678",  # 32
        "12345678-acbd-1234-cdef-123456",
        "12345678-acbd-1234-cdefg",  # 24
        "12345678-acbd-12",  # 16
        "",
    ],
)
def test_encrypt_decrypt(key):
    enc = nxdrive.utils.encrypt
    dec = nxdrive.utils.decrypt
    secret_data = b"Administrator"
    secure_data = enc(secret_data, key)
    assert dec(secure_data, key) == secret_data


def test_decrypt():
    """Ensure the old way of encrypting data works with the new one (NXDRIVE-2617)."""
    # secure_data was generated using PyCryptodomex
    secure_data = b"g3PB1AN9bKZmeeZEa3A3vqLBgXNa6eEUdKjdumU="
    key = b"12345678-acbd-1234-cdef-1234567890ab"
    secret_data = nxdrive.utils.decrypt(secure_data, key)
    assert secret_data == b"Administrator"


@windows_only(reason="Unix has no drive concept")
def test_find_suitable_tmp_dir_different_drive(tmp):
    sync_folder = tmp()
    home_folder = sync_folder / ".nuxeo-drive"
    home_folder.mkdir(parents=True)

    # Change the drive letter
    home_folder._drv = chr(ord(home_folder.drive[:-1]) + 1)

    func = nxdrive.utils.find_suitable_tmp_dir
    assert func(sync_folder, home_folder) == sync_folder.parent / home_folder.name


@windows_only(reason="Unix has no drive concept")
def test_find_suitable_tmp_dir_different_drive_using_the_root(tmp):
    home_folder = tmp() / ".nuxeo-drive"
    home_folder.mkdir(parents=True)

    # Change the drive letter
    drive = chr(ord(home_folder.drive[:-1]) + 1)
    sync_folder = Path(f"{drive}:")

    with pytest.raises(ValueError):
        func = nxdrive.utils.find_suitable_tmp_dir
        func(sync_folder, home_folder)


@not_windows(reason="Windows has no st_dev")
@patch("pathlib.Path.stat")
def test_find_suitable_tmp_dir_different_partition(mocked_stat, tmp):
    class Stat:
        """Return a different st_dev each call."""

        count = 0
        st_mode = 0o7777

        @property
        def st_dev(self):
            self.count += 1
            return self.count

    func = nxdrive.utils.find_suitable_tmp_dir
    sync_folder = tmp()
    home_folder = sync_folder / ".nuxeo-drive"
    home_folder.mkdir(parents=True)
    mocked_stat.return_value = Stat()
    assert func(sync_folder, home_folder) == sync_folder.parent / home_folder.name


@not_windows(reason="Windows has no st_dev")
def test_find_suitable_tmp_dir_different_partition_using_the_root(tmp):
    home_folder = tmp() / ".nuxeo-drive"
    home_folder.mkdir(parents=True)
    sync_folder = Path("/")

    with pytest.raises(ValueError):
        func = nxdrive.utils.find_suitable_tmp_dir
        func(sync_folder, home_folder)


def test_find_suitable_tmp_dir_same_partition(tmp):
    func = nxdrive.utils.find_suitable_tmp_dir
    sync_folder = tmp()
    home_folder = sync_folder / "home"
    home_folder.mkdir(parents=True)
    assert func(sync_folder, home_folder) == home_folder


def test_find_suitable_tmp_dir_inexistant(tmp):
    func = nxdrive.utils.find_suitable_tmp_dir
    sync_folder = tmp()
    home_folder = tmp()
    home_folder.mkdir(parents=True)
    assert func(sync_folder, home_folder) == home_folder


@pytest.mark.parametrize(
    "name, state",
    [
        # Normal
        ("README", (False, None)),
        # Any temporary file
        ("Book1.bak", (True, False)),
        ("pptED23.tmp", (True, False)),
        ("9ABCDEF0.tep", (False, None)),
        # Emacs auto save file
        ("#9ABCDEF0.tep#", (True, False)),
        # AutoCAD
        ("atmp9716", (True, False)),
        ("7151_CART.dwl", (True, False)),
        ("7151_CART.dwl2", (True, False)),
        ("7151_CART.dwg", (False, None)),
        # Microsoft Office
        ("A239FDCA", (True, True)),
        ("A2Z9FDCA", (False, None)),
        ("A239FDZA", (False, None)),
        ("A2D9FDCA1", (False, None)),
        ("~A2D9FDCA1.tm", (False, None)),
    ],
)
def test_generated_tempory_file(name, state):
    assert nxdrive.utils.is_generated_tmp_file(name) == state


def test_get_certificate_details_from_file():
    cert_data = """
-----BEGIN CERTIFICATE-----
MIIG8DCCBdigAwIBAgIQD0AZ0ebFLvmjqSm21WE4FjANBgkqhkiG9w0BAQsFADBk
MQswCQYDVQQGEwJOTDEWMBQGA1UECBMNTm9vcmQtSG9sbGFuZDESMBAGA1UEBxMJ
QW1zdGVyZGFtMQ8wDQYDVQQKEwZURVJFTkExGDAWBgNVBAMTD1RFUkVOQSBTU0wg
Q0EgMzAeFw0xODA3MjAwMDAwMDBaFw0yMDA3MjQxMjAwMDBaMIGZMQswCQYDVQQG
EwJGUjEWMBQGA1UECBMNSWxlLWRlLUZyYW5jZTEaMBgGA1UEBxMRU2FpbnQgRGVu
aXMgQ2VkZXgxHDAaBgNVBAoME1VuaXZlcnNpdMOpIFBhcmlzIDgxGTAXBgNVBAsT
EERTSSBQb2xlIFdFQi1FTlQxHTAbBgNVBAMTFG51eGVvLnVuaXYtcGFyaXM4LmZy
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAosA++LzWOIa8cSaH2Cmk
C4nir+Vmv2XQuMVp8AollXJKeiWTeulttfYU2txC7qDsjpXsSqfkvDQbCfUB25Ty
Y3ze9eh8pXzK5qwYFXIeDZIlVTquEZAA/F5bRnZ6HsaTBI0Gjq/BXiOlykvExVdP
1JK1E7j8pkUD4hygyhKPx95IVgQS5EgXWuCJnHJs/T6VRfYFaOix4yfJG9MOgb4D
3pkWh13WOcwJUQ1M5469e2JweW7jZsW6Oe1cfBR1VgvlRD7fSJDRwCj7MRqOfK5k
LC9so8o+9zUXHcWLk6WuBiKxX4xtr1waqViJxfn2/BUedg0J0juzoE87fZR52hJI
TwIDAQABo4IDZjCCA2IwHwYDVR0jBBgwFoAUZ/2IIBQnmMcJ0iUZu+lREWN1UGIw
HQYDVR0OBBYEFN4UHBjiYDWj5091Qd/fgITrtwGgMDYGA1UdEQQvMC2CFG51eGVv
LnVuaXYtcGFyaXM4LmZyghVtb29kbGUudW5pdi1wYXJpczguZnIwDgYDVR0PAQH/
BAQDAgWgMB0GA1UdJQQWMBQGCCsGAQUFBwMBBggrBgEFBQcDAjBrBgNVHR8EZDBi
MC+gLaArhilodHRwOi8vY3JsMy5kaWdpY2VydC5jb20vVEVSRU5BU1NMQ0EzLmNy
bDAvoC2gK4YpaHR0cDovL2NybDQuZGlnaWNlcnQuY29tL1RFUkVOQVNTTENBMy5j
cmwwTAYDVR0gBEUwQzA3BglghkgBhv1sAQEwKjAoBggrBgEFBQcCARYcaHR0cHM6
Ly93d3cuZGlnaWNlcnQuY29tL0NQUzAIBgZngQwBAgIwbgYIKwYBBQUHAQEEYjBg
MCQGCCsGAQUFBzABhhhodHRwOi8vb2NzcC5kaWdpY2VydC5jb20wOAYIKwYBBQUH
MAKGLGh0dHA6Ly9jYWNlcnRzLmRpZ2ljZXJ0LmNvbS9URVJFTkFTU0xDQTMuY3J0
MAwGA1UdEwEB/wQCMAAwggF+BgorBgEEAdZ5AgQCBIIBbgSCAWoBaAB2AKS5CZC0
GFgUh7sTosxncAo8NZgE+RvfuON3zQ7IDdwQAAABZLh+KWMAAAQDAEcwRQIgPrGk
CO4wULGkZOaipluKHKgVX231md0r65CLxvgKGHoCIQD2oxZfAb7XDqTK9jgs42fo
UQra7C3P9QFjRncCwk3LrQB2AId1v+dZfPiMQ5lfvfNu/1aNR1Y2/0q1YMG06v9e
oIMPAAABZLh+KjQAAAQDAEcwRQIgSrjUujzDVEnVdxenp1ucQpJH6ofa4t+jVfYB
mmDjf6ICIQCsv+Gg67zSdNqcGCPSgLfI88bgYNDK0eZK55uk01E40wB2ALvZ37wf
inG1k5Qjl6qSe0c4V5UKq1LoGpCWZDaOHtGFAAABZLh+KYgAAAQDAEcwRQIgE0Fa
/7qoHixhfjjIN2ZsU8Y0AZFAkOuS0cGGGkKp9xkCIQDIGYAdx5qAdTBOFIL5NAr6
Y7TIycq4avd3Fu1E86HpFTANBgkqhkiG9w0BAQsFAAOCAQEAllmQTDhGDhN8d/uX
E7oOkZknAogXttMXkksDjB7rN0BATV1ufWDbjShGQuoIYmtQYVddf77p5kNk48vT
BuM90iblou8PbFEdTIqLTHLs/+Df8a6wTEFDma3icvNKqeZWfylNLJUErtWILaWN
LBkdHkz68Cr7lhTW91XEbDGK9/IYu6YdWqoAS4bXks/vKJOEaQr2NN+QNDjzR9wG
sIOkgLQ2Kt4lWCaF7xEaOP2e/if3Ebm0alNx1lwUxn00LEm1VyKBlepV+XmsDivB
JROlHjdA3/jyqD4WuFzzXzWwF6zta0l/hqF9BtGmQRR9qXC2+fsQ4mhUK8C9vhCH
7fV0vw==
-----END CERTIFICATE-----
"""
    cert_details_expected = {
        "subject": (
            (("countryName", "FR"),),
            (("stateOrProvinceName", "Ile-de-France"),),
            (("localityName", "Saint Denis Cedex"),),
            (("organizationName", "Université Paris 8"),),
            (("organizationalUnitName", "DSI Pole WEB-ENT"),),
            (("commonName", "nuxeo.univ-paris8.fr"),),
        ),
        "issuer": (
            (("countryName", "NL"),),
            (("stateOrProvinceName", "Noord-Holland"),),
            (("localityName", "Amsterdam"),),
            (("organizationName", "TERENA"),),
            (("commonName", "TERENA SSL CA 3"),),
        ),
        "version": 3,
        "serialNumber": "0F4019D1E6C52EF9A3A929B6D5613816",
        "notBefore": "Jul 20 00:00:00 2018 GMT",
        "notAfter": "Jul 24 12:00:00 2020 GMT",
        "subjectAltName": (
            ("DNS", "nuxeo.univ-paris8.fr"),
            ("DNS", "moodle.univ-paris8.fr"),
        ),
        "OCSP": ("http://ocsp.digicert.com",),
        "caIssuers": ("http://cacerts.digicert.com/TERENASSLCA3.crt",),
        "crlDistributionPoints": (
            "http://crl3.digicert.com/TERENASSLCA3.crl",
            "http://crl4.digicert.com/TERENASSLCA3.crl",
        ),
    }
    cert_details = nxdrive.utils.get_certificate_details(cert_data=cert_data)
    assert cert_details == cert_details_expected


@pytest.mark.parametrize("hostname", BAD_HOSTNAMES)
def test_get_certificate_details_from_hostname(hostname):
    cert_details = nxdrive.utils.get_certificate_details(hostname=hostname)
    for key in {
        "caIssuers",
        "issuer",
        "notAfter",
        "notBefore",
        "serialNumber",
        "subject",
    }:
        assert key in cert_details


def test_get_certificate_details_error():
    cert_details = nxdrive.utils.get_certificate_details(cert_data="qsd351qds")
    assert cert_details == nxdrive.utils.DEFAULTS_CERT_DETAILS


def test_current_milli_time():
    func = nxdrive.utils.current_milli_time

    milli = func()
    assert isinstance(milli, int)

    # Second call must return a higher value
    sleep(2)
    assert milli < func()


def test_find_icon():
    """It will also test find_resource()."""
    assert isinstance(nxdrive.utils.find_icon("boom"), Path)


def test_get_date_from_sqlite():
    func = nxdrive.utils.get_date_from_sqlite

    # No date
    assert func(None) is None
    assert func("") is None

    # Bad date
    assert func("2019-08-02") is None

    # Good date
    assert func("2019-08-02 10:56:57") == datetime(2019, 8, 2, 10, 56, 57)


def test_get_default_local_folder():
    if WINDOWS:
        path = os.path.expandvars("C:\\Users\\%username%\\Documents")
        good_folder = Path(path) / APP_NAME
    else:
        good_folder = Path.home() / APP_NAME

    folder = nxdrive.utils.get_default_local_folder()
    assert isinstance(folder, Path)

    if good_folder.is_dir():
        # Use startswith() in case the already is an old folder, in that case
        # we will get an incremented folder
        assert str(folder).startswith(str(good_folder))
    else:
        assert folder == good_folder


def test_get_timestamp_from_date():
    # No date provided
    assert nxdrive.utils.get_timestamp_from_date(0) == 0
    assert nxdrive.utils.get_timestamp_from_date(None) == 0

    dtime = datetime(2019, 6, 20)
    assert nxdrive.utils.get_timestamp_from_date(dtime) == 1_560_988_800


def test_get_tree_list():
    location = nxdrive.utils.normalized_path(__file__).parent.parent
    path = location / "resources"
    tree = list(nxdrive.utils.get_tree_list(path))

    # Check we got all paths
    expected_paths = [path] + sorted(path.glob("**/*"))
    guessed_paths = sorted(p for p, *_ in tree)
    assert guessed_paths == expected_paths


def test_get_tree_list_root_is_in_ignored_patterns(fs):
    # "fs" is the reference to the fake file system
    fs.create_file("/.fake/folder/sub-folder/fichier.txt")

    assert not list(nxdrive.utils.get_tree_list(Path("/.fake")))


def test_get_tree_list_avoid_symlinks(fs):
    # "fs" is the reference to the fake file system
    fs.create_file("/folder/fichier.txt")  # 1
    fs.create_symlink(
        "/folder/fichier-sym.txt",
        "/folder/fichier.txt",
    )
    fs.create_dir("/folder/sub-folder")  # 2
    fs.create_file("/folder/sub-folder/file.txt")  # 3
    fs.create_symlink(
        "/folder/sub-folder-sym",
        "/folder/sub-folder",
    )
    assert len(list(nxdrive.utils.get_tree_list(Path("/folder")))) == 4  # 3 + root
    assert not list(nxdrive.utils.get_tree_list(Path("/folder/sub-folder-sym")))


def test_get_tree_list_ignored_patterns(fs):
    # "fs" is the reference to the fake file system
    fs.create_file("/fake/.azerty.txt")
    fs.create_file("/fake/Icon\r")
    fs.create_file("/fake/.hidden folder/sub-folder/fichier.txt")

    tree = list(nxdrive.utils.get_tree_list(Path("/fake")))
    expected = [(Path("/fake"), 0)]
    assert tree == expected


@patch("pathlib.Path.is_dir")
def test_get_tree_list_dir_raise_os_error(mock_path):
    mock_path.side_effect = OSError("Mock'ed OSError")
    tree = list(nxdrive.utils.get_tree_list(Path("/fake")))
    # We exit before the first yield because of OSError
    assert not tree


@patch("pyfakefs.fake_scandir.DirEntry.is_dir")
def test_get_tree_list_subdir_raise_os_error(mock_is_dir, fs):
    # "fs" is the reference to the fake file system
    fs.create_file("/fake/folder1/sub-folder/file.txt")
    fs.create_file("/fake/folder2/sub-folder/file.txt")

    n = 0

    def is_dir():
        nonlocal n
        n += 1

        if n == 1:  # /fake/folder1
            raise OSError("Mock'ed OSError")
        elif n == 2:  # /fake/folder2
            raise PermissionError("Mock'ed PermissionError")
        return True

    mock_is_dir.side_effect = is_dir

    tree = list(nxdrive.utils.get_tree_list(Path("/fake")))
    expected = [(Path("/fake"), 0)]
    assert tree == expected


@Options.mock()
def test_if_frozen_decorator():
    @nxdrive.utils.if_frozen
    def check():
        nonlocal checkpoint
        checkpoint = True
        return True

    checkpoint = False

    # The app is not frozen in tests, so the call must return False
    assert not check()
    assert not checkpoint

    Options.is_frozen = True
    assert check()
    assert checkpoint


def test_normalize_and_expand_path():
    if WINDOWS:
        path = "%userprofile%/foo"
        home = os.path.expandvars("C:\\Users\\%username%")
    else:
        path = "$HOME/foo"
        home = str(Path.home())
    expected = Path(f"{home}/foo")
    assert nxdrive.utils.normalize_and_expand_path(path) == expected


def test_normalize_event_filename(tmp):
    func = nxdrive.utils.normalize_event_filename

    folder = tmp()
    folder.mkdir()

    file = folder / "file.txt"
    file.touch()

    # File that needs normalization
    file_to_normalize = str(folder / "file \u0061\u0301.txt")
    file_normalized = folder / "file \xe1.txt"

    # File that needs to be stripped
    file_ending_with_space = folder / "file2.txt "
    file_ending_with_space.touch()
    file_ending_with_space_stripped = folder / "file2.txt"

    assert func(file, action=False) == file

    # The file ending with a space is renamed
    assert func(file_ending_with_space) == file_ending_with_space_stripped
    if not WINDOWS:
        # Sadly, on Windows, checking for "file2.txt " or "file2.txt     " is the
        # same as checking for "file2.txt". So we need to skip this check.
        assert not file_ending_with_space.is_file()
    assert file_ending_with_space_stripped.is_file()

    # Check the file is normalized
    assert func(file_to_normalize) == file_normalized


@pytest.mark.parametrize("hostname", BAD_HOSTNAMES)
def test_retrieve_ssl_certificate_unknown(hostname):
    from ssl import SSLError

    func = nxdrive.utils.get_certificate_details
    assert func(hostname=hostname)

    with pytest.raises(SSLError):
        nxdrive.utils.retrieve_ssl_certificate(hostname, port=80)


@pytest.mark.parametrize(
    "raw_value, expected_value",
    [
        ("true", True),
        ("TRUE", True),
        ("1", True),
        ("on", True),
        ("yes", True),
        ("oui", True),
        ("false", False),
        ("FALSE", False),
        ("0", False),
        ("off", False),
        ("no", False),
        ("non", False),
        ("nope", "nope"),
        ("epsilon\nalpha\ndelta\nbeta", ("alpha", "beta", "delta", "epsilon")),
    ],
)
def test_get_value(raw_value, expected_value):
    assert nxdrive.utils.get_value(raw_value) == expected_value


def test_increment_local_folder(tmp):
    func = nxdrive.utils.increment_local_folder
    basefolder = tmp()
    name = "folder"

    # There is no existing folder
    assert func(basefolder, name) == basefolder / "folder"

    # Create the folder, and check the next call returns an incremented folder name
    (basefolder / "folder").mkdir(parents=True)
    assert func(basefolder, name) == basefolder / "folder 2"

    # Loop on folder creation for 100 iterations to check we always get an incremented folder name.
    # Before NXDRIVE-1723, after 41 iterations it was returning ".", the current folder (bad).
    for n in range(2, 101):
        assert func(basefolder, name) == basefolder / f"folder {n}"
        (basefolder / f"folder {n}").mkdir()

    # Remove 1 folder in the middle of all and check we get it back when calling the function
    (basefolder / "folder 69").rmdir()
    assert func(basefolder, name) == basefolder / "folder 69"


@pytest.mark.parametrize("cmd", ["access-online", "copy-share-link", "edit-metadata"])
def test_parse_protocol_url_cmd(cmd):
    """Parse context menu commands."""
    url = f"nxdrive://{cmd}/00000000-0000-0000-0000/On%20call%20Schedule.docx"
    info = nxdrive.utils.parse_protocol_url(url)
    assert info == {
        "command": cmd,
        "filepath": "00000000-0000-0000-0000/On%20call%20Schedule.docx",
    }


def test_parse_protocol_url_cmd_unknown():
    """Parse an unknown command, it must fail."""
    with pytest.raises(ValueError):
        url = "nxdrive://unknown/00000000-0000-0000-0000/On%20call%20Schedule.docx"
        nxdrive.utils.parse_protocol_url(url)


def test_parse_protocol_url_cmd_outdated():
    """Parse an outdated command, it must not fail."""
    url = "nxdrive://trigger-watch"
    assert not nxdrive.utils.parse_protocol_url(url)


def test_parse_protocol_url_edit():
    """It will also test parse_edit_protocol()."""
    url = (
        "nxdrive://edit"
        "/http/server.cloud.nuxeo.com:8080/nuxeo"
        "/user/Administrator"
        "/repo/default"
        "/nxdocid/00000000-0000-0000-0000"
        "/filename/On%20call%20Schedule.docx"
        "/downloadUrl/nxfile/default/00000000-0000-0000-0000"
        "/file:content/On%20call%20Schedule.docx"
    )
    info = nxdrive.utils.parse_protocol_url(url)
    assert info == {
        "command": "download_edit",
        "user": "Administrator",
        "server_url": "http://server.cloud.nuxeo.com:8080/nuxeo",
        "repo": "default",
        "doc_id": "00000000-0000-0000-0000",
        "filename": "On%20call%20Schedule.docx",
        "download_url": "nxfile/default/00000000-0000-0000-0000/file:content/On%20call%20Schedule.docx",
    }


def test_parse_protocol_url_edit_missing_download_url():
    """The download part must be in the URL."""
    with pytest.raises(ValueError):
        url = (
            "nxdrive://edit"
            "/http/server.cloud.nuxeo.com:8080/nuxeo"
            "/user/Administrator"
            "/repo/default"
            "/nxdocid/00000000-0000-0000-0000"
            "/filename/On%20call%20Schedule.docx"
        )
        nxdrive.utils.parse_protocol_url(url)


def test_parse_protocol_url_edit_missing_username():
    """The username must be in the URL."""
    with pytest.raises(ValueError):
        url = (
            "nxdrive://edit/https/server.cloud.nuxeo.com/nuxeo"
            "/repo/default"
            "/nxdocid/00000000-0000-0000-0000"
            "/filename/lebron-james-beats-by-dre-powerb.psd"
            "/downloadUrl/nxfile/default/00000000-0000-0000-0000"
            "/file:content/lebron-james-beats-by-dre-powerb.psd"
        )
        nxdrive.utils.parse_protocol_url(url)


def test_parse_protocol_url_oauth2_token():
    """Simple token parsing."""
    url = "nxdrive://authorize/?code=EAhJq9aZau&state=uuIwrlQy810Ra49DhDIaH2tXDYYowA"
    info = nxdrive.utils.parse_protocol_url(url)
    assert isinstance(info, dict)
    assert info == {
        "command": "authorize",
        "code": "EAhJq9aZau",
        "state": "uuIwrlQy810Ra49DhDIaH2tXDYYowA",
    }


def test_parse_protocol_url_oauth2_token_error():
    url = (
        "nxdrive://authorize?error=access_denied&error_description=MSIS9605%3a+The+client+is+not+allowed+to+access"
        "+the+requested+resource.&state=pRe1JitkAPJAXqR6WuQjbT944lCv9G&client-request-id=80f15800-e242-4022-fe39-"
        "0080000000ed"
    )
    info = nxdrive.utils.parse_protocol_url(url)
    assert isinstance(info, dict)
    assert info == {
        "command": "authorize",
        "error": "access_denied",
        "error_description": "MSIS9605: The client is not allowed to access the requested resource.",
        "state": "pRe1JitkAPJAXqR6WuQjbT944lCv9G",
        "client-request-id": "80f15800-e242-4022-fe39-0080000000ed",
    }


def test_parse_protocol_url_token():
    """Simple token parsing."""
    url = "nxdrive://token/12345678-acbd-1234-cdef-1234567890ab/user/Administrator@127.0.0.1"
    info = nxdrive.utils.parse_protocol_url(url)
    assert isinstance(info, dict)
    assert info == {
        "command": "token",
        "token": "12345678-acbd-1234-cdef-1234567890ab",
        "username": "Administrator@127.0.0.1",
    }


def test_parse_protocol_url_bad_http_scheme():
    """Bad HTTP scheme."""
    with pytest.raises(ValueError):
        url = (
            "nxdrive://edit"
            "/htto/server.cloud.nuxeo.com:8080/nuxeo"
            "/user/Administrator"
            "/repo/default"
            "/nxdocid/00000000-0000-0000-0000"
            "/filename/On%20call%20Schedule.docx"
            "/downloadUrl/nxfile/default/00000000-0000-0000-0000"
            "/file:content/On%20call%20Schedule.docx"
        )
        nxdrive.utils.parse_protocol_url(url)


@windows_only
@pytest.mark.parametrize(
    "path, result",
    [
        (Path("C:\\Users\\Alice"), False),
        (Path("C:/Users/Alice"), False),
        (Path("\\\\?\\C:\\Users\\Alice"), False),
        (Path("//?/C:/Users/Alice"), False),
        (Path("\\\\Shared\\Alice"), True),
        (Path("//Shared/Alice"), True),
        (Path("//?/UNC/Shared/Alice"), True),
    ],
)
def test_path_is_unc_name(path, result):
    assert nxdrive.utils.path_is_unc_name(path) is result


@not_windows(reason="Non-Windows test.")
def test_path_is_unc_name_unix():
    assert not nxdrive.utils.path_is_unc_name(Path.home())


@pytest.mark.parametrize(
    "url, result",
    [
        # HTTP
        ("http://example.org", "http://example.org"),
        ("http://example.org/", "http://example.org"),
        ("http://example.org:80", "http://example.org"),
        ("http://example.org:80/", "http://example.org"),
        ("http://example.org:8080", "http://example.org:8080"),
        ("http://example.org:8080/", "http://example.org:8080"),
        # HTTPS
        ("https://example.org", "https://example.org"),
        ("https://example.org/", "https://example.org"),
        ("https://example.org:443", "https://example.org"),
        ("https://example.org:443/", "https://example.org"),
        ("https://example.org:4433", "https://example.org:4433"),
        ("https://example.org:4433/", "https://example.org:4433"),
    ],
)
def test_simplify_url(url, result):
    assert nxdrive.utils.simplify_url(url) == result


@pytest.mark.parametrize(
    "invalid, valid",
    [
        ('a/b\\c*d:e<f>g?h"i|j.doc', "a-b-c-d-e-f-g-h-i-j.doc"),
        ("/*@?<>", "--@---"),
        ("/*?<>", "-----"),
        ("/ * @ ? < >", "- - @ - - -"),
        ("/ * ? < >", "- - - - -"),
        ("/*  ?<>", "--  ---"),
    ],
)
def test_safe_filename(invalid, valid):
    assert nxdrive.utils.safe_filename(invalid) == valid


def test_safe_filename_ending_with_space():
    invalid = "<a>zerty.odt "
    valid = nxdrive.utils.safe_filename(invalid)
    if WINDOWS:
        assert valid == "-a-zerty.odt"
    else:
        assert valid == "-a-zerty.odt "


def test_safe_rename(tmp):
    folder = tmp()
    folder.mkdir()

    src = folder / "abcde.txt"
    dst = folder / "fghij.txt"

    src.write_bytes(b"qwerty")
    dst.write_bytes(b"asdfgh")

    if WINDOWS:
        with pytest.raises(FileExistsError):
            src.rename(dst)

    nxdrive.utils.safe_rename(src, dst)

    assert not src.exists()
    assert dst.exists()
    assert dst.read_bytes() == b"qwerty"


@pytest.mark.parametrize(
    "size, result",
    [
        (0, "0.0 B"),
        (1, "1.0 B"),
        (-1024, "-1.0 KiB"),
        (1024, "1.0 KiB"),
        (1024 * 1024, "1.0 MiB"),
        (pow(1024, 2), "1.0 MiB"),
        (pow(1024, 3), "1.0 GiB"),
        (pow(1024, 4), "1.0 TiB"),
        (pow(1024, 5), "1.0 PiB"),
        (pow(1024, 6), "1.0 EiB"),
        (pow(1024, 7), "1.0 ZiB"),
        (pow(1024, 8), "1.0 YiB"),
        (pow(1024, 9), "1,024.0 YiB"),
        (pow(1024, 10), "1,048,576.0 YiB"),
        (168_963_795_964, "157.4 GiB"),
    ],
)
def test_sizeof_fmt(size, result):
    assert nxdrive.utils.sizeof_fmt(size) == result


def test_sizeof_fmt_arg():
    assert nxdrive.utils.sizeof_fmt(168_963_795_964, suffix="o") == "157.4 Gio"


@pytest.mark.parametrize(
    "data, too_long",
    [
        (["A" * 12, "b" * 321, "C" * 22], True),
        (["A" * 12, "b" * 13, "ç" * 20, "à" * 71], True),
        (["A" * 10, "b" * 10, "ç" * 10, "à" * 10], False),
    ],
)
def test_short_name(data, too_long):
    short_name = nxdrive.utils.short_name
    filename = os.path.sep.join(data)

    name = short_name(filename)
    if too_long:
        assert "…" in name
        assert len(name) < 72
    else:
        force_decode = nxdrive.utils.force_decode
        assert name == force_decode(filename)


@Options.mock()
@pytest.mark.parametrize(
    "default_config, config_dump",
    [
        (
            {},
            {
                "feature_direct_edit": True,
                "feature_auto_update": False,
                "feature_s3": False,
                "feature_direct_transfer": False,
            },
        ),
        (
            {"DEFAULT": {"env": "DEBUG"}},
            {
                "feature_direct_edit": True,
                "feature_auto_update": False,
                "feature_s3": False,
                "feature_direct_transfer": False,
            },
        ),
        (
            {
                "DEFAULT": {"env": "DEBUG"},
                "DEBUG": {
                    "feature_direct_edit": False,
                    "feature_auto_update": False,
                    "feature_s3": False,
                    "feature_direct_transfer": False,
                    "feature_plop": True,
                },
            },
            {
                "feature_direct_edit": True,
                "feature_auto_update": True,
                "feature_s3": True,
                "feature_direct_transfer": True,
            },
        ),
        (
            {
                "features": {
                    "feature_direct_edit": False,
                    "feature_auto_update": True,
                    "feature_s3": True,
                    "feature_direct_transfer": True,
                    "feature_plop": True,
                }
            },
            {
                "feature_direct_edit": True,
                "feature_auto_update": False,
                "feature_s3": False,
                "feature_direct_transfer": False,
            },
        ),
    ],
)
def test_save_config(default_config, config_dump, tmp_path):
    conf_name = "config.ini"
    Options.nxdrive_home = tmp_path
    if default_config:
        # Write default_config content in a new config file
        config_writer = configparser.ConfigParser()
        for key, value in default_config.items():
            config_writer[key] = value
        with open(Options.nxdrive_home / conf_name, "w") as test_file:
            config_writer.write(test_file)

    conf_path = nxdrive.utils.save_config(config_dump)
    # Verify that a config file exist
    assert conf_path == Options.nxdrive_home / conf_name
    assert conf_path.is_file()

    # Read the content of the config file after call to save_config()
    config = configparser.ConfigParser()
    config.read(conf_path)
    if default_config:
        if "DEFAULT" in default_config and "env" in default_config["DEFAULT"]:
            # If a DEFAULT section existed in default_config then check that it has not been altered
            assert config["DEFAULT"]["env"] == default_config["DEFAULT"]["env"]
            env = config["DEFAULT"]["env"]
        else:
            env = "features"
        if env in default_config:
            # The section is already defined in the default_config
            for key, value in default_config[env].items():
                if key in default_config[env] and key not in config_dump:
                    # If a key exist in the default_config but not in the dump then check that has not been altered
                    assert config[env].getboolean(key) == default_config[env][key]

    if "DEFAULT" not in default_config:
        # A DEFAULT section was not present in the default config, check that it has been created by save_config()
        env = "features"
        assert config["DEFAULT"]["env"] == env
    for key, value in config[env].items():
        if key in config_dump:
            # Check that everything declared in config_dump has been written to config file by save_config()
            assert config[env].getboolean(key) == config_dump[key]


def test_url_bad_ssl():
    from nxdrive.exceptions import InvalidSSLCertificate

    with pytest.raises(InvalidSSLCertificate):
        nxdrive.utils.test_url(f"https://{BAD_HOSTNAMES[2]}/nuxeo")
