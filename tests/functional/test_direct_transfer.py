"""
Test the Direct Transfer feature in different scenarii.
"""
from pathlib import Path
from shutil import copyfile, copytree
from time import sleep
from unittest.mock import patch
from uuid import uuid4

import pytest
from nuxeo.exceptions import HTTPError
from nuxeo.models import Document
from nxdrive.constants import TransferStatus
from nxdrive.direct_transfer import DirectTransferDuplicateFoundError
from nxdrive.options import Options
from nxdrive.utils import get_tree_list
from requests.exceptions import ConnectionError

from .. import ensure_no_exception
from ..markers import not_windows

LOCATION = Path(__file__).parent.parent


def has_blob(engine, path: str) -> bool:
    """Check that *self.file* exists on the server and has a blob attached.
    As when doing a Direct Transfer, the document is first created on the server,
    this is the only way to check if the blob upload has been finished successfully.
    """
    try:
        doc = engine.remote.documents.get(path=path)
    except Exception:
        return False
    return bool(doc.properties.get("file:content"))


def sync_and_check(engine, should_have_blob: bool = True) -> None:
    # Sync
    wait_sync(engine)

    # Check the file exists on the server and has a blob attached
    path = f"{engine.ws_root.path}/{engine.file.name}"
    blob = has_blob(engine, path)
    assert blob is should_have_blob


def wait_sync(engine):
    """Wait for the Direct transfer session to finish."""
    for _ in range(30):  # 30 sec maxi
        if not engine.dt_manager.is_started:
            break
        sleep(1)


@pytest.fixture
def engine(tmp_path, app, server, manager_factory, obj_factory):
    Options.synchronization_enabled = False

    manager, engine = manager_factory()

    # Attach the fake workspace folder
    engine.ws_root = obj_factory()

    # Grant RW ACLs for the current user
    server.operations.execute(
        command="Document.SetACE",
        input_obj=engine.ws_root.uid,
        user=engine.remote_user,
        permission="ReadWrite",
        grant=True,
    )

    # Start the engine!
    engine.start()

    # Start an empty DT session to create the .dt_manager attribute
    engine.direct_transfer([], "")

    # Lower chunk_* options to have chunked uploads without having to create big files
    default_chunk_limit = Options.chunk_limit
    default_chunk_size = Options.chunk_size
    Options.chunk_limit = 1
    Options.chunk_size = 1

    # The file used for the Direct Transfer (10 MiB)
    engine.file = tmp_path / f"{uuid4()}.bin"
    engine.file.write_bytes(b"0" * 1024 * 1024 * 10)

    try:
        with manager:
            yield engine
    finally:
        # Restore options
        Options.chunk_limit = default_chunk_limit
        Options.chunk_size = default_chunk_size


def test_simple(engine):
    """Simple Direct Transfer test."""
    with ensure_no_exception():
        engine.direct_transfer([engine.file], engine.ws_root.path)
        sync_and_check(engine)

    # Ensure the remote path is saved for next times
    assert engine.dao.get_config("dt_last_remote_location") == engine.ws_root.path


def test_with_engine_not_started(engine):
    """A Direct Transfer should work even if engines are stopped."""
    engine.stop()

    with ensure_no_exception():
        engine.direct_transfer([engine.file], engine.ws_root.path)
        sync_and_check(engine)


def test_duplicate_file_but_no_blob_attached(engine):
    """The file already exists on the server but has no blob attached yet."""

    def create(*_, **__):
        """Patch Nuxeo.server.documents.create() to be able to check that nothing will be done."""
        assert 0, "No twice creation should be done!"

    # Create the document on the server, with no blob attached
    new_doc = Document(
        name=engine.file.name, type="File", properties={"dc:title": engine.file.name}
    )
    doc = engine.remote.documents.create(new_doc, parent_path=engine.ws_root.path)
    assert doc.properties.get("file:content") is None

    # The upload should work: the doc will be retrieved and the blob uploaded and attached
    with patch.object(engine.dt_manager.remote.documents, "create", new=create):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

    # Ensure there is only 1 document on the server
    children = engine.remote.documents.get_children(path=engine.ws_root.path)
    assert len(children) == 1
    assert children[0].title == engine.file.name


def test_duplicate_file_cancellation(engine):
    """The file already exists on the server and has a blob attached.
    Then, the user wants to cancel the transfer.
    """

    def cancel(file: Path, doc: Document) -> None:
        """Mimic the user choosing to cancel the upload."""
        nonlocal checkpoint
        checkpoint = True

        engine.direct_transfer_cancel(file)

    def upload(*_, **__):
        """Patch Remote.upload() to be able to check that nothing will be uploaded."""
        assert 0, "No twice upload should be done!"

    checkpoint = False

    with patch.object(engine.dt_manager, "dupe_callback", new=cancel):
        with ensure_no_exception():
            # 1st upload: OK
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # 2nd upload: it should be cancelled by the user
            with patch.object(engine.dt_manager.remote, "upload", new=upload):
                engine.direct_transfer([engine.file], engine.ws_root.path)
                wait_sync(engine)

    assert checkpoint

    # Ensure there is only 1 document on the server
    children = engine.remote.documents.get_children(path=engine.ws_root.path)
    assert len(children) == 1
    assert children[0].title == engine.file.name


def test_duplicate_file_replace_blob(engine):
    """The file already exists on the server and has a blob attached.
    Then, the user wants to replace the blob.
    """

    def replace(file: Path, doc: Document) -> None:
        """Mimic the user choosing to replace the blob on the server."""
        nonlocal checkpoint
        checkpoint = True

        engine.direct_transfer_replace_blob(file, doc)

    checkpoint = False
    content = b"blob changed!"

    with patch.object(engine.dt_manager, "dupe_callback", new=replace):
        with ensure_no_exception():
            # 1st upload: OK
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # To ease testing, we change local file content
            engine.file.write_bytes(content)

            # 2nd upload: the blob should be replaced on the server
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # Manual upload to test the exception raised
            dt_man = engine.dt_manager
            engine.direct_transfer([engine.file], engine.ws_root.path, start=False)
            with pytest.raises(DirectTransferDuplicateFoundError) as exc:
                dt_man.remote.dt_upload(dt_man.remote, dt_man.transfers[0])
            assert repr(exc)
            assert str(exc)

    assert checkpoint

    # Ensure there is only 1 document on the server
    children = engine.remote.documents.get_children(path=engine.ws_root.path)
    assert len(children) == 1
    assert children[0].title == engine.file.name
    assert engine.remote.get_blob(children[0].uid) == content


def test_pause_upload_manually(engine):
    """
    Pause the transfer by simulating a click on the pause/resume icon
    on the current upload in the systray menu.
    """

    def callback(*_):
        """
        This will mimic what is done in SystrayTranfer.qml:
            - call API.pause_transfer() that will call:
                - engine.dao.pause_transfer(nature, transfer_uid)
        Then the upload will be paused in Remote.upload().
        """
        nonlocal checkpoint
        checkpoint = True

        # Ensure we have 1 ongoing upload
        transfers = engine.dt_manager.uploading
        assert len(transfers) == 1

        # Pause the upload
        transfers[0].status = TransferStatus.PAUSED
        transfers[0].save()

    checkpoint = False

    with patch.object(engine.dt_manager, "chunk_callback", new=callback):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)
        assert len(engine.dt_manager.uploading) == 0

    assert checkpoint

    # Resume the upload
    engine.dt_manager.start()
    sync_and_check(engine)


def test_pause_upload_automatically(engine):
    """
    Pause the transfer by simulating an application exit
    or clicking on the Suspend menu entry from the systray.
    """

    def callback(*_):
        """This will mimic what is done in SystrayMenu.qml: suspend the app."""
        nonlocal checkpoint
        checkpoint = True

        # Ensure we have 1 ongoing upload
        assert len(engine.dt_manager.uploading) == 1

        # Suspend!
        engine.suspend()

    checkpoint = False

    with patch.object(engine.dt_manager, "chunk_callback", new=callback):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)
        assert len(engine.dt_manager.uploading) == 0

    assert checkpoint

    # Resume the upload
    engine.resume()
    sync_and_check(engine)


def test_modifying_paused_upload(engine):
    """Modifying a paused upload should discard the current upload."""

    def callback(*_):
        """Pause the upload and apply changes to the document."""
        nonlocal checkpoint
        checkpoint = True

        # Ensure we have 1 ongoing upload
        transfers = engine.dt_manager.uploading
        assert len(transfers) == 1

        # Pause the upload
        transfers[0].status = TransferStatus.PAUSED
        transfers[0].save()

        # Apply changes to the file
        engine.file.write_bytes(content)

    checkpoint = False
    content = b"locally changed"

    with patch.object(engine.dt_manager, "chunk_callback", new=callback):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

    assert checkpoint

    # Resume the upload
    engine.dt_manager.start()

    # Check the local content is correct
    sync_and_check(engine)
    assert engine.file.read_bytes() == content

    # And check the remote content is correct too
    blob = engine.remote.get_blob(engine.dt_manager.transfers[0].remote_ref)
    assert blob == content


@not_windows(
    reason="Cannot test the behavior as the local deletion is blocked by the OS."
)
def test_deleting_paused_upload(engine):
    """Deleting a paused upload should discard the current upload."""

    def callback(*_):
        """Pause the upload and delete the document."""
        nonlocal checkpoint
        checkpoint = True

        # Ensure we have 1 ongoing upload
        transfers = engine.dt_manager.uploading
        assert len(transfers) == 1

        # Pause the upload
        transfers[0].status = TransferStatus.PAUSED
        transfers[0].save()

        # Remove the document
        # (this is the problematic part on Windows, because for the
        #  file descriptor to be released we need to escape from
        #  Remote.upload(), which is not possible from here)
        engine.file.unlink()
        assert not engine.file.exists()

    checkpoint = False

    with patch.object(engine.dt_manager, "chunk_callback", new=callback):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

    assert checkpoint

    # Resume the upload
    engine.dt_manager.start()
    sync_and_check(engine, should_have_blob=False)


def test_not_server_error_upload(engine):
    """Test an error happening after chunks were uploaded."""

    def bad(*args, **kwargs):
        """Simulate an exception that is not handled by the Processor."""
        nonlocal checkpoint
        checkpoint = True

        raise ValueError("Mocked exception")

    checkpoint = False

    with patch.object(engine.dt_manager.remote, "dt_link_blob_to_doc", new=bad):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # There should be 1 upload with ONGOING transfer status
            assert len(engine.dt_manager.uploading) == 1

            # The file exists on the server but has no blob yet
            path = f"{engine.ws_root.path}/{engine.file.name}"
            assert not has_blob(engine, path)

    assert checkpoint

    # Check thransfer error details
    transfer = engine.dt_manager.uploading[0]
    assert transfer.error_count == 3
    assert transfer.error_count_total == 3

    # Reset the error
    engine.dt_manager.reset_error(transfer)
    assert transfer.error_count == 0
    assert transfer.error_count_total == 3

    # Restart the upload
    engine.dt_manager.start()
    sync_and_check(engine)


def test_server_error_but_upload_ok(engine):
    """
    Test an error happening after chunks were uploaded and the Blob.AttachOnDocument operation call.
    This could happen if a proxy does not understand well the final requests as seen in NXDRIVE-1753.
    """

    def bad(*args, **kwargs):
        # Call the original method to effectively end the upload process
        execute_orig(*args, **kwargs)

        if kwargs.get("command", "") == "Blob.AttachOnDocument":
            # The file should be present on the server
            children = engine.remote.documents.get_children(path=engine.ws_root.path)
            assert len(children) == 1
            assert children[0].title == engine.file.name

            # There should be 1 upload with ONGOING transfer status
            assert len(engine.dt_manager.uploading) == 1

            # And throw an error
            stack = (
                "The proxy server received an invalid response from an upstream server."
            )
            raise HTTPError(status=502, message="Mocked Proxy Error", stacktrace=stack)

    execute_orig = engine.remote.execute

    with patch.object(engine.dt_manager.remote, "execute", new=bad):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)
        assert len(engine.dt_manager.uploading) == 0

    engine.dt_manager.start()
    sync_and_check(engine)


def test_server_error_upload(engine):
    """Test a server error happening after chunks were uploaded, at the Blob.AttachOnDocument operation call."""

    def bad(*args, **kwargs):
        """Simulate a server error."""
        nonlocal checkpoint
        checkpoint = True

        raise ConnectionError("Mocked exception")

    checkpoint = False

    with patch.object(engine.dt_manager.remote, "dt_link_blob_to_doc", new=bad):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # There should be 1 upload with ONGOING transfer status
            assert len(engine.dt_manager.uploading) == 1

            # The file exists on the server but has no blob yet
            path = f"{engine.ws_root.path}/{engine.file.name}"
            assert not has_blob(engine, path)

    assert checkpoint

    # Reset the error
    transfer = engine.dt_manager.uploading[0]
    engine.dt_manager.reset_error(transfer)

    # Restart the upload
    engine.dt_manager.start()
    sync_and_check(engine)


def test_chunk_upload_error(engine):
    """Test a server error happening while uploading chunks."""

    def bad(*args, **kwargs):
        """Simulate an error after the upload of chunk n°1."""
        nonlocal checkpoint
        checkpoint = True

        nonlocal number

        if number == 0:
            number += 1
            return send_data_orig(*args, **kwargs)
        else:
            raise ConnectionError("Mocked error")

    checkpoint = False
    number = 0
    send_data_orig = engine.dt_manager.remote.uploads.send_data

    with patch.object(engine.dt_manager.remote.uploads, "send_data", new=bad):
        with ensure_no_exception():
            engine.direct_transfer([engine.file], engine.ws_root.path)
            wait_sync(engine)

            # There should be 1 upload with ONGOING transfer status
            assert len(engine.dt_manager.uploading) == 1

            # The file exists on the server but has no blob yet
            path = f"{engine.ws_root.path}/{engine.file.name}"
            assert not has_blob(engine, path)

    assert checkpoint

    # Reset the error
    transfer = engine.dt_manager.uploading[0]
    engine.dt_manager.reset_error(transfer)

    # Restart the upload
    engine.dt_manager.start()
    sync_and_check(engine)


def test_folder(tmp_path, engine):
    """Test the Direct Transfer on a folder containing files and a sufolder."""

    # We need more data for this test
    folder = tmp_path / str(uuid4())
    copytree(LOCATION / "resources", folder, copy_function=copyfile)

    # Get folders and files tests will handle
    tree = {path: rpath for rpath, path in get_tree_list(folder, engine.ws_root.path)}
    files = [path for path in tree.keys() if path.is_file()]
    folders = [path for path in tree.keys() if path.is_dir()]
    engine.tree = tree

    def check() -> None:
        # Sync
        wait_sync(engine)

        # Check files exist on the server with their attached blob
        for file in files:
            path = f"{tree[file]}/{file.name}"
            assert has_blob(engine, path)

        # Check subfolders
        for folder in folders:
            assert engine.remote.documents.get(path=tree[folder])

    with ensure_no_exception():
        engine.direct_transfer([folder], engine.ws_root.path)
        check()

    # Ensure there is only 1 folder created at the workspace root
    children = engine.remote.documents.get_children(path=engine.ws_root.path)
    assert len(children) == 1
    assert children[0].title == folder.name

    # All has been uploaded
    assert engine.dt_manager.is_completed
