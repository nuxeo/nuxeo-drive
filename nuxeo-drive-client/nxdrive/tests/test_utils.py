import sys
import hashlib
import unittest
from nxdrive.utils import guess_mime_type
from nxdrive.utils import guess_digest_algorithm
from nxdrive.utils import is_office_temp_file
from nxdrive.manager import ProxySettings


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

    def test_office_temp_file(self):
        # Normal
        self.assertEqual(is_office_temp_file("plop"), False)

        # Powerpoint temp file
        self.assertEqual(is_office_temp_file("ppt.tmp"), False)
        self.assertEqual(is_office_temp_file("pptED23.tmp"), True)
        self.assertEqual(is_office_temp_file("pptzDER.tmp"), False)
        self.assertEqual(is_office_temp_file("ppt1DER.tmp"), False)
        self.assertEqual(is_office_temp_file("ppt21AD.tmp"), True)
        # Powerpoint temp file by Office 365 / 2013
        self.assertEqual(is_office_temp_file("ppt1.tmp"), True)
        self.assertEqual(is_office_temp_file("ppt23F.tmp"), True)

        # Office temp file 2007+
        self.assertEqual(is_office_temp_file("A239FDCA"), True)
        self.assertEqual(is_office_temp_file("A2Z9FDCA"), False)
        self.assertEqual(is_office_temp_file("12345678"), True)
        self.assertEqual(is_office_temp_file("9ABCDEF0"), True)
        self.assertEqual(is_office_temp_file("A239FDZA"), False)
        self.assertEqual(is_office_temp_file("A239FDCA.tmp"), True)
        self.assertEqual(is_office_temp_file("A2Z9FDCA.tmp"), False)
        self.assertEqual(is_office_temp_file("12345678.tmp"), True)
        self.assertEqual(is_office_temp_file("9ABCDEF0.tmp"), True)
        self.assertEqual(is_office_temp_file("A239FDZA.tmp"), False)
        self.assertEqual(is_office_temp_file("A2D9FDCA1"), False)
        self.assertEqual(is_office_temp_file("A2D9FDCA1.tmp"), False)
        self.assertEqual(is_office_temp_file("9ABCDEF0.tep"), False)
        # Office temp file 2013
        self.assertEqual(is_office_temp_file("C199633.tmp"), True)
        self.assertEqual(is_office_temp_file("BCD574.tmp"), True)

        # Office 97
        self.assertEqual(is_office_temp_file("~A2D9FDCA1.tmp"), True)
        self.assertEqual(is_office_temp_file("~Whatever is here.tmp"), True)
        self.assertEqual(is_office_temp_file("~A2D9FDCA1.tm"), False)
        self.assertEqual(is_office_temp_file("Whatever is here.tmp"), False)

    def test_guess_mime_type(self):

        # Text
        self.assertEquals(guess_mime_type('text.txt'), 'text/plain')
        self.assertEquals(guess_mime_type('text.html'), 'text/html')
        self.assertEquals(guess_mime_type('text.css'), 'text/css')
        self.assertEquals(guess_mime_type('text.js'), 'application/javascript')

        # Image
        self.assertEquals(guess_mime_type('picture.jpg'), 'image/jpeg')
        self.assertEquals(guess_mime_type('picture.png'), 'image/png')
        self.assertEquals(guess_mime_type('picture.gif'), 'image/gif')
        self.assertIn(guess_mime_type('picture.bmp'), ['image/x-ms-bmp',
                                                       'image/bmp'])
        self.assertEquals(guess_mime_type('picture.tiff'), 'image/tiff')
        self.assertIn(guess_mime_type('picture.ico'), ['image/x-icon', 'image/vnd.microsoft.icon'])

        # Audio
        self.assertEquals(guess_mime_type('sound.mp3'), 'audio/mpeg')
        self.assertIn(guess_mime_type('sound.wma'), ['audio/x-ms-wma', 'application/octet-stream'])
        self.assertIn(guess_mime_type('sound.wav'), ['audio/x-wav', 'audio/wav'])

        # Video
        self.assertEquals(guess_mime_type('video.mpeg'), 'video/mpeg')
        self.assertEquals(guess_mime_type('video.mp4'), 'video/mp4')
        self.assertEquals(guess_mime_type('video.mov'), 'video/quicktime')
        self.assertIn(guess_mime_type('video.wmv'), ['video/x-ms-wmv', 'application/octet-stream'])
        self.assertIn(guess_mime_type('video.avi'), ['video/x-msvideo',
                                                     'video/avi'])

        # Office
        self.assertEquals(guess_mime_type('office.doc'),
                          'application/msword')
        self.assertEquals(guess_mime_type('office.xls'),
                          'application/vnd.ms-excel')
        self.assertEquals(guess_mime_type('office.ppt'),
                          'application/vnd.ms-powerpoint')

        # PDF
        self.assertEquals(guess_mime_type('document.pdf'),
                          'application/pdf')

        # Unknown
        self.assertEquals(guess_mime_type('file.unknown'),
                          'application/octet-stream')

        # Cases badly handled by Windows
        # See https://jira.nuxeo.com/browse/NXP-11660
        # and http://bugs.python.org/issue15207
        if sys.platform == "win32":
            # Text
            self.assertEquals(guess_mime_type('text.csv'),
                              'application/octet-stream')
            self.assertEquals(guess_mime_type('text.xml'), 'text/xml')

            # Image
            self.assertIn(guess_mime_type('picture.svg'), ['image/svg+xml', 'application/octet-stream'])

            # Video
            self.assertEquals(guess_mime_type('video.flv'),
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
            self.assertEquals(guess_mime_type('text.csv'), 'text/csv')
            self.assertEquals(guess_mime_type('text.xml'), 'application/xml')

            # Image
            self.assertEquals(guess_mime_type('picture.svg'), 'image/svg+xml')

            # Video
            self.assertEquals(guess_mime_type('video.flv'), 'video/x-flv')

            # Office
            self.assertEquals(guess_mime_type('office.docx'),
                              'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
            self.assertEquals(guess_mime_type('office.xlsx'),
                              'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
            self.assertEquals(guess_mime_type('office.pptx'),
                              'application/vnd.openxmlformats-officedocument.presentationml.presentation')

            self.assertEquals(guess_mime_type('office.odt'), 'application/vnd.oasis.opendocument.text')
            self.assertEquals(guess_mime_type('office.ods'), 'application/vnd.oasis.opendocument.spreadsheet')
            self.assertEquals(guess_mime_type('office.odp'), 'application/vnd.oasis.opendocument.presentation')

    def test_guess_digest_algorithm(self):
        s = 'joe'
        md5_digest = hashlib.md5(s).hexdigest()
        self.assertEquals(guess_digest_algorithm(md5_digest), 'md5')
        sha1_digest = hashlib.sha1(s).hexdigest()
        self.assertEquals(guess_digest_algorithm(sha1_digest), 'sha1')
        # For now only md5 and sha1 are supported
        sha256_digest = hashlib.sha256(s).hexdigest()
        try:
            guess_digest_algorithm(sha256_digest)
            self.fail('Other algorithms than md5 and sha1 should not be supported for now')
        except:
            pass
