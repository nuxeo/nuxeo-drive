from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests
from nuxeo.models import FileBlob

from nxdrive.client.remote_client import Remote
from nxdrive.client.uploader import BaseUploader


@pytest.fixture
def baseuploader():
    remote = Remote
    remote.dao = Mock()
    return BaseUploader(remote)


def test_link_blob_to_doc(baseuploader, upload, tmp_path, monkeypatch):
    """Test system network and server side exception handling while linking blob to document"""
    file = tmp_path / f"{uuid4()}.txt"
    file.write_bytes(b"content")

    def mock_transfer_autoType_file(*args, **kwargs):
        raise requests.exceptions.RequestException("Connection Error")

    monkeypatch.setattr(
        baseuploader, "_transfer_autoType_file", mock_transfer_autoType_file
    )

    # server side exceptions
    with pytest.raises(requests.exceptions.RequestException):
        baseuploader.link_blob_to_doc(
            "Filemanager.Import", upload, FileBlob(str(file)), False
        )

    def mock_transfer_autoType_file(*args, **kwargs):
        raise requests.exceptions.RequestException(
            "TCPKeepAliveHTTPSConnectionPool: Connection Error"
        )

    monkeypatch.setattr(
        baseuploader, "_transfer_autoType_file", mock_transfer_autoType_file
    )

    # system network disconnect
    with pytest.raises(requests.exceptions.RequestException):
        baseuploader.link_blob_to_doc(
            "Filemanager.Import", upload, FileBlob(str(file)), False
        )
