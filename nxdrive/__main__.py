# coding: utf-8
"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import io
import os
import sys
from contextlib import suppress
from typing import Any, Set

from nxdrive.constants import APP_NAME, COMPANY, MAC
from nxdrive.options import Options


def check_executable_path() -> bool:
    """ Check that the app runs from the right path, and quit if not. """
    import re
    import sys
    from pathlib import Path

    exe_path = sys.executable
    m = re.match(r"(.*\.app).*", exe_path)
    path = Path(m.group(1) if m else exe_path)

    if not Options.is_frozen or path == Path(f"/Applications/{APP_NAME}.app"):
        return True

    from nxdrive.translator import Translator
    from nxdrive.utils import find_icon, find_resource

    from PyQt5.QtGui import QPixmap
    from PyQt5.QtWidgets import QApplication, QMessageBox

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    Translator(find_resource("i18n"))
    content = Translator.get("RUNNING_FROM_WRONG_PATH", [str(path), f"{APP_NAME}.app"])

    icon = QPixmap(str(find_icon("app_icon.svg")))
    msg = QMessageBox()
    msg.setIconPixmap(icon)
    msg.setText(content)
    msg.setWindowTitle(APP_NAME)
    msg.addButton(Translator.get("QUIT"), QMessageBox.AcceptRole)
    msg.exec_()
    return False


def before_send(event: Any, hint: Any) -> Any:
    """
    Alter an event before sending to the Sentry server.
    The event will not be sent if None is returned.
    """

    # Sentry may have been disabled later, via a CLI argument or GUI parameter
    if not Options.use_sentry:
        return None

    # Local vars to hide from Sentry reports
    to_redact: Set[str] = {"password", "pwd", "token"}
    replace: str = "<REDACTED>"

    # Remove passwords from locals
    with suppress(KeyError):
        for thread in event["threads"]:
            for frame in thread["stacktrace"]["frames"]:
                for var in to_redact:
                    # Only alter the value if it exists
                    if var in frame["vars"]:
                        frame["vars"][var] = replace

    return event


def section(header: str, content: str) -> str:
    """Format a "section" of information."""
    return f"{header}\n```\n{content.strip()}\n```"


def setup_sentry() -> None:
    """ Setup Sentry. """

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    # TODO: Replace the testing DSN by "DSN_PLACEHOLDER" that will be replaced at when generating installers.
    sentry_dsn: str = os.getenv(
        "SENTRY_DSN", "https://c4daa72433b443b08bd25e0c523ecef5@sentry.io/1372714"
    )
    if not sentry_dsn:
        return

    import sentry_sdk
    from nxdrive import __version__

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        release=__version__,
        attach_stacktrace=True,
        before_send=before_send,
    )


def show_critical_error(out) -> None:
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

    from nxdrive.translator import Translator
    from nxdrive.utils import find_icon, find_resource

    Translator(find_resource("i18n"))
    tr = Translator.get

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    dialog = QDialog()
    dialog.setWindowTitle(tr("FATAL_ERROR_TITLE", [APP_NAME]))
    dialog.setWindowIcon(QIcon(str(find_icon("app_icon.svg"))))
    dialog.resize(800, 600)
    layout = QVBoxLayout()
    css = "font-family: monospace; font-size: 12px;"
    details = []

    # Display a little message to apologize
    info = QLabel(tr("FATAL_ERROR_MSG", [APP_NAME, COMPANY]))
    info.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    layout.addWidget(info)

    # Display CLI arguments
    if sys.argv[1:]:
        text = tr("FATAL_ERROR_CLI_ARGS")
        label_cli = QLabel(text)
        label_cli.setAlignment(Qt.AlignVCenter)
        cli_args = QTextEdit()
        cli_args.setStyleSheet(css)
        cli_args.setReadOnly(True)
        args = "\n".join(arg for arg in sys.argv[1:])
        details.append(section(text, args))
        cli_args.setText(args)
        cli_args.setSizeAdjustPolicy(QTextEdit.AdjustToContents)
        layout.addWidget(label_cli)
        layout.addWidget(cli_args)

    # Display the exception
    text = tr("FATAL_ERROR_EXCEPTION")
    label_exc = QLabel(text)
    label_exc.setAlignment(Qt.AlignVCenter)
    exception = QTextEdit()
    exception.setStyleSheet(css)
    exception.setReadOnly(True)
    exc_formatted = "".join(traceback.format_exception(*sys.exc_info()))
    details.append(section(text, exc_formatted))
    exception.setText(exc_formatted)
    layout.addWidget(label_exc)
    layout.addWidget(exception)

    # Display the console output
    output = out.getvalue()
    if output:
        text = tr("FATAL_ERROR_OUTPUT")
        label_err = QLabel(text)
        label_err.setAlignment(Qt.AlignVCenter)
        err = QTextEdit()
        err.setStyleSheet(css)
        err.setReadOnly(True)
        details.append(section(text, output))
        err.setText(output)
        layout.addWidget(label_err)
        layout.addWidget(err)

    # Display last lines from the memory log
    with suppress(Exception):
        from nxdrive.report import Report

        # Last 20th lines
        raw_lines = Report.export_logs(-20)
        lines = b"\n".join(raw_lines).decode(errors="replace")

        if lines:
            text = tr("FATAL_ERROR_LOGS")
            label_log = QLabel(text)
            details.append(section(text, lines))
            label_log.setAlignment(Qt.AlignVCenter)
            layout.addWidget(label_log)

            logs = QTextEdit()
            logs.setStyleSheet(css)
            logs.setReadOnly(True)
            logs.setLineWrapColumnOrWidth(4096)
            logs.setLineWrapMode(QTextEdit.FixedPixelWidth)
            logs.setText(lines)
            layout.addWidget(logs)

    # Buttons
    buttons = QDialogButtonBox()
    buttons.setStandardButtons(QDialogButtonBox.Ok)
    buttons.accepted.connect(dialog.close)
    layout.addWidget(buttons)

    def copy() -> None:
        """Copy details to the clipboard and change the text of the button. """
        copy_to_clipboard("\n".join(details))
        copy_paste.setText(tr("FATAL_ERROR_DETAILS_COPIED"))

    # "Copy details" button
    with suppress(Exception):
        from nxdrive.utils import copy_to_clipboard

        copy_paste = buttons.addButton(
            tr("FATAL_ERROR_DETAILS_COPY"), QDialogButtonBox.ActionRole
        )
        copy_paste.clicked.connect(copy)

    dialog.setLayout(layout)
    dialog.show()
    app.exec_()


class RedirectStdStreams:
    def __init__(self, stdout=None, stderr=None):
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr

    def __enter__(self):
        self.old_stdout, self.old_stderr = sys.stdout, sys.stderr
        self.old_stdout.flush()
        self.old_stderr.flush()
        sys.stdout, sys.stderr = self._stdout, self._stderr

    def __exit__(self, exc_type, exc_value, traceback):
        self._stdout.flush()
        self._stderr.flush()
        sys.stdout, sys.stderr = self.old_stdout, self.old_stderr


def main() -> int:
    """ Entry point. """

    with io.StringIO() as out:
        ret = 0

        with RedirectStdStreams(stdout=out, stderr=out):
            try:
                if sys.version_info < (3, 6):
                    raise RuntimeError(f"{APP_NAME} requires Python 3.6+")

                if MAC and not check_executable_path():
                    ret = 1

                # Setup Sentry even if the user did not allow it because it can be tweaked
                # later via the "use-sentry" parameter. It will be useless if Sentry is not installed first.
                setup_sentry()

                from nxdrive.commandline import CliHandler

                ret = CliHandler().handle(sys.argv[1:])
            except SystemExit as exc:
                if exc.code != 0:
                    show_critical_error(out)
                ret = exc.code
            except:
                show_critical_error(out)
                ret = 1

        print(out.getvalue(), flush=True)
        return ret


sys.exit((main()))
