from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from nxdrive.engine.processor import Processor


def test_synchronize_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote = engine.remote
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

    def mocked_get_session(*args, **kwargs):
        return session

    def mocked_get_none_session(*args, **kwargs):
        return None

    def mocked_upload(*args, **kwargs):
        return

    def mocked_end(*args, **kwargs):
        return

    processor = Processor(engine, True)

    with patch.object(remote, "upload", new=mocked_upload):
        with patch.object(processor, "_direct_transfer_end", new=mocked_end):
            with patch.object(dao, "get_session", new=mocked_get_session):
                assert processor._synchronize_direct_transfer(doc_pair) == "paused"
            with patch.object(dao, "get_session", new=mocked_get_none_session):
                assert processor._synchronize_direct_transfer(doc_pair) == "cancelled"
