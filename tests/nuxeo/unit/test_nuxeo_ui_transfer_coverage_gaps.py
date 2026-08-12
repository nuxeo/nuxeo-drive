"""Focused Direct Edit, Direct Download, and Engine coverage-gap tests."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from nuxeo.exceptions import HTTPError

from nxdrive.drive.exceptions import ThreadInterrupt
from nxdrive.nuxeo.direct_download import DirectDownload
from nxdrive.nuxeo.direct_edit import DirectEdit
from nxdrive.nuxeo.engine.processor import Processor
from tests.nuxeo.unit.test_nuxeo_engine_extra import _make_engine


@pytest.fixture(autouse=True)
def _restore_processor_class_state():
    soft_locks = Processor.soft_locks
    readonly_locks = Processor.readonly_locks
    yield
    Processor.soft_locks = soft_locks
    Processor.readonly_locks = readonly_locks


def _direct_download():
    with patch.object(DirectDownload, "__init__", return_value=None):
        worker = DirectDownload.__new__(DirectDownload)
    worker.downloadStarting = MagicMock()
    worker.downloadCompleted = MagicMock()
    worker.downloadError = MagicMock()
    return worker


def _direct_edit(manager):
    with patch.object(DirectEdit, "__init__", return_value=None):
        worker = DirectEdit.__new__(DirectEdit)
    worker._manager = manager
    worker.directEditError = MagicMock()
    return worker


def _binding(url="https://server.example/nuxeo", username="alice"):
    return SimpleNamespace(server_url=url, username=username)


class TestDirectDownloadCoverageGaps:
    def test_process_note_dispatches_inline_download(self, tmp_path):
        worker = _direct_download()
        engine = MagicMock()
        info = SimpleNamespace(
            folderish=False,
            name="note.txt",
            doc_type="Note",
            properties={"note:note": "hello"},
            get_blob=Mock(return_value=None),
        )
        engine.remote.get_info.return_value = info
        worker._get_engine = Mock(return_value=engine)
        worker._download_note = Mock()

        worker._process_download(
            {"server_url": "https://server", "doc_id": "note-1"}, tmp_path
        )

        worker._download_note.assert_called_once_with(
            engine, "note-1", "note.txt", tmp_path, record_uid=None
        )

    def test_existing_folder_is_reused_on_resume(self, tmp_path):
        worker = _direct_download()
        engine = MagicMock()
        existing = tmp_path / "Existing"
        existing.mkdir()
        worker._get_children = Mock(return_value=[])
        worker._get_unique_path = Mock()

        worker._download_folder(engine, "folder-1", "Existing", tmp_path)

        worker._get_unique_path.assert_not_called()
        assert existing.is_dir()

    @pytest.mark.parametrize(
        "properties",
        [
            {"files:files": []},
            {"files:files": [None]},
            {"files:files": {"0": "not-a-list"}},
            {"files:files": "not-a-container"},
        ],
    )
    def test_download_url_handles_malformed_nested_properties(self, properties):
        worker = _direct_download()

        assert worker._get_download_url({"properties": properties}) is None


class TestDirectEditCoverageGaps:
    def test_uuid_is_resolved_to_matching_bound_user(self):
        engine = MagicMock()
        engine.get_binder.return_value = _binding()
        engine.remote.client.resolve_username.return_value = "alice"
        manager = SimpleNamespace(engines={"engine": engine})
        worker = _direct_edit(manager)

        found = worker._DirectEdit__get_engine(
            "https://server.example/nuxeo", user="uuid-alice"
        )

        assert found is engine
        engine.remote.client.resolve_username.assert_called_once_with("uuid-alice")

    def test_no_user_does_not_attempt_case_insensitive_lookup(self):
        engine = MagicMock()
        engine.get_binder.return_value = _binding(username="alice")
        manager = SimpleNamespace(engines={"engine": engine})
        worker = _direct_edit(manager)

        assert worker._DirectEdit__get_engine("https://other.example/nuxeo") is None

    def test_missing_engine_error_displays_resolved_username(self):
        engine = MagicMock()
        engine.get_binder.return_value = _binding()
        engine.remote.client.resolve_username.return_value = "Alice Example"
        manager = SimpleNamespace(engines={"engine": engine})
        worker = _direct_edit(manager)

        assert (
            worker._get_engine(
                "https://server.example/nuxeo",
                doc_id="doc-1",
                user="uuid-alice",
            )
            is None
        )
        emitted = worker.directEditError.emit.call_args.args
        assert emitted[0] == "DIRECT_EDIT_CANT_FIND_ENGINE"
        assert emitted[1][0] == "Alice Example"

    def test_non_retryable_lock_http_error_is_reraised(self):
        manager = SimpleNamespace(engines={})
        worker = _direct_edit(manager)
        worker._lock_queue = MagicMock()
        ref = Path("doc/file.txt")
        worker._lock_queue.get_nowait.side_effect = [
            (ref, "unlock"),
            __import__("queue").Empty(),
        ]
        details = SimpleNamespace(
            uid="doc-1", engine=SimpleNamespace(remote=MagicMock())
        )
        worker._extract_edit_info = Mock(return_value=details)
        worker._unlock = Mock(
            side_effect=HTTPError(status=400, message="invalid request")
        )

        with pytest.raises(HTTPError):
            worker._handle_lock_queue()

    def test_upload_queue_reraises_thread_interrupt(self, tmp_path):
        manager = SimpleNamespace(engines={})
        worker = _direct_edit(manager)
        worker._upload_queue = MagicMock()
        ref = Path("doc/file.txt")
        worker._upload_queue.get_nowait.return_value = ref
        worker.local = MagicMock()
        worker.local.abspath.return_value = tmp_path / "file.txt"
        worker.local.get_info.side_effect = ThreadInterrupt()
        remote = MagicMock()
        details = SimpleNamespace(
            xpath="file:content",
            engine=SimpleNamespace(remote=remote),
            digest_func="md5",
        )
        worker._extract_edit_info = Mock(return_value=details)

        with pytest.raises(ThreadInterrupt):
            worker._handle_upload_queue()


class TestEngineCoverageGaps:
    def test_stop_terminates_stuck_local_and_remote_watchers(self):
        engine = _make_engine()
        engine._threads = []
        local_thread = MagicMock()
        remote_thread = MagicMock()
        local_thread.wait.side_effect = [False, None]
        remote_thread.wait.side_effect = [False, None]
        local_thread.isRunning.return_value = True
        remote_thread.isRunning.return_value = True
        engine._local_watcher.thread = local_thread
        engine._remote_watcher.thread = remote_thread

        engine.stop()

        local_thread.terminate.assert_called_once()
        remote_thread.terminate.assert_called_once()

    def test_bind_uuid_refresh_failure_does_not_abort_binding(self):
        from nxdrive.drive.objects import Binder

        engine = _make_engine()
        engine._normalize_url = Mock(return_value="https://server.example/nuxeo/")
        engine._save_token = Mock()
        engine._refresh_user_uuid = Mock(side_effect=OSError("offline"))
        engine._check_root = Mock()
        binder = Binder(
            username="alice",
            password=None,
            token="token",
            url="https://server.example/nuxeo/",
            no_check=True,
            no_fscheck=True,
        )

        with patch("nxdrive.nuxeo.engine.engine.Feature") as feature:
            feature.synchronization = False
            engine.bind(binder)

        engine._check_root.assert_called_once()

    def test_create_processor_returns_nuxeo_processor(self):
        engine = _make_engine()
        getter = Mock(return_value=None)

        with patch(
            "nxdrive.nuxeo.engine.engine.Processor", autospec=True
        ) as processor_cls:
            processor = engine.create_processor(getter)

        processor_cls.assert_called_once_with(engine, getter)
        assert processor is processor_cls.return_value

    def test_direct_transfer_normalizes_default_document_types(self, tmp_path):
        engine = _make_engine()
        engine.doc_container_type = "Workspace"
        engine._save_last_dt_session_infos = Mock()
        engine.dao.get_count.return_value = 0
        engine.dao.create_session.return_value = 8
        engine.dao.plan_many_direct_transfer_items.return_value = 101
        folder = tmp_path / "folder"
        child = folder / "child.txt"
        folder.mkdir()
        child.write_text("x")

        with patch("nxdrive.nuxeo.engine.engine.Options") as options:
            options.database_batch_size = 100
            engine._direct_transfer(
                {folder: 0, child: 1},
                "/remote",
                "remote-ref",
                "Remote",
                document_type="Workspace",
                container_type="Workspace",
            )

        planned = list(engine.dao.plan_many_direct_transfer_items.call_args.args[0])
        assert [item[7] for item in planned] == [None, None]
        engine.dao.queue_many_direct_transfer_items.assert_called_once_with(101)

    def test_direct_transfer_delegates_all_public_arguments(self):
        engine = _make_engine()
        engine._direct_transfer = Mock()
        paths = {Path("file.txt"): 1}

        engine.direct_transfer(
            paths,
            "/remote",
            "remote-ref",
            "Remote",
            duplicate_behavior="overwrite",
            new_folder="New",
            new_folder_type="Workspace",
        )

        engine._direct_transfer.assert_called_once_with(
            paths,
            "/remote",
            "remote-ref",
            "Remote",
            duplicate_behavior="overwrite",
            last_local_selected_location=None,
            last_local_selected_doc_type=None,
            new_folder="New",
            new_folder_type="Workspace",
        )
