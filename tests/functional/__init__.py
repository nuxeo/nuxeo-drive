# coding: utf-8
import os
from typing import Any


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

    # TODO: Remove the testing DSN
    sentry_dsn = os.getenv(
        "SENTRY_DSN", "https://c4daa72433b443b08bd25e0c523ecef5@sentry.io/1372714"
    )

    import sentry_sdk
    from nxdrive import __version__

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "testing"),
        release=__version__,
        attach_stacktrace=True,
        before_send=before_send,
    )


setup_sentry()
