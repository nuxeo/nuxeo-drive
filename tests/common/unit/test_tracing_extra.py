"""Focused tests for deterministic Sentry setup behavior."""

import logging
from types import SimpleNamespace
from unittest.mock import patch

import sentry_sdk

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


def test_setup_sentry_initializes_for_advanced_analytics(monkeypatch):
    Options.use_analytics = True
    Options.use_sentry = False
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    scope = SimpleNamespace(_contexts={})

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
    monkeypatch.delenv("SKIP_SENTRY", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENV", "test-environment")
    scope = SimpleNamespace(_contexts={"preserved": {"value": True}})

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
        before_send=tracing.before_send,
        integrations=[logging_integration.return_value],
        traces_sample_rate=1.0,
    )
    logging_integration.assert_called_once_with(
        level=logging.INFO, event_level=logging.ERROR
    )
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
