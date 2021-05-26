"""
Fatal error screen management using either Qt or OS-specific dialogs.
"""
import sys
from contextlib import suppress
from pathlib import Path

from nxdrive.constants import APP_NAME, COMPANY, MAC, WINDOWS
from nxdrive.options import Options

__all__ = ("check_executable_path", "check_os_version", "show_critical_error")


def check_executable_path_error_qt(path: Path, /) -> None:
    """Display an error using Qt about the app not running from the right path."""

    from nxdrive.qt import constants as qt
    from nxdrive.qt.imports import QApplication, QMessageBox, QPixmap
    from nxdrive.translator import Translator
    from nxdrive.utils import find_icon, find_resource

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    Translator(find_resource("i18n"))
    content = Translator.get(
        "RUNNING_FROM_WRONG_PATH", values=[str(path), f"{APP_NAME}.app"]
    )

    icon = QPixmap(str(find_icon("app_icon.svg")))
    msg = QMessageBox()
    msg.setIconPixmap(icon)
    msg.setText(content)
    msg.setWindowTitle(APP_NAME)
    msg.addButton(Translator.get("QUIT"), qt.AcceptRole)
    msg.exec_()


def fatal_error_qt(exc_formatted: str, /) -> None:
    """Display a "friendly" dialog box on fatal error using Qt."""

    from nxdrive.qt import constants as qt
    from nxdrive.qt.imports import (
        QApplication,
        QDesktopServices,
        QDialog,
        QDialogButtonBox,
        QIcon,
        QLabel,
        QTextEdit,
        QUrl,
        QVBoxLayout,
    )
    from nxdrive.translator import Translator
    from nxdrive.utils import find_icon, find_resource

    def section(header: str, content: str, /) -> str:
        """Format a "section" of information."""
        return f"{header}\n```\n{content.strip()}\n```"

    Translator(find_resource("i18n"))
    tr = Translator.get

    app = QApplication([])
    app.setQuitOnLastWindowClosed(True)

    dialog = QDialog()
    dialog.setWindowTitle(tr("FATAL_ERROR_TITLE", values=[APP_NAME]))
    dialog.setWindowIcon(QIcon(str(find_icon("app_icon.svg"))))
    dialog.resize(800, 600)
    layout = QVBoxLayout()
    css = "font-family: Courier; font-size: 12px;"
    details = []

    # Display a little message to apologize
    info = QLabel(tr("FATAL_ERROR_MSG", values=[APP_NAME, COMPANY]))
    info.setAlignment(qt.AlignHCenter | qt.AlignVCenter)
    layout.addWidget(info)

    # Display CLI arguments
    if sys.argv[1:]:
        text = tr("FATAL_ERROR_CLI_ARGS")
        label_cli = QLabel(text)
        label_cli.setAlignment(qt.AlignVCenter)
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
    label_exc.setAlignment(qt.AlignVCenter)
    exception = QTextEdit()
    exception.setStyleSheet(css)
    exception.setReadOnly(True)
    details.append(section(text, exc_formatted))
    exception.setText(exc_formatted)
    layout.addWidget(label_exc)
    layout.addWidget(exception)

    # Display last lines from the memory log
    with suppress(Exception):
        from nxdrive.report import Report

        # Last 20th lines
        raw_lines = Report.export_logs(20)
        lines = b"\n".join(raw_lines).decode(errors="replace")

        if lines:
            text = tr("FATAL_ERROR_LOGS")
            label_log = QLabel(text)
            details.append(section(text, lines))
            label_log.setAlignment(qt.AlignVCenter)
            layout.addWidget(label_log)

            logs = QTextEdit()
            logs.setStyleSheet(css)
            logs.setReadOnly(True)
            logs.setLineWrapColumnOrWidth(4096)
            logs.setLineWrapMode(qt.FixedPixelWidth)
            logs.setText(lines)
            layout.addWidget(logs)

    def open_update_site() -> None:
        """Open the update web site."""
        if WINDOWS:
            exe = "nuxeo-drive.exe"
        elif MAC:
            exe = "nuxeo-drive.dmg"
        else:
            exe = "nuxeo-drive-x86_64.AppImage"

        url = f"{Options.update_site_url}/{exe}"
        with suppress(Exception):
            QDesktopServices.openUrl(QUrl(url))

    # Buttons
    buttons = QDialogButtonBox()
    buttons.setStandardButtons(qt.Ok)
    buttons.accepted.connect(dialog.close)
    update_button = buttons.addButton(tr("FATAL_ERROR_UPDATE_BTN"), qt.ActionRole)
    update_button.setToolTip(tr("FATAL_ERROR_UPDATE_TOOLTIP", values=[APP_NAME]))
    update_button.clicked.connect(open_update_site)
    layout.addWidget(buttons)

    def copy() -> None:
        """Copy details to the clipboard and change the text of the button."""
        osi.cb_set("\n".join(details))
        copy_paste.setText(tr("FATAL_ERROR_DETAILS_COPIED"))

    # "Copy details" button
    with suppress(Exception):
        from nxdrive.osi import AbstractOSIntegration

        osi = AbstractOSIntegration.get(None)
        copy_paste = buttons.addButton(tr("FATAL_ERROR_DETAILS_COPY"), qt.ActionRole)
        copy_paste.clicked.connect(copy)

    dialog.setLayout(layout)
    dialog.show()
    app.exec_()


def fatal_error_win(text: str, /) -> None:
    """
    Display a fatal error using Windows-specific dialog.
    Taken from https://stackoverflow.com/a/27257176/1117028.
    """

    import ctypes

    MB_OK = 0x0
    ICON_STOP = 0x10

    title = f"{APP_NAME} Fatal Error"
    ctypes.windll.user32.MessageBoxW(0, text, title, MB_OK | ICON_STOP)


def fatal_error_mac(text: str, /) -> None:
    """Display a fatal error using macOS-specific dialog."""

    import subprocess

    title = f"{APP_NAME} Fatal Error"
    text = text.replace('"', r"\"")
    msg = (
        f'Tell me to display dialog "{text}" with title "{title}"'
        ' buttons {"OK"} with icon stop'
    )
    cmd = ["osascript", "-e", msg]

    subprocess.Popen(cmd)


def check_executable_path() -> bool:
    """Check that the app runs from the right path, and quit if not."""

    if not (MAC and Options.is_frozen):
        return True

    import re
    import sys
    from pathlib import Path

    exe_path = sys.executable
    m = re.match(r"(.*\.app).*", exe_path)
    path = Path(m.group(1) if m else exe_path)

    if path in (
        Path(f"/Applications/{APP_NAME}.app"),
        Path.home() / "Applications" / f"{APP_NAME}.app",
    ):
        return True

    try:
        check_executable_path_error_qt(path)
    except Exception as exc:
        full_error = (
            f"You are running this app from {path}. However, "
            "for all features to run normally, the application"
            f" must be named '{APP_NAME}.app' and located in "
            "the /Applications directory."
        )
        text = (
            f"{APP_NAME} cannot start, the entire installation is broken."
            f"\n\nOriginal error:\n{full_error}"
            f"\n\nDetails:\n{exc}"
        )
        fatal_error_mac(text)

    return False


def check_os_version() -> bool:
    """Check that the current OS version is supported."""

    if MAC:
        from distutils.version import StrictVersion
        from platform import mac_ver

        version = mac_ver()[0]
        if StrictVersion(version) < StrictVersion("10.13"):
            fatal_error_mac(
                f"macOS 10.13 (High Sierra) or newer is required (your version is {version})."
            )
            return False
    elif WINDOWS and sys.getwindowsversion()[:2] < (6, 2):
        fatal_error_win("Windows 8 or newer is required.")
        return False

    return True


def show_critical_error() -> None:
    """Display a "friendly" dialog box on fatal error."""

    import traceback

    full_error = "".join(traceback.format_exception(*sys.exc_info()))

    with suppress(Exception):
        # Note1: do not rely on Options.nxdrive_home as it may be changed in options.
        # Note2: keep that code synced with commandline.py::`HealthCheck.__init__()`.
        crash_file = Path.home() / ".nuxeo-drive" / "crash.state"
        crash_file.parent.mkdir(parents=True, exist_ok=True)
        crash_file.write_text(full_error, encoding="utf-8", errors="replace")

    try:
        fatal_error_qt(full_error)
    except Exception as exc:
        # Fallback to OS-specific dialog but only to prompt the user for installation error.
        text = (
            f"{APP_NAME} cannot start, the entire installation is broken."
            f"\n\nOriginal error:\n{full_error}"
            f"\n\nDetails:\n{exc}"
        )

        if WINDOWS:
            fatal_error_win(text)
        elif MAC:
            fatal_error_mac(text)
        else:
            # Best effort on GNU/Linux
            print(text, file=sys.stderr)
