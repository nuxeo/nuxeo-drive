import logging
import os
from typing import TYPE_CHECKING, Any, Dict, Set
from uuid import uuid4

from .options import Options

if TYPE_CHECKING:
    from sentry_sdk._types import Event as _Event
    from sentry_sdk._types import Hint as _Hint
    from sentry_sdk.types import Metric as _Metric
else:
    _Event = Dict[str, Any]
    _Hint = Dict[str, Any]
    _Metric = Dict[str, Any]

# Sentry events already sent
_EVENTS: Set[int] = set()

_FIRST_RUN_METRIC = "drive.first_run"
_FIRST_RUN_ATTRIBUTES = (
    "drive.server",
    "os.version",
    "sentry.release",
    "user.id",
)
_FATAL_ERROR_MARKER = "_drive_fatal_error"
_FATAL_ERROR_MESSAGE = "Drive fatal error"


def _close_client(client: Any, /) -> None:
    import sentry_sdk

    try:
        client.close(timeout=2.0)
    finally:
        for get_scope in (
            sentry_sdk.get_current_scope,
            sentry_sdk.get_isolation_scope,
            sentry_sdk.get_global_scope,
        ):
            scope = get_scope()
            if scope.get_client() is client:
                scope.set_client(None)


def shutdown_sentry() -> None:
    """Close and detach the active Sentry client."""
    import sentry_sdk

    if sentry_sdk.is_initialized():
        _close_client(sentry_sdk.get_client())


def before_send_metric(metric: _Metric, _: _Hint, /) -> _Metric:
    """Remove automatic SDK attributes from the consent-independent metric."""
    if metric.get("name") == _FIRST_RUN_METRIC:
        attributes = metric.get("attributes", {})
        metric["attributes"] = {
            name: attributes[name]
            for name in _FIRST_RUN_ATTRIBUTES
            if name in attributes
        }
    return metric


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
    extra = event.get("extra", {})
    if _FATAL_ERROR_MARKER in extra:
        extra.pop(_FATAL_ERROR_MARKER, None)
        if not extra:
            event.pop("extra", None)
        return event

    if should_ignore(event):
        # The event will not be sent if None is returned
        return None

    return event


def setup_sentry(app_version: str, /, *, force: bool = False) -> bool:
    """Setup Sentry."""

    if not force and not (Options.use_sentry or Options.use_analytics):
        return False

    if os.getenv("SKIP_SENTRY", "0") == "1":
        return False

    sentry_dsn: str = os.getenv(
        "SENTRY_DSN",
        "https://b025db54cb1face8405a66da3ea78705@o4511315922976768.ingest.us.sentry.io/4511579252129792",
    )
    if not sentry_dsn:
        return False

    import platform

    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    from . import server_type as st
    from .metrics.utils import current_os

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=os.getenv("SENTRY_ENV", "production"),
        release=app_version,
        attach_stacktrace=True,
        include_local_variables=False,
        before_send=before_send,
        before_send_metric=before_send_metric,
        integrations=[
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)
        ],
        # Set traces_sample_rate to 1.0 to capture 100%
        # of transactions for performance monitoring.
        traces_sample_rate=1.0,
    )

    scope = sentry_sdk.get_isolation_scope()
    server_name = (Options.server_type or st.get_default_key()).upper()
    scope.set_tag("drive.server", server_name)
    scope._contexts.update(
        {
            "runtime": {"name": "Python", "version": platform.python_version()},
            "os": {"name": current_os(full=True)},
        }
    )

    return True


def capture_first_run_metric(app_version: str, server_name: str, /) -> bool:
    """Capture the non-sensitive metric emitted once per installation."""
    import sentry_sdk

    from .metrics.utils import current_os

    if sentry_sdk.is_initialized():
        return False

    client = None
    try:
        if not setup_sentry(app_version, force=True):
            return False
        client = sentry_sdk.get_client()

        sentry_sdk.metrics.count(
            _FIRST_RUN_METRIC,
            1,
            attributes={
                "drive.server": server_name,
                "os.version": current_os(full=True),
                "sentry.release": app_version,
                "user.id": str(uuid4()),
            },
        )
        sentry_sdk.flush(timeout=5.0)
    except Exception:
        return False
    finally:
        if client is None and sentry_sdk.is_initialized():
            client = sentry_sdk.get_client()
        if client is not None:
            _close_client(client)

    return True


def capture_fatal_error(exc_info: Any, traceback_text: str, logs: list[str], /) -> bool:
    """Temporarily capture a fatal exception and recent logs."""
    import sentry_sdk

    from . import constants

    initialized_here = not sentry_sdk.is_initialized()
    event_id = None
    try:
        if initialized_here and not setup_sentry(constants.APP_VERSION, force=True):
            return False

        with sentry_sdk.new_scope() as scope:
            scope.set_extra(_FATAL_ERROR_MARKER, True)
            for line in logs:
                scope.add_breadcrumb(
                    category="fatal_error.log", message=line, level="info"
                )

            if exc_info and exc_info[1] is not None:
                event_id = sentry_sdk.capture_exception(exc_info)
            else:
                scope.set_extra("fatal_error.traceback", traceback_text)
                event_id = sentry_sdk.capture_message(
                    _FATAL_ERROR_MESSAGE, level="error"
                )

        sentry_sdk.flush(timeout=5.0)
    except Exception:
        return False
    finally:
        if initialized_here and sentry_sdk.is_initialized():
            _close_client(sentry_sdk.get_client())

    return event_id is not None
