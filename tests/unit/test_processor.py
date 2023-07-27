from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from nxdrive.engine.processor import Processor


def test_synchronize_direct_transfer(engine, engine_dao, remote):
    engine = engine()
    dao = engine_dao()
    remote = remote
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

    def mocked_direct_transfer_end(*args, **kwargs):
        return

    def mocked_pause_session(*args, **kwargs):
        return

    processor = Processor(engine, True)

    with patch.object(dao, "pause_session", new=mocked_pause_session):
        with patch.object(remote, "upload", new=mocked_upload):
            with patch.object(
                processor, "_direct_transfer_end", new=mocked_direct_transfer_end
            ):
                with patch.object(dao, "get_session", new=mocked_get_session):
                    assert processor._synchronize_direct_transfer(doc_pair) is None
                with patch.object(dao, "get_session", new=mocked_get_none_session):
                    assert processor._synchronize_direct_transfer(doc_pair) is None
