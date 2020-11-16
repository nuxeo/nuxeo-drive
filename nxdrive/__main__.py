# coding: utf-8
"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import locale
import os
import platform
import signal
import sys
from contextlib import suppress
from types import FrameType
from typing import Any, Set

from nxdrive.constants import APP_NAME, MAC
from nxdrive.fatal_error import (
    check_executable_path,
    check_os_version,
    show_critical_error,
)
from nxdrive.options import Options

if MAC:
    # NXDRIVE-2270: this envar is required in order to support Big Sur.
    #
    # From Tor Arne Vestbø, a Qt core-dev:
    #
    #   macOS nowadays (10.14 and above) defaults to apps using CoreAnimation layers for their views,
    #   if the app was built using Xcode 10 or above, to opt in to this behavior.
    #
    #   The legacy code path, surface-backed views, appears to have regressed in macOS Big Sur.
    #   It may be an issue in Qt's use of this mode, or a regression in macOS, or both, but
    #   investigating it is not a high priority.
    #
    #   The QT_MAC_WANTS_LAYER environment variable tells Qt to use layers even if it's not
    #   automatically enabled by macOS based on the Xcode version you used to build.
    #
    #   Clarification: Layer-backed views are not a problem on newer macOS, surface-backed views are.
    os.environ["QT_MAC_WANTS_LAYER"] = "1"


def before_send(event: Any, _hint: Any) -> Any:
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


def setup_sentry() -> None:
    """ Setup Sentry. """

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    sentry_dsn: str = os.getenv(
        "SENTRY_DSN",
        "https://c4daa72433b443b08bd25e0c523ecef5@o223531.ingest.sentry.io/1372714",
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
        auto_enabling_integrations=False,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
    )


def signal_handler(signum: int, frame: FrameType) -> None:
    """Signal handler."""
    from PyQt5.QtWidgets import QApplication

    signame = signal.Signals(signum).name
    print("\r", flush=True)
    print(f" ! Caught {signame} ({signum}), gracefully exiting {APP_NAME}", flush=True)
    QApplication.quit()
    QApplication.processEvents()


def main() -> int:
    """ Entry point. """

    # Catch CTRL+C
    signal.signal(signal.SIGINT, signal_handler)

    ret = 0

    try:
        # XXX_PYTHON
        if sys.version_info < (3, 7):
            raise RuntimeError(f"{APP_NAME} requires Python 3.7")

        # NXDRIVE-2230: Ensure the OS locale will be respected through the application
        locale.setlocale(locale.LC_TIME, "")

        if not (check_executable_path() and check_os_version()):
            return 1

        # Setup Sentry even if the user did not allow it because it can be tweaked
        # later via the "use-sentry" parameter. It will be useless if Sentry is not installed first.
        setup_sentry()

        from sentry_sdk import configure_scope

        from nxdrive.commandline import CliHandler
        from nxdrive.utils import get_current_os

        with configure_scope() as scope:
            # Append OS and Python versions to all events
            # pylint: disable=protected-access
            os_name, os_version = get_current_os()
            scope._contexts.update(
                {
                    "runtime": {"name": "Python", "version": platform.python_version()},
                    "os": {"name": os_name, "version": os_version},
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
