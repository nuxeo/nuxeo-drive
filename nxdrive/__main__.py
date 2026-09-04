"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""

import locale
import os
import signal
import sqlite3
import sys
from datetime import datetime
from types import FrameType

import pip_system_certs.wrapt_requests

import nxdrive  # noqa: F401  # Ensure server-type registrations run before startup checks.
from nxdrive.drive.constants import APP_NAME, WINDOWS
from nxdrive.drive.fatal_error import (
    check_executable_path,
    check_os_version,
    show_critical_error,
)
from nxdrive.drive.utils import adapt_datetime_iso

# Set Qt Quick Controls style to "Basic" to avoid loading Windows-specific plugins
# that may have missing DLL dependencies (the Windows style impl DLL is not shipped
# with PyQt6 nor PySide6 in the same layout).
# https://stackoverflow.com/questions/79568766/pyqt6-on-windows-qtquickcontrols2windowsstyleimplplugin-dll-the-specified-mod
# PySide6's Qt Quick engine honors this environment variable.
if WINDOWS:
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

pip_system_certs.wrapt_requests.inject_truststore()


def signal_handler(signum: int, _: FrameType, /) -> None:
    """Signal handler."""
    from nxdrive.drive.qt.imports import QApplication

    signame = signal.Signals(signum).name
    print("\r", flush=True)
    print(f" ! Caught {signame} ({signum}), gracefully exiting {APP_NAME}", flush=True)
    QApplication.quit()
    QApplication.processEvents()


def main() -> int:
    """Entry point."""

    # On Windows, GUI applications (built with console=False) don't have stdout/stderr
    # connected to the parent console. This is needed for CLI output like --version.
    if sys.platform == "win32":
        import ctypes

        # Try to attach to the parent console (e.g., Command Prompt or PowerShell)
        # ATTACH_PARENT_PROCESS = -1
        if ctypes.windll.kernel32.AttachConsole(-1):
            # Reopen stdout and stderr to write to the attached console
            try:
                sys.stdout = open("CONOUT$", "w")
                sys.stderr = open("CONOUT$", "w")
            except OSError as exc:
                import logging

                logging.getLogger(__name__).error(
                    "Failed to attach console output: %s", exc
                )

    # Catch CTRL+C
    signal.signal(signal.SIGINT, signal_handler)

    sqlite3.register_adapter(datetime, adapt_datetime_iso)

    ret = 0

    try:
        # XXX_PYTHON
        if sys.version_info < (3, 13, 1):
            raise RuntimeError(f"{APP_NAME} requires Python 3.13.1+")

        # NXDRIVE-2230: Ensure the OS locale will be respected through the application
        try:
            locale.setlocale(locale.LC_TIME, "")
        except locale.Error as exc:
            # NXDRIVE-2714: Not a big deal, let's not make the app crashing
            print('[ERROR] locale.setlocale(locale.LC_TIME, ""):', exc)

        if not (check_executable_path() and check_os_version()):
            return 1

        from nxdrive.drive.commandline import CliHandler

        ret = CliHandler().handle(sys.argv[1:])
    except SystemExit as exc:
        if exc.code != 0:
            show_critical_error()
        ret = exc.code
    except Exception:
        show_critical_error()
        ret = 1

    return ret


sys.exit(main())
