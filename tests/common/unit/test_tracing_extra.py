"""Focused tests for deterministic Sentry setup behavior."""

from types import SimpleNamespace
from unittest.mock import patch

import sentry_sdk

from nxdrive.drive import tracing
from nxdrive.drive.metrics import utils as metrics_utils


def test_setup_sentry_returns_when_explicitly_skipped(monkeypatch):
    monkeypatch.setenv("SKIP_SENTRY", "1")

    with patch.object(sentry_sdk, "init") as init:
        tracing.setup_sentry("9.8.7")

    init.assert_not_called()


def test_setup_sentry_returns_when_dsn_is_empty(monkeypatch):
    monkeypatch.delenv("SKIP_SENTRY", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "")

    with patch.object(sentry_sdk, "init") as init:
        tracing.setup_sentry("9.8.7")

    init.assert_not_called()


def test_setup_sentry_initializes_client_and_runtime_context(monkeypatch):
    monkeypatch.delenv("SKIP_SENTRY", raising=False)
    monkeypatch.setenv("SENTRY_DSN", "https://public@example.invalid/1")
    monkeypatch.setenv("SENTRY_ENV", "test-environment")
    scope = SimpleNamespace(_contexts={"preserved": {"value": True}})

    with patch.object(sentry_sdk, "init") as init, patch.object(
        sentry_sdk, "get_isolation_scope", return_value=scope
    ), patch("platform.python_version", return_value="3.test"), patch.object(
        metrics_utils, "current_os", return_value="Test OS"
    ) as current_os:
        tracing.setup_sentry("9.8.7")

    init.assert_called_once_with(
        dsn="https://public@example.invalid/1",
        environment="test-environment",
        release="9.8.7",
        attach_stacktrace=True,
        before_send=tracing.before_send,
        traces_sample_rate=1.0,
    )
    current_os.assert_called_once_with(full=True)
    assert scope._contexts == {
        "preserved": {"value": True},
        "runtime": {"name": "Python", "version": "3.test"},
        "os": {"name": "Test OS"},
    }
