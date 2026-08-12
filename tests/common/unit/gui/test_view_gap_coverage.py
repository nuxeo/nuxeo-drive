"""Focused tests for uncovered list-model role and error branches."""

from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.gui.view import (
    ActiveDirectDownloadModel,
    ActiveSessionModel,
    CompletedDirectDownloadModel,
    CompletedSessionModel,
    DirectTransferModel,
    EngineModel,
    FileModel,
    LanguageModel,
    TransferModel,
    format_file_names_for_display,
)
from nxdrive.drive.qt import constants as qt


def translate(key, values=None):
    return f"{key}:{values}" if values else key


def test_engine_get_missing_engine_and_remove_rows_failure():
    application = SimpleNamespace(manager=SimpleNamespace(engines={}))
    model = EngineModel(application)
    model.engines_uid = ["missing"]
    assert model.get(0) == ""

    model.engines_uid = []
    assert model.removeRows(0, 1) is False


def test_transfer_missing_download_progress_role_and_path_match(tmp_path):
    model = TransferModel(translate)
    missing = tmp_path / "missing.partial"
    transfer = {
        "uid": "one",
        "name": "file.txt",
        "status": TransferStatus.ONGOING,
        "progress": 0.0,
        "transfer_type": "download",
        "engine": "engine",
        "doc_pair": 1,
        "path": Path("folder/file.txt"),
        "tmpname": missing,
        "filesize": 100,
        "is_direct_edit": False,
    }
    model.set_transfers([transfer])
    index = model.index(0, 0)

    assert "0" in model.data(index, model.PROGRESS_METRICS)
    assert model.setData(index, 1) is None
    model.set_progress(
        {
            "filepath": str(transfer["path"]),
            "progress": 25.0,
            "action_type": "Transfer",
            "speed": 2.0,
        }
    )
    assert transfer["progress"] == 25.0


def test_direct_transfer_finalizing_role_none_and_nonmatching_progress():
    model = DirectTransferModel(translate)
    first = {
        "uid": "one",
        "name": "one",
        "status": TransferStatus.ONGOING,
        "progress": 10.0,
        "engine": "first",
        "doc_pair": 1,
        "filesize": 100,
        "remote_parent_path": "/",
        "remote_parent_ref": "root",
        "finalizing": True,
    }
    second = dict(first, uid="two", engine="second", doc_pair=2, finalizing=False)
    model.items = [first, second]

    assert model.data(model.index(0, 0), model.FINALIZING) is True
    assert model.setData(model.index(0, 0), False) is None
    model.set_progress(
        {
            "engine": "second",
            "doc_pair": 2,
            "progress": 50.0,
            "action_type": "Transfer",
        }
    )
    assert first["progress"] == 10.0
    assert second["progress"] == 50.0


@pytest.mark.parametrize("model_class", [ActiveSessionModel, CompletedSessionModel])
def test_session_models_set_data_and_ignore_role_none(model_class):
    model = model_class(translate)
    session = {
        "uid": 1,
        "status": TransferStatus.ONGOING,
        "remote_ref": "ref",
        "remote_path": Path("/path"),
        "uploaded": 1,
        "total": 2,
        "planned_items": 2,
        "engine": "engine",
        "created_on": datetime.now().isoformat(),
        "completed_on": None,
        "description": "description",
    }
    model.sessions = [session]
    index = model.index(0, 0)

    assert model.setData(index, "ignored") is None
    model.setData(index, "changed", role=model.DESCRIPTION)
    assert session["description"] == "changed"


def test_long_single_file_name_is_truncated():
    result = format_file_names_for_display(["x" * 100, "second"], max_length=20)
    assert len(result) == 20
    assert result.endswith("... +1")


def test_direct_download_dates_apply_nonzero_local_offset():
    active = ActiveDirectDownloadModel(translate)
    completed = CompletedDirectDownloadModel(translate)
    row = {
        "uid": 1,
        "created_at": "2026-01-02 03:04:05",
        "completed_at": "2026-01-02 03:04:05",
        "status": "COMPLETED",
    }
    active.downloads = [row]
    completed.downloads = [row]
    offset = timedelta(hours=1)

    with (
        patch("nxdrive.drive.gui.view.tzlocal") as local_timezone,
        patch("nxdrive.drive.gui.view.Translator.format_datetime", return_value="date"),
    ):
        local_timezone.return_value.utcoffset.return_value = offset
        assert active.data(active.index(0, 0), active.CREATED_AT).startswith(
            "STARTED_ON"
        )
        assert completed.data(completed.index(0, 0), completed.COMPLETED_AT).startswith(
            "COMPLETED_ON"
        )


def test_active_download_count_without_shadow_delegates():
    model = ActiveDirectDownloadModel(translate)
    model.row_count_no_shadow = Mock(return_value=3)
    assert model.count_no_shadow == 3


def test_file_model_none_role_and_editable_flags():
    model = FileModel(translate)
    model.files = [{"state": "synced"}]
    index = model.index(0, 0)

    assert model.setData(index, "ignored") is None
    flags = model.flags(index)
    assert flags == qt.ItemIsEditable | qt.ItemIsEnabled | qt.ItemIsSelectable


def test_language_unknown_role_and_remove_failure():
    model = LanguageModel()
    model.languages = [("en", "English")]
    assert model.data(model.index(0, 0), qt.UserRole + 99) == ""

    model.languages = []
    assert model.removeRows(0, 1) is False
