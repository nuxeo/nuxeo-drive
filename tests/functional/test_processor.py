"""
Functional tests for nxdrive/engine/processor.py
"""

from collections import namedtuple
from pathlib import Path
from sqlite3 import Connection, Cursor
from unittest.mock import patch

import pytest
from nuxeo.exceptions import HTTPError

from nxdrive.constants import DigestStatus, TransferStatus
from nxdrive.engine.processor import Processor
from nxdrive.exceptions import NotFound, UploadCancelled, UploadPaused
from tests.functional.mocked_classes import (
    Mock_DAO,
    Mock_Doc_Pair,
    Mock_Engine,
    Mock_Local_Client,
    Mock_Remote,
    Mock_Remote_File_Info,
)

from ..markers import windows_only


def test_unlock_soft_path():
    # self.engine.uid in Processor.soft_locks
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    Processor.soft_locks = {mock_engine.uid: {Path(""): True}}
    assert (
        processor._unlock_soft_path(Path("tests/resources/files/testFile.txt")) is None
    )
    # self.engine.uid not in Processor.soft_locks
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    Processor.soft_locks = {"some_other_value": {Path(""): True}}
    assert processor._unlock_soft_path(mock_path) is None


def test_unlock_readonly():
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    assert processor._unlock_readonly(mock_path) is None
    # path in Processor.readonly_locks[self.engine.uid]
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    Processor.readonly_locks = {mock_engine.uid: {mock_path: [0]}}
    assert processor._unlock_readonly(mock_path) is None


def test_lock_readonly():
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    Processor.readonly_locks = {mock_engine.uid: {Path("different_path"): [0, 2]}}
    assert processor._lock_readonly(mock_path) is None
    # path in Processor.readonly_locks[self.engine.uid]
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    Processor.readonly_locks = {mock_engine.uid: {mock_path: [0, 2]}}
    assert processor._lock_readonly(mock_path) is None


def test_lock_soft_path():
    mock_engine = Mock_Engine()
    mock_path = Path("tests/resources/files/testFile.txt")
    processor = Processor(mock_engine, True)
    assert isinstance(processor._lock_soft_path(mock_path), Path)


def test_get_current_pair():
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor.get_current_pair() is None


def test_check_pair_state():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    assert Processor.check_pair_state(mock_doc_pair) is True


def test_digest_status():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    assert isinstance(Processor._digest_status(mock_doc_pair), DigestStatus)
    # doc_pair.folderish == False
    # doc_pair.pair_state == "remotely_created"
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "remotely_created"
    assert isinstance(Processor._digest_status(mock_doc_pair), DigestStatus)


def test_handle_doc_pair_sync():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    # finder_info and "brokMACS" in finder_info
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "brok + MacOS = brokMACS"
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch("nxdrive.engine.processor.Processor._postpone_pair") as mock_postpone:
        mock_postpone.return_value = None
        assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # finder_info and "brokMACS" not in finder_info
    # parent_pair and parent_pair.last_error == "DEDUP"
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_paired"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # finder_info and "brokMACS" not in finder_info
    # not (refreshed and self.check_pair_state(refreshed))
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_paired"
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.digest = mock_doc_pair.remote_digest
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor.check_pair_state"
    ) as mock_pair_state:
        mock_pair_state.return_value = False
        assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # finder_info and "brokMACS" not in finder_info
    # not (refreshed and self.check_pair_state(refreshed))
    # parent_pair.last_error != "DEDUP"
    # not self.local.exists(parent_path)
    mock_client = Mock_Local_Client()
    mock_client.exist = False
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.last_error = "dummy_last_error"
    mock_doc_pair.local_parent_path = Path("dummy_local_parent_path")
    mock_doc_pair.pair_state = "locally_paired"
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.digest = mock_doc_pair.remote_digest
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor.check_pair_state"
    ) as mock_pair_state, patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_get_normal_state:
        mock_pair_state.return_value = True
        mock_get_normal_state.return_value = mock_doc_pair
        assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # finder_info and "brokMACS" not in finder_info
    # parent_pair and parent_pair.last_error != "DEDUP"
    # download is not None
    # download.status not in (TransferStatus.ONGOING, TransferStatus.DONE)
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_paired"
    mock_doc_pair.last_error = "dummy_last_error"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_parent_pair:
        mock_parent_pair.return_value = mock_doc_pair
        assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # download.status == TransferStatus.ONGOING
    # upload.status not in (TransferStatus.ONGOING, TransferStatus.DONE)
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_paired"
    mock_doc_pair.last_error = "dummy_last_error"
    mock_engine = Mock_Engine()
    mock_engine.dao.download.status = TransferStatus.ONGOING
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_parent_pair:
        mock_parent_pair.return_value = mock_doc_pair
        assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None
    # download.status == TransferStatus.ONGOING
    # download.status == TransferStatus.ONGOING
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_paired"
    mock_doc_pair.last_error = "dummy_last_error"
    mock_engine = Mock_Engine()
    mock_engine.dao.download.status = TransferStatus.ONGOING
    mock_engine.dao.upload.status = TransferStatus.ONGOING
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_parent_pair:
        mock_parent_pair.return_value = mock_doc_pair
        assert processor._handle_doc_pair_sync(mock_doc_pair, Mock_Local_Client) is None


def test_handle_doc_pair_dt():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    # Not Found
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call, patch(
        "nxdrive.engine.processor.Processor._direct_transfer_cancel"
    ) as mock_transfer_cancel:
        mock_client_call.side_effect = NotFound("Custom NotFound Exception")
        mock_transfer_cancel.return_value = None
        with pytest.raises(NotFound) as ex:
            processor._handle_doc_pair_dt(mock_doc_pair, mock_client)
        assert str(ex.exconly()).startswith("nxdrive.exceptions.NotFound")
    # HTTPError
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call:
        mock_client_call.side_effect = HTTPError(status=500)
        with pytest.raises(HTTPError) as ex:
            processor._handle_doc_pair_dt(mock_doc_pair, mock_client)
        assert str(ex.exconly()).startswith("nuxeo.exceptions.HTTPError")
    # HTTPError, status = 404
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call, patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone:
        mock_client_call.side_effect = HTTPError(status=404)
        mock_postpone.return_value = None
        assert processor._handle_doc_pair_dt(mock_doc_pair, mock_client) is None
    # UploadPaused
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call:
        mock_client_call.side_effect = UploadPaused(1)
        with pytest.raises(UploadPaused) as ex:
            processor._handle_doc_pair_dt(mock_doc_pair, mock_client)
        assert str(ex.exconly()).startswith("nxdrive.exceptions.UploadPaused")
    # RuntimeError
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call:
        mock_client_call.side_effect = RuntimeError()
        with pytest.raises(RuntimeError) as ex:
            processor._handle_doc_pair_dt(mock_doc_pair, mock_client)
        assert str(ex.exconly()) == "RuntimeError"
    # Exception
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call, patch(
        "nxdrive.engine.processor.Processor._direct_transfer_cancel"
    ) as mock_dt_cancel:
        mock_client_call.side_effect = Exception("Custom Exception")
        mock_dt_cancel.return_value = None
        with pytest.raises(Exception) as ex:
            processor._handle_doc_pair_dt(mock_doc_pair, mock_client)
        assert str(ex.exconly()) == "Exception: Custom Exception"
    # UploadCancelled
    # not upload or not upload.doc_pair
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call:
        mock_client_call.side_effect = UploadCancelled(1)
        assert processor._handle_doc_pair_dt(mock_doc_pair, mock_client) is None
    # UploadCancelled
    # not refreshed_doc_pair
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_engine.dao.upload.doc_pair = True
    mock_engine.dao.doc_pairs[0] = None
    processor = Processor(mock_engine, True)
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call:
        mock_client_call.side_effect = UploadCancelled(1)
        assert processor._handle_doc_pair_dt(mock_doc_pair, mock_client) is None
    # UploadCancelled - direct transfer cancel
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_engine.dao.upload.doc_pair = True
    processor = Processor(mock_engine, True)
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.__call__"
    ) as mock_client_call, patch(
        "nxdrive.engine.processor.Processor._direct_transfer_cancel"
    ) as mock_dt_cancel:
        mock_client_call.side_effect = UploadCancelled(1)
        mock_dt_cancel.return_value = None
        assert processor._handle_doc_pair_dt(mock_doc_pair, mock_client) is None


def test_get_next_doc_pair():
    from sqlite3 import OperationalError

    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor._get_next_doc_pair(mock_doc_pair) == "DocPair_object"
    # sqlite3.OperationalError
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "tests.functional.mocked_classes.Mock_DAO.acquire_state"
    ) as mock_acquire_state, patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone_pair:
        mock_acquire_state.side_effect = OperationalError()
        mock_postpone_pair.return_value = None
        assert processor._get_next_doc_pair(mock_doc_pair) is None


def test_check_exists_on_the_server():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    # doc_pair.pair_state != "locally_created"
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone_pair:
        assert processor._check_exists_on_the_server(mock_doc_pair) is None
    # doc_pair.pair_state == "locally_created"
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_created"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone_pair, patch(
        "nxdrive.engine.processor.Processor.remove_void_transfers"
    ) as mock_void_transfer:
        mock_postpone_pair.return_value = None
        mock_void_transfer.return_value = None
        assert processor._check_exists_on_the_server(mock_doc_pair) is None
    # Exception
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_created"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone_pair, patch(
        "nxdrive.engine.processor.Processor.remove_void_transfers"
    ) as mock_void_transfer, patch(
        "tests.functional.mocked_classes.Mock_Remote.fetch"
    ) as mock_fetch:
        mock_postpone_pair.return_value = None
        mock_void_transfer.return_value = None
        mock_fetch.side_effect = Exception("Custom exception")
        assert processor._check_exists_on_the_server(mock_doc_pair) is None


def test_handle_pair_handler_exception():
    import errno

    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    mock_exception = Exception("Custom exception")
    with patch(
        "nxdrive.engine.processor.Processor.increase_error"
    ) as mock_increase_error:
        mock_increase_error.return_value = None
        assert (
            processor._handle_pair_handler_exception(
                mock_doc_pair, "dummy_handler", mock_exception
            )
            is None
        )
    # isinstance(e, OSError) and e.errno in NO_SPACE_ERRORS
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    mock_exception = OSError("Custom OSError")
    mock_exception.errno = errno.ENOMEM
    with patch(
        "nxdrive.engine.processor.Processor.increase_error"
    ) as mock_increase_error:
        mock_increase_error.return_value = None
        assert (
            processor._handle_pair_handler_exception(
                mock_doc_pair, "dummy_handler", mock_exception
            )
            is None
        )


def test_direct_transfer_end():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor._direct_transfer_end(mock_doc_pair, False, recursive=False) is None


def test_synchronize_conflicted():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_conflicted(mock_doc_pair) is None
    # doc_pair.folderish == True
    # self.local.get_remote_id(doc_pair.local_path) == doc_pair.remote_ref
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_conflicted(mock_doc_pair) is None


def test_synchronize_if_not_remotely_dirty():
    mock_client = Mock_Local_Client()
    mock_remote_file = Mock_Remote_File_Info()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_modified"
    ) as mock_sync_remote:
        mock_sync_remote.return_value = None
        assert (
            processor._synchronize_if_not_remotely_dirty(
                mock_doc_pair, remote_info=mock_remote_file
            )
            is None
        )
    # remote_info is None
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_modified"
    ) as mock_sync_remote:
        mock_sync_remote.return_value = None
        assert processor._synchronize_if_not_remotely_dirty(mock_doc_pair) is None
    # NotFound
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_modified"
    ) as mock_sync_remote, patch(
        "tests.functional.mocked_classes.Mock_Local_Client.get_info"
    ) as mock_get_info:
        mock_sync_remote.return_value = None
        mock_get_info.side_effect = NotFound()
        assert processor._synchronize_if_not_remotely_dirty(mock_doc_pair) is None


def test_synchronize_locally_modified():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone_pair:
        mock_postpone_pair.return_value = None
        assert processor._synchronize_locally_modified(mock_doc_pair) is None
    # doc_pair.local_digest != UNACCESSIBLE_HASH
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_update = True
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_if_not_remote_dirty:
        mock_sync_if_not_remote_dirty.return_value = None
        assert processor._synchronize_locally_modified(mock_doc_pair) is None
    # doc_pair.local_digest != UNACCESSIBLE_HASH
    # doc_pair.remote_can_update = False
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_update = False
    mock_engine = Mock_Engine()
    mock_engine.rollback = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_if_not_remote_dirty:
        mock_sync_if_not_remote_dirty.return_value = None
        assert processor._synchronize_locally_modified(mock_doc_pair) is None
    # doc_pair.local_digest != UNACCESSIBLE_HASH
    # doc_pair.remote_can_update == False
    # self.engine.local_rollback == False
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_update = False
    mock_engine = Mock_Engine()
    mock_engine.rollback = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_if_not_remote_dirty:
        mock_sync_if_not_remote_dirty.return_value = None
        assert processor._synchronize_locally_modified(mock_doc_pair) is None
    # NotFound
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_update = False
    mock_engine = Mock_Engine()
    mock_engine.rollback = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_if_not_remote_dirty, patch(
        "tests.functional.mocked_classes.Mock_Remote.get_fs_info"
    ) as mock_fs_info:
        mock_sync_if_not_remote_dirty.return_value = None
        mock_fs_info.return_value = Mock_Remote()
        mock_fs_info.side_effect = NotFound()
        assert processor._synchronize_locally_modified(mock_doc_pair) is None


def test_postpone_pair():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor._postpone_pair(mock_doc_pair, "failed") is None


def test_synchronize_locally_created():
    from nxdrive.exceptions import ParentNotSynced

    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # not delay
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch("nxdrive.engine.processor.is_generated_tmp_file") as mock_tmp_file:
        mock_tmp_file.return_value = True, False
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # doc_pair.error_count == 0
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.error_count = 0
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.is_generated_tmp_file"
    ) as mock_tmp_file, patch(
        "nxdrive.engine.processor.Processor.increase_error"
    ) as mock_increase_error:
        mock_tmp_file.return_value = True, True
        mock_increase_error.return_value = None
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # parent_pair is not None
    # parent_pair.pair_state == "unsynchronized"
    mock_client = Mock_Local_Client()
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.pair_state = "unsynchronized"
    mock_doc_pair.remote_ref = None
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    with patch(
        "tests.functional.mocked_classes.Mock_DAO.get_state_from_local"
    ) as mock_get_state, patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_get_state.return_value = None
        mock_normal_state.return_value = mock_doc_pair
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # ParentNoSynced
    mock_client = Mock_Local_Client()
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.remote_ref = None
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    with patch(
        "tests.functional.mocked_classes.Mock_DAO.get_state_from_local"
    ) as mock_get_state, patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_get_state.return_value = None
        mock_normal_state.return_value = mock_doc_pair
        with pytest.raises(ParentNotSynced) as ex:
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ParentNotSynced")
    # remote_ref and info
    # uid and info.is_trashed
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # not info
    # uid and info.is_trashed
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    with patch("tests.functional.mocked_classes.Mock_Remote.get_info") as mock_get_info:
        mock_get_info.return_value = None
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # info.is_trashed == False
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_name = "dummy_name"
    mock_doc_pair.local_state = "resolved"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # local.is_equal_digests == False
    # doc_pair.pair_state == "locally_resolved"
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_state = "resolved"
    mock_doc_pair.pair_state = "locally_resolved"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # HTTPError, status == 404
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_state = "resolved"
    mock_doc_pair.pair_state = "locally_resolved"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "tests.functional.mocked_classes.Mock_Remote.get_fs_info"
    ) as mock_get_fs_info:
        mock_get_fs_info.side_effect = HTTPError(status=404)
        with pytest.raises(HTTPError) as ex:
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
        assert str(ex.exconly()).startswith("nuxeo.exceptions.HTTPError")
    # HTTPError, status == 401
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_state = "resolved"
    mock_doc_pair.pair_state = "locally_resolved"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "tests.functional.mocked_classes.Mock_Remote.get_fs_info"
    ) as mock_get_fs_info:
        mock_get_fs_info.side_effect = HTTPError(status=401)
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # NotFound
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_state = "resolved"
    mock_doc_pair.pair_state = "locally_resolved"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "tests.functional.mocked_classes.Mock_Remote.get_fs_info"
    ) as mock_get_fs_info:
        mock_get_fs_info.side_effect = NotFound()
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # parent_pair.remote_can_create_child == True
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 1
    mock_dao.remote_can_create_child = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.pair_state = "locally_resolved"
    mock_doc_pair.remote_can_create_child = True
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_not_dirty:
        mock_sync_not_dirty.return_value = None
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )
    # doc_pair.folderish == False
    # local_info.size != doc_pair.size
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 1
    mock_dao.remote_can_create_child = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_resolved"
    mock_doc_pair.remote_can_create_child = True
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # doc_pair.folderish == False
    # doc_pair.local_digest == UNACCESSIBLE_HASH
    mock_client = Mock_Local_Client()
    mock_client.default_file_info.size = 1
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 1
    mock_dao.remote_can_create_child = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_doc_pair.pair_state = "locally_resolved"
    mock_doc_pair.remote_can_create_child = True
    mock_doc_pair.size = 1
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    assert (
        processor._synchronize_locally_created(mock_doc_pair, overwrite=False) is None
    )
    # stream file
    mock_client = Mock_Local_Client()
    mock_client.default_file_info.size = 1
    mock_client.equal_digest = False
    mock_client.remote_id = "dummy#remote_id"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 1
    mock_dao.remote_can_create_child = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.pair_state = "locally_resolved"
    mock_doc_pair.remote_can_create_child = True
    mock_doc_pair.size = 1
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.is_trashed = False
    mock_remote.parent_uid = "dummy_remote_ref"
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_if_not_remotely_dirty"
    ) as mock_sync_not_remote_dirty:
        mock_sync_not_remote_dirty.return_value = None
        assert (
            processor._synchronize_locally_created(mock_doc_pair, overwrite=False)
            is None
        )


def test_synchronize_locally_deleted():
    from nxdrive.behavior import Behavior

    # doc_pair.remote_can_delete
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor.remove_void_transfers"
    ) as mock_void_transfers:
        mock_search_dedup.return_value = None
        mock_void_transfers.return_value = None
        assert processor._synchronize_locally_deleted(mock_doc_pair) is None
    # not doc_pair.remote_can_delete
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_delete = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor.remove_void_transfers"
    ) as mock_void_transfers:
        mock_search_dedup.return_value = None
        mock_void_transfers.return_value = None
        assert processor._synchronize_locally_deleted(mock_doc_pair) is None
    # not doc_pair.remote_ref
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_ref = ""
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor.remove_void_transfers"
    ) as mock_void_transfers:
        mock_search_dedup.return_value = None
        mock_void_transfers.return_value = None
        assert processor._synchronize_locally_deleted(mock_doc_pair) is None
    # not Behavior.server_deletion
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    Behavior.server_deletion = False
    processor = Processor(mock_engine, True)
    assert processor._synchronize_locally_deleted(mock_doc_pair) is None


def test_synchronize_locally_moved_remotely_modified():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_locally_moved"
    ) as mock_sync_local_move, patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_modified"
    ) as mock_sync_remote_modify:
        mock_sync_local_move.return_value = None
        mock_sync_remote_modify.return_value = None
        assert (
            processor._synchronize_locally_moved_remotely_modified(mock_doc_pair)
            is None
        )


def test_synchronize_locally_moved_created():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._synchronize_locally_created"
    ) as mock_sync_local_create:
        mock_sync_local_create.return_value = None
        assert processor._synchronize_locally_moved_created(mock_doc_pair) is None


def test_synchronize_locally_moved():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup:
        mock_search_dedup.return_value = None
        assert processor._synchronize_locally_moved(mock_doc_pair, update=True) is None
    # parent_ref and parent_ref == doc_pair.remote_parent_ref
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_parent_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup:
        mock_search_dedup.return_value = None
        assert processor._synchronize_locally_moved(mock_doc_pair, update=True) is None
    # Exception
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_parent_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor._handle_failed_remote_rename"
    ) as mock_handle_failed_remote, patch(
        "nxdrive.engine.processor.Processor._refresh_remote"
    ) as mock_refresh_remote:
        mock_search_dedup.return_value = None
        mock_handle_failed_remote.return_value = None
        mock_refresh_remote.side_effect = Exception("Custom Exception")
        assert processor._synchronize_locally_moved(mock_doc_pair, update=True) is None
    # not doc_pair.remote_can_rename
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_rename = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor._handle_failed_remote_rename"
    ) as mcok_failed_remote_name:
        mock_search_dedup.return_value = None
        mcok_failed_remote_name.return_value = None
        assert processor._synchronize_locally_moved(mock_doc_pair, update=True) is None
    # doc_pair.remote_can_delete == True
    # not parent_pair.pair_state == "unsynchronized"
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_can_delete = True
    mock_engine = Mock_Engine()
    mock_engine.dao.pair_state = "synchronized"
    mock_engine.dao.remote_can_create_child = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup, patch(
        "nxdrive.engine.processor.Processor._handle_failed_remote_rename"
    ) as mcok_failed_remote_name:
        mock_search_dedup.return_value = None
        mcok_failed_remote_name.return_value = None
        assert processor._synchronize_locally_moved(mock_doc_pair, update=True) is None


def test_synchronize_deleted_unknown():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor._synchronize_deleted_unknown(mock_doc_pair) is None


def test_download_content():
    class Custom_DocPair:
        def __init__(self) -> None:
            self.local_path = Path("tests/resources/files/testFile.txt")

    mock_client = Mock_Local_Client()
    mock_client.abs_path = Path("tests/resources/files/testFile.txt")
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_dao = Mock_DAO()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_ref = "tests/resources/files/"
    mock_dao.mocked_doc_pair = Custom_DocPair()
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.dao = mock_dao
    processor.local = mock_client
    new_file = Path("testFile2.txt")
    mock_path = new_file
    assert isinstance(processor._download_content(mock_doc_pair, mock_path), Path)
    # Deleting the file created by shutil
    new_file = Path.cwd() / "tests" / "resources" / "files" / new_file
    new_file.unlink(missing_ok=True)


def test_update_remotely():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._download_content"
    ) as mock_download_content, patch("shutil.rmtree") as mock_shutil, patch(
        "nxdrive.engine.processor.Processor._refresh_local_state"
    ) as mock_refresh_state:
        mock_download_content.return_value = Path("")
        mock_shutil.return_value = None
        mock_refresh_state.return_value = None
        assert processor._update_remotely(mock_doc_pair, True) is None


def test_search_for_dedup():
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    assert processor._search_for_dedup(mock_doc_pair, name="dummy") is None


def test_synchronize_remotely_modified():
    # not doc_pair.folderish
    # doc_pair.local_digest is not None
    # local.is_equal_digests
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_doc_pair.local_digest = "dummy_digest"
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._update_remotely"
    ) as mock_update_remote:
        mock_update_remote.return_value = None
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None
    # remote.is_filtered
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._update_remotely"
    ) as mock_update_remote:
        mock_update_remote.return_value = None
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None
    # not new_parent_pair
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone, patch(
        "nxdrive.engine.processor.Processor._is_remote_move"
    ) as mock_is_move:
        mock_postpone.return_value = None
        mock_is_move.return_value = (True, None)
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None
    # not (is_move or is_renaming) == False
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone, patch(
        "nxdrive.engine.processor.Processor._is_remote_move"
    ) as mock_is_move:
        mock_postpone.return_value = None
        mock_is_move.return_value = (True, mock_doc_pair)
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None
    # old_path == new_path
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_doc_pair.local_path = Path("dummy_local_path/doc_pair_remote")
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone, patch(
        "nxdrive.engine.processor.Processor._is_remote_move"
    ) as mock_is_move:
        mock_postpone.return_value = None
        mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
        mock_is_move.return_value = (True, mock_doc_pair2)
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None
    # is_move == False
    mock_client = Mock_Local_Client()
    mock_client.equal_digest = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._postpone_pair"
    ) as mock_postpone, patch(
        "nxdrive.engine.processor.Processor._is_remote_move"
    ) as mock_is_move:
        mock_postpone.return_value = None
        mock_is_move.return_value = (False, mock_doc_pair)
        assert processor._synchronize_remotely_modified(mock_doc_pair) is None


def test_synchronize_remotely_created():
    from nxdrive.exceptions import ParentNotSynced

    # parent_pair is None
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_normal_state.return_value = None
        with pytest.raises(ParentNotSynced) as ex:
            processor._synchronize_remotely_created(mock_doc_pair)
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ParentNotSynced")
    # parent_pair.local_path is None
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.local_path = None
    mock_doc_pair.pair_state = "unsynchronized"
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    processor = Processor(mock_engine, True)
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_normal_state.return_value = mock_doc_pair
        assert processor._synchronize_remotely_created(mock_doc_pair) is None
    # remote.is_filtered
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = True
    processor = Processor(mock_engine, True)
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_normal_state.return_value = mock_doc_pair
        assert processor._synchronize_remotely_created(mock_doc_pair) is None
    # not self.local.exists
    mock_client = Mock_Local_Client()
    mock_client.exist = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_normal_state.return_value = mock_doc_pair
        assert processor._synchronize_remotely_created(mock_doc_pair) is None
    # not self.local.exists
    # NotFound
    mock_client = Mock_Local_Client()
    mock_client.exist = False
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state, patch(
        "nxdrive.engine.processor.Processor._create_remotely"
    ) as mock_create_remotely, patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_deleted"
    ) as mock_sync_remote_delete:
        mock_normal_state.return_value = mock_doc_pair
        mock_create_remotely.side_effect = NotFound()
        mock_sync_remote_delete.return_value = None
        assert processor._synchronize_remotely_created(mock_doc_pair) is None
    # local.exists == True
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state:
        mock_normal_state.return_value = mock_doc_pair
        assert processor._synchronize_remotely_created(mock_doc_pair) is None
    # local.exists == True
    # remote_ref != doc_pair.remote_ref
    # not self.dao.synchronize_state
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    mock_remote = Mock_Remote()
    mock_remote.filter_state = False
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    processor.remote = mock_remote
    mock_engine.dao.synchronize = False
    with patch(
        "nxdrive.engine.processor.Processor._get_normal_state_from_remote_ref"
    ) as mock_normal_state, patch(
        "nxdrive.engine.processor.Processor._create_remotely"
    ) as mock_create_remotely, patch(
        "nxdrive.engine.processor.Processor._synchronize_remotely_modified"
    ) as mock_sync_remote_modify:
        mock_normal_state.return_value = mock_doc_pair
        mock_create_remotely.return_value = Path("")
        mock_sync_remote_modify.return_value = None
        assert processor._synchronize_remotely_created(mock_doc_pair) is None


def test_create_remotely():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    mock_name = "dummy_name"
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._unlock_readonly"
    ) as mock_unlock_readonly:
        mock_unlock_readonly.return_value = None
        assert processor._create_remotely(
            mock_doc_pair, mock_doc_pair2, mock_name
        ) == Path("")
    # doc_pair.folderish == False
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_engine = Mock_Engine()
    mock_name = "dummy_name"
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._unlock_readonly"
    ) as mock_unlock_readonly, patch(
        "nxdrive.engine.processor.Processor._download_content"
    ) as mock_download_content, patch(
        "shutil.rmtree"
    ) as mock_shutil, patch(
        "nxdrive.engine.processor.Processor._lock_readonly"
    ) as mock_lock_readonly:
        mock_unlock_readonly.return_value = None
        mock_download_content.return_value = Path("")
        mock_shutil.return_value = None
        mock_lock_readonly.retunr_value = None
        assert processor._create_remotely(
            mock_doc_pair, mock_doc_pair2, mock_name
        ) == Path("")


def test_synchronize_remotely_deleted():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_remotely_deleted(mock_doc_pair) is None
    # remote_id != doc_pair.remote_ref
    # doc_pair.local_state == "deleted"
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_doc_pair.local_state = "deleted"
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "nxdrive.engine.processor.Processor._search_for_dedup"
    ) as mock_search_dedup:
        mock_search_dedup.return_value = None
        assert processor._synchronize_remotely_deleted(mock_doc_pair) is None
    # remote_id != doc_pair.remote_ref
    # doc_pair.local_state == "unsynchronized"
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_doc_pair.local_state = "unsynchronized"
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_remotely_deleted(mock_doc_pair) is None
    # remote_id != doc_pair.remote_ref
    # doc_pair.local_state == "unsynchronized" or "deleted"
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = False
    mock_doc_pair.remote_ref = mock_client.remote_id
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch("shutil.rmtree") as mock_shutil:
        mock_shutil.return_value = None
        assert processor._synchronize_remotely_deleted(mock_doc_pair) is None


def test_synchronize_unknown_deleted():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_unknown_deleted(mock_doc_pair) is None
    # doc_pair.local_path == None
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.local_path = None
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._synchronize_unknown_deleted(mock_doc_pair) is None


@windows_only
def test_handle_failed_remote_rename_win():
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert (
        processor._handle_failed_remote_rename(mock_doc_pair, mock_doc_pair2) is False
    )


def test_handle_failed_remote_rename():
    # not target_pair.remote_name
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2.remote_name = None
    mock_engine = Mock_Engine()
    mock_engine.rollback = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert (
        processor._handle_failed_remote_rename(mock_doc_pair, mock_doc_pair2) is False
    )
    # target_pair.remote_name exists
    # target_pair.folderish
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2.folderish = True
    mock_engine = Mock_Engine()
    mock_engine.rollback = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_failed_remote_rename(mock_doc_pair, mock_doc_pair2) is True
    # target_pair.remote_name exists
    # target_pair.folderish == False
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2.folderish = False
    mock_engine = Mock_Engine()
    mock_engine.rollback = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_failed_remote_rename(mock_doc_pair, mock_doc_pair2) is True
    # Exception
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    mock_engine.rollback = True
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    with patch(
        "tests.functional.mocked_classes.Mock_Local_Client.rename"
    ) as mock_rename:
        mock_rename.side_effect = Exception("Custom Exception")
        assert (
            processor._handle_failed_remote_rename(mock_doc_pair, mock_doc_pair2)
            is False
        )


def test_handle_readonly():
    # doc_pair.folderish and WINDOWS
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.folderish = True
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_readonly(mock_doc_pair) is None
    # doc_pair.is_readonly == True
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.read_only = True
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_readonly(mock_doc_pair) is None
    # doc_pair.is_readonly == False
    mock_client = Mock_Local_Client()
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.read_only = False
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_readonly(mock_doc_pair) is None


def test_synchronize_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao

    Mocked_Session = namedtuple(
        "session",
        "status, uid",
        defaults=("ok", "1"),
    )
    session = Mocked_Session()
    str_path = "unknownPath"
    path = Path(str_path)
    DocPair = namedtuple(
        "DocPair",
        "local_path, session",
        defaults=(path, session),
    )
    doc_pair = DocPair()

    def mocked_direct_transfer_end(*args, **kwargs):
        try:
            if kwargs["recursive"]:
                assert args[1]
        except Exception:
            assert not args[1]

    processor = Processor(engine, True)

    with patch.object(
        processor, "_direct_transfer_end", new=mocked_direct_transfer_end
    ):
        with patch.object(dao, "get_session", return_value=session):
            processor._synchronize_direct_transfer(doc_pair)
        with patch.object(dao, "get_session", return_value=None):
            processor._synchronize_direct_transfer(doc_pair)
