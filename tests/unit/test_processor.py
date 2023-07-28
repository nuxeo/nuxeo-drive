from collections import namedtuple
from pathlib import Path
from unittest.mock import Mock, patch


def test_synchronize_direct_transfer(processor, engine_dao):
    Mocked_Session = namedtuple(
        "session",
        "status, uid",
        defaults=("ok", "1"),
    )
    session = Mocked_Session()
    path = Path("/document_path")
    DocPair = namedtuple(
        "DocPair",
        "local_path, session",
        defaults=(path, session),
    )
    doc_pair = DocPair()
    processor.remote.upload = Mock()
    engine_dao.pause_session = Mock()
    processor._direct_transfer_end = Mock()
    processor.engine.directTranferError = Mock()
    processor._direct_transfer_cancel = Mock()
    with patch.object(engine_dao, "get_session", return_value=None):
        with patch.object(Path, "exists", return_value=True):
            assert processor._synchronize_direct_transfer(processor, doc_pair) is None
        assert processor._synchronize_direct_transfer(processor, doc_pair) is None
    with patch.object(engine_dao, "get_session", return_value=session):
        assert processor._synchronize_direct_transfer(processor, doc_pair) is None
