__author__ = 'jowensla'

from nxdrive.controller import Controller
from PyQt4.QtGui import QApplication
import sys
import tempfile

class MockCommandLine(object):

    def __init__(self):
        self.handle(sys.argv)

    def handle(self, argv):
        self.controller = MockController()
        self.launch()

    def launch(self, options=None):
        self.app = MockApplication(self.controller, options)


class MockController(Controller):

    def __init__(self):
        tempfolder = tempfile.mkdtemp(u'-nuxeo-drive-test')
        self.mock_server_binding = MockServerBinding()
        super(MockController, self).__init__(tempfolder)

    def list_server_bindings(self, session=None):
        return [self.mock_server_binding]


class MockApplication(QApplication):

    def __init__(self, controller, options, argv=()):
        super(MockApplication, self).__init__(list(argv))


class MockServerBinding(object):
    def __init__(self):
        self.remote_token = '0270a087-ca91-4ec9-8c8c-18975282722e'
