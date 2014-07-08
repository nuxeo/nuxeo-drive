"""GUI prompt to manage metadata"""
import sys
from nxdrive.logging_config import get_logger

from PyQt4 import QtGui
from PyQt4.QtWebKit import QWebView
from PyQt4.QtCore import QUrl

log = get_logger(__name__)


class MetadataWebView(QWebView):
    """Web view to prompt about metadata."""

    def __init__(self, url):
        super(MetadataWebView, self).__init__()
        self.load(QUrl(url))


def prompt_metadata(url):
    """Display a Qt web view to prompt about metadata."""

    app = QtGui.QApplication(sys.argv)

    webview = MetadataWebView(url)
    webview.show()

    app.exec_()

if __name__ == '__main__':
    url = "http://localhost:8080/nuxeo"
    sys.exit(prompt_metadata(url))
