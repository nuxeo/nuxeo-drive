"""GUI prompt to manage metadata"""
import sys
from nxdrive.logging_config import get_logger
from PyQt4 import QtCore, QtGui, QtWebKit, QtNetwork
from PyQt4.Qt import QUrl, QObject
from PyQt4.QtCore import Qt

log = get_logger(__name__)

METADATA_WEBVIEW_WIDTH = 500
METADATA_WEBVIEW_HEIGHT = 500

class MetadataWebView(QtWebKit.QWebView):
    """Web view to prompt about metadata."""

    def __init__(self, controller, file_path):
        super(MetadataWebView, self).__init__()

        self.controller = controller

        url, token = self.controller.get_metadata_url(file_path)

        self.request = QtNetwork.QNetworkRequest(QUrl(url))
        self.request.setRawHeader("X-Authentication-Token",
                                  QtCore.QByteArray(token))

        self.load(self.request)


def prompt_metadata(controller, file_path):
    """Display a Qt web view to prompt about metadata."""

    def close(): sys.exit()

    app = QtGui.QApplication(sys.argv)
    webview = MetadataWebView(controller, file_path)
    webview.setWindowTitle("Nuxeo Drive : "+file_path)
    webview.resize(METADATA_WEBVIEW_WIDTH, METADATA_WEBVIEW_HEIGHT)

    webview.setWindowFlags(Qt.WindowStaysOnTopHint)

    QObject.connect(webview.page(), QtCore.SIGNAL("windowCloseRequested ()"),
                    close)

    webview.show()

    sys.exit(app.exec_())

if __name__ == '__main__':

    sys.exit(prompt_metadata(None, None))
