# coding: utf-8
import hashlib
import sys

import pytest

import nxdrive.utils
from nxdrive.manager import ProxySettings


def test_encrypt_decrypt():
    enc = nxdrive.utils.encrypt
    dec = nxdrive.utils.decrypt

    pwd = 'Administrator'
    token = '12345678-acbd-1234-cdef-1234567890ab'
    cipher = enc(pwd, token)

    assert dec(cipher, token) == pwd


def test_proxy_settings():
    proxy = ProxySettings()
    proxy.from_url('localhost:3128')
    assert not proxy.username
    assert not proxy.password
    assert proxy.authenticated == False
    assert proxy.server == 'localhost'
    assert proxy.port == 3128
    assert not proxy.proxy_type
    assert proxy.to_url() == 'localhost:3128'
    assert proxy.to_url(False) == 'localhost:3128'

    proxy.from_url('user@localhost:3128')
    assert proxy.username == 'user'
    assert not proxy.password
    assert not proxy.authenticated
    assert proxy.server == 'localhost'
    assert proxy.port == 3128
    assert not proxy.proxy_type
    assert proxy.to_url() == 'localhost:3128'
    assert proxy.to_url(False) == 'localhost:3128'

    proxy.from_url('user:password@localhost:3128')
    assert proxy.username == 'user'
    assert proxy.password == 'password'
    assert proxy.authenticated
    assert proxy.server == 'localhost'
    assert proxy.port == 3128
    assert not proxy.proxy_type
    assert proxy.to_url() == 'user:password@localhost:3128'
    assert proxy.to_url(False) == 'localhost:3128'

    proxy.from_url('http://user:password@localhost:3128')
    assert proxy.username == 'user'
    assert proxy.password == 'password'
    assert proxy.authenticated
    assert proxy.server == 'localhost'
    assert proxy.port == 3128
    assert proxy.proxy_type == 'http'
    assert proxy.to_url() == 'http://user:password@localhost:3128'
    assert proxy.to_url(False) == 'http://localhost:3128'

    proxy.from_url('https://user:password@localhost:3129')
    assert proxy.username == 'user'
    assert proxy.password == 'password'
    assert proxy.authenticated
    assert proxy.server == 'localhost'
    assert proxy.port == 3129
    assert proxy.proxy_type == 'https'
    assert proxy.to_url() == 'https://user:password@localhost:3129'
    assert proxy.to_url(False) == 'https://localhost:3129'


def test_generated_tempory_file():
    func = nxdrive.utils.is_generated_tmp_file

    # Normal
    assert func('README') == (False, None)

    # Any temporary file
    assert func('Book1.bak') == (True, False)
    assert func('pptED23.tmp') == (True, False)
    assert func('9ABCDEF0.tep') == (False, None)

    # AutoCAD
    assert func('atmp9716') == (True, False)
    assert func('7151_CART.dwl') == (True, False)
    assert func('7151_CART.dwl2') == (True, False)
    assert func('7151_CART.dwg') == (False, None)

    # Microsoft Office
    assert func('A239FDCA') == (True, True)
    assert func('A2Z9FDCA') == (False, None)
    assert func('A239FDZA') == (False, None)
    assert func('A2D9FDCA1') == (False, None)
    assert func('~A2D9FDCA1.tm') == (False, None)


def test_guess_mime_type():
    func = nxdrive.utils.guess_mime_type
    
    # Text
    assert func('text.txt') == 'text/plain'
    assert func('text.html') == 'text/html'
    assert func('text.css') == 'text/css'
    assert func('text.csv') == 'text/csv'
    assert func('text.js') == 'application/javascript'

    # Image
    assert func('picture.jpg') == 'image/jpeg'
    assert func('picture.png') == 'image/png'
    assert func('picture.gif') == 'image/gif'
    assert func('picture.bmp') in ('image/x-ms-bmp', 'image/bmp')
    assert func('picture.tiff') == 'image/tiff'
    assert func('picture.ico') in ('image/x-icon', 'image/vnd.microsoft.icon')

    # Audio
    assert func('sound.mp3') == 'audio/mpeg'
    assert func('sound.wma') in ('audio/x-ms-wma', 'application/octet-stream')
    assert func('sound.wav') in ('audio/x-wav', 'audio/wav')

    # Video
    assert func('video.mpeg') == 'video/mpeg'
    assert func('video.mp4') == 'video/mp4'
    assert func('video.mov') == 'video/quicktime'
    assert func('video.wmv') in ('video/x-ms-wmv', 'application/octet-stream')
    assert func('video.avi') in ('video/x-msvideo', 'video/avi')

    # Office
    assert func('office.doc') ==  'application/msword'
    assert func('office.xls') == 'application/vnd.ms-excel'
    assert func('office.ppt') == 'application/vnd.ms-powerpoint'

    # PDF
    assert func('document.pdf') == 'application/pdf'

    # Unknown
    assert func('file.unknown') == 'application/octet-stream'
    assert func('file.rvt') == 'application/octet-stream'

    # Cases badly handled by Windows
    # See https://jira.nuxeo.com/browse/NXP-11660
    # and http://bugs.python.org/issue15207
    if sys.platform == "win32":
        # Text
        assert func('text.xml') == 'text/xml'

        # Image
        assert func('picture.svg') in ('image/svg+xml', 'application/octet-stream')

        # Video
        assert func('video.flv') == 'application/octet-stream'

        # Office
        assert func('office.docx') in (
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'application/octet-stream')
        assert func('office.xlsx') in (
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/octet-stream')
        assert func('office.pptx') in (
            'application/vnd.openxmlformats-officedocument.presentationml.presentation',
            'application/x-mspowerpoint.12',
            'application/octet-stream')

        assert func('office.odt') in (
            'application/vnd.oasis.opendocument.text',
            'application/octet-stream')
        assert func('office.ods') in (
            'application/vnd.oasis.opendocument.spreadsheet',
            'application/octet-stream')
        assert func('office.odp') in  (
            'application/vnd.oasis.opendocument.presentation',
            'application/octet-stream')
    else:
        # Text
        assert func('text.xml') == 'application/xml'

        # Image
        assert func('picture.svg') == 'image/svg+xml'

        # Video
        assert func('video.flv') == 'video/x-flv'

        # Office
        assert func('office.docx') == 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        assert func('office.xlsx') == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        assert func('office.pptx') == 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

        assert func('office.odt') == 'application/vnd.oasis.opendocument.text'
        assert func('office.ods') == 'application/vnd.oasis.opendocument.spreadsheet'
        assert func('office.odp') == 'application/vnd.oasis.opendocument.presentation'


def test_guess_digest_algorithm():  # TODO: Remove when using the Python client
    func = nxdrive.utils.guess_digest_algorithm
    
    md5_digest = hashlib.md5('joe').hexdigest()
    assert func(md5_digest) == 'md5'

    sha1_digest = hashlib.sha1('joe').hexdigest()
    assert func(sha1_digest) == 'sha1'


def test_guess_server_url():
    func = nxdrive.utils.guess_server_url
    
    domain = 'localhost'
    good_url = 'http://localhost:8080/nuxeo'
    assert func(domain) == good_url

    # HTTPS domain
    domain = 'intranet.nuxeo.com'
    good_url = 'https://intranet.nuxeo.com/nuxeo'
    assert func(domain) == good_url

    # With additional parameters
    domain = 'https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf'
    good_url = domain
    assert func(domain) == good_url

    # Incomplete URL
    domain = 'https://intranet.nuxeo.com'
    good_url = 'https://intranet.nuxeo.com/nuxeo'
    assert func(domain) == good_url

    # Bad IP
    domain = '1.2.3.4'
    good_url = None
    assert func(domain) == good_url

    # Bad protocal
    domain = 'htto://intranet.nuxeo.com/nuxeo'
    good_url = None
    assert func(domain) == good_url


def test_simplify_url():
    func = nxdrive.utils.simplify_url

    # HTTP
    assert func('http://example.org') == 'http://example.org'
    assert func('http://example.org/') == 'http://example.org'
    assert func('http://example.org:80') == 'http://example.org'
    assert func('http://example.org:80/') == 'http://example.org'
    assert func('http://example.org:8080') == 'http://example.org:8080'
    assert func('http://example.org:8080/') == 'http://example.org:8080'

    # HTTPS
    assert func('https://example.org') == 'https://example.org'
    assert func('https://example.org/') == 'https://example.org'
    assert func('https://example.org:443') == 'https://example.org'
    assert func('https://example.org:443/') == 'https://example.org'
    assert func('https://example.org:4433') == 'https://example.org:4433'
    assert func('https://example.org:4433/') == 'https://example.org:4433'


@pytest.mark.parametrize('x, y, z', [
    ('7.10', '10.1-SNAPSHOT', '10.1-HF10'),
    ('10.1-SNAPSHOT', '10.1', '999.999.999'),
    ('10.1-SNAPSHOT', '10.1-SNAPSHOT', '999.999.999'),
    ('10.1-SNAPSHOT', '10.1-SNAPSHOT', '10.1-SNAPSHOT'),
    ('10.1-HF1', '10.1-HF1', '10.1-HF1'),
])
def test_version_between(x, y, z):
    assert nxdrive.utils.version_between(x, y, z)


@pytest.mark.parametrize('x, y, result', [
    # Releases
    ('5.9.2', '5.9.3', -1),
    ('5.9.3', '5.9.3', 0),
    ('5.9.3', '5.9.2', 1),
    ('5.9.3', '5.8', 1),
    ('5.8', '5.6.0', 1),
    ('5.9.1', '5.9.0.1', 1),
    ('6.0', '5.9.3', 1),
    ('5.10', '5.1.2', 1),

    # Snapshots
    ('5.9.3-SNAPSHOT', '5.9.4-SNAPSHOT', -1),
    ('5.8-SNAPSHOT', '5.9.4-SNAPSHOT', -1),
    ('5.9.4-SNAPSHOT', '5.9.4-SNAPSHOT', 0),
    ('5.9.4-SNAPSHOT', '5.9.3-SNAPSHOT', 1),
    ('5.9.4-SNAPSHOT', '5.8-SNAPSHOT', 1),

    # Releases and snapshots
    ('5.9.4-SNAPSHOT', '5.9.4', -1),
    ('5.9.4-SNAPSHOT', '5.9.5', -1),
    ('5.9.3', '5.9.4-SNAPSHOT', -1),
    ('5.9.4-SNAPSHOT', '5.9.3', 1),
    ('5.9.4', '5.9.4-SNAPSHOT', 1),
    ('5.9.5', '5.9.4-SNAPSHOT', 1),

    # Hotfixes
    ('5.6.0-H35', '5.8.0-HF14', -1),
    ('5.8.0-HF14', '5.8.0-HF15', -1),
    ('5.8.0-HF14', '5.8.0-HF14', 0),
    ('5.8.0-HF14', '5.8.0-HF13', 1),
    ('5.8.0-HF14', '5.6.0-HF35', 1),

    # Releases and hotfixes
    ('5.8.0-HF14', '5.9.1', -1),
    ('5.6', '5.8.0-HF14', -1),
    ('5.8', '5.8.0-HF14', -1),
    ('5.8.0-HF14', '5.6', 1),
    ('5.8.0-HF14', '5.8', 1),
    ('5.9.1', '5.8.0-HF14', 1),

    # Snaphsots and hotfixes
    ('5.8.0-HF14', '5.9.1-SNAPSHOT', -1),
    ('5.7.1-SNAPSHOT', '5.8.0-HF14', -1),
    ('5.8.0-SNAPSHOT', '5.8.0-HF14', -1),
    ('5.8-SNAPSHOT', '5.8.0-HF14', -1),
    ('5.8.0-HF14', '5.7.1-SNAPSHOT', 1),
    ('5.8.0-HF14', '5.8.0-SNAPSHOT', 1),
    ('5.8.0-HF14', '5.8-SNAPSHOT', 1),
    ('5.9.1-SNAPSHOT', '5.8.0-HF14', 1),

    # Snapshot hotfixes
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF15-SNAPSHOT', -1),
    ('5.6.0-H35-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', 0),
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF13-SNAPSHOT', 1),
    ('5.8.0-HF14-SNAPSHOT', '5.6.0-HF35-SNAPSHOT', 1),

    # Releases and snapshot hotfixes
    ('5.8.0-HF14-SNAPSHOT', '5.9.1', -1),
    ('5.6', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.6', 1),
    ('5.8.0-HF14-SNAPSHOT', '5.8', 1),
    ('5.9.1', '5.8.0-HF14-SNAPSHOT', 1),

    # Snaphsots and snapshot hotfixes
    ('5.8.0-HF14-SNAPSHOT', '5.9.1-SNAPSHOT', -1),
    ('5.7.1-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8.0-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.7.1-SNAPSHOT', 1),
    ('5.8.0-HF14-SNAPSHOT', '5.8-SNAPSHOT', 1),
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-SNAPSHOT', 1),
    ('5.9.1-SNAPSHOT', '5.8.0-HF14-SNAPSHOT', 1),

    # Hotfixes and snapshot hotfixes
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF14', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF15', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.10.0-HF01', -1),
    ('5.8.0-HF14-SNAPSHOT', '5.6.0-HF35', 1),
    ('5.8.0-HF14-SNAPSHOT', '5.8.0-HF13', 1),
])
def test_version_compare(x, y, result):
    assert nxdrive.utils.version_compare(x, y) == result


@pytest.mark.parametrize('x, y, result', [
    ('0.1', '1.0', -1),
    ('2.0.0626', '2.0.806', -1),
    ('2.0.0805', '2.0.806', -1),
    ('2.0.805', '2.0.1206', -1),
    ('1.0', '1.0', 0),
    ('1.3.0424', '1.3.0424', 0),
    ('1.3.0524', '1.3.0424', 1),
    ('1.4', '1.3.0524', 1),
    ('1.4.0622', '1.3.0524', 1),
    ('1.10', '1.1.2', 1),
    ('2.1.0528', '1.10', 1),
    ('2.0.0905', '2.0.806', 1),

    # Semantic versioning
    ('2.0.805', '2.4.0', -1),
    ('2.1.1130', '2.4.0b1', -1),
    ('2.4.0b1', '2.4.0b2', -1),
    ('2.4.2b1', '2.4.2', -1),
    ('2.4.0b1', '2.4.0b1', 0),
    ('2.4.0b10', '2.4.0b1', 1),

    # Compare to None
    (None, '8.10-HF37', -1),
    (None, '2.0.805', -1),
    (None, None, 0),
    ('8.10-HF37', None, 1),
    ('2.0.805', None, 1),
])
def test_version_compare_client(x, y, result):
    assert nxdrive.utils.version_compare_client(x, y) == result
