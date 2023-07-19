from collections import namedtuple
from unittest.mock import patch

from nxdrive.engine.processor import Processor

DocPair = namedtuple(
    "DocPair",
    "local_path, session",
    defaults=("unknownPath", {"status": "OK"}),
)


def test__synchronize_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote = engine.remote
    doc_pair = DocPair()

    def mocked_get_session(*args, **kwargs):
        return {"status": "OK", "": ""}

    def mocked_upload(*args, **kwargs):
        return

    def mocked_direct_transfer_end(*args, **kwargs):
        return

    processor = Processor(engine, True)
    sync_transfer = Processor._synchronize_direct_transfer

    with patch.object(dao, "get_session", new=mocked_get_session):
        with patch.object(remote, "upload", new=mocked_upload):
            with patch.object(
                processor, "_direct_transfer_end", new=mocked_direct_transfer_end
            ):
                assert sync_transfer(doc_pair) is None
