from unittest.mock import Mock

from tests import conftest as test_config


def test_sessionfinish_returns_normally_on_windows(monkeypatch):
    exit_process = Mock()
    monkeypatch.setattr(test_config.os, "_exit", exit_process)
    monkeypatch.setattr(test_config.sys, "platform", "win32")

    test_config.pytest_sessionfinish(None, 0)

    exit_process.assert_not_called()


def test_sessionfinish_forces_exit_on_other_platforms(monkeypatch):
    exit_process = Mock()
    monkeypatch.setattr(test_config.os, "_exit", exit_process)
    monkeypatch.setattr(test_config.sys, "platform", "linux")

    test_config.pytest_sessionfinish(None, 3)

    exit_process.assert_called_once_with(3)
