"""
Unit test cases for nxdrive/client/uploader/direct_transfer.py
"""

from pathlib import Path
from sqlite3 import Connection, Cursor
from unittest.mock import patch

import pytest

from nxdrive.client.remote_client import Remote
from nxdrive.client.uploader.direct_transfer import DirectTransferUploader
from nxdrive.dao.engine import EngineDAO
from nxdrive.exceptions import NotFound
from nxdrive.objects import DocPair


class Mock_Doc_Pair(DocPair):
    def __init__(self, cursor: Cursor, data: tuple) -> None:
        super().__init__()
        self.id = 1
        self.remote_parent_path = "parent_path"
        self.remote_parent_ref = "parent_ref"
        self.duplicate_behavior = ""
        self.folderish = True
        self.doc_type = ""
        self.session = 2
        self.local_name = "testFile"
        self.size = 10


@patch("nxdrive.client.uploader.BaseUploader.upload_impl")
@patch("nxdrive.client.remote_client.Remote.fetch")
@patch("nxdrive.client.remote_client.Remote.upload_folder_type")
@patch("nxdrive.client.remote_client.Remote.upload_folder")
@patch("nxdrive.client.remote_client.Remote.exists_in_parent")
def test_upload(
    mock_exist_parent,
    mock_upload_folder,
    mock_upload_folder_type,
    mock_fetch,
    mock_upload_impl,
):
    remote = Remote(
        "dummy_url",
        "dummy_user",
        "dummy_device",
        "dummy_version",
        dao=EngineDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db"),
    )
    dtu_obj = DirectTransferUploader(remote)
    cursor = Cursor(
        Connection(database=Path("tests/resources/databases/test_engine.db"))
    )
    mock_doc_pair = Mock_Doc_Pair(cursor, ("uid", "path"))
    mock_file_path = Path().cwd() / "tests" / "resources" / "files" / "testFile.txt"
    mock_upload_folder.return_value = {"path": "dummy_path", "uid": "dummy_uid"}
    # without doc_type
    output = dtu_obj.upload(mock_file_path, doc_pair=mock_doc_pair)
    assert output == {"path": "dummy_path", "uid": "dummy_uid"}
    # with doc_type
    mock_upload_folder_type.return_value = {"path": "dummy_path", "uid": "dummy_uid"}
    mock_doc_pair.doc_type = "Note"
    mock_fetch.return_value = {"path": "dummy_path", "uid": "dummy_uid"}
    output = dtu_obj.upload(mock_file_path, doc_pair=mock_doc_pair)
    assert output == {"path": "dummy_path", "uid": "dummy_uid"}
    # NotFound exception
    mock_upload_folder_type.return_value = {"path": "dummy_path", "uid": "dummy_uid"}
    mock_doc_pair.doc_type = "Note"
    mock_fetch.side_effect = NotFound()
    with pytest.raises(NotFound) as ex:
        dtu_obj.upload(mock_file_path, doc_pair=mock_doc_pair)
    assert str(ex.value) == "Could not find 'parent_path/testFile' on dummy_url/"
    # folderish == False
    mock_doc_pair.folderish = False
    mock_upload_impl.return_value = {"path": "dummy_path", "uid": "dummy_uid"}
    output = dtu_obj.upload(mock_file_path, doc_pair=mock_doc_pair)
    assert output == {"path": "dummy_path", "uid": "dummy_uid"}
    # duplicate_behavior == "ignore" and exists_in_parent == True
    mock_exist_parent.return_vaue = True
    mock_doc_pair.duplicate_behavior = "ignore"
    output = dtu_obj.upload(mock_file_path, doc_pair=mock_doc_pair)
    assert output == {}
