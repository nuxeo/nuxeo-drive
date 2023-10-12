from unittest.mock import Mock
from uuid import uuid4

from nuxeo.models import FileBlob


def test_link_blob_to_doc(baseuploader, upload, tmp_path):
    file = tmp_path / f"{uuid4()}.txt"
    file.write_bytes(b"content")

    baseuploader.dao = Mock()
    baseuploader._transfer_autoType_file = Mock()

    baseuploader.link_blob_to_doc(
        baseuploader, "Filemanager.Import", upload, FileBlob(str(file)), True
    )
