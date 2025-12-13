"""Unit tests for nxdrive.engine.processor module."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from nxdrive.constants import TransferStatus
from nxdrive.engine.processor import Processor
from nxdrive.exceptions import NotFound, UploadCancelled, UploadPaused
from nxdrive.objects import DocPair, Session


@pytest.fixture
def mock_engine():
    """Create a mock Engine for testing."""
    engine = Mock()
    engine.uid = "test-engine-uid"
    engine.dao = Mock()
    engine.local = Mock()
    engine.remote = Mock()
    engine.queue_manager = Mock()
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    engine.get_metadata_url = Mock(return_value="http://test.url/metadata")
    engine.get_remote_url = Mock(return_value="http://test.url/remote")
    return engine


@pytest.fixture
def processor(mock_engine):
    """Create a Processor instance with mocked dependencies."""
    item_getter = Mock(return_value=None)
    return Processor(mock_engine, item_getter)


@pytest.fixture
def doc_pair():
    """Create a sample DocPair for testing."""
    pair = Mock(spec=DocPair)
    pair.id = 1
    pair.local_path = Path("test_file.txt")
    pair.local_parent_path = Path(".")
    pair.remote_ref = "remote123"
    pair.remote_parent_ref = "parent123"
    pair.local_name = "test_file.txt"
    pair.remote_name = "test_file.txt"
    pair.pair_state = "locally_created"
    pair.local_state = "created"
    pair.remote_state = "unknown"
    pair.folderish = False
    pair.local_digest = "abc123"
    pair.remote_digest = "abc123"
    pair.session = None
    pair.version = 0
    return pair


class TestHandleDocPairSync:
    """Tests for _handle_doc_pair_sync method."""

    def test_handle_doc_pair_sync_non_standard_digest(self, processor, doc_pair):
        """Test handling document with non-standard digest."""
        doc_pair.pair_state = "remotely_created"
        doc_pair.remote_digest = "invalid_digest"

        with patch.object(processor.dao, "unsynchronize_state") as mock_unsync:
            processor._handle_doc_pair_sync(doc_pair, Mock())

            # Should unsynchronize with digest status
            mock_unsync.assert_called_once()
            args = mock_unsync.call_args[0]
            assert args[0] == doc_pair

    def test_handle_doc_pair_sync_mac_finder_info(self, processor, doc_pair):
        """Test MAC-specific finder info handling."""
        doc_pair.remote_ref = "remote123"

        with patch("nxdrive.engine.processor.MAC", True):
            with patch.object(
                processor.local, "get_remote_id", return_value="brokMACS_data"
            ):
                with patch.object(processor, "_postpone_pair") as mock_postpone:
                    with patch.object(processor.engine.manager.osi, "send_sync_status"):
                        sync_handler = Mock()
                        processor._handle_doc_pair_sync(doc_pair, sync_handler)

                        # Should postpone when brokMACS found
                        mock_postpone.assert_called_once()

    def test_handle_doc_pair_sync_parent_dedup_error(self, processor, doc_pair):
        """Test handling when parent has duplication error."""
        doc_pair.remote_parent_ref = "parent123"

        parent_pair = Mock()
        parent_pair.last_error = "DEDUP"

        with patch.object(
            processor, "_get_normal_state_from_remote_ref", return_value=parent_pair
        ):
            with patch.object(processor.engine.manager.osi, "send_sync_status"):
                with patch.object(processor.local, "get_remote_id", return_value=None):
                    sync_handler = Mock()
                    processor._handle_doc_pair_sync(doc_pair, sync_handler)

                    # Should not call sync_handler
                    sync_handler.assert_not_called()

    def test_handle_doc_pair_sync_parent_not_exists(self, processor, doc_pair):
        """Test handling when parent path doesn't exist and parent moved."""
        doc_pair.local_parent_path = Path("nonexistent")
        doc_pair.remote_parent_ref = "parent123"

        parent_pair = Mock()
        parent_pair.local_path = Path("new_parent")

        with patch.object(processor.engine.manager.osi, "send_sync_status"):
            with patch.object(processor.local, "get_remote_id", return_value=None):
                with patch.object(processor.local, "exists", return_value=False):
                    with patch.object(
                        processor,
                        "_get_normal_state_from_remote_ref",
                        return_value=parent_pair,
                    ):
                        with patch.object(
                            processor.dao, "get_download", return_value=None
                        ):
                            with patch.object(
                                processor.dao, "get_upload", return_value=None
                            ):
                                with patch.object(
                                    processor,
                                    "_lock_soft_path",
                                    return_value=Path("test"),
                                ):
                                    with patch.object(processor, "_unlock_soft_path"):
                                        with patch.object(
                                            processor.dao,
                                            "get_state_from_id",
                                            return_value=doc_pair,
                                        ):
                                            with patch.object(
                                                processor.local,
                                                "abspath",
                                                return_value=Path("/abs/test"),
                                            ):
                                                sync_handler = Mock(
                                                    __name__="sync_handler"
                                                )
                                                processor._handle_doc_pair_sync(
                                                    doc_pair, sync_handler
                                                )

                                                # Parent path should be updated
                                                assert (
                                                    doc_pair.local_parent_path
                                                    == parent_pair.local_path
                                                )

    def test_handle_doc_pair_sync_download_paused(self, processor, doc_pair):
        """Test handling when download is paused."""
        download = Mock()
        download.status = TransferStatus.PAUSED

        with patch.object(processor.engine.manager.osi, "send_sync_status"):
            with patch.object(processor.local, "get_remote_id", return_value=None):
                with patch.object(processor.local, "exists", return_value=True):
                    with patch.object(
                        processor,
                        "_get_normal_state_from_remote_ref",
                        return_value=None,
                    ):
                        with patch.object(
                            processor.dao, "get_download", return_value=download
                        ):
                            sync_handler = Mock()
                            processor._handle_doc_pair_sync(doc_pair, sync_handler)

                            # Should not call sync_handler when download is paused
                            sync_handler.assert_not_called()

    def test_handle_doc_pair_sync_upload_paused(self, processor, doc_pair):
        """Test handling when upload is paused."""
        upload = Mock()
        upload.status = TransferStatus.PAUSED

        with patch.object(processor.engine.manager.osi, "send_sync_status"):
            with patch.object(processor.local, "get_remote_id", return_value=None):
                with patch.object(processor.local, "exists", return_value=True):
                    with patch.object(
                        processor,
                        "_get_normal_state_from_remote_ref",
                        return_value=None,
                    ):
                        with patch.object(
                            processor.dao, "get_download", return_value=None
                        ):
                            with patch.object(
                                processor.dao, "get_upload", return_value=upload
                            ):
                                sync_handler = Mock()
                                processor._handle_doc_pair_sync(doc_pair, sync_handler)

                                # Should not call sync_handler when upload is paused
                                sync_handler.assert_not_called()

    def test_handle_doc_pair_sync_success(self, processor, doc_pair):
        """Test successful sync handling."""
        with patch.object(processor.engine.manager.osi, "send_sync_status"):
            with patch.object(processor.local, "get_remote_id", return_value=None):
                with patch.object(processor.local, "exists", return_value=True):
                    with patch.object(
                        processor,
                        "_get_normal_state_from_remote_ref",
                        return_value=None,
                    ):
                        with patch.object(
                            processor.dao, "get_download", return_value=None
                        ):
                            with patch.object(
                                processor.dao, "get_upload", return_value=None
                            ):
                                with patch.object(
                                    processor,
                                    "_lock_soft_path",
                                    return_value=Path("test"),
                                ):
                                    with patch.object(processor, "_unlock_soft_path"):
                                        with patch.object(
                                            processor.dao,
                                            "get_state_from_id",
                                            return_value=doc_pair,
                                        ):
                                            with patch.object(
                                                processor.local,
                                                "abspath",
                                                return_value=Path("/abs/test"),
                                            ):
                                                sync_handler = Mock(
                                                    __name__="sync_handler"
                                                )
                                                processor._handle_doc_pair_sync(
                                                    doc_pair, sync_handler
                                                )

                                                # Sync handler should be called
                                                sync_handler.assert_called_once_with(
                                                    doc_pair
                                                )

    def test_handle_doc_pair_sync_signals_emitted(self, processor, doc_pair):
        """Test that signals are emitted correctly."""
        with patch.object(processor.engine.manager.osi, "send_sync_status"):
            with patch.object(processor.local, "get_remote_id", return_value=None):
                with patch.object(processor.local, "exists", return_value=True):
                    with patch.object(
                        processor,
                        "_get_normal_state_from_remote_ref",
                        return_value=None,
                    ):
                        with patch.object(
                            processor.dao, "get_download", return_value=None
                        ):
                            with patch.object(
                                processor.dao, "get_upload", return_value=None
                            ):
                                with patch.object(
                                    processor,
                                    "_lock_soft_path",
                                    return_value=Path("test"),
                                ):
                                    with patch.object(processor, "_unlock_soft_path"):
                                        with patch.object(
                                            processor.dao,
                                            "get_state_from_id",
                                            return_value=doc_pair,
                                        ):
                                            with patch.object(
                                                processor.local,
                                                "abspath",
                                                return_value=Path("/abs/test"),
                                            ):
                                                with patch.object(
                                                    processor, "pairSyncStarted"
                                                ) as mock_started:
                                                    with patch.object(
                                                        processor, "pairSyncEnded"
                                                    ) as mock_ended:
                                                        sync_handler = Mock(
                                                            __name__="sync_handler"
                                                        )
                                                        processor._handle_doc_pair_sync(
                                                            doc_pair, sync_handler
                                                        )

                                                        # Both signals should be emitted
                                                        mock_started.emit.assert_called_once()
                                                        mock_ended.emit.assert_called_once()


class TestHandleDocPairDt:
    """Tests for _handle_doc_pair_dt method."""

    def test_handle_doc_pair_dt_not_found(self, processor, doc_pair):
        """Test handling NotFound exception in Direct Transfer."""
        sync_handler = Mock(
            __name__="sync_handler", side_effect=NotFound("Batch not found")
        )

        with patch.object(processor, "_direct_transfer_cancel") as mock_cancel:
            with pytest.raises(NotFound):
                processor._handle_doc_pair_dt(doc_pair, sync_handler)

            mock_cancel.assert_called_once_with(doc_pair)

    def test_handle_doc_pair_dt_parent_not_synced(self, processor, doc_pair):
        """Test handling HTTPError 404 (parent not synced)."""
        from nuxeo.exceptions import HTTPError

        exc = HTTPError(status=404, message="Not found")
        sync_handler = Mock(__name__="sync_handler", side_effect=exc)

        with patch.object(processor, "_postpone_pair") as mock_postpone:
            processor._handle_doc_pair_dt(doc_pair, sync_handler)

            # Should call postpone with proper arguments
            assert mock_postpone.called
            call_args = mock_postpone.call_args[0]
            assert call_args[0] == doc_pair

    def test_handle_doc_pair_dt_upload_cancelled(self, processor, doc_pair):
        """Test handling UploadCancelled exception."""
        upload = Mock()
        upload.batch = "batch123"
        upload.doc_pair = 1

        exc = UploadCancelled(123)
        sync_handler = Mock(__name__="sync_handler", side_effect=exc)

        with patch.object(processor.dao, "get_dt_upload", return_value=upload):
            with patch.object(processor.remote, "cancel_batch"):
                with patch.object(
                    processor.dao, "get_state_from_id", return_value=doc_pair
                ):
                    with patch.object(
                        processor, "_direct_transfer_cancel"
                    ) as mock_cancel:
                        processor._handle_doc_pair_dt(doc_pair, sync_handler)

                        mock_cancel.assert_called_once_with(doc_pair)

    def test_handle_doc_pair_dt_upload_paused(self, processor, doc_pair):
        """Test that UploadPaused is re-raised."""
        sync_handler = Mock(__name__="sync_handler", side_effect=UploadPaused(123))

        with pytest.raises(UploadPaused):
            processor._handle_doc_pair_dt(doc_pair, sync_handler)

    def test_handle_doc_pair_dt_runtime_error(self, processor, doc_pair):
        """Test that RuntimeError is re-raised."""
        sync_handler = Mock(
            __name__="sync_handler", side_effect=RuntimeError("Test error")
        )

        with pytest.raises(RuntimeError):
            processor._handle_doc_pair_dt(doc_pair, sync_handler)

    def test_handle_doc_pair_dt_general_exception(self, processor, doc_pair):
        """Test handling general exceptions in Direct Transfer."""
        doc_pair.local_path = Path("test_file.txt")
        doc_pair.local_state = "direct"

        # Create a generic exception (not one of the special cases)
        class CustomException(Exception):
            pass

        exc = CustomException("Test error")
        sync_handler = Mock(__name__="sync_handler", side_effect=exc)

        # The exception should be re-raised
        with pytest.raises(CustomException):
            processor._handle_doc_pair_dt(doc_pair, sync_handler)


class TestExecute:
    """Tests for _execute method."""

    def test_execute_no_items(self, processor):
        """Test execute when no items in queue."""
        processor._get_item = Mock(return_value=None)

        # Should exit loop when no items
        processor._execute()

        processor._get_item.assert_called_once()

    def test_execute_acquire_state_fails(self, processor, doc_pair):
        """Test execute when acquiring state fails."""
        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])

        with patch.object(processor, "_get_next_doc_pair", return_value=None):
            processor._execute()

            # Should continue to next iteration
            assert processor._get_item.call_count == 2

    def test_execute_thread_interrupt(self, processor, doc_pair):
        """Test handling ThreadInterrupt exception."""
        from nxdrive.exceptions import ThreadInterrupt

        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(
                processor, "_handle_doc_pair_sync", side_effect=ThreadInterrupt()
            ):
                with patch.object(processor, "_interact"):
                    with pytest.raises(ThreadInterrupt):
                        processor._execute()

                    # Verify the doc_pair was pushed back to queue
                    processor.engine.queue_manager.push.assert_called_once_with(
                        doc_pair
                    )

    def test_execute_not_found(self, processor, doc_pair):
        """Test handling NotFound exception."""
        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"
        doc_pair.version = 1

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(processor, "check_pair_state", return_value=True):
                with patch.object(processor, "remove_void_transfers"):
                    with patch.object(
                        processor,
                        "_synchronize_locally_created",
                        side_effect=NotFound(),
                    ):
                        with patch.object(
                            processor, "_handle_doc_pair_sync", side_effect=NotFound()
                        ):
                            with patch.object(processor, "_interact"):
                                with patch.object(processor.dao, "release_state"):
                                    processor._execute()

                                    # Should call remove_void_transfers for NotFound
                                    assert processor.remove_void_transfers.called

    def test_execute_pair_interrupt(self, processor, doc_pair):
        """Test handling PairInterrupt exception."""
        from nxdrive.exceptions import PairInterrupt

        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"
        doc_pair.version = 1

        exc = PairInterrupt("Interrupted", doc_pair)

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(processor, "check_pair_state", return_value=True):
                with patch.object(processor, "remove_void_transfers"):
                    with patch.object(
                        processor, "_handle_doc_pair_sync", side_effect=exc
                    ):
                        with patch.object(
                            processor.engine.queue_manager, "push"
                        ) as mock_push:
                            with patch.object(processor, "_interact"):
                                with patch.object(processor.dao, "release_state"):
                                    processor._execute()

                                    # Should push back to queue
                                    mock_push.assert_called_once_with(doc_pair)

    def test_execute_connection_error(self, processor, doc_pair):
        """Test handling connection errors."""
        from requests.exceptions import ConnectionError

        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"
        doc_pair.version = 1

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(processor, "check_pair_state", return_value=True):
                with patch.object(processor, "remove_void_transfers"):
                    with patch.object(
                        processor,
                        "_handle_doc_pair_sync",
                        side_effect=ConnectionError(),
                    ):
                        with patch.object(processor, "_postpone_pair") as mock_postpone:
                            with patch.object(processor, "_interact"):
                                with patch.object(processor.dao, "release_state"):
                                    processor._execute()

                                    # Should postpone with CONNECTION_ERROR
                                    assert mock_postpone.called
                                    call_args = mock_postpone.call_args[0]
                                    assert call_args[1] == "CONNECTION_ERROR"

    def test_execute_duplication_disabled_error(self, processor, doc_pair):
        """Test handling DuplicationDisabledError."""
        from nxdrive.exceptions import DuplicationDisabledError

        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(
                processor,
                "_handle_doc_pair_sync",
                side_effect=DuplicationDisabledError(),
            ):
                with patch.object(processor.dao, "increase_error") as mock_error:
                    with patch.object(processor.engine.queue_manager, "push_error"):
                        with patch.object(processor, "_interact"):
                            with patch.object(
                                processor, "check_pair_state", return_value=True
                            ):
                                processor._execute()

                                # giveup_error calls dao.increase_error
                                mock_error.assert_called_once()

    def test_execute_permission_error(self, processor, doc_pair):
        """Test handling PermissionError."""
        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(
                processor, "_handle_doc_pair_sync", side_effect=PermissionError()
            ):
                with patch.object(processor, "_postpone_pair") as mock_postpone:
                    with patch.object(processor.engine, "errorOpenedFile"):
                        with patch.object(processor, "_interact"):
                            with patch.object(
                                processor, "check_pair_state", return_value=True
                            ):
                                processor._execute()

                                # PermissionError calls _postpone_pair, not increase_error
                                mock_postpone.assert_called_once_with(
                                    doc_pair, "Used by another process"
                                )

    def test_execute_oserror_no_space(self, processor, doc_pair):
        """Test handling OSError with no space left."""
        item = Mock(id=1)
        processor._get_item = Mock(side_effect=[item, None])
        doc_pair.pair_state = "locally_created"
        doc_pair.version = 1

        exc = OSError()
        exc.errno = 28  # ENOSPC

        with patch.object(processor, "_get_next_doc_pair", return_value=doc_pair):
            with patch.object(processor, "check_pair_state", return_value=True):
                with patch.object(processor, "remove_void_transfers"):
                    with patch.object(
                        processor, "_handle_doc_pair_sync", side_effect=exc
                    ):
                        with patch.object(processor.engine, "suspend") as mock_suspend:
                            with patch.object(processor, "_interact"):
                                with patch.object(processor.dao, "release_state"):
                                    processor._execute()

                                    mock_suspend.assert_called_once()


class TestSynchronizeDirectTransfer:
    """Tests for _synchronize_direct_transfer method."""

    def test_synchronize_direct_transfer_session_paused(self, processor, doc_pair):
        """Test Direct Transfer when session is paused."""
        doc_pair.session = 1
        session = Mock(spec=Session)
        session.uid = 1
        session.status = TransferStatus.PAUSED

        with patch.object(processor.dao, "get_session", return_value=session):
            processor._synchronize_direct_transfer(doc_pair)

            # Should return early without uploading

    def test_synchronize_direct_transfer_file_not_exists(self, processor, doc_pair):
        """Test Direct Transfer when file doesn't exist."""
        doc_pair.local_path = Path("nonexistent.txt")
        doc_pair.session = None

        # Need to patch the specific Path creation and exists check
        # On non-Windows, the code does: path = Path(f"/{doc_pair.local_path}")
        with patch("nxdrive.engine.processor.WINDOWS", False):
            # Create a mock Path object to return from Path constructor
            mock_path = Mock(spec=Path)
            mock_path.exists.return_value = False

            with patch("nxdrive.engine.processor.Path", return_value=mock_path):
                # Ensure get_session returns None when session is None
                with patch.object(processor.dao, "get_session", return_value=None):
                    mock_signal = Mock()
                    processor.engine.directTranferError = mock_signal

                    # When no session, it calls _direct_transfer_cancel
                    with patch.object(
                        processor, "_direct_transfer_cancel"
                    ) as mock_cancel:
                        processor._synchronize_direct_transfer(doc_pair)

                        # Should emit error and cancel transfer
                        assert mock_signal.emit.called
                        mock_cancel.assert_called_once_with(doc_pair)

    def test_synchronize_direct_transfer_file_not_exists_with_session(
        self, processor, doc_pair
    ):
        """Test Direct Transfer when file doesn't exist with active session."""
        doc_pair.local_path = Path("nonexistent.txt")
        doc_pair.session = 1
        session = Mock(spec=Session)
        session.uid = 1
        session.status = TransferStatus.ONGOING

        with patch.object(processor.dao, "get_session", return_value=session):
            with patch.object(processor.engine, "directTranferError") as mock_error:
                with patch.object(processor.dao, "decrease_session_counts"):
                    with patch.object(processor, "_direct_transfer_end"):
                        processor._synchronize_direct_transfer(doc_pair)

                        mock_error.emit.assert_called_once()

    def test_synchronize_direct_transfer_success_unix(self, processor, doc_pair):
        """Test successful Direct Transfer on Unix."""
        doc_pair.local_path = Path("/tmp/test_file.txt")
        doc_pair.session = None

        with patch("nxdrive.engine.processor.WINDOWS", False):
            with patch.object(Path, "exists", return_value=True):
                with patch.object(processor.remote, "upload") as mock_upload:
                    with patch.object(processor, "_direct_transfer_end") as mock_end:
                        processor._synchronize_direct_transfer(doc_pair)

                        # Upload should be called with correct path
                        mock_upload.assert_called_once()
                        call_args = mock_upload.call_args
                        assert call_args[0][0] == Path(f"/{doc_pair.local_path}")

                        mock_end.assert_called_once_with(doc_pair, False)

    def test_synchronize_direct_transfer_success_windows(self, processor, doc_pair):
        """Test successful Direct Transfer on Windows."""
        doc_pair.local_path = Path("C:/Users/test/file.txt")
        doc_pair.session = None

        with patch("nxdrive.engine.processor.WINDOWS", True):
            with patch.object(Path, "exists", return_value=True):
                with patch.object(processor.remote, "upload") as mock_upload:
                    with patch.object(processor, "_direct_transfer_end") as mock_end:
                        processor._synchronize_direct_transfer(doc_pair)

                        # Upload should be called with path as-is on Windows
                        mock_upload.assert_called_once()
                        call_args = mock_upload.call_args
                        assert call_args[0][0] == doc_pair.local_path

                        mock_end.assert_called_once_with(doc_pair, False)


class TestDirectTransferHelpers:
    """Tests for Direct Transfer helper methods."""

    def test_direct_transfer_cancel(self, processor, doc_pair):
        """Test _direct_transfer_cancel method."""
        with patch.object(processor, "_direct_transfer_end") as mock_end:
            processor._direct_transfer_cancel(doc_pair)

            mock_end.assert_called_once_with(doc_pair, True, recursive=True)

    def test_direct_transfer_end_no_session(self, processor, doc_pair):
        """Test _direct_transfer_end without session."""
        doc_pair.session = None
        doc_pair.folderish = False
        doc_pair.size = 1024

        with patch.object(processor.dao, "remove_transfer"):
            with patch.object(processor.dao, "remove_state"):
                with patch.object(processor.dao, "get_session", return_value=None):
                    with patch.object(processor.engine.manager, "directTransferStats"):
                        processor._direct_transfer_end(doc_pair, False)

    def test_direct_transfer_end_with_ongoing_session(self, processor, doc_pair):
        """Test _direct_transfer_end with ongoing session."""
        doc_pair.session = 1
        doc_pair.folderish = False
        doc_pair.size = 1024
        session = Mock(spec=Session)
        session.uid = 1
        session.status = TransferStatus.ONGOING

        with patch.object(processor.dao, "remove_transfer"):
            with patch.object(processor.dao, "remove_state"):
                with patch.object(processor.dao, "get_session", return_value=session):
                    with patch.object(processor.dao, "decrease_session_counts"):
                        with patch.object(processor.engine, "handle_session_status"):
                            with patch.object(
                                processor.engine.manager, "directTransferStats"
                            ):
                                processor._direct_transfer_end(doc_pair, False)

    def test_direct_transfer_end_cancelled(self, processor, doc_pair):
        """Test _direct_transfer_end with cancelled transfer."""
        doc_pair.session = 1
        doc_pair.folderish = True
        doc_pair.size = 0
        session = Mock(spec=Session)
        session.uid = 1
        session.status = TransferStatus.ONGOING

        with patch.object(processor.dao, "remove_transfer"):
            with patch.object(processor.dao, "remove_state"):
                with patch.object(processor.dao, "get_session", return_value=session):
                    with patch.object(processor.dao, "decrease_session_counts"):
                        with patch.object(processor.engine, "handle_session_status"):
                            with patch.object(
                                processor.engine.manager, "directTransferStats"
                            ):
                                processor._direct_transfer_end(doc_pair, True)


class TestGetNextDocPair:
    """Tests for _get_next_doc_pair method."""

    def test_get_next_doc_pair_success(self, processor, doc_pair):
        """Test successful acquisition of next doc pair."""
        item = Mock(id=1)

        with patch.object(processor.dao, "acquire_state", return_value=doc_pair):
            result = processor._get_next_doc_pair(item)

            assert result == doc_pair

    def test_get_next_doc_pair_operational_error(self, processor, doc_pair):
        """Test handling sqlite OperationalError."""
        import sqlite3

        item = Mock(id=1)

        with patch.object(
            processor.dao, "acquire_state", side_effect=sqlite3.OperationalError()
        ):
            with patch.object(
                processor.dao, "get_state_from_id", return_value=doc_pair
            ):
                result = processor._get_next_doc_pair(item)

                # Should return None but log the state
                assert result is None

    def test_get_next_doc_pair_operational_error_no_state(self, processor):
        """Test OperationalError when state doesn't exist."""
        import sqlite3

        item = Mock(id=1)

        with patch.object(
            processor.dao, "acquire_state", side_effect=sqlite3.OperationalError()
        ):
            with patch.object(processor.dao, "get_state_from_id", return_value=None):
                result = processor._get_next_doc_pair(item)

                assert result is None


class TestCheckPairState:
    """Tests for check_pair_state static method."""

    def test_check_pair_state_synchronized(self, doc_pair):
        """Test that synchronized state is filtered out."""
        from nxdrive.engine.processor import Processor

        doc_pair.pair_state = "synchronized"
        assert not Processor.check_pair_state(doc_pair)

    def test_check_pair_state_unsynchronized(self, doc_pair):
        """Test that unsynchronized state is filtered out."""
        from nxdrive.engine.processor import Processor

        doc_pair.pair_state = "unsynchronized"
        assert not Processor.check_pair_state(doc_pair)

    def test_check_pair_state_parent_prefix(self, doc_pair):
        """Test that parent_ prefix states are filtered out."""
        from nxdrive.engine.processor import Processor

        doc_pair.pair_state = "parent_locally_modified"
        assert not Processor.check_pair_state(doc_pair)

    def test_check_pair_state_remote_todo(self, doc_pair):
        """Test that remote todo state is filtered out."""
        from nxdrive.engine.processor import Processor

        doc_pair.remote_state = "todo"
        assert not Processor.check_pair_state(doc_pair)

    def test_check_pair_state_valid(self, doc_pair):
        """Test that valid states pass through."""
        from nxdrive.engine.processor import Processor

        doc_pair.pair_state = "locally_created"
        doc_pair.remote_state = "unknown"
        assert Processor.check_pair_state(doc_pair)
