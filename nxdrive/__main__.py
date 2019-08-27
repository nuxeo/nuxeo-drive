# coding: utf-8
"""
In this file we cannot use a relative import here, else Drive will not start when packaged.
See https://github.com/pyinstaller/pyinstaller/issues/2560
"""
import os
import platform
import sys
from contextlib import suppress
from typing import Any, Set

from nxdrive.constants import APP_NAME
from nxdrive.fatal_error import check_executable_path, show_critical_error
from nxdrive.options import Options


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


def main() -> int:
    """ Entry point. """

    ret = 0

    try:
        # XXX_PYTHON
        if sys.version_info < (3, 7):
            raise RuntimeError(f"{APP_NAME} requires Python 3.7")

        if not check_executable_path():
            return 1

        # Setup Sentry even if the user did not allow it because it can be tweaked
        # later via the "use-sentry" parameter. It will be useless if Sentry is not installed first.
        setup_sentry()

        from nxdrive.commandline import CliHandler
        from nxdrive.utils import get_current_os
        from sentry_sdk import configure_scope

        with configure_scope() as scope:
            # Append OS and Python versions to all events
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


sys.exit((main()))
