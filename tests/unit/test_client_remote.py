"""
For file nxdrive/client/remote_client.py
"""

from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch

import pytest

from nxdrive.auth.oauth2 import OAuthentication
from nxdrive.client.remote_client import Remote
from nxdrive.constants import TransferStatus
from nxdrive.dao.base import BaseDAO
from nxdrive.dao.engine import EngineDAO
from nxdrive.engine.activity import DownloadAction, UploadAction


class Mock_Values:
    """
    Mock class to generate values for test case
    """

    def __init__(self) -> None:
        self.auth = self
        self.verify = True
        self.client = self
        self.headers = {"Content-Length": 20000000}
        self.status = ""
        self.content = bytes()

    def mock_auth(self):
        return self

    def mock_verify(self):
        return self.verify

    def mock_fetch(self):
        return {"kfetch": "vfetch"}

    def mock_metrics(self):
        return self

    def mock_uploader(self):
        return self

    def mock_action(self):
        return self

    def revoke_token(self, client):
        pass

    def request(self, protocol, url, headers: str = "", ssl_verify: bool = False):
        return self


class Mock_Auth(OAuthentication):
    def __init__(self, url, *args, **kwargs):
        dao = BaseDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db")
        super().__init__(url, dao=dao)

    def revoke_token(self, **kwargs: Any) -> None:
        pass

    def set_token(self, token: Dict[str, Any] | str) -> None:
        pass


@patch("nxdrive.metrics.poll_metrics.CustomPollMetrics")
@patch("nxdrive.client.remote_client.Remote.fetch")
@patch("nuxeo.client.Nuxeo")
@patch("nxdrive.utils.get_verify")
@patch("nxdrive.auth.get_auth")
def test_init(
    mock_get_auth, mock_get_verify, mock_nuxeo_init, mock_fetch, mock_poll_metrics
):
    """
    Testing the constructor
    """
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        base_folder="dummy_folder",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_values = Mock_Values()
    mock_get_auth.return_value = mock_values.mock_auth()
    mock_get_verify.return_value = mock_values.mock_verify()
    mock_nuxeo_init.return_value = mock_values
    mock_fetch.return_value = mock_values.mock_fetch()
    mock_poll_metrics.return_value = mock_values.mock_metrics()

    assert remote_obj.__class__.__name__ == "Remote"


def test_repr():
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    output = remote_obj.__repr__()
    assert output.startswith("<Remote") and output.endswith("version='dummy_version'>")


@patch("nuxeo.handlers.default.Uploader")
@patch("nxdrive.engine.activity.Action.get_current_action")
def test_transfer_start_callback(mock_action, mock_uploader):
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_values = Mock_Values()
    mock_uploader.return_value = mock_values.mock_uploader()
    mock_action.return_value = mock_values.mock_action()
    output = remote_obj.transfer_start_callback(mock_uploader)
    assert output is None


@patch("nxdrive.dao.engine.EngineDAO.get_download")
@patch("nuxeo.handlers.default.Uploader")
@patch("nxdrive.engine.activity.Action.get_current_action")
def test_transfer_end_callback_download(mock_action, mock_uploader, mock_dao):
    """
    This test case will only cover DownloadAction scenario
    """

    class Mock_Download(DownloadAction):
        def __init__(self, filepath: Path, size: int) -> None:
            super().__init__(Path(), 1000000)
            self.chunk_transfer_start_time_ns = 0
            self.chunk_transfer_end_time_ns = 1_000_000_002
            self.transferred_chunks = 0
            self.last_chunk_transfer_speed = 0
            self.chunk_size = 100
            self.progress = 0
            self.status = TransferStatus.ONGOING

        @staticmethod
        def get_current_action(*, thread_id=None):
            return Mock_Download(Path(), 200)

        def get_download(self, path):
            print("Get download")
            return self

        def get_percent(self):
            return 50.0

        def set_transfer_progress(self, nature: str, transfer):
            return self

    mock_values = Mock_Values()
    mock_download = Mock_Download(Path(), 2000)
    mock_uploader.return_value = mock_values.mock_uploader()
    mock_action.return_value = mock_download
    mock_dao.return_value = mock_download
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        dao=EngineDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db"),
        token="dummy_token",
        repository="dummy_repository",
    )
    output = remote_obj.transfer_end_callback(mock_uploader)
    assert output is None


@patch("nxdrive.dao.engine.EngineDAO.get_download")
@patch("nuxeo.handlers.default.Uploader")
@patch("nxdrive.engine.activity.Action.get_current_action")
def test_transfer_end_callback_upload(mock_action, mock_uploader, mock_dao):
    """
    This test case will only cover UploadAction scenario
    """

    class Mock_Upload(UploadAction):
        def __init__(self, filepath: Path, size: int) -> None:
            super().__init__(Path(), 1000000)
            self.chunk_transfer_start_time_ns = 0
            self.chunk_transfer_end_time_ns = 1_000_000_002
            self.transferred_chunks = 0
            self.last_chunk_transfer_speed = 0
            self.chunk_size = 100
            self.progress = 0
            self.status = TransferStatus.ONGOING

        @staticmethod
        def get_current_action(*, thread_id=None):
            return Mock_Upload(Path(), 200)

        def get_download(self, path):
            print("Get download")
            return self

        def get_percent(self):
            return 50.0

        def set_transfer_progress(self, nature: str, transfer):
            return self

    mock_values = Mock_Values()
    mock_upload = Mock_Upload(Path(), 2000)
    mock_uploader.return_value = mock_values.mock_uploader()
    mock_action.return_value = mock_upload
    mock_dao.return_value = mock_upload
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        dao=EngineDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db"),
        token="dummy_token",
        repository="dummy_repository",
    )
    output = remote_obj.transfer_end_callback(mock_uploader)
    assert output is None


def test_escape_carriage_return():
    output = Remote.escapeCarriageReturn("/dummy_path\n\r")
    assert output == "/dummy_path\\\\n\\\\r"


@patch("nxdrive.client.remote_client.Remote.query")
@patch("nxdrive.client.remote_client.Remote.escape")
def test_exists(mock_escape, mock_query):
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_escape.return_value = "dummy_escaped_string"
    mock_query.return_value = {"totalSize": 10}
    output = remote_obj.exists("dummy_uid", use_trash=False)
    assert output is True


def test_revoke_token():
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    remote_obj.auth = Mock_Auth("dummy_url")
    output = remote_obj.revoke_token()
    assert output is None
    # Test exception scenario
    remote_obj.auth = Mock_Auth("dummy_url").revoke_token(
        value=Exception("dummy_exception")
    )
    output = remote_obj.revoke_token()
    assert output is None


@patch("nxdrive.auth.Token")
def test_update_token(mock_token):
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    remote_obj.auth = Mock_Auth("dummy_url")
    mock_token.return_value = "dummy_token"
    output = remote_obj.update_token(mock_token)
    assert output is None


@patch("nxdrive.client.remote_client.Remote.check_integrity")
@patch("nxdrive.dao.engine.EngineDAO.set_transfer_status")
@patch("nxdrive.client.remote_client.Remote.check_integrity")
@patch("nuxeo.operations.API.save_to_file")
@patch("nxdrive.utils.unlock_path")
@patch("nxdrive.engine.activity.DownloadAction")
@patch("nxdrive.dao.engine.EngineDAO.get_download")
@patch("nuxeo.client.NuxeoClient.request")
def test_download(
    mock_nuxeo,
    mock_dao,
    mock_download_action,
    mock_unlock,
    mock_save,
    mock_integrity,
    mock_set_transfer_status,
    mock_integrity_simple,
):
    class Mock_Download_Action:
        def __init__(self):
            self.progress = 10
            self.chunk_size = 10
            self.chunk_transfer_start_time_ns = 10

    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        dao=EngineDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db"),
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_values = Mock_Values()
    # if chunked
    mock_nuxeo.return_value = mock_values
    mock_dao.return_value = mock_values
    mock_download_action.return_value = Mock_Download_Action()
    mock_unlock.return_value = 0
    mock_save.return_value = None
    mock_integrity.return_value = None
    mock_set_transfer_status.return_value = None
    output = remote_obj.download(
        "dummy_url", Path(), Path(), "digest", kwargs={"callback": "10"}
    )
    assert isinstance(output, Path)
    # if not chunked
    mock_values.headers = {"Content-Length": 10000000}
    mock_nuxeo.return_value = mock_values
    mock_dao.return_value = mock_values
    mock_download_action.return_value = Mock_Download_Action()
    mock_unlock.return_value = 0
    mock_save.return_value = None
    mock_integrity.return_value = None
    mock_integrity_simple.return_value = None
    output = remote_obj.download(
        "dummy_url",
        Path(),
        Path() / "tests" / "resources" / "files" / "testFile.txt",
        "digest",
        kwargs={"callback": "10"},
    )
    assert isinstance(output, Path)


@patch("nxdrive.engine.activity.VerificationAction")
def test_check_integrity(mock_verification):
    class Mock_Download(DownloadAction):
        def __init__(self, filepath: Path, size: int) -> None:
            super().__init__(Path(), 1000000)
            self.chunk_transfer_start_time_ns = 0
            self.chunk_transfer_end_time_ns = 1_000_000_002
            self.transferred_chunks = 0
            self.last_chunk_transfer_speed = 0
            self.chunk_size = 100
            self.progress = 0
            self.status = TransferStatus.ONGOING

        @staticmethod
        def finish_action() -> None:
            pass

    class Mock_Verification:
        def __init__(self):
            self.progress = 10

        def finish_action(self):
            pass

    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_download_action = Mock_Download(Path(), 10)
    mock_digest = "275876e34cf609db118f3d84b799a790"
    mock_verification.return_value = Mock_Verification()
    # Testing exception when digest != computed_digest
    with pytest.raises(Exception) as ex:
        remote_obj.check_integrity(mock_digest, mock_download_action)
    assert "CorruptedFile" in str(ex)


@patch("nxdrive.engine.activity.VerificationAction")
def test_check_integrity_simple(mock_verification):
    class Mock_Verification:
        def __init__(self):
            self.progress = 10

        def finish_action(self):
            pass

    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_digest = "275876e34cf609db118f3d84b799a790"
    mock_verification.return_value = Mock_Verification()
    # Testing exception when digest != computed_digest
    with pytest.raises(Exception) as ex:
        remote_obj.check_integrity_simple(mock_digest, Path())
    assert "CorruptedFile" in str(ex)


@patch("nxdrive.client.uploader.sync.SyncUploader")
def test_upload(mock_sync_uploader):
    from nxdrive.client.uploader import BaseUploader

    class Mock_Uploader(BaseUploader):
        def __init__(self, remote: Remote) -> None:
            super().__init__(remote)

        def upload(
            self,
            file_path: Path,
            /,
            *,
            command: str = "",
            filename: str = "",
            **kwargs: Any,
        ) -> Dict[str, Any]:
            return {"dummy": "dummy"}

    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        dao=EngineDAO(Path() / "tests" / "resources" / "databases" / "test_engine.db"),
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_sync_uploader.return_value = Mock_Uploader(remote_obj)
    output = remote_obj.upload(
        Path() / "tests" / "resources" / "files" / "testFile.txt",
        uploader=type(Mock_Uploader(remote_obj)),
    )
    assert output == {"dummy": "dummy"}


@patch("json.dumps")
@patch("nxdrive.client.remote_client.Remote.execute")
def test_upload_folder(mock_execute, mock_json):
    remote_obj = Remote(
        "dummy_url",
        "dummy_user_id",
        "dummy_device_id",
        "dummy_version",
        token="dummy_token",
        repository="dummy_repository",
    )
    mock_execute.return_value = {}
    mock_json.return_value = None
    output = remote_obj.upload_folder(
        "dummy_parent", {"dummy_k": "dummy_v"}, headers={"headers_k": "headers_v"}
    )
    assert output.__class__.__name__ == "dict"
