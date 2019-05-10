import logging
import os
import os.path
import shutil
import sys
from contextlib import contextmanager
from typing import Any

import nuxeo.constants

from nxdrive.logging_config import configure


# Automatically check all operations done with the Python client
nuxeo.constants.CHECK_PARAMS = True


def _basename(path: str) -> str:
    """
    Patch shutil._basename for pathlib compatibility.
    TODO: remove when https://bugs.python.org/issue32689 is fixed (Python 3.7.3 or newer)
    """
    if isinstance(path, os.PathLike):
        return path.name

    sep = os.path.sep + (os.path.altsep or "")
    return os.path.basename(path.rstrip(sep))


shutil._basename = _basename


def configure_logs():
    """Configure the logging module."""

    formatter = logging.Formatter(
        "%(thread)-4d %(module)-14s %(levelname).1s %(message)s"
    )
    configure(
        console_level="DEBUG",
        command_name="test",
        force_configure=True,
        formatter=formatter,
    )


configure_logs()


def before_send(event: Any, hint: Any) -> Any:
    """
    Alter an event before sending to the Sentry server.
    The event will not be sent if None is returned.
    """

    # Do not send Mock'ed exceptions to not pollute Sentry events
    if "threads" in event:
        for thread in event["threads"]:
            for frame in thread["stacktrace"]["frames"]:
                for value in frame["vars"].values():
                    if "Mock" in value:
                        return None
    elif "exception" in event:
        for exception in event["exception"]["values"]:
            if "Mock" in exception["value"]:
                return None

    return event


def setup_sentry() -> None:
    """ Setup Sentry. """

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    sentry_dsn = os.getenv(
        "SENTRY_DSN", "https://c4daa72433b443b08bd25e0c523ecef5@sentry.io/1372714"
    )

    # Force a Sentry env while working on a specific ticket
    sentry_env = os.getenv("SENTRY_ENV", "testing")
    if "JENKINS_URL" not in os.environ and sentry_env == "testing":
        sys.exit(
            "You must set SENTRY_ENV to the working issue, e.g.: SENTRY_ENV='NXDRIVE-42'."
        )

    import sentry_sdk
    from nxdrive import __version__

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=sentry_env,
        release=__version__,
        attach_stacktrace=True,
        before_send=before_send,
        ignore_errors=[KeyboardInterrupt],
    )


setup_sentry()


@contextmanager
def ensure_no_exception():
    """
    Helper to use as a context manager to check a snippet does not throw any exception.
    Usefull when one exception is only loggued and not forwared to the parent thread.
        >>> with ensure_no_exception():
        ...     # some code where you do not want any exception
    """

    def error(type_, value, traceback) -> None:
        """ Install an exception hook to catch any error. """
        nonlocal received
        received = True
        print(type_)
        print(value)
        print(repr(traceback))

    received = False
    excepthook, sys.excepthook = sys.excepthook, error

    try:
        yield
    finally:
        sys.excepthook = excepthook

    assert not received, "Unhandled exception raised!"
