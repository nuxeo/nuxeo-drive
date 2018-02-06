# coding: utf-8
import hashlib
import sys

import nxdrive.utils
from nxdrive.manager import ProxySettings


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
