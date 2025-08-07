"""
Functional test cases for nxdrive/client/uploader/direct_transfer.py
"""

from nxdrive.client.uploader.direct_transfer import DirectTransferUploader


def test_get_upload(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dtu_obj = DirectTransferUploader(remote)
    output = dtu_obj.get_upload(path=None, doc_pair=0)
    assert output is None
