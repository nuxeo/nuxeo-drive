# coding: utf-8
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
    assert not proxy.authenticated
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


@pytest.mark.parametrize('name, state', [
    # Normal
    ('README', (False, None)),

    # Any temporary file
    ('Book1.bak', (True, False)),
    ('pptED23.tmp', (True, False)),
    ('9ABCDEF0.tep', (False, None)),

    # AutoCAD
    ('atmp9716', (True, False)),
    ('7151_CART.dwl', (True, False)),
    ('7151_CART.dwl2', (True, False)),
    ('7151_CART.dwg', (False, None)),

    # Microsoft Office
    ('A239FDCA', (True, True)),
    ('A2Z9FDCA', (False, None)),
    ('A239FDZA', (False, None)),
    ('A2D9FDCA1', (False, None)),
    ('~A2D9FDCA1.tm', (False, None)),
])
def test_generated_tempory_file(name, state):
    assert nxdrive.utils.is_generated_tmp_file(name) == state


@pytest.mark.parametrize('name, mime', [
    # Text
    ('foo.txt', 'text/plain'),
    ('foo.html', 'text/html'),
    ('foo.css', 'text/css'),
    ('foo.csv', 'text/csv'),
    ('foo.js', 'application/javascript'),

    # Image
    ('foo.jpg', 'image/jpeg'),
    ('foo.jpeg', 'image/jpeg'),
    ('foo.png', 'image/png'),
    ('foo.gif', 'image/gif'),
    ('foo.bmp', ('image/x-ms-bmp', 'image/bmp')),
    ('foo.tiff', 'image/tiff'),
    ('foo.ico', ('image/x-icon', 'image/vnd.microsoft.icon')),

    # Audio
    ('foo.mp3', 'audio/mpeg'),
    ('foo.vma', ('audio/x-ms-wma', 'application/octet-stream')),
    ('foo.wav', ('audio/x-wav', 'audio/wav')),

    # Video
    ('foo.mpeg', 'video/mpeg'),
    ('foo.mp4', 'video/mp4'),
    ('foo.mov', 'video/quicktime'),
    ('foo.wmv', ('video/x-ms-wmv', 'application/octet-stream')),
    ('foo.avi', ('video/x-msvideo', 'video/avi')),

    # Office
    ('foo.doc', 'application/msword'),
    ('foo.xls', 'application/vnd.ms-excel'),
    ('foo.ppt', 'application/vnd.ms-powerpoint'),

    # PDF
    ('foo.pdf', 'application/pdf'),

    # Unknown
    ('foo.unknown', 'application/octet-stream'),
    ('foo.rvt', 'application/octet-stream'),

    # Cases badly handled by Windows
    # See /NXP-11660 http://bugs.python.org/issue15207
    ('foo.xml', ('text/xml', 'application/xml')),
    ('foo.svg', ('image/svg+xml', 'application/octet-stream', 'image/svg+xml')),
    ('foo.flv', ('application/octet-stream', 'video/x-flv')),
    ('foo.docx', ('application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                  'application/octet-stream')),
    ('foo.xlsx', ('application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                  'application/octet-stream')),
    ('foo.pptx', ('application/vnd.openxmlformats-officedocument.presentationml.presentation',
                  'application/x-mspowerpoint.12',
                  'application/octet-stream')),
    ('foo.odt', ('application/vnd.oasis.opendocument.text',
                 'application/octet-stream')),
    ('foo.ods', ('application/vnd.oasis.opendocument.spreadsheet',
                 'application/octet-stream')),
    ('foo.odp', ('application/vnd.oasis.opendocument.presentation',
                 'application/octet-stream')),
])
def test_guess_mime_type(name, mime):
    if isinstance(mime, tuple):
        assert nxdrive.utils.guess_mime_type(name) in mime
    else:
        assert nxdrive.utils.guess_mime_type(name) == mime


@pytest.mark.parametrize('url, result', [
    ('localhost', 'http://localhost:8080/nuxeo'),
    # HTTPS domain
    ('intranet.nuxeo.com', 'https://intranet.nuxeo.com/nuxeo'),
    # With additional parameters
    ('https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf', 'https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf'),
    # Incomplete URL
    ('https://intranet.nuxeo.com', 'https://intranet.nuxeo.com/nuxeo'),
    # Bad IP
    ('1.2.3.4', None),
    # Bad protocol
    ('htto://intranet.nuxeo.com/nuxeo', None),
])
def test_guess_server_url(url, result):
    assert nxdrive.utils.guess_server_url(url) == result


@pytest.mark.parametrize('url, result', [
    # HTTP
    ('http://example.org', 'http://example.org'),
    ('http://example.org/', 'http://example.org'),
    ('http://example.org:80', 'http://example.org'),
    ('http://example.org:80/', 'http://example.org'),
    ('http://example.org:8080', 'http://example.org:8080'),
    ('http://example.org:8080/', 'http://example.org:8080'),

    # HTTPS
    ('https://example.org', 'https://example.org'),
    ('https://example.org/', 'https://example.org'),
    ('https://example.org:443', 'https://example.org'),
    ('https://example.org:443/', 'https://example.org'),
    ('https://example.org:4433', 'https://example.org:4433'),
    ('https://example.org:4433/', 'https://example.org:4433'),
])
def test_simplify_url(url, result):
    assert nxdrive.utils.simplify_url(url) == result


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
