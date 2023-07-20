import os
from typing import Any, Dict, Set

from .options import Options

# From sentry_sdk._types
_Event = Dict[str, Any]
_Hint = Dict[str, Any]

# Sentry events already sent
_EVENTS: Set[int] = set()


def should_ignore(event: _Event) -> bool:
    """Return False if the event can be sent to Sentry."""
    # Sentry may have been disabled later, via a CLI argument or GUI parameter
    if not Options.use_sentry:
        return True

    # Compute a "fingerprint" of the stacktrace. Peusdo-code:
    # hash(
    #     "nxdrive/engine/activity.py:262",
    #     "nxdrive/engine/watcher/local_watcher.py:99",
    #     "nxdrive/engine/watcher/local_watcher.py:275",
    #     "nxdrive/engine/watcher/local_watcher.py:283",
    #     "nxdrive/engine/workers.py:196",
    # )
    fingerprint = hash(
        tuple(
            sorted(
                f"{err['filename']}:{err['lineno']}"
                for err in event["exception"]["values"][0]["stacktrace"]["frames"]
            )
        )
    )
    if fingerprint in _EVENTS:
        return True
    _EVENTS.add(fingerprint)

    return False


def before_send(event: _Event, _: _Hint, /) -> Any:
    """Alter an event before sending to the Sentry server."""
    if should_ignore(event):
        # The event will not be sent if None is returned
        return None

    return event


def setup_sentry() -> None:
    """Setup Sentry."""

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    sentry_dsn: str = os.getenv(
        "SENTRY_DSN",
        "https://c4daa72433b443b08bd25e0c523ecef5@o223531.ingest.sentry.io/1372714",
    )
    if not sentry_dsn:
        return

    import sentry_sdk

    from . import __version__

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        release=__version__,
        attach_stacktrace=True,
        before_send=before_send,
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
    )
