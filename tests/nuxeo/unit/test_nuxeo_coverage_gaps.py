"""Focused tests for baseline Codecov gaps in Nuxeo implementations."""

import errno
import hashlib
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from nuxeo.exceptions import CorruptedFile, HTTPError

from nxdrive.drive.constants import TransferStatus
from nxdrive.drive.engine.activity import DownloadAction, UploadAction
from nxdrive.drive.exceptions import (
    DownloadPaused,
    NotFound,
    ScrollDescendantsError,
    UploadPaused,
)
from nxdrive.nuxeo.client.remote_client import Remote
from nxdrive.nuxeo.engine.processor import Processor


@pytest.fixture(autouse=True)
def _restore_processor_class_state():
    soft_locks = Processor.soft_locks
    readonly_locks = Processor.readonly_locks
    yield
    Processor.soft_locks = soft_locks
    Processor.readonly_locks = readonly_locks


def _processor():
    engine = MagicMock()
    engine.uid = "engine-1"
    engine.type = "NUXEO"
    engine.download_dir = Path("downloads")
    engine.dao = MagicMock()
    engine.local = MagicMock()
    engine.remote = MagicMock()
    processor = Processor(engine, Mock(return_value=None))
    processor.thread_id = 17
    processor._current_doc_pair = None
    processor._current_metrics = {}
    processor._interact = Mock()
    Processor.soft_locks = {}
    Processor.readonly_locks = {}
    return processor


def _pair(**changes):
    values = {
        "id": 7,
        "pair_state": "locally_modified",
        "local_state": "modified",
        "remote_state": "synchronized",
        "local_path": Path("parent/file.txt"),
        "local_parent_path": Path("parent"),
        "local_name": "file.txt",
        "local_digest": "local-digest",
        "remote_ref": "factory#remote-id",
        "remote_parent_ref": "factory#parent-id",
        "remote_parent_path": "/root",
        "remote_name": "file.txt",
        "remote_digest": "remote-digest",
        "remote_can_create_child": True,
        "remote_can_delete": True,
        "remote_can_rename": True,
        "remote_can_update": True,
        "folderish": False,
        "error_count": 0,
        "last_error": None,
        "version": 1,
        "session": 0,
        "size": 10,
        "last_remote_updated": "2026-01-01",
        "creation_date": "2025-01-01",
    }
    values.update(changes)
    return SimpleNamespace(**values)


def _execute_with(exception, *, pair=None):
    processor = _processor()
    pair = pair or _pair()
    processor._get_item = Mock(side_effect=[pair, None])
    processor._get_next_doc_pair = Mock(return_value=pair)
    processor._handle_doc_pair_sync = Mock(side_effect=exception)
    processor._handle_doc_pair_dt = Mock(side_effect=exception)
    processor.remove_void_transfers = Mock()
    processor.increase_error = Mock()
    processor._handle_pair_handler_exception = Mock()
    processor._postpone_pair = Mock()
    return processor, pair


def _remote():
    remote = Remote.__new__(Remote)
    remote.client = MagicMock()
    remote.client.host = "https://server.example/nuxeo/"
    remote.client.api_path = "/api/v1"
    remote.client.client_kwargs = {}
    remote.operations = MagicMock()
    remote.dao = MagicMock()
    remote.auth = MagicMock()
    remote.token = None
    remote.verification_needed = True
    remote.download_callback = ()
    return remote


class TestProcessorExecuteGaps:
    def test_skips_unprocessable_pair_and_releases_it(self):
        processor = _processor()
        pair = _pair(pair_state="synchronized")
        processor._get_item = Mock(side_effect=[pair, None])
        processor._get_next_doc_pair = Mock(return_value=pair)
        processor.remove_void_transfers = Mock()
        processor._synchronize_synchronized = Mock()

        processor._execute()

        processor.remove_void_transfers.assert_called_once_with(pair)
        processor.dao.release_state.assert_called_once_with(processor.thread_id)

    def test_unhandled_http_status_uses_status_specific_error(self):
        error = HTTPError(status=418, message="teapot")
        processor, pair = _execute_with(error)

        processor._execute()

        processor._handle_pair_handler_exception.assert_called_once_with(
            pair, "_synchronize_locally_modified_http_error_418", error
        )

    def test_long_path_error_removes_filter_and_notifies(self):
        error = OSError(errno.ENAMETOOLONG, "too long")
        error.winerror = None
        processor, pair = _execute_with(error)

        processor._execute()

        processor.dao.remove_filter.assert_called_once_with("/root/factory#remote-id")
        processor.engine.longPathError.emit.assert_called_once_with(pair)

    def test_unexpected_exception_is_forwarded_and_recorded(self):
        error = ValueError("boom")
        processor, pair = _execute_with(error)

        with patch("nxdrive.nuxeo.engine.processor.sys.excepthook") as excepthook:
            processor._execute()

        excepthook.assert_called_once()
        processor._handle_pair_handler_exception.assert_called_once_with(
            pair, "_synchronize_locally_modified", error
        )


class TestProcessorSynchronizationGaps:
    def test_refresh_that_invalidates_pair_stops_sync_dispatch(self):
        processor = _processor()
        pair = _pair(pair_state="locally_modified")
        remote_info = SimpleNamespace(digest=pair.remote_digest, name=pair.remote_name)
        processor.remote.get_fs_info.return_value = remote_info
        processor._refresh_remote = Mock()
        processor.dao.get_state_from_id.return_value = None
        handler = Mock()

        with patch("nxdrive.nuxeo.engine.processor.MAC", False):
            processor._handle_doc_pair_sync(pair, handler)

        handler.assert_not_called()

    def test_refresh_during_sync_can_report_remote_not_found(self):
        processor = _processor()
        pair = _pair(pair_state="locally_modified", remote_ref="missing")
        processor.remote.get_fs_info.side_effect = NotFound("gone")
        processor.local.exists.return_value = False
        processor._get_normal_state_from_remote_ref = Mock(return_value=None)

        processor._handle_doc_pair_sync(pair, Mock())

        assert pair.remote_ref == ""
        processor.dao.remove_state.assert_called_once_with(pair)

    def test_unaccessible_digest_is_refreshed_and_postponed(self):
        from nxdrive.drive.constants import UNACCESSIBLE_HASH

        processor = _processor()
        pair = _pair(local_digest=UNACCESSIBLE_HASH)
        info = Mock()
        info.get_digest.return_value = UNACCESSIBLE_HASH
        processor.local.get_info.return_value = info
        processor._postpone_pair = Mock()

        processor._synchronize_locally_modified(pair)

        processor._postpone_pair.assert_called_once_with(pair, "Unaccessible hash")

    def test_unaccessible_digest_refresh_updates_local_state(self):
        from nxdrive.drive.constants import UNACCESSIBLE_HASH

        processor = _processor()
        pair = _pair(local_digest=UNACCESSIBLE_HASH, remote_digest="fresh")
        info = Mock()
        info.get_digest.return_value = "fresh"
        processor.local.get_info.return_value = info
        processor.local.is_equal_digests.return_value = True
        processor.remote.get_fs_info.return_value = SimpleNamespace(
            name=pair.local_name, digest="fresh"
        )

        processor._synchronize_locally_modified(pair)

        processor.dao.update_local_state.assert_called_once_with(
            pair, info, versioned=False, queue=False
        )

    def test_existing_resolved_folder_dispatches_move(self):
        processor = _processor()
        pair = _pair(
            pair_state="locally_resolved",
            local_state="resolved",
            folderish=True,
            remote_ref="factory#uid",
        )
        parent = _pair(remote_ref="factory#parent")
        info = SimpleNamespace(
            is_trashed=False,
            name=pair.local_name,
            folderish=True,
        )
        fs_info = SimpleNamespace(
            uid=pair.remote_ref,
            parent_uid=parent.remote_ref,
            digest=pair.local_digest,
            name=pair.local_name,
        )
        processor.local.get_remote_id.return_value = pair.remote_ref
        processor.dao.get_state_from_local.return_value = parent
        processor.remote.get_info.return_value = info
        processor.remote.get_fs_info.return_value = fs_info
        processor.local.is_equal_digests.return_value = True
        processor._synchronize_locally_moved = Mock()

        processor._synchronize_locally_created(pair, overwrite=True)

        processor._synchronize_locally_moved.assert_called_once_with(pair)
        processor.dao.synchronize_state.assert_called_once_with(pair)

    def test_created_file_moved_while_remote_id_is_written(self):
        processor = _processor()
        pair = _pair(pair_state="locally_created", local_state="created")
        parent = _pair(
            local_path=Path("parent"),
            remote_ref="parent-ref",
            remote_parent_path="/root",
            remote_name="parent",
        )
        moved = _pair(id=pair.id, local_path=Path("new/file.txt"))
        local_info = SimpleNamespace(size=pair.size)
        remote_info = SimpleNamespace(uid="new-ref")
        processor.local.get_remote_id.return_value = None
        processor.dao.get_state_from_local.return_value = parent
        processor.local.get_info.return_value = local_info
        processor.remote.stream_file.return_value = remote_info
        processor.local.set_remote_id.side_effect = [
            NotFound("moved"),
            NotFound("moved again"),
            None,
        ]
        processor.dao.get_state_from_id.return_value = moved
        processor._synchronize_locally_moved = Mock()

        processor._synchronize_locally_created(pair)

        assert processor.remote.stream_file.call_args.kwargs["doc_pair"] == pair.id
        processor.local.set_remote_id.assert_any_call(moved.local_path, "new-ref")
        processor._synchronize_locally_moved.assert_called_once_with(
            moved, update=False
        )

    def test_readonly_creation_rolls_back_local_pair(self):
        processor = _processor()
        pair = _pair(pair_state="locally_created", local_state="created")
        parent = _pair(
            remote_ref="parent-ref",
            remote_can_create_child=False,
            remote_name="readonly-parent",
        )
        processor.local.get_remote_id.return_value = None
        processor.dao.get_state_from_local.return_value = parent
        processor.engine.local_rollback.return_value = True

        processor._synchronize_locally_created(pair)

        processor.local.delete.assert_called_once_with(pair.local_path)
        processor.dao.remove_state.assert_called_once_with(pair)

    def test_local_move_uses_database_parent_when_xattr_is_missing(self):
        processor = _processor()
        pair = _pair(local_state="moved", local_name="file.txt", remote_name="file.txt")
        parent = _pair(remote_ref=pair.remote_parent_ref)
        processor.local.get_remote_id.return_value = None
        processor.dao.get_state_from_local.return_value = parent
        processor._synchronize_if_not_remotely_dirty = Mock()

        processor._synchronize_locally_moved(pair)

        processor._synchronize_if_not_remotely_dirty.assert_called_once_with(
            pair, remote_info=None
        )

    def test_local_move_without_parent_fails_clearly(self):
        processor = _processor()
        pair = _pair(local_name="renamed.txt", remote_name="file.txt")
        processor.local.get_remote_id.return_value = "new-parent"
        processor._get_normal_state_from_remote_ref = Mock(return_value=None)
        processor.remote.rename.return_value = SimpleNamespace(name="renamed.txt")
        processor._refresh_remote = Mock()

        with pytest.raises(ValueError, match="parent pair"):
            processor._synchronize_locally_moved(pair)

    def test_download_duplicate_fallback_streams_remote_content(self, tmp_path):
        processor = _processor()
        processor.engine.download_dir = tmp_path
        pair = _pair()
        duplicate = _pair(local_path=Path("stale"))
        processor.dao.get_valid_duplicate_file.return_value = duplicate
        processor.local.abspath.return_value = tmp_path / "missing"
        expected = tmp_path / "downloaded"
        processor.remote.stream_content.return_value = expected

        result = processor._download_content(pair, Path("target.txt"))

        assert result == expected
        processor.remote.stream_content.assert_called_once()

    def test_remote_content_update_without_rename_keeps_original_path(self):
        processor = _processor()
        pair = _pair()
        os_path = Path("sync/file.txt")
        tmp_file = Path("temporary/file.txt")
        updated = SimpleNamespace(
            filepath=os_path,
            get_digest=Mock(return_value=pair.remote_digest),
        )
        processor.local.abspath.return_value = os_path
        processor._download_content = Mock(return_value=tmp_file)
        processor.local.get_remote_id.return_value = None
        processor.local.move.return_value = updated
        processor._refresh_local_state = Mock()

        with patch("nxdrive.nuxeo.engine.processor.shutil.rmtree"):
            processor._update_remotely(pair, False)

        processor._download_content.assert_called_once_with(pair, os_path)

    def test_remote_folder_move_locks_and_releases_folder(self):
        processor = _processor()
        pair = _pair(
            pair_state="remotely_modified",
            folderish=True,
            local_path=Path("old/folder"),
            local_parent_path=Path("old"),
            local_name="folder",
            remote_name="renamed",
        )
        parent = _pair(
            local_path=Path("new-parent"),
            remote_ref="new-parent-ref",
            remote_parent_path="/root",
        )
        processor.local.is_equal_digests.return_value = True
        processor._is_remote_move = Mock(return_value=(True, parent))
        processor.remote.is_filtered.return_value = False
        processor.local.exists.return_value = True
        processor.local.get_remote_id.return_value = pair.remote_ref
        processor.local.abspath.side_effect = lambda path: path
        updated = SimpleNamespace(path=Path("new-parent/renamed"))
        processor.local.move.return_value = updated
        processor._refresh_local_state = Mock()
        processor._handle_readonly = Mock()

        processor._synchronize_remotely_modified(pair)

        processor.engine.set_local_folder_lock.assert_called_once_with(pair.local_path)
        processor.local.move.assert_called_once_with(
            pair.local_path, parent.local_path, name=pair.remote_name
        )
        processor.engine.release_folder_lock.assert_called_once()

    def test_remote_create_missing_parent_is_postponed(self):
        processor = _processor()
        pair = _pair(pair_state="remotely_created")
        processor._get_normal_state_from_remote_ref = Mock(return_value=None)

        with pytest.raises(Exception) as caught:
            processor._synchronize_remotely_created(pair)

        assert type(caught.value).__name__ == "ParentNotSynced"

    def test_remote_create_parent_without_local_path_is_postponed(self):
        processor = _processor()
        pair = _pair(pair_state="remotely_created")
        parent = _pair(local_path=None, pair_state="synchronized")
        processor._get_normal_state_from_remote_ref = Mock(return_value=parent)

        with pytest.raises(Exception) as caught:
            processor._synchronize_remotely_created(pair)

        assert type(caught.value).__name__ == "ParentNotSynced"

    def test_remote_create_not_found_dispatches_remote_delete(self):
        processor = _processor()
        pair = _pair(pair_state="remotely_created")
        parent = _pair(local_path=Path("parent"), remote_ref=pair.remote_parent_ref)
        processor._get_normal_state_from_remote_ref = Mock(return_value=parent)
        processor.remote.is_filtered.return_value = False
        processor.local.exists.return_value = False
        processor.local.get_remote_id.return_value = parent.remote_ref
        processor._create_remotely = Mock(side_effect=NotFound("gone"))
        processor._synchronize_remotely_deleted = Mock()

        processor._synchronize_remotely_created(pair)

        processor._synchronize_remotely_deleted.assert_called_once_with(pair)

    def test_remote_create_version_race_dispatches_move_and_delete(self):
        processor = _processor()
        pair = _pair(pair_state="remotely_created")
        parent = _pair(local_path=Path("parent"), remote_ref=pair.remote_parent_ref)
        created_path = Path("parent/file.txt")
        moved = _pair(
            local_state="moved",
            remote_state="synchronized",
            local_path=created_path,
        )
        deleted = _pair(
            local_state="synchronized",
            remote_state="deleted",
            local_path=created_path,
        )
        processor._get_normal_state_from_remote_ref = Mock(return_value=parent)
        processor.remote.is_filtered.return_value = False
        processor.local.exists.return_value = False
        processor.local.get_remote_id.return_value = parent.remote_ref
        processor._create_remotely = Mock(return_value=created_path)
        processor.local.get_info.return_value = Mock()
        processor._refresh_local_state = Mock()
        processor._handle_readonly = Mock()
        processor.dao.synchronize_state.side_effect = [False, False, False]
        processor.dao.get_state_from_id.side_effect = [moved, deleted, None]
        processor._synchronize_locally_moved = Mock()
        processor._synchronize_remotely_deleted = Mock()

        processor._synchronize_remotely_created(pair)
        processor._synchronize_remotely_created(pair)
        processor._synchronize_remotely_created(pair)

        processor._synchronize_locally_moved.assert_called_once_with(
            moved, update=False
        )
        processor._synchronize_remotely_deleted.assert_called_once_with(deleted)

    def test_remote_folder_delete_uses_lock_and_trash(self):
        processor = _processor()
        pair = _pair(
            pair_state="remotely_deleted",
            folderish=True,
            local_state="synchronized",
        )
        processor.local.get_remote_id.return_value = pair.remote_ref
        processor.engine.use_trash.return_value = True

        processor._synchronize_remotely_deleted(pair)

        processor.engine.set_local_folder_lock.assert_called_once_with(pair.local_path)
        processor.local.delete.assert_called_once_with(pair.local_path)
        processor.dao.remove_state.assert_called_once_with(pair)
        processor.engine.release_folder_lock.assert_called_once()


class TestRemoteClientCoverageGaps:
    def test_transfer_end_without_current_action_is_a_noop(self):
        remote = _remote()

        with patch(
            "nxdrive.nuxeo.client.remote_client.Action.get_current_action",
            return_value=None,
        ):
            remote.transfer_end_callback(Mock())

        remote.dao.get_download.assert_not_called()

    def test_transfer_end_pauses_download_and_upload(self):
        remote = _remote()
        download_action = MagicMock(spec=DownloadAction)
        download_action.filepath = Path("download")
        download_action.chunk_transfer_end_time_ns = 10
        download_action.chunk_transfer_start_time_ns = 0
        download_action.transferred_chunks = 0
        download_action.size = 100
        download_action.chunk_size = 10
        download = SimpleNamespace(uid=4, status=TransferStatus.PAUSED, progress=0)
        remote.dao.get_download.return_value = download

        with patch(
            "nxdrive.nuxeo.client.remote_client.Action.get_current_action",
            return_value=download_action,
        ):
            with pytest.raises(DownloadPaused):
                remote.transfer_end_callback(Mock())
        assert download_action.last_chunk_transfer_speed == 0

        upload_action = MagicMock(spec=UploadAction)
        upload_action.filepath = Path("upload")
        upload_action.doc_pair = 7
        upload_action.chunk_transfer_end_time_ns = 10
        upload_action.chunk_transfer_start_time_ns = 0
        upload_action.transferred_chunks = 0
        upload_action.size = 100
        upload_action.chunk_size = 10
        remote.dao.get_upload.return_value = SimpleNamespace(
            uid=5, status=TransferStatus.PAUSED
        )
        with patch(
            "nxdrive.nuxeo.client.remote_client.Action.get_current_action",
            return_value=upload_action,
        ):
            with pytest.raises(UploadPaused):
                remote.transfer_end_callback(Mock())
        assert upload_action.last_chunk_transfer_speed == 0

    def test_execute_maps_not_found_and_reraises_other_http_errors(self):
        remote = _remote()
        remote.operations.execute.side_effect = HTTPError(status=404, message="gone")
        with pytest.raises(NotFound):
            remote.execute(command="Document.Fetch")

        error = HTTPError(status=500, message="failed")
        remote.operations.execute.side_effect = error
        with pytest.raises(HTTPError) as caught:
            remote.execute(command="Document.Fetch")
        assert caught.value is error

    def test_request_token_uses_non_basic_auth(self):
        remote = _remote()
        remote.auth = MagicMock()
        remote.auth.get_token.return_value = "token"

        assert remote.request_token() == "token"
        remote.auth.get_token.assert_called_once_with(client=remote.client)

    def test_revoke_token_swallows_http_error(self):
        remote = _remote()
        remote.auth.revoke_token.side_effect = HTTPError(status=404, message="gone")

        remote.revoke_token()

    def test_download_without_output_returns_response_content(self):
        remote = _remote()
        response = SimpleNamespace(content=b"payload", headers={})
        remote.client.request.return_value = response

        assert remote.download("/blob", Path("logical"), None, "") == b"payload"

    def test_download_creates_transfer_record(self, tmp_path):
        remote = _remote()
        output = tmp_path / "small.bin"
        response = SimpleNamespace(content=b"payload", headers={"Content-Length": "7"})
        remote.client.request.return_value = response
        remote.dao.get_download.return_value = None
        remote.check_integrity_simple = Mock()

        result = remote.download(
            "/blob",
            Path("logical.bin"),
            output,
            "digest",
            doc_pair_id=3,
            engine_uid="engine-1",
            is_direct_edit=True,
        )

        assert result == output
        assert output.read_bytes() == b"payload"
        saved = remote.dao.save_download.call_args.args[0]
        assert saved.doc_pair == 3
        assert saved.engine == "engine-1"
        assert saved.is_direct_edit is True

    def test_corrupted_download_removes_temporary_file(self, tmp_path):
        remote = _remote()
        output = tmp_path / "bad.bin"
        response = SimpleNamespace(content=b"bad", headers={"Content-Length": "3"})
        remote.client.request.return_value = response
        remote.dao.get_download.return_value = SimpleNamespace(
            status=TransferStatus.ONGOING
        )
        remote.check_integrity_simple = Mock(
            side_effect=CorruptedFile(output, "expected", "actual")
        )

        with pytest.raises(CorruptedFile):
            remote.download("/blob", Path("logical.bin"), output, "expected")
        assert not output.exists()

    def test_integrity_skip_paths_and_success_callback(self, tmp_path):
        remote = _remote()
        output = tmp_path / "file.bin"
        output.write_bytes(b"payload")
        action = SimpleNamespace(size=7, tmppath=output, filepath=output)

        with patch("nxdrive.nuxeo.client.remote_client.Options") as options:
            options.disabled_file_integrity_check = True
            remote.check_integrity("not-a-digest", action)
            remote.check_integrity_simple("not-a-digest", output)

        with patch("nxdrive.nuxeo.client.remote_client.Options") as options:
            options.disabled_file_integrity_check = False
            with patch(
                "nxdrive.nuxeo.client.remote_client.get_digest_algorithm",
                return_value=None,
            ):
                remote.check_integrity("unknown", action)
                remote.check_integrity_simple("unknown", output)

        digest = hashlib.md5(b"payload").hexdigest()
        verification = SimpleNamespace(progress=0)

        def compute(_path, _digester, *, callback):
            callback(output)
            return digest

        with patch("nxdrive.nuxeo.client.remote_client.Options") as options:
            options.disabled_file_integrity_check = False
            with patch(
                "nxdrive.nuxeo.client.remote_client.get_digest_algorithm",
                return_value=hashlib.md5,
            ), patch(
                "nxdrive.nuxeo.client.remote_client.compute_digest",
                side_effect=compute,
            ), patch(
                "nxdrive.nuxeo.client.remote_client.VerificationAction",
                return_value=verification,
            ):
                remote.check_integrity(digest, action)
        assert verification.progress > 0

    def test_get_fs_info_and_scroll_reject_empty_responses(self):
        remote = _remote()
        remote.get_fs_item = Mock(return_value=None)
        with pytest.raises(NotFound):
            remote.get_fs_info("missing")

        remote.execute = Mock(return_value={})
        with pytest.raises(ScrollDescendantsError):
            remote.scroll_descendants("root", None)

    def test_proxy_and_server_configuration_errors_are_safe(self):
        remote = _remote()
        proxy = Mock()
        proxy.settings.side_effect = ValueError("bad proxy")

        remote.set_proxy(proxy)
        assert "proxies" not in remote.client.client_kwargs

        remote.client.request.side_effect = OSError("offline")
        assert remote.get_server_configuration() == {}
        assert remote.get_config_types() == {}
