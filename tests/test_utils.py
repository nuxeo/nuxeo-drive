# coding: utf-8
import os


import pytest

import nxdrive.utils


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
    "url, result",
    [
        ("localhost", "http://localhost:8080/nuxeo"),
        # HTTPS domain
        ("intranet.nuxeo.com", "https://intranet.nuxeo.com/nuxeo"),
        # With additional parameters
        (
            "https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf",
            "https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf",
        ),
        # Incomplete URL
        ("https://intranet.nuxeo.com", "https://intranet.nuxeo.com/nuxeo"),
        # Bad IP
        ("1.2.3.4", None),
        # Bad protocol
        ("htto://intranet.nuxeo.com/nuxeo", None),
    ],
)
def test_guess_server_url(url, result):
    assert nxdrive.utils.guess_server_url(url) == result


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
    ],
)
def test_version_compare_client(x, y, result):
    assert nxdrive.utils.version_compare_client(x, y) == result
