# coding: utf-8
import os
import re
from math import pow
from unittest.mock import patch

import pytest

import nxdrive.utils


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


def test_encrypt_decrypt():
    enc = nxdrive.utils.encrypt
    dec = nxdrive.utils.decrypt

    pwd = b"Administrator"
    token = b"12345678-acbd-1234-cdef-1234567890ab"
    cipher = enc(pwd, token)

    assert dec(cipher, token) == pwd


@pytest.mark.parametrize(
    "name, state",
    [
        # Normal
        ("README", (False, None)),
        # Any temporary file
        ("Book1.bak", (True, False)),
        ("pptED23.tmp", (True, False)),
        ("9ABCDEF0.tep", (False, None)),
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


def test_get_arch():
    import struct

    with patch.object(struct, "calcsize", return_value=12):
        assert nxdrive.utils.get_arch() == f"{12 * 8}-bit"

    # Clear the LRU cache to revert previous cached value
    nxdrive.utils.get_arch.cache_clear()

    assert nxdrive.utils.get_arch() in ("32-bit", "64-bit")


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


def test_get_current_os():
    ver = nxdrive.utils.get_current_os()
    assert isinstance(ver, tuple)
    assert ver
    assert isinstance(ver[0], str)
    assert isinstance(ver[1], str)


def test_get_current_os_full():
    ver = nxdrive.utils.get_current_os_full()
    assert isinstance(ver, tuple)
    assert ver


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
        ("epsilon\nalpha\ndelta\nbeta", ("alpha", "beta", "delta", "epsilon")),
    ],
)
def test_get_value(raw_value, expected_value):
    assert nxdrive.utils.get_value(raw_value) == expected_value


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org/",
        "http://example.org//",
        "http://example.org",
        "http://example.org:8080",
        "http://example.org:8080//nuxeo",
        "http://example.org:8080/nuxeo/",
        "https://example.org",
        "https://example.org:8080",
        "https://example.org:8080/nuxeo",
        "https://example.org:8080/nuxeo/",
        "https://example.org:8080/nuxeo?param=value",
        "https://example.org:8080/////nuxeo////submarine//",
        "http://example.org/\n:8080/nuxeo",
        "http://example.org/\t:8080/nuxeo",
        """http://example.org/
        :8080/nuxeo""",
    ],
)
def test_compute_urls(url):
    no_whitespace = re.compile(r"\s+")

    for generated_url in nxdrive.utils.compute_urls(url):
        # There should be only one "//" in each URL
        assert generated_url.count("//") == 1

        # There should be no whitespace
        assert not no_whitespace.findall(generated_url)


@pytest.mark.parametrize(
    "url, result",
    [
        ("localhost", "http://localhost:8080/nuxeo"),
        # HTTPS domain
        (
            "intranet-prerod.nuxeocloud.com",
            "https://intranet-preprod.nuxeocloud.com/nuxeo",
        ),
        # With additional parameters
        (
            "http://localhost:8080/nuxeo?TenantId=0xdeadbeaf",
            "http://localhost:8080/nuxeo?TenantId=0xdeadbeaf",
        ),
        # Incomplete URL
        ("http://localhost", "http://localhost:8080/nuxeo"),
        # Bad IP
        ("1.2.3.4", ""),
        # Bad protocol
        ("htto://localhost:8080/nuxeo", "http://localhost:8080/nuxeo"),
    ],
)
def test_guess_server_url(url, result):
    func = nxdrive.utils.guess_server_url
    if "intranet" in url:
        # The intranet is not stable enough to rely on it.
        # So we give a try and skip on error.
        try:
            assert func(url) == result
        except AssertionError as exc:
            pytest.skip(f"Intranet not stable ({exc})")
    else:
        assert func(url) == result


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


@pytest.mark.parametrize(
    "size, result",
    [
        (0, "0.0 o"),
        (1, "1.0 o"),
        (-1024, "-1.0 Kio"),
        (1024, "1.0 Kio"),
        (1024 * 1024, "1.0 Mio"),
        (pow(1024, 2), "1.0 Mio"),
        (pow(1024, 3), "1.0 Gio"),
        (pow(1024, 4), "1.0 Tio"),
        (pow(1024, 5), "1.0 Pio"),
        (pow(1024, 6), "1.0 Eio"),
        (pow(1024, 7), "1.0 Zio"),
        (pow(1024, 8), "1.0 Yio"),
        (pow(1024, 9), "1024.0 Yio"),
        (pow(1024, 10), "1048576.0 Yio"),
        (168_963_795_964, "157.4 Gio"),
    ],
)
def test_sizeof_fmt(size, result):
    assert nxdrive.utils.sizeof_fmt(size) == result


def test_sizeof_fmt_arg():
    assert nxdrive.utils.sizeof_fmt(168_963_795_964, suffix="B") == "157.4 GiB"


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
    force_decode = nxdrive.utils.force_decode

    filename = os.path.sep.join(data)

    name = short_name(filename)
    if too_long:
        assert "…" in name
        assert len(name) < 72
    else:
        assert name == force_decode(filename)


@pytest.mark.parametrize(
    "x, y",
    [
        ("7.10", "10.1-SNAPSHOT"),
        ("10.1-SNAPSHOT", "10.1"),
        ("10.1", "10.2-SNAPSHOT"),
        ("10.1", "10.1-HF1"),
        ("10.1-SNAPSHOT", "10.1-HF1"),
    ],
)
def test_version_lt(x, y):
    assert nxdrive.utils.version_lt(x, y)


@pytest.mark.parametrize(
    "x, y, result",
    [
        # Releases
        ("5.9.2", "5.9.3", -1),
        ("5.9.3", "5.9.3", 0),
        ("5.9.3", "5.9.2", 1),
        ("5.9.3", "5.8", 1),
        ("5.8", "5.6.0", 1),
        ("5.9.1", "5.9.0.1", 1),
        ("6.0", "5.9.3", 1),
        ("5.10", "5.1.2", 1),
        # Snapshots
        ("5.9.3-SNAPSHOT", "5.9.4-SNAPSHOT", -1),
        ("5.8-SNAPSHOT", "5.9.4-SNAPSHOT", -1),
        ("5.9.4-SNAPSHOT", "5.9.4-SNAPSHOT", 0),
        ("5.9.4-SNAPSHOT", "5.9.3-SNAPSHOT", 1),
        ("5.9.4-SNAPSHOT", "5.8-SNAPSHOT", 1),
        # Releases and snapshots
        ("5.9.4-SNAPSHOT", "5.9.4", -1),
        ("5.9.4-SNAPSHOT", "5.9.5", -1),
        ("5.9.3", "5.9.4-SNAPSHOT", -1),
        ("5.9.4-SNAPSHOT", "5.9.3", 1),
        ("5.9.4", "5.9.4-SNAPSHOT", 1),
        ("5.9.5", "5.9.4-SNAPSHOT", 1),
        # Hotfixes
        ("5.6.0-H35", "5.8.0-HF14", -1),
        ("5.8.0-HF14", "5.8.0-HF15", -1),
        ("5.8.0-HF14", "5.8.0-HF14", 0),
        ("5.8.0-HF14", "5.8.0-HF13", 1),
        ("5.8.0-HF14", "5.6.0-HF35", 1),
        # Releases and hotfixes
        ("5.8.0-HF14", "5.9.1", -1),
        ("5.6", "5.8.0-HF14", -1),
        ("5.8", "5.8.0-HF14", -1),
        ("5.8.0-HF14", "5.6", 1),
        ("5.8.0-HF14", "5.8", 1),
        ("5.9.1", "5.8.0-HF14", 1),
        # Snaphsots and hotfixes
        ("5.8.0-HF14", "5.9.1-SNAPSHOT", -1),
        ("5.7.1-SNAPSHOT", "5.8.0-HF14", -1),
        ("5.8.0-SNAPSHOT", "5.8.0-HF14", -1),
        ("5.8-SNAPSHOT", "5.8.0-HF14", -1),
        ("5.8.0-HF14", "5.7.1-SNAPSHOT", 1),
        ("5.8.0-HF14", "5.8.0-SNAPSHOT", 1),
        ("5.8.0-HF14", "5.8-SNAPSHOT", 1),
        ("5.9.1-SNAPSHOT", "5.8.0-HF14", 1),
        # Snapshot hotfixes
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF15-SNAPSHOT", -1),
        ("5.6.0-H35-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", 0),
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF13-SNAPSHOT", 1),
        ("5.8.0-HF14-SNAPSHOT", "5.6.0-HF35-SNAPSHOT", 1),
        # Releases and snapshot hotfixes
        ("5.8.0-HF14-SNAPSHOT", "5.9.1", -1),
        ("5.6", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.6", 1),
        ("5.8.0-HF14-SNAPSHOT", "5.8", 1),
        ("5.9.1", "5.8.0-HF14-SNAPSHOT", 1),
        # Snaphsots and snapshot hotfixes
        ("5.8.0-HF14-SNAPSHOT", "5.9.1-SNAPSHOT", -1),
        ("5.7.1-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8.0-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.7.1-SNAPSHOT", 1),
        ("5.8.0-HF14-SNAPSHOT", "5.8-SNAPSHOT", 1),
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-SNAPSHOT", 1),
        ("5.9.1-SNAPSHOT", "5.8.0-HF14-SNAPSHOT", 1),
        # Hotfixes and snapshot hotfixes
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF14", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF15", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.10.0-HF01", -1),
        ("5.8.0-HF14-SNAPSHOT", "5.6.0-HF35", 1),
        ("5.8.0-HF14-SNAPSHOT", "5.8.0-HF13", 1),
    ],
)
def test_version_compare(x, y, result):
    assert nxdrive.utils.version_compare(x, y) == result


@pytest.mark.parametrize(
    "x, y, result",
    [
        ("0.1", "1.0", -1),
        ("2.0.0626", "2.0.806", -1),
        ("2.0.0805", "2.0.806", -1),
        ("2.0.805", "2.0.1206", -1),
        ("1.0", "1.0", 0),
        ("1.3.0424", "1.3.0424", 0),
        ("1.3.0524", "1.3.0424", 1),
        ("1.4", "1.3.0524", 1),
        ("1.4.0622", "1.3.0524", 1),
        ("1.10", "1.1.2", 1),
        ("2.1.0528", "1.10", 1),
        ("2.0.0905", "2.0.806", 1),
        # Semantic versioning
        ("2.0.805", "2.4.0", -1),
        ("2.1.1130", "2.4.0b1", -1),
        ("2.4.0b1", "2.4.0b2", -1),
        ("2.4.2b1", "2.4.2", -1),
        ("2.4.0b1", "2.4.0b1", 0),
        ("2.4.0b10", "2.4.0b1", 1),
        # Compare to None
        (None, "8.10-HF37", -1),
        (None, "2.0.805", -1),
        (None, None, 0),
        ("8.10-HF37", None, 1),
        ("2.0.805", None, 1),
        # Date based versions are treated as normal versions
        ("10.3-I20180803_0125", "10.1", 1),
        ("10.2-I20180703_0125", "10.3-I20180803_0125", -1),
        ("10.3-I20180803_0125", "10.3-I20180803_0125", 0),
        # Alpha
        ("4.0.0", "4.0.0.32", -1),
        ("4.0.0.1", "4.0.0.32", -1),
        ("4.0.0.32", "4.0.0.32", 0),
        ("4.0.0.42", "4.0.0.32", 1),
    ],
)
def test_version_compare_client(x, y, result):
    assert nxdrive.utils.version_compare_client(x, y) == result
