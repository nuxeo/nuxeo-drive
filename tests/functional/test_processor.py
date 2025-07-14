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
    Mock_Doc_Pair,
    Mock_Engine,
    Mock_Local_Client,
    Mock_Remote,
)


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
