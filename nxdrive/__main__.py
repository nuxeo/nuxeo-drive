# coding: utf-8
"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import sys
from contextlib import suppress


def show_critical_error() -> None:
    """ Display a "friendly" dialog box on fatal error. """

    import traceback

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QIcon
    from PyQt5.QtWidgets import (
        QApplication,
        QDialog,
        QDialogButtonBox,
        QLabel,
        QTextEdit,
        QVBoxLayout,
    )

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    dialog = QDialog()
    dialog.setWindowTitle("Nuxeo Drive - Fatal error")
    dialog.resize(600, 400)

    with suppress(Exception):
        from nxdrive.utils import find_icon

        dialog.setWindowIcon(QIcon(find_icon("app_icon.svg")))

    # Display a little message to apologize
    text = """Ooops! Sadly a fatal error occurred and Nuxeo Drive cannot work.
This is unfortunate and we want to apologize for the inconvenience.
"""
    info = QLabel(text)
    info.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)

    # Display the the exception
    label_exc = QLabel("Exception:")
    label_exc.setAlignment(Qt.AlignVCenter)
    exception = QTextEdit()
    exception.setStyleSheet("font-family: monospace;")
    exception.setReadOnly(True)
    exc_type, exc_value, exc_traceback = sys.exc_info()
    exc_formatted = traceback.format_exception(exc_type, exc_value, exc_traceback)
    exception.setText("".join(exc_formatted))

    # OK button
    buttons = QDialogButtonBox()
    buttons.setStandardButtons(QDialogButtonBox.Ok)
    buttons.clicked.connect(dialog.close)

    layout = QVBoxLayout()
    layout.addWidget(info)
    layout.addWidget(label_exc)
    layout.addWidget(exception)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    dialog.show()

    app.exec_()


def main() -> int:
    """ Entry point. """

    if sys.version_info < (3, 6):
        raise RuntimeError("Nuxeo Drive requires Python 3.6+")

    try:
        from nxdrive.commandline import CliHandler

        return CliHandler().handle(sys.argv)
    except:
        show_critical_error()
        return 1


sys.exit((main()))
