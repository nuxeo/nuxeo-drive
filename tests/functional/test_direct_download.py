"""
Functional tests for nxdrive.direct_download module.

These tests verify the DirectDownload feature working with a real Manager
instance and DAO, using mocks only for remote server interactions.
"""

from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import Mock, patch

import pytest

from nxdrive.constants import DirectDownloadStatus
from nxdrive.dao.engine import EngineDAO
from nxdrive.gui.view import (
    ActiveDirectDownloadModel,
    CompletedDirectDownloadModel,
    DirectDownloadMonitoringModel,
    format_file_names_for_display,
)
from nxdrive.objects import DirectDownload as DirectDownloadRecord
from nxdrive.options import Options
from nxdrive.qt.imports import QModelIndex
from nxdrive.translator import Translator
from nxdrive.utils import find_resource

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def dao(tmp_path, app):
    """Create a real EngineDAO with the DirectDownloads table."""
    db_path = tmp_path / "test_dd.db"
    dao = EngineDAO(db_path)
    yield dao
    dao.dispose()


@pytest.fixture()
def translate():
    """Provide a translate function for view models.

    Uses the Translator instance methods directly instead of the static
    ``Translator.get`` / ``Translator.format_datetime`` helpers because
    other test modules (e.g. test_notification.py) may permanently mock
    those static methods at module-level, contaminating parallel xdist
    workers.
    """
    translator = Translator(find_resource("i18n"), lang="en")

    def _translate(message: str, /, *, values: List[Any] = None) -> str:
        return translator.get_translation(message, values=values)

    def _real_format_datetime(date, /):
        fmt = translator.get_translation("DATETIME_FORMAT")
        return date.strftime(fmt)

    with patch.object(
        Translator, "format_datetime", staticmethod(_real_format_datetime)
    ):
        yield _translate


def _make_record(
    doc_uid="uid-1",
    doc_name="test.pdf",
    doc_size=1024,
    server_url="https://server.com",
    status=DirectDownloadStatus.PENDING,
    engine="engine-1",
    is_folder=False,
    zip_file=None,
    selected_items=None,
    file_count=1,
    folder_count=0,
    bytes_downloaded=0,
    total_bytes=1024,
):
    return DirectDownloadRecord(
        uid=None,
        doc_uid=doc_uid,
        doc_name=doc_name,
        doc_size=doc_size,
        download_path=None,
        server_url=server_url,
        status=status,
        bytes_downloaded=bytes_downloaded,
        total_bytes=total_bytes,
        progress_percent=0.0,
        created_at=datetime.now(timezone.utc),
        started_at=None,
        completed_at=None,
        is_folder=is_folder,
        folder_count=folder_count,
        file_count=file_count,
        retry_count=0,
        last_error=None,
        engine=engine,
        zip_file=zip_file,
        selected_items=selected_items,
    )


# ---------------------------------------------------------------------------
# DAO Functional Tests
# ---------------------------------------------------------------------------


class TestDAODirectDownloadCRUD:
    """Functional tests for EngineDAO direct download CRUD operations."""

    def test_save_and_get(self, dao):
        """Test saving and retrieving a download record."""
        record = _make_record()
        uid = dao.save_direct_download(record)
        assert uid > 0

        fetched = dao.get_direct_download(uid)
        assert fetched is not None
        assert fetched.doc_uid == "uid-1"
        assert fetched.doc_name == "test.pdf"
        assert fetched.status == DirectDownloadStatus.PENDING

    def test_get_nonexistent(self, dao):
        """Test retrieving a nonexistent record returns None."""
        assert dao.get_direct_download(9999) is None

    def test_save_multiple(self, dao):
        """Test saving multiple records."""
        uid1 = dao.save_direct_download(_make_record(doc_uid="a"))
        uid2 = dao.save_direct_download(_make_record(doc_uid="b"))
        assert uid1 != uid2
        assert dao.get_direct_download(uid1).doc_uid == "a"
        assert dao.get_direct_download(uid2).doc_uid == "b"

    def test_get_all_direct_downloads(self, dao):
        """Test get_direct_downloads returns all records."""
        dao.save_direct_download(_make_record(doc_uid="a"))
        dao.save_direct_download(_make_record(doc_uid="b"))
        results = list(dao.get_direct_downloads())
        assert len(results) == 2

    def test_get_with_status_filter(self, dao):
        """Test get_direct_downloads_with_status filters correctly."""
        dao.save_direct_download(
            _make_record(doc_uid="a", status=DirectDownloadStatus.PENDING)
        )
        dao.save_direct_download(
            _make_record(doc_uid="b", status=DirectDownloadStatus.COMPLETED)
        )
        pending = dao.get_direct_downloads_with_status(DirectDownloadStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].doc_uid == "a"

    def test_update_direct_download(self, dao):
        """Test updating a download record."""
        uid = dao.save_direct_download(_make_record())
        record = dao.get_direct_download(uid)
        record.doc_name = "updated.pdf"
        record.download_path = "/downloads/updated.pdf"
        dao.update_direct_download(record)

        fetched = dao.get_direct_download(uid)
        assert fetched.doc_name == "updated.pdf"
        assert fetched.download_path == "/downloads/updated.pdf"

    def test_delete_direct_download(self, dao):
        """Test deleting a download record."""
        uid = dao.save_direct_download(_make_record())
        dao.delete_direct_download(uid)
        assert dao.get_direct_download(uid) is None

    def test_delete_completed(self, dao):
        """Test delete_completed_direct_downloads."""
        dao.save_direct_download(
            _make_record(doc_uid="a", status=DirectDownloadStatus.COMPLETED)
        )
        dao.save_direct_download(
            _make_record(doc_uid="b", status=DirectDownloadStatus.COMPLETED)
        )
        dao.save_direct_download(
            _make_record(doc_uid="c", status=DirectDownloadStatus.PENDING)
        )
        count = dao.delete_completed_direct_downloads()
        assert count == 2
        remaining = list(dao.get_direct_downloads())
        assert len(remaining) == 1
        assert remaining[0].doc_uid == "c"


class TestDAODirectDownloadStatus:
    """Test DAO status update methods."""

    def test_update_status_in_progress(self, dao):
        """Test setting status to IN_PROGRESS sets started_at."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(uid, DirectDownloadStatus.IN_PROGRESS)
        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.IN_PROGRESS
        assert record.started_at is not None

    def test_update_status_completed(self, dao):
        """Test setting status to COMPLETED sets completed_at and progress 100."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(uid, DirectDownloadStatus.COMPLETED)
        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.COMPLETED
        assert record.completed_at is not None
        assert record.progress_percent == 100.0

    def test_update_status_failed(self, dao):
        """Test setting status to FAILED sets error and increments retry."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(
            uid, DirectDownloadStatus.FAILED, last_error="Network timeout"
        )
        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.FAILED
        assert record.last_error == "Network timeout"
        assert record.retry_count == 1

    def test_update_status_failed_increments_retry(self, dao):
        """Test retry_count increments on each FAILED status."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(uid, DirectDownloadStatus.FAILED)
        dao.update_direct_download_status(uid, DirectDownloadStatus.FAILED)
        record = dao.get_direct_download(uid)
        assert record.retry_count == 2

    def test_update_status_paused(self, dao):
        """Test generic status update (PAUSED)."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(uid, DirectDownloadStatus.PAUSED)
        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.PAUSED

    def test_update_status_cancelled(self, dao):
        """Test generic status update (CANCELLED)."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_status(uid, DirectDownloadStatus.CANCELLED)
        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.CANCELLED


class TestDAODirectDownloadProgress:
    """Test DAO progress update methods."""

    def test_update_progress(self, dao):
        """Test updating download progress."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_progress(uid, 512, 1024, 50.0)
        record = dao.get_direct_download(uid)
        assert record.bytes_downloaded == 512
        assert record.total_bytes == 1024
        assert record.progress_percent == 50.0

    def test_update_progress_complete(self, dao):
        """Test progress at 100%."""
        uid = dao.save_direct_download(_make_record())
        dao.update_direct_download_progress(uid, 1024, 1024, 100.0)
        record = dao.get_direct_download(uid)
        assert record.bytes_downloaded == 1024
        assert record.progress_percent == 100.0


class TestDAODirectDownloadHistory:
    """Test history limit enforcement."""

    def test_history_limit(self, dao):
        """Test that save_direct_download enforces total_download_history."""
        original = Options.total_download_history
        try:
            Options.total_download_history = 3
            for i in range(5):
                dao.save_direct_download(_make_record(doc_uid=f"doc-{i}"))
            results = list(dao.get_direct_downloads())
            assert len(results) == 3
        finally:
            Options.total_download_history = original

    def test_history_limit_zero_no_delete(self, dao):
        """Test history limit of 0 means no cleanup."""
        original = Options.total_download_history
        try:
            Options.total_download_history = 0
            for i in range(5):
                dao.save_direct_download(_make_record(doc_uid=f"doc-{i}"))
            results = list(dao.get_direct_downloads())
            assert len(results) == 5
        finally:
            Options.total_download_history = original


class TestDAODirectDownloadBatchQueries:
    """Test batch/grouped query methods."""

    def test_get_active_downloads_empty(self, dao):
        """Test get_active_direct_downloads with no records."""
        result = dao.get_active_direct_downloads()
        assert result == []

    def test_get_active_downloads_single_active(self, dao):
        """Test active downloads returns pending."""
        dao.save_direct_download(
            _make_record(
                doc_uid="a",
                status=DirectDownloadStatus.PENDING,
                zip_file="batch_1",
            )
        )
        result = dao.get_active_direct_downloads()
        assert len(result) == 1

    def test_get_active_downloads_excludes_completed(self, dao):
        """Test active downloads excludes completed."""
        dao.save_direct_download(
            _make_record(doc_uid="a", status=DirectDownloadStatus.COMPLETED)
        )
        result = dao.get_active_direct_downloads()
        assert result == []

    def test_get_active_downloads_batch_grouping(self, dao):
        """Test active downloads groups by batch."""
        dao.save_direct_download(
            _make_record(
                doc_uid="a",
                status=DirectDownloadStatus.PENDING,
                zip_file="batch_1",
                total_bytes=1000,
            )
        )
        dao.save_direct_download(
            _make_record(
                doc_uid="b",
                status=DirectDownloadStatus.COMPLETED,
                zip_file="batch_1",
                total_bytes=2000,
            )
        )
        result = dao.get_active_direct_downloads()
        # Both records should be in one batch (since batch has an active item)
        assert len(result) == 1
        assert result[0]["total_bytes"] == 3000

    def test_get_active_downloads_null_zip(self, dao):
        """Test active downloads with zip_file=NULL (single file downloads)."""
        dao.save_direct_download(
            _make_record(
                doc_uid="a",
                status=DirectDownloadStatus.IN_PROGRESS,
                zip_file=None,
            )
        )
        result = dao.get_active_direct_downloads()
        assert len(result) == 1

    def test_get_completed_downloads(self, dao):
        """Test get_completed_direct_downloads returns completed/cancelled."""
        dao.save_direct_download(
            _make_record(doc_uid="a", status=DirectDownloadStatus.COMPLETED)
        )
        dao.save_direct_download(
            _make_record(doc_uid="b", status=DirectDownloadStatus.CANCELLED)
        )
        dao.save_direct_download(
            _make_record(doc_uid="c", status=DirectDownloadStatus.PENDING)
        )
        result = dao.get_completed_direct_downloads()
        assert len(result) == 2

    def test_get_completed_downloads_limit(self, dao):
        """Test completed downloads respects limit."""
        for i in range(5):
            r = _make_record(doc_uid=f"doc-{i}", status=DirectDownloadStatus.COMPLETED)
            dao.save_direct_download(r)
        result = dao.get_completed_direct_downloads(limit=2)
        assert len(result) == 2

    def test_get_monitoring_downloads(self, dao):
        """Test get_direct_downloads_for_monitoring returns individual records."""
        dao.save_direct_download(
            _make_record(doc_uid="a", status=DirectDownloadStatus.PENDING)
        )
        dao.save_direct_download(
            _make_record(doc_uid="b", status=DirectDownloadStatus.IN_PROGRESS)
        )
        dao.save_direct_download(
            _make_record(doc_uid="c", status=DirectDownloadStatus.COMPLETED)
        )
        result = dao.get_direct_downloads_for_monitoring()
        # Only PENDING and IN_PROGRESS
        assert len(result) == 2

    def test_get_monitoring_downloads_limit(self, dao):
        """Test monitoring downloads respects limit."""
        for i in range(5):
            dao.save_direct_download(
                _make_record(doc_uid=f"doc-{i}", status=DirectDownloadStatus.PENDING)
            )
        result = dao.get_direct_downloads_for_monitoring(limit=2)
        assert len(result) == 2


class TestDAOBatchAggregation:
    """Test _get_batch_key and _aggregate_batch methods."""

    def test_batch_key_with_zip(self, dao):
        """Test batch key with zip_file."""
        key = dao._get_batch_key({"zip_file": "batch_1", "uid": 1})
        assert key == "zip:batch_1"

    def test_batch_key_without_zip(self, dao):
        """Test batch key without zip_file (single file)."""
        key = dao._get_batch_key({"zip_file": None, "uid": 42})
        assert key == "single:42"

    def test_aggregate_empty(self, dao):
        """Test aggregating empty list."""
        assert dao._aggregate_batch([]) == {}

    def test_aggregate_single_row(self, dao):
        """Test aggregating a single row."""
        rows = [
            {
                "uid": 1,
                "doc_name": "test.pdf",
                "total_bytes": 1000,
                "bytes_downloaded": 500,
                "file_count": 1,
                "folder_count": 0,
                "status": "IN_PROGRESS",
                "completed_at": None,
            }
        ]
        result = dao._aggregate_batch(rows)
        assert result["total_bytes"] == 1000
        assert result["batch_count"] == 1

    def test_aggregate_multiple_rows(self, dao):
        """Test aggregating multiple rows."""
        rows = [
            {
                "uid": 1,
                "doc_name": "a.txt",
                "total_bytes": 1000,
                "bytes_downloaded": 1000,
                "file_count": 1,
                "folder_count": 0,
                "status": "COMPLETED",
                "completed_at": "2025-01-01",
            },
            {
                "uid": 2,
                "doc_name": "b.txt",
                "total_bytes": 2000,
                "bytes_downloaded": 500,
                "file_count": 1,
                "folder_count": 0,
                "status": "IN_PROGRESS",
                "completed_at": None,
            },
        ]
        result = dao._aggregate_batch(rows)
        assert result["total_bytes"] == 3000
        assert result["bytes_downloaded"] == 1500
        assert result["file_count"] == 2
        assert result["batch_count"] == 2
        # Worst status wins
        assert result["status"] == "IN_PROGRESS"

    def test_aggregate_status_priority_failed(self, dao):
        """Test FAILED status has highest priority."""
        rows = [
            {
                "uid": 1,
                "doc_name": "a",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "COMPLETED",
                "completed_at": None,
            },
            {
                "uid": 2,
                "doc_name": "b",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "FAILED",
                "completed_at": None,
            },
        ]
        result = dao._aggregate_batch(rows)
        assert result["status"] == "FAILED"

    def test_aggregate_status_priority_cancelled(self, dao):
        """Test CANCELLED status priority."""
        rows = [
            {
                "uid": 1,
                "doc_name": "a",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "CANCELLED",
                "completed_at": None,
            },
            {
                "uid": 2,
                "doc_name": "b",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "COMPLETED",
                "completed_at": None,
            },
        ]
        result = dao._aggregate_batch(rows)
        assert result["status"] == "CANCELLED"

    def test_aggregate_status_priority_paused(self, dao):
        """Test PAUSED status priority."""
        rows = [
            {
                "uid": 1,
                "doc_name": "a",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "PAUSED",
                "completed_at": None,
            },
            {
                "uid": 2,
                "doc_name": "b",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "PENDING",
                "completed_at": None,
            },
        ]
        result = dao._aggregate_batch(rows)
        assert result["status"] == "PAUSED"

    def test_aggregate_zero_total_bytes(self, dao):
        """Test progress_percent with zero total_bytes."""
        rows = [
            {
                "uid": 1,
                "doc_name": "a",
                "total_bytes": 0,
                "bytes_downloaded": 0,
                "file_count": 1,
                "folder_count": 0,
                "status": "PENDING",
                "completed_at": None,
            },
        ]
        result = dao._aggregate_batch(rows)
        assert result["progress_percent"] == 0.0


class TestDAORowConversion:
    """Test _row_to_direct_download method."""

    def test_row_to_direct_download(self, dao):
        """Test that saved records round-trip correctly through the DB."""
        record = _make_record(
            doc_uid="uuid-test",
            doc_name="doc.pdf",
            doc_size=2048,
            is_folder=True,
            folder_count=3,
            file_count=10,
        )
        uid = dao.save_direct_download(record)
        fetched = dao.get_direct_download(uid)
        assert fetched.doc_uid == "uuid-test"
        assert fetched.is_folder is True
        assert fetched.folder_count == 3
        assert fetched.file_count == 10


# ---------------------------------------------------------------------------
# View Model Functional Tests
# ---------------------------------------------------------------------------


class TestActiveDirectDownloadModel:
    """Functional tests for ActiveDirectDownloadModel."""

    def test_init(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        names = model.roleNames()
        assert b"uid" in names.values()
        assert b"doc_name" in names.values()
        assert b"status" in names.values()

    def test_set_downloads(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        downloads = [
            {
                "uid": 1,
                "doc_name": "test.pdf",
                "status": "PENDING",
                "total_bytes": 1024,
                "download_path": "/dl/test.pdf",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "shadow": False,
                "zip_file": "batch_1",
                "all_file_names": ["test.pdf"],
                "batch_count": 1,
                "selected_items": "test.pdf",
            }
        ]
        model.set_downloads(downloads)
        assert model.rowCount() == 1
        assert model.count == 1

    def test_set_downloads_replace(self, translate, app):
        """Test that set_downloads replaces existing data."""
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "doc_name": "a.pdf"}])
        assert model.rowCount() == 1
        model.set_downloads(
            [{"uid": 2, "doc_name": "b.pdf"}, {"uid": 3, "doc_name": "c.pdf"}]
        )
        assert model.rowCount() == 2

    def test_data_status(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "IN_PROGRESS"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.STATUS) == "IN_PROGRESS"

    def test_data_download_path(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "download_path": None}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOWNLOAD_PATH) == ""

    def test_data_total_size_fmt(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "total_bytes": 1048576}])
        idx = model.createIndex(0, 0)
        assert "1.0" in model.data(idx, model.TOTAL_SIZE_FMT)

    def test_data_total_size_zero(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "total_bytes": 0}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.TOTAL_SIZE_FMT) == "0 B"

    def test_data_selected_items_display(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "selected_items": "a.txt, b.txt, c.txt"}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.SELECTED_ITEMS_DISPLAY)
        assert "+1" in result

    def test_data_shadow(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "shadow": True}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.SHADOW) is True

    def test_data_zip_file_fallback(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "zip_file": None, "doc_name": "fallback.pdf"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ZIP_FILE) == "fallback.pdf"

    def test_data_all_file_names_empty(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads(
            [{"uid": 1, "all_file_names": [], "doc_name": "single.pdf"}]
        )
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ALL_FILE_NAMES) == "single.pdf"

    def test_data_all_file_names_list(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "all_file_names": ["a.txt", "b.txt"]}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.ALL_FILE_NAMES)
        assert "a.txt" in result

    def test_data_batch_count(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "batch_count": 5}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.BATCH_COUNT) == 5

    def test_data_created_at_with_date(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "created_at": "2025-01-15 12:00:00"}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.CREATED_AT)
        assert isinstance(result, str)
        # Translator produces something like "Started on 01/15/25 ..."
        assert "tarted" in result or "15" in result

    def test_data_invalid_index(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        idx = QModelIndex()
        assert model.data(idx, model.STATUS) is None

    def test_data_out_of_range(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1}])
        idx = model.createIndex(5, 0)
        assert model.data(idx, model.STATUS) is None

    def test_data_generic_role(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 42, "doc_uid": "test-uid"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOC_UID) == "test-uid"

    def test_setData(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "PENDING"}])
        idx = model.createIndex(0, 0)
        model.setData(idx, "COMPLETED", role=model.STATUS)
        assert model.downloads[0]["status"] == "COMPLETED"

    def test_setData_none_role(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "PENDING"}])
        idx = model.createIndex(0, 0)
        model.setData(idx, "COMPLETED", role=None)
        assert model.downloads[0]["status"] == "PENDING"

    def test_format_selected_items_empty(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        assert model._format_selected_items("") == ""

    def test_format_selected_items_short(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        assert model._format_selected_items("a.txt, b.txt") == "a.txt, b.txt"

    def test_format_selected_items_long(self, translate, app):
        model = ActiveDirectDownloadModel(translate)
        result = model._format_selected_items(
            "first_file.txt, second_file_that_is_long.txt, third.txt, fourth.txt"
        )
        assert "+2" in result

    def test_data_created_at_no_date(self, translate, app):
        """CREATED_AT with no date returns the base label."""
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "created_at": None}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.CREATED_AT)
        assert isinstance(result, str)

    def test_data_all_file_names_empty_fallback(self, translate, app):
        """ALL_FILE_NAMES with empty list falls back to doc_name."""
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads(
            [{"uid": 1, "all_file_names": [], "doc_name": "fallback.pdf"}]
        )
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ALL_FILE_NAMES) == "fallback.pdf"

    def test_data_all_file_names_format(self, translate, app):
        """ALL_FILE_NAMES with names calls format_file_names_for_display."""
        model = ActiveDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "all_file_names": ["a.pdf", "b.pdf", "c.pdf"]}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.ALL_FILE_NAMES)
        assert "a.pdf" in result


class TestCompletedDirectDownloadModel:
    """Functional tests for CompletedDirectDownloadModel."""

    def test_init(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, translate, app):
        """Test roleNames returns expected roles."""
        model = CompletedDirectDownloadModel(translate)
        names = model.roleNames()
        assert b"uid" in names.values()
        assert b"status" in names.values()
        assert b"completed_at" in names.values()

    def test_set_downloads(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "COMPLETED"}])
        assert model.rowCount() == 1

    def test_data_status_completed(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "COMPLETED"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.STATUS) == "COMPLETED"

    def test_data_status_default(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.STATUS) == "COMPLETED"

    def test_data_download_path_empty(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "download_path": None}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOWNLOAD_PATH) == ""

    def test_data_total_size(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "total_bytes": 2048}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.TOTAL_SIZE_FMT) is not None

    def test_data_completed_at_cancelled(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "status": "CANCELLED", "completed_at": None}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.COMPLETED_AT)
        assert isinstance(result, str)

    def test_data_completed_at_with_date(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads(
            [
                {
                    "uid": 1,
                    "status": "COMPLETED",
                    "completed_at": "2025-01-15 12:00:00",
                }
            ]
        )
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.COMPLETED_AT)
        assert isinstance(result, str)
        # Translator produces "Completed on 01/15/25 ..."
        assert "ompleted" in result or "15" in result

    def test_data_zip_file_fallback(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "zip_file": None, "doc_name": "f.pdf"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ZIP_FILE) == "f.pdf"

    def test_data_all_file_names(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "all_file_names": ["x.pdf", "y.pdf"]}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.ALL_FILE_NAMES)
        assert "x.pdf" in result

    def test_data_all_file_names_empty(self, translate, app):
        """ALL_FILE_NAMES with empty list falls back to doc_name."""
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads(
            [{"uid": 1, "all_file_names": [], "doc_name": "single.pdf"}]
        )
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ALL_FILE_NAMES) == "single.pdf"

    def test_data_batch_count(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "batch_count": 3}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.BATCH_COUNT) == 3

    def test_data_batch_count_default(self, translate, app):
        """BATCH_COUNT defaults to 1 when not in row."""
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.BATCH_COUNT) == 1

    def test_data_completed_at_cancelled_with_date(self, translate, app):
        """COMPLETED_AT for CANCELLED status with a valid date."""
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads(
            [
                {
                    "uid": 1,
                    "status": "CANCELLED",
                    "completed_at": "2025-01-15 12:00:00",
                }
            ]
        )
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.COMPLETED_AT)
        assert isinstance(result, str)
        # Translator produces "Cancelled on 01/15/25 ..."
        assert "ancelled" in result or "15" in result

    def test_data_invalid_index(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        idx = QModelIndex()
        assert model.data(idx, model.STATUS) is None

    def test_data_generic_role(self, translate, app):
        model = CompletedDirectDownloadModel(translate)
        model.set_downloads([{"uid": 1, "doc_uid": "test-uid"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOC_UID) == "test-uid"


class TestDirectDownloadMonitoringModel:
    """Functional tests for DirectDownloadMonitoringModel."""

    def test_init(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        assert model.rowCount() == 0
        assert model.count == 0

    def test_role_names(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        names = model.roleNames()
        assert b"uid" in names.values()
        assert b"progress" in names.values()

    def test_set_items(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        items = [
            {
                "uid": 1,
                "doc_name": "test.pdf",
                "status": "IN_PROGRESS",
                "progress": 50.0,
                "total_bytes": 1024,
                "bytes_downloaded": 512,
                "shadow": False,
            }
        ]
        model.set_items(items)
        assert model.rowCount() == 1

    def test_set_items_replace(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1}])
        assert model.rowCount() == 1
        model.set_items([{"uid": 2}, {"uid": 3}])
        assert model.rowCount() == 2

    def test_data_status(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "status": "IN_PROGRESS"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.STATUS) == "IN_PROGRESS"

    def test_data_status_enum(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "status": DirectDownloadStatus.PENDING}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.STATUS) == "PENDING"

    def test_data_progress(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "progress": 75.3}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.PROGRESS) == "75.3"

    def test_data_shadow(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "shadow": True}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.SHADOW) is True

    def test_data_filesize(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "total_bytes": 1048576}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.FILESIZE)
        assert isinstance(result, str)

    def test_data_transferred_with_bytes(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "bytes_downloaded": 512, "total_bytes": 1024}])
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.TRANSFERRED)
        assert isinstance(result, str)

    def test_data_transferred_from_progress(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items(
            [{"uid": 1, "bytes_downloaded": 0, "total_bytes": 1000, "progress": 50.0}]
        )
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.TRANSFERRED)
        assert isinstance(result, str)

    def test_data_transferred_zero_total(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items(
            [{"uid": 1, "bytes_downloaded": 0, "total_bytes": 0, "progress": 0}]
        )
        idx = model.createIndex(0, 0)
        result = model.data(idx, model.TRANSFERRED)
        assert result == "0 B"

    def test_data_doc_name(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "doc_name": "report.pdf"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOC_NAME) == "report.pdf"

    def test_data_download_path(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "download_path": "/dl/file.pdf"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.DOWNLOAD_PATH) == "/dl/file.pdf"

    def test_data_engine(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "engine": "engine-1"}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.ENGINE) == "engine-1"

    def test_data_uid(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 42}])
        idx = model.createIndex(0, 0)
        assert model.data(idx, model.UID) == 42

    def test_data_invalid_index(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        idx = QModelIndex()
        assert model.data(idx, model.STATUS) is None

    def test_data_generic_key(self, translate, app):
        """Test generic fallback for a role not explicitly handled in data()."""
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "custom_key": "val"}])
        idx = model.createIndex(0, 0)
        # Use a role integer not in the explicit if/elif chain
        # qt.UserRole is imported in view.py; model.UID is UserRole+1,
        # so UserRole+99 won't match any known role
        unknown_role = model.UID + 98  # UserRole + 99
        result = model.data(idx, unknown_role)
        assert result == ""

    def test_setData(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "status": "PENDING"}])
        idx = model.createIndex(0, 0)
        model.setData(idx, "DONE", role=model.STATUS)
        assert model.items[0]["status"] == "DONE"

    def test_setData_none_role(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "status": "PENDING"}])
        idx = model.createIndex(0, 0)
        model.setData(idx, "DONE", role=None)
        assert model.items[0]["status"] == "PENDING"

    def test_set_progress(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items(
            [{"uid": 1, "progress": 0.0, "bytes_downloaded": 0, "total_bytes": 1000}]
        )
        action = {
            "uid": 1,
            "progress": 50.0,
            "bytes_downloaded": 500,
            "total_bytes": 1000,
        }
        model.set_progress(action)
        assert model.items[0]["progress"] == 50.0
        assert model.items[0]["bytes_downloaded"] == 500

    def test_set_progress_no_match(self, translate, app):
        model = DirectDownloadMonitoringModel(translate)
        model.set_items([{"uid": 1, "progress": 0.0}])
        action = {"uid": 999, "progress": 50.0}
        model.set_progress(action)
        assert model.items[0]["progress"] == 0.0


# ---------------------------------------------------------------------------
# format_file_names_for_display functional tests
# ---------------------------------------------------------------------------


class TestFormatFileNamesForDisplay:
    """Test the format_file_names_for_display utility."""

    def test_empty_list(self):
        assert format_file_names_for_display([]) == ""

    def test_single_name(self):
        assert format_file_names_for_display(["file.txt"]) == "file.txt"

    def test_two_names_fit(self):
        result = format_file_names_for_display(["a.txt", "b.txt"], max_length=100)
        assert result == "a.txt, b.txt"

    def test_all_names_fit(self):
        result = format_file_names_for_display(
            ["a.txt", "b.txt", "c.txt"], max_length=100
        )
        assert result == "a.txt, b.txt, c.txt"

    def test_truncation_with_count(self):
        result = format_file_names_for_display(
            ["file1.txt", "file2.txt", "file3.txt", "file4.txt"],
            max_length=30,
        )
        assert "+" in result

    def test_very_long_single_name(self):
        long_name = "a" * 100
        result = format_file_names_for_display([long_name, "b.txt"], max_length=20)
        assert "..." in result

    def test_very_long_single_name_only(self):
        long_name = "a" * 100
        result = format_file_names_for_display([long_name], max_length=20)
        assert len(result) <= 100  # just the name itself

    def test_very_long_name_tiny_max_length(self):
        """Edge case: max_length so small that available <= 0 after suffix."""
        # With 2 names, suffix=" +1" (4 chars), available = max_length - 4 - 3
        # max_length=5 => available = 5 - 4 - 3 = -2 (<=0) => triggers line 740-741
        long_name = "a" * 50
        result = format_file_names_for_display([long_name, "b.txt"], max_length=5)
        assert "..." in result


# ---------------------------------------------------------------------------
# GUI API Functional Tests
# ---------------------------------------------------------------------------


class TestGUIApiDirectDownload:
    """Test GUI API methods for direct download."""

    def test_get_active_direct_downloads_items(self, dao):
        """Test API wrapper for active downloads."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_active_direct_downloads_items = (
            QMLDriveApi.get_active_direct_downloads_items.__get__(api)
        )
        result = api.get_active_direct_downloads_items(dao)
        assert result == []

    def test_get_completed_direct_downloads_items(self, dao):
        """Test API wrapper for completed downloads."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_completed_direct_downloads_items = (
            QMLDriveApi.get_completed_direct_downloads_items.__get__(api)
        )
        result = api.get_completed_direct_downloads_items(dao)
        assert result == []

    def test_get_direct_downloads_for_monitoring(self, dao):
        """Test API wrapper for monitoring."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_direct_downloads_for_monitoring = (
            QMLDriveApi.get_direct_downloads_for_monitoring.__get__(api)
        )
        result = api.get_direct_downloads_for_monitoring(dao)
        assert result == []

    def test_get_download_location_default(self):
        """Test get_download_location returns default."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_download_location = QMLDriveApi.get_download_location.__get__(api)
        original = Options.download_folder
        try:
            Options.download_folder = None
            result = api.get_download_location()
            assert "Downloads" in result
        finally:
            Options.download_folder = original

    def test_get_download_location_custom(self, tmp_path):
        """Test get_download_location returns custom path."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_download_location = QMLDriveApi.get_download_location.__get__(api)
        # Options metaclass prevents resetting to None once set to str.
        # Use a mock to avoid side effects.
        with patch("nxdrive.gui.api.Options") as mock_opts:
            mock_opts.download_folder = str(tmp_path)
            result = api.get_download_location()
            assert result == str(tmp_path)

    def test_pause_direct_download(self, dao):
        """Test pause_direct_download API."""
        from nxdrive.gui.api import QMLDriveApi

        uid = dao.save_direct_download(
            _make_record(status=DirectDownloadStatus.IN_PROGRESS)
        )

        engine = Mock()
        engine.dao = dao
        manager = Mock()
        manager.engines = {"engine-1": engine}

        api = Mock(spec=QMLDriveApi)
        api._manager = manager
        api.pause_direct_download = QMLDriveApi.pause_direct_download.__get__(api)
        api.pause_direct_download("engine-1", uid)

        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.PAUSED

    def test_resume_direct_download(self, dao):
        """Test resume_direct_download API."""
        from nxdrive.gui.api import QMLDriveApi

        uid = dao.save_direct_download(_make_record(status=DirectDownloadStatus.PAUSED))

        engine = Mock()
        engine.dao = dao
        manager = Mock()
        manager.engines = {"engine-1": engine}

        api = Mock(spec=QMLDriveApi)
        api._manager = manager
        api.resume_direct_download = QMLDriveApi.resume_direct_download.__get__(api)
        api.resume_direct_download("engine-1", uid)

        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.PENDING

    def test_cancel_direct_download(self, dao):
        """Test cancel_direct_download API."""
        from nxdrive.gui.api import QMLDriveApi

        uid = dao.save_direct_download(
            _make_record(status=DirectDownloadStatus.IN_PROGRESS)
        )

        engine = Mock()
        engine.dao = dao
        manager = Mock()
        manager.engines = {"engine-1": engine}

        api = Mock(spec=QMLDriveApi)
        api._manager = manager
        api.cancel_direct_download = QMLDriveApi.cancel_direct_download.__get__(api)
        api.cancel_direct_download("engine-1", uid)

        record = dao.get_direct_download(uid)
        assert record.status == DirectDownloadStatus.CANCELLED

    def test_pause_no_engine(self):
        """Test pause_direct_download with unknown engine."""
        from nxdrive.gui.api import QMLDriveApi

        manager = Mock()
        manager.engines = {}

        api = Mock(spec=QMLDriveApi)
        api._manager = manager
        api.pause_direct_download = QMLDriveApi.pause_direct_download.__get__(api)
        api.pause_direct_download("unknown-engine", 1)

    def test_open_download_folder(self, tmp_path):
        """Test open_download_folder calls open_local_file."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_download_location = Mock(return_value=str(tmp_path))
        api.open_download_folder = QMLDriveApi.open_download_folder.__get__(api)
        manager = Mock()
        api._manager = manager

        api.open_download_folder()
        manager.open_local_file.assert_called_once_with(str(tmp_path))

    def test_change_download_location(self, tmp_path):
        """Test change_download_location with a selected folder."""
        from nxdrive.gui.api import QMLDriveApi

        new_folder = str(tmp_path / "new_downloads")
        api = Mock(spec=QMLDriveApi)
        api.get_download_location = Mock(return_value=str(tmp_path))
        api.change_download_location = QMLDriveApi.change_download_location.__get__(api)

        with (
            patch("nxdrive.qt.imports.QFileDialog") as mock_dialog,
            patch("nxdrive.gui.api.Options") as mock_opts,
            patch("nxdrive.gui.api.save_config") as mock_save,
            patch("nxdrive.gui.api.Translator") as mock_tr,
        ):
            mock_dialog.getExistingDirectory.return_value = new_folder
            mock_dialog.Option.ShowDirsOnly = 1
            mock_dialog.Option.DontResolveSymlinks = 2
            mock_tr.get.return_value = "Select"

            api.change_download_location()

            mock_opts.set.assert_called_once_with(
                "download_folder", new_folder, setter="manual"
            )
            mock_save.assert_called_once_with({"download_folder": new_folder})
            api.downloadLocationChanged.emit.assert_called_once()

    def test_change_download_location_cancelled(self, tmp_path):
        """Test change_download_location when user cancels dialog."""
        from nxdrive.gui.api import QMLDriveApi

        api = Mock(spec=QMLDriveApi)
        api.get_download_location = Mock(return_value=str(tmp_path))
        api.change_download_location = QMLDriveApi.change_download_location.__get__(api)

        with (
            patch("nxdrive.qt.imports.QFileDialog") as mock_dialog,
            patch("nxdrive.gui.api.Options") as mock_opts,
            patch("nxdrive.gui.api.save_config") as mock_save,
            patch("nxdrive.gui.api.Translator") as mock_tr,
        ):
            mock_dialog.getExistingDirectory.return_value = ""
            mock_dialog.Option.ShowDirsOnly = 1
            mock_dialog.Option.DontResolveSymlinks = 2
            mock_tr.get.return_value = "Select"

            api.change_download_location()

            mock_opts.set.assert_not_called()
            mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Migration Functional Tests
# ---------------------------------------------------------------------------


class TestMigrationDirectDownloads:
    """Test database migration for DirectDownloads table."""

    @staticmethod
    def _get_migration():
        import importlib

        m = importlib.import_module(
            "nxdrive.dao.migrations.engine.0023_direct_downloads"
        )
        return m.migration

    def test_upgrade(self, tmp_path, app):
        """Test migration creates table."""
        import sqlite3

        migration = self._get_migration()

        db_path = tmp_path / "test_migration.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        migration.upgrade(cursor)
        conn.commit()

        # Verify table exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='DirectDownloads'"
        )
        assert cursor.fetchone() is not None
        conn.close()

    def test_downgrade(self, tmp_path, app):
        """Test migration drops table."""
        import sqlite3

        migration = self._get_migration()

        db_path = tmp_path / "test_migration.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()
        migration.upgrade(cursor)
        conn.commit()
        migration.downgrade(cursor)
        conn.commit()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='DirectDownloads'"
        )
        assert cursor.fetchone() is None
        conn.close()

    def test_version(self, app):
        migration = self._get_migration()

        assert migration.version == 23
        assert migration.previous_version == 22
