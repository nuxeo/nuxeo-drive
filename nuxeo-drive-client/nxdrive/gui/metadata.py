"""GUI prompt to manage metadata"""
import sys
from nxdrive.logging_config import get_logger
from PyQt4 import QtCore, QtGui, QtWebKit, QtNetwork
from PyQt4.Qt import QUrl, QObject, QToolBar, QWebPage, QKeySequence, QNetworkCookie
from PyQt4.QtCore import Qt, QByteArray
from PyQt4.QtNetwork import QNetworkCookieJar


log = get_logger(__name__)


class MetadataWebView(QtWebKit.QWebView):
    """Web view to prompt about metadata."""

    def __init__(self, controller, file_path, mode):
        super(MetadataWebView, self).__init__()

        self.controller = controller

        url, token = self.controller.get_metadata_url(file_path, mode)

        log.debug("token : %s", token)
        
        self.request = QtNetwork.QNetworkRequest(QUrl(url))
        self.request.setRawHeader("X-Authentication-Token",
                                  QtCore.QByteArray(token))

        cookies = []
        cookieJar = QNetworkCookieJar()
        cookie = QNetworkCookie(QByteArray("X-Authentication-Token"),
                                QByteArray(token))
        cookies.append(cookie)
        cookieJar.setAllCookies(cookies)
        #    cookieJar = MyCookieJar(self);

        self.page().networkAccessManager().setCookieJar(cookieJar)

        self.load(self.request)


def prompt_metadata(controller, file_path, mode):
    """Display a Qt web view to prompt about metadata."""

    def close(): sys.exit()

    app = QtGui.QApplication(sys.argv)
    webview = MetadataWebView(controller, file_path, mode)
    webview.setWindowTitle("Nuxeo Metadata : "+file_path)
    webview.setMaximumSize(400, 500)

    webview.setWindowFlags(Qt.WindowStaysOnTopHint)

    QObject.connect(webview.page(), QtCore.SIGNAL("windowCloseRequested ()"),
                    close)
    webview.show()

    sys.exit(app.exec_())

if __name__ == '__main__':

    mode = "view"
    sys.exit(prompt_metadata(None, None, mode))
