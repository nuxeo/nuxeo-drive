"""Tests for the error-handling wrappers around shared DAO backups."""

import errno
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.drive.dao import base as dao_base


def make_dao(tmp_path):
    return SimpleNamespace(db=tmp_path / "shared.db", lock=MagicMock())


@pytest.mark.parametrize(
    "method_name, dependency_name",
    [
        ("restore_backup", "restore_backup"),
        ("save_backup", "save_backup"),
    ],
)
def test_backup_wrapper_calls_utility_while_holding_lock(
    tmp_path, method_name, dependency_name
):
    dao = make_dao(tmp_path)

    with patch.object(dao_base, dependency_name, return_value=True) as backup_utility:
        result = getattr(dao_base.BaseDAO, method_name)(dao)

    assert result is True
    backup_utility.assert_called_once_with(dao.db)
    dao.lock.__enter__.assert_called_once_with()
    dao.lock.__exit__.assert_called_once_with(None, None, None)


def test_restore_backup_reraises_no_space_error(tmp_path):
    dao = make_dao(tmp_path)
    error = OSError(errno.ENOSPC, "disk full")

    with patch.object(dao_base, "restore_backup", side_effect=error), patch.object(
        dao_base.sys, "excepthook"
    ) as excepthook, pytest.raises(OSError) as exc_info:
        dao_base.BaseDAO.restore_backup(dao)

    assert exc_info.value is error
    excepthook.assert_not_called()


def test_save_backup_swallows_no_space_error_without_excepthook(tmp_path):
    dao = make_dao(tmp_path)
    error = OSError(errno.ENOSPC, "disk full")

    with patch.object(dao_base, "save_backup", side_effect=error), patch.object(
        dao_base.sys, "excepthook"
    ) as excepthook:
        result = dao_base.BaseDAO.save_backup(dao)

    assert result is False
    excepthook.assert_not_called()


@pytest.mark.parametrize(
    "method_name, dependency_name",
    [
        ("restore_backup", "restore_backup"),
        ("save_backup", "save_backup"),
    ],
)
def test_backup_wrapper_reports_other_os_errors(tmp_path, method_name, dependency_name):
    dao = make_dao(tmp_path)
    error = OSError(errno.EACCES, "denied")

    with patch.object(dao_base, dependency_name, side_effect=error), patch.object(
        dao_base.sys, "excepthook"
    ) as excepthook:
        result = getattr(dao_base.BaseDAO, method_name)(dao)

    assert result is False
    error_type, reported_error, traceback = excepthook.call_args.args
    assert error_type is type(error)
    assert reported_error is error
    assert traceback is not None


@pytest.mark.parametrize(
    "method_name, dependency_name",
    [
        ("restore_backup", "restore_backup"),
        ("save_backup", "save_backup"),
    ],
)
def test_backup_wrapper_reports_unexpected_errors(
    tmp_path, method_name, dependency_name
):
    dao = make_dao(tmp_path)
    error = RuntimeError("backup failed")

    with patch.object(dao_base, dependency_name, side_effect=error), patch.object(
        dao_base.sys, "excepthook"
    ) as excepthook:
        result = getattr(dao_base.BaseDAO, method_name)(dao)

    assert result is False
    error_type, reported_error, traceback = excepthook.call_args.args
    assert error_type is RuntimeError
    assert reported_error is error
    assert traceback is not None
