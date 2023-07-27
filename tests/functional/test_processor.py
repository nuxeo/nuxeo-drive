from collections import namedtuple
from pathlib import Path
from unittest.mock import Mock, patch

from nxdrive.engine.processor import Processor


def test__synchronize_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote = engine.remote

    Mocked_Session = namedtuple(
        "session",
        "status, uid",
        defaults=("ok", "1"),
    )

    session = Mocked_Session()

    path = Path("unknownPath")

    DocPair = namedtuple(
        "DocPair",
        "local_path, session",
        defaults=(path, session),
    )

    doc_pair = DocPair()

    processor = Processor(engine, True)

    with patch.object(dao, "pause_session", new=Mock()):
        with patch.object(remote, "upload", new=Mock()):
            with patch.object(processor, "_direct_transfer_end", new=Mock()):
                with patch.object(dao, "get_session", return_value=session):
                    assert processor._synchronize_direct_transfer(doc_pair) is None
                with patch.object(dao, "get_session", return_value=None):
                    assert processor._synchronize_direct_transfer(doc_pair) is None
