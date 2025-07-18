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


# def test_upload(manager_factory):
#     manager, engine = manager_factory()
#     remote = engine.remote
#     dtu_obj = DirectTransferUploader(remote)
#     cursor = Cursor(Connection(database=Path("tests/resources/databases/test_engine.db")))
#     mock_doc_pair = DocPair(cursor,("uid","url"))
#     mock_doc_pair.duplicate_behavior = "ignore"
#     mock_doc_pair.remote_parent_ref = WS_DIR
#     mock_doc_pair.remote_parent_path = WS_DIR
#     mock_doc_pair.folderish = True
#     mock_doc_pair.doc_type = "Note"
#     mock_doc_pair.local_name = "testFile"
#     mock_doc_pair.session = 1
#     output = dtu_obj.upload(Path("tests/resources/files/testFile.odt"),doc_pair = mock_doc_pair)
#     assert output is None
