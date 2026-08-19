"""Focused tests for deterministic Sentry setup behavior."""

import logging
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import sentry_sdk

from nxdrive.drive import constants as drive_constants
from nxdrive.drive import tracing
from nxdrive.drive.metrics import utils as metrics_utils
from nxdrive.drive.options import Options


def enable_sentry() -> None:
    Options.is_frozen = True
    Options.is_alpha = False
    Options.use_analytics = False
    Options.use_sentry = True


def test_setup_sentry_returns_without_consent(monkeypatch):
    Options.use_analytics = False
    Options.use_sentry = False

    with patch.object(sentry_sdk, "init") as init:
        tracing.setup_sentry("9.8.7")

    init.assert_not_called()


def test_setup_sentry_force_bypasses_consent(monkeypatch):
    Options.use_analytics = False
    Options.use_sentry = False
    monkeypatch.setenv("SKIP_SENTRY", "0")
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    scope = SimpleNamespace(_contexts={}, set_tag=MagicMock())

    with patch.object(sentry_sdk, "init") as init, patch.object(
        sentry_sdk, "get_isolation_scope", return_value=scope
    ):
        assert tracing.setup_sentry("9.8.7", force=True) is True

    init.assert_called_once()


def test_setup_sentry_initializes_for_advanced_analytics(monkeypatch):
    Options.use_analytics = True
    Options.use_sentry = False
    monkeypatch.setenv("SKIP_SENTRY", "0")
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    scope = SimpleNamespace(_contexts={}, set_tag=MagicMock())

    with patch.object(sentry_sdk, "init") as init, patch.object(
        sentry_sdk, "get_isolation_scope", return_value=scope
    ):
        tracing.setup_sentry("9.8.7")

    init.assert_called_once()


def test_advanced_analytics_does_not_enable_error_events():
    Options.use_analytics = True
    Options.use_sentry = False

    assert tracing.before_send({"message": "error"}, {}) is None


def test_setup_sentry_returns_when_explicitly_skipped(monkeypatch):
    enable_sentry()
    monkeypatch.setenv("SKIP_SENTRY", "1")

    with patch.object(sentry_sdk, "init") as init:
        tracing.setup_sentry("9.8.7")

    init.assert_not_called()


def test_setup_sentry_returns_when_dsn_is_empty(monkeypatch):
    enable_sentry()
    monkeypatch.delenv("SKIP_SENTRY", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "")

    with patch.object(sentry_sdk, "init") as init:
        tracing.setup_sentry("9.8.7")

    init.assert_not_called()


def test_setup_sentry_initializes_client_and_runtime_context(monkeypatch):
    enable_sentry()
    Options.server_type = "ALFRESCO"
    monkeypatch.delenv("SKIP_SENTRY", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENV", "test-environment")
    scope = SimpleNamespace(
        _contexts={"preserved": {"value": True}}, set_tag=MagicMock()
    )

    with patch.object(sentry_sdk, "init") as init, patch(
        "sentry_sdk.integrations.logging.LoggingIntegration"
    ) as logging_integration, patch.object(
        sentry_sdk, "get_isolation_scope", return_value=scope
    ), patch(
        "platform.python_version", return_value="3.test"
    ), patch.object(
        metrics_utils, "current_os", return_value="Test OS"
    ) as current_os:
        tracing.setup_sentry("9.8.7")

    init.assert_called_once_with(
        dsn="https://public@example.invalid/1",
        environment="test-environment",
        release="9.8.7",
        attach_stacktrace=True,
        include_local_variables=False,
        before_send=tracing.before_send,
        before_send_metric=tracing.before_send_metric,
        integrations=[logging_integration.return_value],
        traces_sample_rate=1.0,
    )
    logging_integration.assert_called_once_with(
        level=logging.INFO, event_level=logging.ERROR
    )
    scope.set_tag.assert_called_once_with("drive.server", "ALFRESCO")
    current_os.assert_called_once_with(full=True)
    assert scope._contexts == {
        "preserved": {"value": True},
        "runtime": {"name": "Python", "version": "3.test"},
        "os": {"name": "Test OS"},
    }


def test_before_send_accepts_and_deduplicates_error_log_events():
    event = {
        "threads": {
            "values": [
                {
                    "stacktrace": {
                        "frames": [
                            {"filename": "nxdrive/drive/example.py", "lineno": 42}
                        ]
                    }
                }
            ]
        }
    }

    tracing._EVENTS.clear()

    assert tracing.before_send(event, {}) is event
    assert tracing.before_send(event, {}) is None

    tracing._EVENTS.clear()


def test_before_send_accepts_frames_without_locations():
    event = {
        "threads": {"values": [{"stacktrace": {"frames": [{"function": "worker"}]}}]}
    }

    tracing._EVENTS.clear()

    assert tracing.before_send(event, {}) is event
    assert tracing.before_send(event, {}) is event
    assert not tracing._EVENTS


def test_before_send_metric_sanitizes_first_run_metric():
    metric = {
        "name": tracing._FIRST_RUN_METRIC,
        "type": "counter",
        "value": 1.0,
        "attributes": {
            "drive.server": "NUXEO",
            "os.version": "macOS 15.6.0",
            "sentry.release": "9.8.7",
            "user.id": "123e4567-e89b-12d3-a456-426614174000",
            "server.address": "sensitive-hostname",
            "sdk.name": "sentry.python",
        },
    }

    assert tracing.before_send_metric(metric, {}) is metric
    assert metric["attributes"] == {
        "drive.server": "NUXEO",
        "os.version": "macOS 15.6.0",
        "sentry.release": "9.8.7",
        "user.id": "123e4567-e89b-12d3-a456-426614174000",
    }


def test_before_send_metric_preserves_advanced_analytics_attributes():
    metric = {
        "name": "drive.sync.duration",
        "attributes": {
            "handler": "upload",
            "sentry.environment": "production",
        },
    }

    assert tracing.before_send_metric(metric, {}) is metric
    assert metric["attributes"] == {
        "handler": "upload",
        "sentry.environment": "production",
    }


def test_capture_first_run_metric(monkeypatch):
    monkeypatch.setattr(tracing, "setup_sentry", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: False)
    monkeypatch.setattr(
        tracing, "uuid4", lambda: "123e4567-e89b-12d3-a456-426614174000"
    )

    client = MagicMock()
    with patch.object(sentry_sdk.metrics, "count") as count, patch.object(
        sentry_sdk, "flush"
    ) as flush, patch.object(
        sentry_sdk, "get_client", return_value=client
    ), patch.object(
        tracing, "_close_client"
    ) as close_client, patch.object(
        metrics_utils, "current_os", return_value="Test OS 1.2.3"
    ):
        assert tracing.capture_first_run_metric("9.8.7", "ALFRESCO") is True

    count.assert_called_once_with(
        tracing._FIRST_RUN_METRIC,
        1,
        attributes={
            "drive.server": "ALFRESCO",
            "os.version": "Test OS 1.2.3",
            "sentry.release": "9.8.7",
            "user.id": "123e4567-e89b-12d3-a456-426614174000",
        },
    )
    flush.assert_called_once_with(timeout=5.0)
    close_client.assert_called_once_with(client)


def test_capture_first_run_metric_returns_false_when_setup_is_blocked(monkeypatch):
    monkeypatch.setattr(tracing, "setup_sentry", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: False)

    with patch.object(sentry_sdk.metrics, "count") as count, patch.object(
        tracing, "_close_client"
    ) as close_client:
        assert tracing.capture_first_run_metric("9.8.7", "ALFRESCO") is False

    count.assert_not_called()
    close_client.assert_not_called()


def test_capture_first_run_metric_closes_client_when_emission_fails(monkeypatch):
    monkeypatch.setattr(tracing, "setup_sentry", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: False)
    client = MagicMock()

    with patch.object(
        sentry_sdk.metrics, "count", side_effect=RuntimeError("failure")
    ), patch.object(
        sentry_sdk, "get_client", return_value=client
    ), patch.object(
        tracing, "_close_client"
    ) as close_client:
        assert tracing.capture_first_run_metric("9.8.7", "ALFRESCO") is False

    close_client.assert_called_once_with(client)


def test_capture_first_run_metric_closes_partially_initialized_client(monkeypatch):
    client = MagicMock()
    initialized = iter((False, True))
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: next(initialized))

    with patch.object(
        tracing, "setup_sentry", side_effect=RuntimeError("initialization failure")
    ), patch.object(
        sentry_sdk, "get_client", return_value=client
    ), patch.object(
        tracing, "_close_client"
    ) as close_client:
        assert tracing.capture_first_run_metric("9.8.7", "ALFRESCO") is False

    close_client.assert_called_once_with(client)


def test_shutdown_sentry_closes_and_detaches_active_client(monkeypatch):
    client = MagicMock()
    current_scope = MagicMock()
    isolation_scope = MagicMock()
    global_scope = MagicMock()
    for scope in (current_scope, isolation_scope, global_scope):
        scope.get_client.return_value = client

    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: True)
    with patch.object(sentry_sdk, "get_client", return_value=client), patch.object(
        sentry_sdk, "get_current_scope", return_value=current_scope
    ), patch.object(
        sentry_sdk, "get_isolation_scope", return_value=isolation_scope
    ), patch.object(
        sentry_sdk, "get_global_scope", return_value=global_scope
    ):
        tracing.shutdown_sentry()

    client.close.assert_called_once_with(timeout=2.0)
    current_scope.set_client.assert_called_once_with(None)
    isolation_scope.set_client.assert_called_once_with(None)
    global_scope.set_client.assert_called_once_with(None)


@Options.mock()
def test_capture_fatal_error_temporarily_initializes_sentry(monkeypatch):
    Options.use_sentry = False
    Options.use_analytics = False
    exc = RuntimeError("failure")
    exc_info = (RuntimeError, exc, None)
    scope = MagicMock()
    scope_context = MagicMock()
    scope_context.__enter__.return_value = scope
    client = MagicMock()
    current_scope = MagicMock()
    isolation_scope = MagicMock()
    global_scope = MagicMock()
    for sentry_scope in (current_scope, isolation_scope, global_scope):
        sentry_scope.get_client.return_value = client
    initialized = iter((False, True))

    monkeypatch.setattr(
        sentry_sdk, "is_initialized", lambda: next(initialized, True)
    )
    with patch.object(tracing, "setup_sentry", return_value=True) as setup, patch.object(
        sentry_sdk, "new_scope", return_value=scope_context
    ), patch.object(
        sentry_sdk, "capture_exception", return_value="event-id"
    ) as capture_exception, patch.object(
        sentry_sdk, "flush"
    ) as flush, patch.object(
        sentry_sdk, "get_client", return_value=client
    ), patch.object(
        sentry_sdk, "get_current_scope", return_value=current_scope
    ), patch.object(
        sentry_sdk, "get_isolation_scope", return_value=isolation_scope
    ), patch.object(
        sentry_sdk, "get_global_scope", return_value=global_scope
    ):
        assert tracing.capture_fatal_error(
            exc_info, "formatted traceback", ["first log", "second log"]
        ) is True

    setup.assert_called_once_with(drive_constants.APP_VERSION, force=True)
    scope.set_extra.assert_called_once_with(tracing._FATAL_ERROR_MARKER, True)
    assert scope.add_breadcrumb.call_args_list == [
        call(category="fatal_error.log", message="first log", level="info"),
        call(category="fatal_error.log", message="second log", level="info"),
    ]
    capture_exception.assert_called_once_with(exc_info)
    flush.assert_called_once_with(timeout=5.0)
    client.close.assert_called_once_with(timeout=2.0)
    current_scope.set_client.assert_called_once_with(None)
    isolation_scope.set_client.assert_called_once_with(None)
    global_scope.set_client.assert_called_once_with(None)
    assert Options.use_sentry is False
    assert Options.use_analytics is False


def test_capture_fatal_error_reuses_initialized_sentry(monkeypatch):
    scope = MagicMock()
    scope_context = MagicMock()
    scope_context.__enter__.return_value = scope
    client = MagicMock()
    monkeypatch.setattr(sentry_sdk, "is_initialized", lambda: True)

    with patch.object(tracing, "setup_sentry") as setup, patch.object(
        sentry_sdk, "new_scope", return_value=scope_context
    ), patch.object(
        sentry_sdk, "capture_message", return_value="event-id"
    ) as capture_message, patch.object(
        sentry_sdk, "flush"
    ), patch.object(
        sentry_sdk, "get_client", return_value=client
    ):
        assert tracing.capture_fatal_error(
            (None, None, None), "formatted traceback", []
        ) is True

    setup.assert_not_called()
    scope.set_extra.assert_has_calls(
        [
            call(tracing._FATAL_ERROR_MARKER, True),
            call("fatal_error.traceback", "formatted traceback"),
        ]
    )
    capture_message.assert_called_once_with(
        tracing._FATAL_ERROR_MESSAGE, level="error"
    )
    client.close.assert_not_called()
