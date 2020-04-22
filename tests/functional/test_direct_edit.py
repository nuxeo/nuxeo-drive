import shutil
from collections import namedtuple
from pathlib import Path
from typing import List
from unittest.mock import Mock, patch

import pytest
from nuxeo.exceptions import CorruptedFile
from nxdrive.constants import ROOT
from nxdrive.engine.engine import Engine, ServerBindingSettings
from nxdrive.translator import Translator
from nxdrive.utils import find_resource

from .. import ensure_no_exception


class MockUrlTestEngine(Engine):
    def __init__(self, url: str, user: str):
        self._url = url
        self._user = user
        self._stopped = True
        self._invalid_credentials = False

    def get_binder(self):
        """
        Must redefine to prevent:
            RuntimeError: super-class __init__() of type MockUrlTestEngine was never called
        """
        return ServerBindingSettings(self._url, None, self._user, ROOT, True)


@pytest.fixture()
def direct_edit(manager_factory):
    with manager_factory(with_engine=False) as manager:
        manager.direct_edit._folder.mkdir()
        yield manager.direct_edit


def test_binder(manager_factory):
    """Also test username retrieval."""
    manager, engine = manager_factory()

    with manager:
        binder = engine.get_binder()
        assert repr(binder)
        assert not binder.server_version
        assert not binder.password
        assert not binder.pwd_update_required
        assert binder.server_url
        assert binder.username
        assert binder.initialized
        assert binder.local_folder

        # Test user name retrieval
        full_username = (
            f"{manager.user_details.firstName} {manager.user_details.lastName}"
        )
        username = engine.get_user_full_name(binder.username)
        assert username == full_username

        # Test unknown user name retrieval
        username = engine.get_user_full_name("unknown")
        assert username == "unknown"


def test_cleanup_no_local_folder(direct_edit):
    """If local folder does not exist, it should be created."""

    shutil.rmtree(direct_edit._folder)
    assert not direct_edit._folder.is_dir()

    direct_edit._cleanup()
    assert direct_edit._folder.is_dir()


def test_cleanup_file(direct_edit):
    """There should be not files, but in that case, just ignore them."""

    file = direct_edit._folder / "this is a file.txt"
    file.touch()
    file.write_text("bla" * 3, encoding="utf-8")
    assert file.is_file()

    direct_edit._cleanup()

    # The file should still be present as it is ignored by the clean-up
    assert file.is_file()


def test_corrupted_download(app, manager_factory, tmp_path):
    manager, engine = manager_factory()

    def corrupted_error_signals(label: str, values: List) -> None:
        nonlocal received_corrupted
        nonlocal received_failure

        assert label in [
            "DIRECT_EDIT_CORRUPTED_DOWNLOAD_FAILURE",
            "DIRECT_EDIT_CORRUPTED_DOWNLOAD_RETRY",
        ]
        assert values == []
        if label == "DIRECT_EDIT_CORRUPTED_DOWNLOAD_FAILURE":
            received_failure = True
        else:
            received_corrupted += 1

    def corrupted_download(*args, **__):
        file_out = args[2]
        file_out.write_bytes(b"test")
        raise CorruptedFile("Mock'ed test", "remote-digest", "local-digest")

    with manager:
        received_corrupted = 0
        received_failure = False

        direct_edit = manager.direct_edit
        direct_edit._folder.mkdir()

        direct_edit.directEditError.connect(corrupted_error_signals)

        blob = Mock()
        blob.digest = None

        filename = "download corrupted.txt"
        file_out = tmp_path / filename

        with patch.object(engine.remote, "download", new=corrupted_download):
            tmp = direct_edit._download(
                engine, None, None, file_out, blob, None, "test_url"
            )
            assert not tmp
        assert received_corrupted == 3
        assert received_failure
        assert not file_out.is_file()


def test_cleanup_bad_folder_name(direct_edit):
    """Subfolders must be named with valid document UID. Ignore others."""

    folder = direct_edit._folder / "bad folder name"
    folder.mkdir()
    assert folder.is_dir()

    direct_edit._cleanup()

    # The folder should still be present as it is ignored by the clean-up
    assert folder.is_dir()


def test_document_not_found(manager_factory):
    """Trying to Direct Edit'ing a inexistent document should display a notification."""

    manager, engine = manager_factory()
    doc_uid = "0000"

    def error_signal(label: str, values: List) -> None:
        nonlocal received
        assert label == "DIRECT_EDIT_NOT_FOUND"
        assert values == [doc_uid, engine.hostname]
        received = True

    with manager:
        direct_edit = manager.direct_edit
        received = False
        direct_edit.directEditError.connect(error_signal)

        direct_edit._prepare_edit(engine.server_url, doc_uid)
        assert received


def test_invalid_credentials(manager_factory):
    """Opening a document without being authenticated is not allowed."""

    manager, engine = manager_factory()
    doc_uid = "0000"

    Translator(find_resource("i18n"), "en")

    def has_invalid_credentials(self) -> bool:
        return True

    def error_signal() -> None:
        nonlocal received
        received = True

    with manager:
        direct_edit = manager.direct_edit
        received = False
        engine.invalidAuthentication.connect(error_signal)

        with patch.object(
            Engine, "has_invalid_credentials", new=has_invalid_credentials
        ):
            direct_edit._prepare_edit(engine.server_url, doc_uid)
            assert received


def test_is_valid_folder_name(direct_edit):
    func = direct_edit._is_valid_folder_name

    # Valid
    assert func("37b1502b-26ff-430f-9f20-4bd0d803191e_")
    assert func("37b1502b-26ff-430f-9f20-4bd0d803191e_file-")
    assert func("37b1502b-26ff-430f-9f20-4bd0d803191e_file-content")

    # Invalid
    assert not func("37b1502b-26ff-430f-9f20-4bd0d803191e")  # missing xpath
    assert not func("37b1502b-26ff-430f-9f20-4bd0d803191z")  # z is not hexadecimal
    assert not func("37b1502b-26ff-430f-9f20-4bd0d803191ee")  # 1 extra char (not _)
    assert not func("is this a real file name.jpeg")
    assert not func("")
    assert not func(None)


def test_lock_queue_doc_not_found(direct_edit):
    ref = Path("something inexistent.docx")
    direct_edit._lock_queue.put((ref, "lock"))

    with ensure_no_exception():
        direct_edit._handle_lock_queue()


def test_upload_queue_doc_is_a_folder(direct_edit):
    """NXDRIVE-1862: some way or another, a folder can be stuck in the upload queue."""
    folder = (
        direct_edit.local.base_folder
        / "00000000-1111-2222-3333-444444444444_file-content"
        / "T0088"
    )
    folder.mkdir(parents=True)
    ref = direct_edit.local.get_path(folder)
    direct_edit._upload_queue.put(ref)

    with ensure_no_exception():
        direct_edit._handle_upload_queue()


def test_metrics(direct_edit):
    assert isinstance(direct_edit.get_metrics(), dict)


def test_send_lock_status(direct_edit):
    Engine = namedtuple("Engine", ["local_folder", "engine", "uid", "name"])

    local_path = Path("doc_id_xpath/testfile.txt")
    direct_edit._manager._engine_definitions.insert(
        0, Engine(Path(), None, "invalid_uid", "bla")
    )
    direct_edit._send_lock_status(local_path)


def test_url_resolver(manager_factory, nuxeo_url):
    manager, engine = manager_factory()

    with manager:
        direct_edit = manager.direct_edit
        direct_edit._folder.mkdir()

        user = engine.remote_user
        get_engine = direct_edit._get_engine

        # Engine found, even with uppercase username
        assert get_engine(nuxeo_url, user=user)
        assert get_engine(nuxeo_url, user=user.upper())

        # No engine found
        assert not get_engine(nuxeo_url, user="user-not-found")
        assert not get_engine("server-url-not-found", user=user)

        # HTTP explicit
        manager.engines["0"] = MockUrlTestEngine("http://localhost:80/nuxeo", user)
        assert get_engine("http://localhost:80/nuxeo", user=user)
        assert get_engine("http://localhost/nuxeo/", user=user)

        # HTTP implicit
        manager.engines["0"] = MockUrlTestEngine("http://localhost/nuxeo", user)
        assert get_engine("http://localhost:80/nuxeo/", user=user)
        assert get_engine("http://localhost/nuxeo", user=user)

        # HTTPS explicit
        manager.engines["0"] = MockUrlTestEngine("https://localhost:443/nuxeo", user)
        assert get_engine("https://localhost:443/nuxeo", user=user)
        assert get_engine("https://localhost/nuxeo/", user=user)

        # HTTPS implicit
        manager.engines["0"] = MockUrlTestEngine("https://localhost/nuxeo", user)
        assert get_engine("https://localhost:443/nuxeo/", user=user)
        assert get_engine("https://localhost/nuxeo", user=user)
