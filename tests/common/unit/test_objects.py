from datetime import datetime, timedelta
from pathlib import Path, PureWindowsPath
from types import SimpleNamespace
from unittest.mock import Mock, patch

from nxdrive.drive import objects


def _doc_pair(**overrides):
    values = {
        "pair_state": "synchronized",
        "last_local_updated": "2026-08-05 11:00:00",
        "last_remote_updated": "2026-08-05 10:00:00",
        "last_sync_date": "2026-08-05 10:30:00",
        "last_transfer": "",
        "local_name": "local.txt",
        "remote_name": "remote.txt",
        "last_error": None,
        "local_path": Path("folder/local.txt"),
        "local_parent_path": Path("folder"),
        "remote_ref": "remote-id",
        "doc_type": "File",
        "folderish": False,
        "id": 42,
        "size": 128,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_doc_pair_export_formats_recent_download():
    pair = _doc_pair()
    sync_date = datetime(2026, 8, 5, 10, 30)
    local_zone = Mock()
    local_zone.utcoffset.return_value = timedelta(hours=2)

    with (
        patch.object(objects, "time", return_value=1_000),
        patch.object(objects, "get_date_from_sqlite", return_value=sync_date),
        patch.object(objects, "get_timestamp_from_date", return_value=900),
        patch.object(objects, "tzlocal", return_value=local_zone),
        patch.object(
            objects.Translator, "format_datetime", return_value="localized date"
        ) as format_datetime,
    ):
        result = objects.DocPair.export(pair)

    assert result == {
        "state": "synchronized",
        "last_sync_date": "localized date",
        "last_sync_direction": "download",
        "name": "local.txt",
        "remote_name": "remote.txt",
        "last_error": None,
        "local_path": str(pair.local_path),
        "local_parent_path": str(pair.local_parent_path),
        "remote_ref": "remote-id",
        "doc_type": "File",
        "folderish": False,
        "id": 42,
        "size": 128,
        "last_transfer": "download",
        "last_sync": 100,
    }
    local_zone.utcoffset.assert_called_once_with(sync_date)
    format_datetime.assert_called_once_with(sync_date + timedelta(hours=2))


def test_doc_pair_export_uses_posix_separators():
    pair = _doc_pair(
        local_path=PureWindowsPath("folder/local.txt"),
        local_parent_path=PureWindowsPath("folder"),
        last_sync_date="",
    )

    result = objects.DocPair.export(pair)

    assert result["local_path"] == "folder/local.txt"
    assert result["local_parent_path"] == "folder"


def test_doc_pair_export_handles_missing_sync_date_and_local_name():
    pair = _doc_pair(
        last_local_updated=None,
        last_remote_updated="2026-08-05 10:00:00",
        last_sync_date="",
        last_transfer="upload",
        local_name="",
        remote_name="server.txt",
    )

    with (
        patch.object(objects, "time", return_value=50),
        patch.object(objects, "get_date_from_sqlite", return_value=None),
        patch.object(objects, "get_timestamp_from_date", return_value=0),
        patch.object(objects.Translator, "format_datetime") as format_datetime,
    ):
        result = objects.DocPair.export(pair)

    assert result["last_sync_direction"] == "upload"
    assert result["last_transfer"] == "upload"
    assert result["last_sync"] == 50
    assert result["last_sync_date"] == ""
    assert result["name"] == "server.txt"
    format_datetime.assert_not_called()
