# coding: utf-8
import hashlib
import os
import sys
import unittest
import urlparse

from nxdrive.manager import ProxySettings
from nxdrive.utils import guess_digest_algorithm, guess_mime_type, \
    guess_server_url, is_generated_tmp_file


class TestUtils(unittest.TestCase):

    def test_proxy_settings(self):
        proxy = ProxySettings()
        proxy.from_url("localhost:3128")
        self.assertEqual(proxy.username, None)
        self.assertEqual(proxy.password, None)
        self.assertEqual(proxy.authenticated, False)
        self.assertEqual(proxy.server, "localhost")
        self.assertEqual(proxy.port, 3128)
        self.assertEqual(proxy.proxy_type, None)
        self.assertEqual(proxy.to_url(), 'localhost:3128')
        self.assertEqual(proxy.to_url(False), 'localhost:3128')
        proxy.from_url("user@localhost:3128")
        self.assertEqual(proxy.username, "user")
        self.assertEqual(proxy.password, None)
        self.assertEqual(proxy.authenticated, False)
        self.assertEqual(proxy.server, "localhost")
        self.assertEqual(proxy.port, 3128)
        self.assertEqual(proxy.proxy_type, None)
        self.assertEqual(proxy.to_url(), 'localhost:3128')
        self.assertEqual(proxy.to_url(False), 'localhost:3128')
        proxy.from_url("user:password@localhost:3128")
        self.assertEqual(proxy.username, "user")
        self.assertEqual(proxy.password, "password")
        self.assertEqual(proxy.authenticated, True)
        self.assertEqual(proxy.server, "localhost")
        self.assertEqual(proxy.port, 3128)
        self.assertEqual(proxy.proxy_type, None)
        self.assertEqual(proxy.to_url(), 'user:password@localhost:3128')
        self.assertEqual(proxy.to_url(False), 'localhost:3128')
        proxy.from_url("http://user:password@localhost:3128")
        self.assertEqual(proxy.username, "user")
        self.assertEqual(proxy.password, "password")
        self.assertEqual(proxy.authenticated, True)
        self.assertEqual(proxy.server, "localhost")
        self.assertEqual(proxy.port, 3128)
        self.assertEqual(proxy.proxy_type, 'http')
        self.assertEqual(proxy.to_url(), 'http://user:password@localhost:3128')
        self.assertEqual(proxy.to_url(False), 'http://localhost:3128')
        proxy.from_url("https://user:password@localhost:3129")
        self.assertEqual(proxy.username, "user")
        self.assertEqual(proxy.password, "password")
        self.assertEqual(proxy.authenticated, True)
        self.assertEqual(proxy.server, "localhost")
        self.assertEqual(proxy.port, 3129)
        self.assertEqual(proxy.proxy_type, 'https')
        self.assertEqual(proxy.to_url(), 'https://user:password@localhost:3129')
        self.assertEqual(proxy.to_url(False), 'https://localhost:3129')

    def test_generated_tempory_file(self):
        # Normal
        self.assertEqual(is_generated_tmp_file('README'), (False, None))

        # Any temporary file
        self.assertEqual(is_generated_tmp_file('Book1.bak'), (True, False))
        self.assertEqual(is_generated_tmp_file('pptED23.tmp'), (True, False))
        self.assertEqual(is_generated_tmp_file('9ABCDEF0.tep'), (False, None))

        # AutoCAD
        self.assertEqual(is_generated_tmp_file('atmp9716'), (True, False))
        self.assertEqual(is_generated_tmp_file('7151_CART.dwl'), (True, False))
        self.assertEqual(is_generated_tmp_file('7151_CART.dwl2'), (True, False))
        self.assertEqual(is_generated_tmp_file('7151_CART.dwg'), (False, None))

        # Microsoft Office
        self.assertEqual(is_generated_tmp_file('A239FDCA'), (True, True))
        self.assertEqual(is_generated_tmp_file('A2Z9FDCA'), (False, None))
        self.assertEqual(is_generated_tmp_file('A239FDZA'), (False, None))
        self.assertEqual(is_generated_tmp_file('A2D9FDCA1'), (False, None))
        self.assertEqual(is_generated_tmp_file('~A2D9FDCA1.tm'), (False, None))

    def test_guess_mime_type(self):
        # Text
        self.assertEqual(guess_mime_type('text.txt'), 'text/plain')
        self.assertEqual(guess_mime_type('text.html'), 'text/html')
        self.assertEqual(guess_mime_type('text.css'), 'text/css')
        self.assertEqual(guess_mime_type('text.csv'), 'text/csv')
        self.assertEqual(guess_mime_type('text.js'), 'application/javascript')

        # Image
        self.assertEqual(guess_mime_type('picture.jpg'), 'image/jpeg')
        self.assertEqual(guess_mime_type('picture.png'), 'image/png')
        self.assertEqual(guess_mime_type('picture.gif'), 'image/gif')
        self.assertIn(guess_mime_type('picture.bmp'), ['image/x-ms-bmp',
                                                       'image/bmp'])
        self.assertEqual(guess_mime_type('picture.tiff'), 'image/tiff')
        self.assertIn(guess_mime_type('picture.ico'), ['image/x-icon', 'image/vnd.microsoft.icon'])

        # Audio
        self.assertEqual(guess_mime_type('sound.mp3'), 'audio/mpeg')
        self.assertIn(guess_mime_type('sound.wma'), ['audio/x-ms-wma', 'application/octet-stream'])
        self.assertIn(guess_mime_type('sound.wav'), ['audio/x-wav', 'audio/wav'])

        # Video
        self.assertEqual(guess_mime_type('video.mpeg'), 'video/mpeg')
        self.assertEqual(guess_mime_type('video.mp4'), 'video/mp4')
        self.assertEqual(guess_mime_type('video.mov'), 'video/quicktime')
        self.assertIn(guess_mime_type('video.wmv'), ['video/x-ms-wmv', 'application/octet-stream'])
        self.assertIn(guess_mime_type('video.avi'), ['video/x-msvideo',
                                                     'video/avi'])

        # Office
        self.assertEqual(guess_mime_type('office.doc'),
                         'application/msword')
        self.assertEqual(guess_mime_type('office.xls'),
                         'application/vnd.ms-excel')
        self.assertEqual(guess_mime_type('office.ppt'),
                         'application/vnd.ms-powerpoint')

        # PDF
        self.assertEqual(guess_mime_type('document.pdf'),
                         'application/pdf')

        # Unknown
        self.assertEqual(guess_mime_type('file.unknown'),
                         'application/octet-stream')

        # Cases badly handled by Windows
        # See https://jira.nuxeo.com/browse/NXP-11660
        # and http://bugs.python.org/issue15207
        if sys.platform == "win32":
            # Text
            self.assertEqual(guess_mime_type('text.xml'), 'text/xml')

            # Image
            self.assertIn(guess_mime_type('picture.svg'), ['image/svg+xml', 'application/octet-stream'])

            # Video
            self.assertEqual(guess_mime_type('video.flv'),
                             'application/octet-stream')

            # Office
            self.assertIn(guess_mime_type('office.docx'),
                          ['application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                           'application/octet-stream'])
            self.assertIn(guess_mime_type('office.xlsx'),
                          ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                           'application/octet-stream'])
            self.assertIn(guess_mime_type('office.pptx'),
                          ['application/vnd.openxmlformats-officedocument.presentationml.presentation',
                           'application/x-mspowerpoint.12', 'application/octet-stream'])

            self.assertIn(guess_mime_type('office.odt'),
                          ['application/vnd.oasis.opendocument.text', 'application/octet-stream'])
            self.assertIn(guess_mime_type('office.ods'),
                          ['application/vnd.oasis.opendocument.spreadsheet', 'application/octet-stream'])
            self.assertIn(guess_mime_type('office.odp'),
                          ['application/vnd.oasis.opendocument.presentation', 'application/octet-stream'])
        else:
            # Text
            self.assertEqual(guess_mime_type('text.xml'), 'application/xml')

            # Image
            self.assertEqual(guess_mime_type('picture.svg'), 'image/svg+xml')

            # Video
            self.assertEqual(guess_mime_type('video.flv'), 'video/x-flv')

            # Office
            self.assertEqual(guess_mime_type('office.docx'),
                             'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.assertEqual(guess_mime_type('office.xlsx'),
                             'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.assertEqual(guess_mime_type('office.pptx'),
                             'application/vnd.openxmlformats-officedocument.presentationml.presentation')

            self.assertEqual(guess_mime_type('office.odt'), 'application/vnd.oasis.opendocument.text')
            self.assertEqual(guess_mime_type('office.ods'), 'application/vnd.oasis.opendocument.spreadsheet')
            self.assertEqual(guess_mime_type('office.odp'), 'application/vnd.oasis.opendocument.presentation')

    def test_guess_digest_algorithm(self):
        md5_digest = hashlib.md5('joe').hexdigest()
        self.assertEqual(guess_digest_algorithm(md5_digest), 'md5')
        sha1_digest = hashlib.sha1('joe').hexdigest()
        self.assertEqual(guess_digest_algorithm(sha1_digest), 'sha1')
        # For now only md5 and sha1 are supported
        sha256_digest = hashlib.sha256('joe').hexdigest()
        try:
            guess_digest_algorithm(sha256_digest)
            self.fail('Other algorithms than MD5 and SHA1 should not'
                      ' be supported for now')
        except:
            pass

    def test_guess_server_url(self):
        good_url = os.environ.get(
            'NXDRIVE_TEST_NUXEO_URL',
            'http://localhost:8080/nuxeo')
        self.assertEqual(guess_server_url(good_url), good_url)

        # IP or domain
        if '#' in good_url:
            # Remove the engine type for the rest of the test
            good_url = good_url.split('#')[0]
        domain = urlparse.urlsplit(good_url).netloc
        self.assertEqual(guess_server_url(domain), good_url)

        # IP or domain + default port => remove the port
        if ':' in domain:
            domain = domain.split(':')[0]
            self.assertEqual(guess_server_url(domain), good_url)

        # HTTPS domain
        domain = 'intranet.nuxeo.com'
        good_url = 'https://intranet.nuxeo.com/nuxeo'
        self.assertEqual(guess_server_url(domain), good_url)

        # With additional parameters
        domain = 'https://intranet.nuxeo.com/nuxeo?TenantId=0xdeadbeaf'
        good_url = domain
        self.assertEqual(guess_server_url(domain), good_url)

        # Incomplete URL
        domain = 'https://nightly.nuxeo.com'
        good_url = 'https://nightly.nuxeo.com/nuxeo'
        self.assertEqual(guess_server_url(domain), good_url)

        # Bad IP
        domain = '1.2.3.4'
        good_url = '1.2.3.4'
        self.assertEqual(guess_server_url(domain), good_url)
