import logging
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

    exception_values = event.get("exception", {}).get("values", [])
    if exception_values:
        frames = exception_values[0].get("stacktrace", {}).get("frames", [])
    else:
        thread_values = event.get("threads", {}).get("values", [])
        frames = [
            frame
            for thread in thread_values
            for frame in thread.get("stacktrace", {}).get("frames", [])
        ]

    frame_locations = sorted(
        f"{frame['filename']}:{frame['lineno']}"
        for frame in frames
        if frame.get("filename") is not None and frame.get("lineno") is not None
    )
    if not frame_locations:
        return False

    # Compute a "fingerprint" of the stacktrace. Pseudo-code:
    # hash(
    #     "nxdrive/engine/activity.py:262",
    #     "nxdrive/engine/watcher/local_watcher.py:99",
    #     "nxdrive/engine/watcher/local_watcher.py:275",
    #     "nxdrive/engine/watcher/local_watcher.py:283",
    #     "nxdrive/engine/workers.py:196",
    # )
    fingerprint = hash(tuple(frame_locations))
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


def setup_sentry(app_version: str) -> None:
    """Setup Sentry."""

    if not (Options.use_sentry or Options.use_analytics):
        return

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return

    sentry_dsn: str = os.getenv(
        "SENTRY_DSN",
        "https://b025db54cb1face8405a66da3ea78705@o4511315922976768.ingest.us.sentry.io/4511579252129792",
    )
    if not sentry_dsn:
        return

    import platform

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    from .metrics.utils import current_os

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        release=app_version,
        attach_stacktrace=True,
        before_send=before_send,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        ],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
    )

    scope = sentry_sdk.get_isolation_scope()
    scope._contexts.update(
        {
            "runtime": {"name": "Python", "version": platform.python_version()},
            "os": {"name": current_os(full=True)},
        }
    )
