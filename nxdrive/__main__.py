"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import locale
import platform
import signal
import sys
from types import FrameType

from nxdrive.constants import APP_NAME
from nxdrive.fatal_error import (
    check_executable_path,
    check_os_version,
    show_critical_error,
)


def signal_handler(signum: int, _: FrameType, /) -> None:
    """Signal handler."""
    from nxdrive.qt.imports import QApplication

    signame = signal.Signals(signum).name
    print("\r", flush=True)
    print(f" ! Caught {signame} ({signum}), gracefully exiting {APP_NAME}", flush=True)
    QApplication.quit()
    QApplication.processEvents()


def main() -> int:
    """Entry point."""

    # Catch CTRL+C
    signal.signal(signal.SIGINT, signal_handler)

    ret = 0

    try:
        # XXX_PYTHON
        if sys.version_info < (3, 9, 1):
            raise RuntimeError(f"{APP_NAME} requires Python 3.9.1+")

        # NXDRIVE-2230: Ensure the OS locale will be respected through the application
        locale.setlocale(locale.LC_TIME, "")

        if not (check_executable_path() and check_os_version()):
            return 1

        from sentry_sdk import configure_scope

        from nxdrive.commandline import CliHandler
        from nxdrive.metrics.utils import current_os
        from nxdrive.tracing import setup_sentry

        # Setup Sentry even if the user did not allow it because it can be tweaked
        # later via the "use-sentry" parameter. It will be useless if Sentry is not installed first.
        setup_sentry()

        with configure_scope() as scope:
            # Append OS and Python versions to all events
            # pylint: disable=protected-access
            scope._contexts.update(
                {
                    "runtime": {"name": "Python", "version": platform.python_version()},
                    "os": {"name": current_os(full=True)},
                }
            )

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
