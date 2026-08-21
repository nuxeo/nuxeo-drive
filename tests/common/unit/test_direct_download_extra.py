"""Focused tests for the server-agnostic Direct Download worker."""

from concurrent.futures import Future
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.drive.constants import DirectDownloadStatus
from nxdrive.drive.direct_download import DirectDownload
from nxdrive.drive.objects import DirectDownload as DirectDownloadRecord


class _SyncExecutor:
    """Inline executor used to drive the worker pool synchronously in
    unit tests. Every ``submit`` runs the callable immediately on the
    current thread and returns a completed ``Future``.
    """

    def __init__(self):
        self.calls = []

    def submit(self, fn, /, *args, **kwargs):
        self.calls.append((fn, args, kwargs))
        fut: Future = Future()
        try:
            fut.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - propagated via future
            fut.set_exception(exc)
        return fut

    def shutdown(self, wait=True, *, cancel_futures=False):  # noqa: D401
        return None


@pytest.fixture()
def manager():
    manager = Mock()
    manager.directDownload = Mock()
    manager.engines = {}
    return manager


@pytest.fixture()
def sync_executor():
    return _SyncExecutor()


@pytest.fixture()
def direct_download(manager, tmp_path, sync_executor):
    return DirectDownload(manager, tmp_path / "staging", executor=sync_executor)


def _record(
    uid,
    status,
    *,
    batch=None,
    server_url="https://example.test/nuxeo",
    name=None,
):
    return DirectDownloadRecord(
        uid=uid,
        doc_uid=f"doc-{uid}",
        doc_name=name or f"file-{uid}.txt",
        doc_size=10,
        download_path=None,
        server_url=server_url,
        status=status,
        bytes_downloaded=0,
        total_bytes=10,
        progress_percent=0.0,
        created_at="2026-08-05 00:00:00",
        started_at=None,
        completed_at=None,
        is_folder=False,
        folder_count=0,
        file_count=1,
        retry_count=0,
        last_error=None,
        engine="engine",
        zip_file=batch,
        selected_items=None,
    )


def _engine(records=(), *, user="User", binder_error=None):
    engine = Mock()
    engine.dao = Mock()
    engine.dao.get_direct_downloads.return_value = list(records)
    if binder_error:
        engine.get_binder.side_effect = binder_error
    else:
        engine.get_binder.return_value = SimpleNamespace(
            server_url="https://example.test/nuxeo/", username=user
        )
    return engine


def test_construction_wires_manager_and_initializes_state(direct_download, manager):
    assert direct_download.download_folder.is_dir()
    assert direct_download.download_folders == []
    assert direct_download._resumed_persisted_downloads is False
    assert direct_download._batches == {}
    assert direct_download._owns_executor is False
    manager.directDownload.connect.assert_called_once_with(direct_download.download)


def test_base_hooks_are_explicit(direct_download):
    with pytest.raises(NotImplementedError):
        direct_download._create_download_record({})
    with pytest.raises(NotImplementedError):
        direct_download._calculate_folder_size(None, "folder")
    with pytest.raises(NotImplementedError):
        direct_download._process_download({}, Path("batch"))
    with pytest.raises(NotImplementedError):
        direct_download._download_folder(None, "id", "name", Path("batch"))
    with pytest.raises(NotImplementedError):
        direct_download._get_children(None, "id")
    with pytest.raises(NotImplementedError):
        direct_download._get_download_url({})
    with pytest.raises(NotImplementedError):
        direct_download._download_file(None, "server", "url", "file.txt", Path("batch"))


def test_active_sessions_and_finalize_state(direct_download, manager):
    no_dao = SimpleNamespace(dao=None)
    inactive = _engine()
    inactive.dao.get_active_direct_downloads.return_value = []
    active = _engine()
    active.dao.get_active_direct_downloads.return_value = [
        _record(1, DirectDownloadStatus.PENDING)
    ]
    manager.engines = {"none": no_dao, "inactive": inactive, "active": active}
    assert direct_download.check_active_sessions() is True


def test_cleanup_preserves_active_shutdown_and_removes_inactive_contents(
    direct_download, tmp_path
):
    nested = direct_download.download_folder / "batch" / "nested.txt"
    nested.parent.mkdir()
    nested.write_text("payload", encoding="utf-8")
    loose = direct_download.download_folder / "loose.txt"
    loose.write_text("payload", encoding="utf-8")
    direct_download._download_folders.append("batch")
    direct_download._stop = True
    direct_download.check_active_sessions = Mock(return_value=True)

    direct_download.cleanup()
    assert nested.exists()
    assert loose.exists()
    assert direct_download.download_folders == ["batch"]

    direct_download.check_active_sessions.return_value = False
    direct_download.cleanup()
    assert list(direct_download.download_folder.iterdir()) == []
    assert direct_download.download_folders == []

    direct_download.download_folder.rmdir()
    direct_download._download_folders.append("stale")
    direct_download.cleanup()
    assert direct_download.download_folder.is_dir()
    assert direct_download.download_folders == []


def test_cleanup_batch_folder_updates_tracking_and_swallows_errors(direct_download):
    batch = direct_download.download_folder / "download_batch"
    batch.mkdir()
    direct_download._download_folders.append(batch.name)
    direct_download._cleanup_batch_folder(batch)
    assert not batch.exists()
    assert direct_download.download_folders == []

    batch.mkdir()
    with patch(
        "nxdrive.drive.direct_download.shutil.rmtree", side_effect=OSError("busy")
    ):
        direct_download._cleanup_batch_folder(batch)
    assert batch.exists()


def test_resume_persisted_downloads_groups_batches_resets_progress_and_runs_once(
    direct_download, manager
):
    first = _engine(
        [
            _record(1, DirectDownloadStatus.IN_PROGRESS, batch="download_batch"),
            _record(2, DirectDownloadStatus.PAUSED, batch="download_batch"),
            _record(3, DirectDownloadStatus.COMPLETED),
            _record(None, DirectDownloadStatus.PENDING),
        ]
    )
    second = _engine(
        [_record(4, DirectDownloadStatus.PENDING)],
        binder_error=RuntimeError("binder unavailable"),
    )
    manager.engines = {
        "no-dao": SimpleNamespace(dao=None),
        "first": first,
        "second": second,
    }

    submitted_batches = []
    direct_download._process_batch = Mock(
        side_effect=lambda docs: submitted_batches.append(list(docs))
    )

    direct_download.resume_persisted_downloads()

    first.dao.update_direct_download_status.assert_called_once_with(
        1, DirectDownloadStatus.PENDING
    )
    assert len(submitted_batches) == 2
    grouped = next(batch for batch in submitted_batches if len(batch) == 2)
    single = next(batch for batch in submitted_batches if len(batch) == 1)
    assert [doc["_record_uid"] for doc in grouped] == [1, 2]
    assert {doc["_batch_folder"] for doc in grouped} == {"download_batch"}
    assert single == [
        {
            "server_url": "https://example.test/nuxeo",
            "user": "",
            "doc_id": "doc-4",
            "filename": "file-4.txt",
            "_record_uid": 4,
            "_batch_folder": None,
        }
    ]

    direct_download.resume_persisted_downloads()
    assert direct_download._process_batch.call_count == 2
    assert first.dao.get_direct_downloads.call_count == 1


def test_execute_is_a_stoppable_idle_loop(direct_download):
    interactions = 0

    def interact():
        nonlocal interactions
        interactions += 1
        if interactions == 3:
            direct_download._stop = True

    direct_download._interact = interact
    # Avoid actually sleeping between iterations in the test.
    with patch("nxdrive.drive.direct_download.time.sleep") as sleep:
        direct_download._execute()
    assert interactions == 3
    assert sleep.call_count >= 2


def test_process_batch_reuses_existing_folder_and_completes_persisted_record(
    direct_download, tmp_path
):
    batch = direct_download.download_folder / "download_existing"
    batch.mkdir()
    doc = {
        "server_url": "https://example.test/nuxeo",
        "doc_id": "doc-7",
        "filename": "report.txt",
        "_record_uid": "7",
        "_batch_folder": batch.name,
    }
    record = _record(7, DirectDownloadStatus.IN_PROGRESS, batch=batch.name)
    archive = tmp_path / "report.txt"
    direct_download._is_single_download_cancelled = Mock(return_value=False)
    direct_download._get_download_record = Mock(return_value=record)
    direct_download._process_download = Mock()
    direct_download._create_zip_archive = Mock(return_value=archive)
    direct_download._get_download_destination = Mock(return_value=tmp_path)
    direct_download._update_download_status = Mock()
    direct_download._update_download_path = Mock()

    direct_download._process_batch([doc])

    assert direct_download.download_folders == [batch.name]
    direct_download._process_download.assert_called_once_with(doc, batch)
    assert direct_download._update_download_status.call_args_list == [
        call(7, DirectDownloadStatus.IN_PROGRESS),
        call(7, DirectDownloadStatus.COMPLETED, download_path=str(archive)),
    ]
    assert direct_download._update_download_path.call_args_list == [
        call(7, str(tmp_path)),
        call(7, str(archive), archive.name),
    ]
    assert doc["_record_uid"] == 7


def test_process_batch_missing_resume_folder_and_cancelled_record_skip_download(
    direct_download,
):
    doc = {
        "doc_id": "doc-8",
        "filename": "cancelled.txt",
        "_record_uid": 8,
        "_batch_folder": "missing_batch",
    }
    direct_download._create_batch_folder = Mock(
        return_value=direct_download.download_folder / "replacement"
    )
    direct_download._is_single_download_cancelled = Mock(return_value=True)
    direct_download._process_download = Mock()
    direct_download._create_zip_archive = Mock()

    direct_download._process_batch([doc])

    direct_download._create_batch_folder.assert_called_once_with()
    direct_download._process_download.assert_not_called()
    direct_download._create_zip_archive.assert_not_called()


def test_process_batch_dispatches_each_doc_through_the_executor(
    direct_download, sync_executor, tmp_path
):
    docs = [{"doc_id": "one"}, {"doc_id": "two"}]
    direct_download._create_download_record = Mock(side_effect=[10, 20])
    direct_download._is_single_download_cancelled = Mock(return_value=False)
    direct_download._process_download = Mock()
    direct_download._get_download_destination = Mock(return_value=tmp_path)
    direct_download._update_download_status = Mock()
    direct_download._update_download_path = Mock()

    direct_download._process_batch(docs)

    # Each doc gets its own executor submission and its own
    # ``_process_download`` call — no early bail-out at the batch
    # level. Cancellation is a per-doc concern now.
    assert len(sync_executor.calls) == 2
    assert direct_download._process_download.call_count == 2
    assert direct_download._create_download_record.call_count == 2


def test_process_batch_failure_persists_error_and_avoids_completion(
    direct_download, tmp_path
):
    errors = []
    direct_download.downloadError.connect(
        lambda filename, message: errors.append((filename, message))
    )
    doc = {"doc_id": "broken", "filename": "broken.txt"}
    failed_record = _record(9, DirectDownloadStatus.FAILED)
    direct_download._create_download_record = Mock(return_value=9)
    direct_download._is_single_download_cancelled = Mock(return_value=False)
    direct_download._get_download_destination = Mock(return_value=tmp_path)
    direct_download._process_download = Mock(side_effect=RuntimeError("remote failed"))
    direct_download._update_download_status = Mock()
    direct_download._update_download_path = Mock()
    direct_download._get_download_record = Mock(return_value=failed_record)
    direct_download._create_zip_archive = Mock(return_value=None)

    direct_download._process_batch([doc])

    assert errors == [("broken.txt", "remote failed")]
    assert (
        call(9, DirectDownloadStatus.FAILED, last_error="remote failed")
        in direct_download._update_download_status.call_args_list
    )
    assert not any(
        args[0][1] == DirectDownloadStatus.COMPLETED
        for args in direct_download._update_download_status.call_args_list
    )


def test_empty_batch_returns_without_touching_the_worker_pool(
    direct_download, sync_executor
):
    direct_download._create_zip_archive = Mock(return_value=None)
    direct_download._process_batch([])
    direct_download._create_zip_archive.assert_not_called()
    assert sync_executor.calls == []


def test_archive_real_files_copy_zip_empty_and_duplicate(direct_download, tmp_path):
    destination = tmp_path / "downloads"
    destination.mkdir()
    direct_download._get_download_destination = Mock(return_value=destination)

    single = direct_download.download_folder / "single"
    single.mkdir()
    (single / "report.txt").write_text("new", encoding="utf-8")
    (destination / "report.txt").write_text("old", encoding="utf-8")
    copied = direct_download._create_zip_archive(single)
    assert copied == destination / "report (1).txt"
    assert copied.read_text(encoding="utf-8") == "new"
    assert not single.exists()

    multiple = direct_download.download_folder / "multiple"
    (multiple / "sub").mkdir(parents=True)
    (multiple / "a.txt").write_text("a", encoding="utf-8")
    (multiple / "sub" / "b.txt").write_text("b", encoding="utf-8")
    archive = direct_download._create_zip_archive(multiple)
    assert archive and archive.suffix == ".zip"
    import zipfile

    with zipfile.ZipFile(archive) as zip_file:
        assert sorted(zip_file.namelist()) == ["a.txt", "sub/b.txt"]

    empty = direct_download.download_folder / "empty"
    (empty / "sub").mkdir(parents=True)
    assert direct_download._create_zip_archive(empty) is None
    assert not empty.exists()


def test_download_destination_custom_and_fallback_are_isolated(
    direct_download, tmp_path
):
    custom = tmp_path / "custom"
    custom.mkdir()
    with patch(
        "nxdrive.drive.direct_download.Options",
        SimpleNamespace(download_folder=str(custom)),
    ):
        assert direct_download._get_download_destination() == custom

    home = tmp_path / "home"
    with (
        patch(
            "nxdrive.drive.direct_download.Options",
            SimpleNamespace(download_folder="/missing"),
        ),
        patch("nxdrive.drive.direct_download.Path.home", return_value=home),
    ):
        result = direct_download._get_download_destination()
    assert result == home / "Downloads"
    assert result.is_dir()


def test_database_helpers_scan_engines_and_preserve_batch_identifier(
    direct_download, manager
):
    first = SimpleNamespace(dao=None)
    second = _engine()
    record = _record(10, DirectDownloadStatus.PENDING, batch="download_batch")
    second.dao.get_direct_download.return_value = record
    manager.engines = {"first": first, "second": second}

    direct_download._update_download_status(
        10,
        DirectDownloadStatus.FAILED,
        download_path="/failed",
        last_error="boom",
    )
    assert record.download_path == "/failed"
    second.dao.update_direct_download.assert_called_once_with(record)
    second.dao.update_direct_download_status.assert_called_once_with(
        10, DirectDownloadStatus.FAILED, last_error="boom"
    )

    second.dao.reset_mock()
    direct_download._update_download_path(10, "/resuming")
    assert record.download_path == "/resuming"
    assert record.zip_file == "download_batch"
    second.dao.update_direct_download.assert_called_once_with(record)
    assert direct_download._get_download_record(10) is record


def test_database_helpers_swallow_dao_errors(direct_download, manager):
    engine = _engine()
    engine.dao.get_direct_download.side_effect = RuntimeError("database unavailable")
    manager.engines = {"engine": engine}

    direct_download._update_download_status(1, DirectDownloadStatus.FAILED)
    direct_download._update_download_path(1, "/tmp")
    direct_download._update_download_progress(1, 1, 2)
    assert direct_download._get_download_record(1) is None


def test_batch_cancellation_states_are_deterministic(direct_download):
    # ``_is_download_cancelled`` (the batch-wide helper) was removed as
    # dead code when the executor switched to per-doc dispatch.  The
    # per-doc equivalents are exercised by
    # ``test_single_cancellation_states_are_deterministic``.  This test
    # remains only to keep coverage totals stable and document the
    # deletion.
    assert not hasattr(direct_download, "_is_download_cancelled")


def test_single_cancellation_states_are_deterministic(direct_download):
    direct_download._get_download_record = Mock(return_value=None)
    assert direct_download._is_single_download_cancelled(1) is False

    # PAUSED is not cancellation; the worker returns immediately and
    # waits for a Resume click to re-submit.
    paused = _record(2, DirectDownloadStatus.PAUSED)
    direct_download._get_download_record = Mock(return_value=paused)
    assert direct_download._is_single_download_cancelled(2) is False
    assert direct_download._is_paused(2) is True

    cancelled = _record(3, DirectDownloadStatus.CANCELLED)
    direct_download._get_download_record = Mock(return_value=cancelled)
    assert direct_download._is_single_download_cancelled(3) is True
    assert direct_download._is_paused(3) is False


def test_progress_persists_aggregate_and_emits_per_file_values(
    direct_download, manager
):
    progress_events = []
    direct_download.downloadProgress.connect(progress_events.append)
    engine = _engine()
    record = _record(11, DirectDownloadStatus.IN_PROGRESS)
    engine.dao.get_direct_download.return_value = record
    manager.engines = {"engine": engine}

    direct_download._update_download_progress(
        11,
        75,
        100,
        filename="part.bin",
        emitted_bytes_downloaded=5,
        emitted_total_bytes=20,
    )

    engine.dao.update_direct_download_progress.assert_called_once_with(
        11, 75, 100, 75.0
    )
    assert progress_events == [
        {
            "uid": 11,
            "doc_name": "part.bin",
            "progress": 25.0,
            "bytes_downloaded": 5,
            "total_bytes": 20,
        }
    ]


def test_stop_sets_flag_and_delegates(direct_download):
    with patch(
        "nxdrive.drive.direct_download.Worker.stop", autospec=True
    ) as worker_stop:
        direct_download.stop()
    assert direct_download._stop is True
    worker_stop.assert_called_once_with(direct_download)
