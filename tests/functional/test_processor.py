from collections import namedtuple
from pathlib import Path
from unittest.mock import patch

from nxdrive.engine.processor import Processor


def test_synchronize_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    # remote = engine.remote

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
