import logging
import os
import os.path
import re
import subprocess
import sys
from contextlib import contextmanager
from typing import Any

import nuxeo.constants

# Silence any logging errors, we do not need more noise to output
logging.raiseExceptions = False


# Automatically check all operations done with the Python client
nuxeo.constants.CHECK_PARAMS = True


def configure_logs():
    """Configure the logging module."""

    from nxdrive.logging_config import configure

    configure(
        console_level="DEBUG",
        command_name="test",
        force_configure=True,
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
    """Setup Sentry."""

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    # Guess the current the branch name
    cmd = ["git", "rev-parse", "--abbrev-ref", "HEAD"]
    branch = subprocess.check_output(cmd, encoding="utf-8").strip()
    if branch == "HEAD" and "GITHUB_HEAD_REF" in os.environ:
        # Guess from the special envar set in GitHub Actions
        branch = os.environ["GITHUB_HEAD_REF"].split("/")[-1]

    # Guess the current ticket to use for the SENTRY_ENV envar
    ticket = re.findall(r".+-((NXDRIVE|NXP)-\d+)-.+", branch)
    sentry_env = ticket[0] if ticket else "testing"

    import sentry_sdk

    from nxdrive import __version__

    sentry_dsn = os.getenv(
        "SENTRY_DSN", "https://c4daa72433b443b08bd25e0c523ecef5@sentry.io/1372714"
    )

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
    Useful when one exception is only loggued and not forwarded to the parent thread.
        >>> with ensure_no_exception():
        ...     # some code where you do not want any exception
    """

    def error(type_, value, traceback) -> None:
        """Install an exception hook to catch any error."""
        # Mock'ed errors should not entrave the check
        if "mock" in str(value).lower():
            return

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
