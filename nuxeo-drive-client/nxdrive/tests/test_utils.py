import sys
import unittest
from nxdrive.utils import guess_mime_type


class UtilsTestCase(unittest.TestCase):

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
        self.assertEquals(guess_mime_type('picture.bmp'), 'image/x-ms-bmp')
        self.assertEquals(guess_mime_type('picture.tiff'), 'image/tiff')
        self.assertEquals(guess_mime_type('picture.ico'),
                          'image/x-icon')

        # Audio
        self.assertEquals(guess_mime_type('sound.mp3'), 'audio/mpeg')
        self.assertIn(guess_mime_type('sound.wma'), ['audio/x-ms-wma',
                                                'application/octet-stream'])
        self.assertEquals(guess_mime_type('sound.wav'), 'audio/x-wav')

        # Video
        self.assertEquals(guess_mime_type('video.mpeg'), 'video/mpeg')
        self.assertEquals(guess_mime_type('video.mp4'), 'video/mp4')
        self.assertEquals(guess_mime_type('video.mov'), 'video/quicktime')
        self.assertIn(guess_mime_type('video.wmv'), ['video/x-ms-wmv',
                                                'application/octet-stream'])
        self.assertIn(guess_mime_type('video.avi'), ['video/x-msvideo',
                                                     'video/avi'])

        # Office
        self.assertEquals(guess_mime_type('office.doc'),
                          'application/msword')
        self.assertIn(guess_mime_type('office.xls'), [
                          'application/vnd.ms-excel',
                          'application/x-msexcel'])
        self.assertIn(guess_mime_type('office.ppt'), [
                          'application/vnd.ms-powerpoint',
                          'application/x-mspowerpoint'])

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
            self.assertIn(guess_mime_type('picture.svg'), ['image/svg+xml',
                              'application/octet-stream'])

            # Video
            self.assertEquals(guess_mime_type('video.flv'),
                              'application/octet-stream')

            # Office
            self.assertEquals(guess_mime_type('office.docx'),
                              'application/octet-stream')
            self.assertEquals(guess_mime_type('office.xlsx'),
                              'application/octet-stream')
            self.assertEquals(guess_mime_type('office.pptx'),
                              'application/octet-stream')

            self.assertEquals(guess_mime_type('office.odt'),
                              'application/octet-stream')
            self.assertEquals(guess_mime_type('office.ods'),
                              'application/octet-stream')
            self.assertEquals(guess_mime_type('office.odp'),
                              'application/octet-stream')
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
                          'application/vnd.openxmlformats-officedocument'
                          '.wordprocessingml.document')
            self.assertEquals(guess_mime_type('office.xlsx'),
                          'application/vnd.openxmlformats-officedocument'
                          '.spreadsheetml.sheet')
            self.assertEquals(guess_mime_type('office.pptx'),
                          'application/vnd.openxmlformats-officedocument'
                          '.presentationml.presentation')

            self.assertEquals(guess_mime_type('office.odt'),
                          'application/vnd.oasis.opendocument.text')
            self.assertEquals(guess_mime_type('office.ods'),
                          'application/vnd.oasis.opendocument.spreadsheet')
            self.assertEquals(guess_mime_type('office.odp'),
                          'application/vnd.oasis.opendocument.presentation')
