"""
Functional tests for nxdrive/engine/processor.py
"""

from collections import namedtuple
from pathlib import Path
from sqlite3 import Connection, Cursor
from unittest.mock import patch

from nxdrive.constants import DigestStatus
from nxdrive.engine.processor import Processor
from tests.functional.mocked_classes import (
    Mock_Doc_Pair,
    Mock_Engine,
    Mock_Local_Client,
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
    mock_client = Mock_Local_Client()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_engine = Mock_Engine()
    processor = Processor(mock_engine, True)
    processor.local = mock_client
    assert processor._handle_doc_pair_sync(mock_doc_pair, True) is None


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
