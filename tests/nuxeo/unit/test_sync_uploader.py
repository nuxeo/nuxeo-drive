"""Unit tests for nxdrive.nuxeo.client.uploader.sync module."""

from pathlib import Path
from unittest.mock import Mock, patch

from nxdrive.nuxeo.client.uploader.sync import SyncUploader


def _make_uploader():
    """Create a SyncUploader with mocked dependencies."""
    with patch.object(SyncUploader, "__init__", return_value=None):
        uploader = SyncUploader.__new__(SyncUploader)
    uploader.dao = Mock()
    uploader.upload_impl = Mock(return_value={"blob": "result"})
    return uploader


class TestGetUpload:
    def test_returns_upload_from_dao(self):
        uploader = _make_uploader()
        uploader.dao.get_upload.return_value = Mock(path=Path("/tmp/f.txt"))
        result = uploader.get_upload(path=Path("/tmp/f.txt"), doc_pair=1)
        uploader.dao.get_upload.assert_called_once_with(path=Path("/tmp/f.txt"))
        assert result is not None

    def test_returns_none_when_no_upload(self):
        uploader = _make_uploader()
        uploader.dao.get_upload.return_value = None
        result = uploader.get_upload(path=Path("/tmp/missing.txt"), doc_pair=None)
        assert result is None


class TestUpload:
    def test_calls_upload_impl_and_removes_transfer(self):
        uploader = _make_uploader()
        file_path = Path("/tmp/test.txt")
        result = uploader.upload(file_path, command="FileManager.Import")
        uploader.upload_impl.assert_called_once()
        uploader.dao.remove_transfer.assert_called_once_with("upload", path=file_path)
        assert result == {"blob": "result"}

    def test_passes_kwargs_to_upload_impl(self):
        uploader = _make_uploader()
        file_path = Path("/tmp/test.txt")
        uploader.upload(file_path, command="cmd", filename="custom.txt", extra="val")
        call_kwargs = uploader.upload_impl.call_args
        assert call_kwargs[1]["filename"] == "custom.txt"
        assert call_kwargs[1]["extra"] == "val"
