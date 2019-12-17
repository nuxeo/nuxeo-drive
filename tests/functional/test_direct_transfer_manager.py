# coding: utf-8
"""
Test the Direct Transfer manager.
"""
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import patch
from uuid import uuid4

import pytest
from nuxeo.models import Batch
from nxdrive.constants import TransferStatus
from nxdrive.direct_transfer import DirectTransferManager
from nxdrive.direct_transfer.models import Session, Transfer
from nxdrive.options import Options


class FakeRemote:
    """Fake Remote client."""


@pytest.fixture
def manager(tmp_path):
    db = tmp_path / f"{uuid4()}.db"
    remote = FakeRemote()
    yield DirectTransferManager(str(db), "UID", remote)


def create_tree(root: Path) -> List[Path]:
    """Create the tree for tests."""
    paths = []
    size = 0

    # Folders
    folder = root / "one folder"
    subfolder = folder / "subfolder"
    subfolder.mkdir(parents=True)
    paths.append(folder)
    paths.append(subfolder)

    # Files
    file = root / "root-file.bin"
    size += file.write_bytes(b"0" * Options.chunk_size * 1024 * 1024 + b"0" * 1024)
    paths.append(file)

    file = folder / "one file.txt"
    size += file.write_text("azerty")
    paths.append(file)
    file = folder / "two files.txt"
    size += file.write_text("azerty" * 2)
    paths.append(file)

    file = subfolder / "file1.txt"
    size += file.write_text("azerty")
    paths.append(file)
    file = subfolder / "file2.txt"
    size += file.write_text("azerty" * 2)
    paths.append(file)

    return paths, size


def test_manager_empty(manager):
    assert repr(manager)
    assert manager.engine_uid == "UID"
    assert len(manager.transfers) == 0
    assert manager.is_completed
    assert not manager.is_started
    assert manager.progress == 100.0
    assert manager.size == 0.0
    assert manager.uploaded == 0.0

    # Check the session
    session = manager.session
    assert session == Session.get(Session.id == 1)
    assert session.started is None
    assert session.finished is None
    assert session.priority == 0
    assert session.status is TransferStatus.ONGOING

    # Check the transfers
    assert isinstance(manager.transfers, list)
    assert len(manager.transfers) == 0

    # Check methods were injected into the remote client
    for meth in (
        "dt_upload",
        "dt_do_upload",
        "dt_link_blob_to_doc",
        "dt_upload_chunks",
    ):
        assert hasattr(manager.remote, meth)

    # Check priority changes
    manager.increase_priority(session)
    manager.increase_priority(session)
    assert session.priority == 2
    manager.decrease_priority(session)
    assert session.priority == 1
    manager.decrease_priority(session)
    assert session.priority == 0
    manager.decrease_priority(session)
    assert session.priority == 0


def test_manager_session_resume(tmp_path, manager):
    """Test resuming a session with 1 transfer."""
    paths, _ = create_tree(tmp_path)
    remote_path = "/default-domain/something"

    manager.add(paths[-1], remote_path)
    assert isinstance(manager.transfers, list)
    assert len(manager.transfers) == 1

    manager.reinit()

    assert isinstance(manager.transfers, list)
    assert len(manager.transfers) == 1
    assert manager.transfers[0].local_path == paths[-1]
    assert manager.session.id == 1

    manager.add_all(paths, remote_path)
    assert isinstance(manager.transfers, list)
    assert len(manager.transfers) == len(paths)


def test_manager_with_transfers(tmp_path, manager):
    paths, size = create_tree(tmp_path)
    remote_path = "/default-domain/something"

    # Starting an empty session is useless
    assert not manager.transfers
    manager.start()

    # Add several paths
    manager.add_all(paths, remote_path)
    assert len(manager.transfers) == len(paths)

    # Ensure the total size is well-computed
    assert manager.size == size

    # Add again all paths, this should not affect the actual paths list
    for path in paths:
        assert manager.add(path, remote_path) is None

    # Add a problematic path, this should not affect the actual paths list
    assert manager.add(Path("inexistent"), remote_path) is None

    # Check transfers
    transfer = manager.transfers[0]
    assert isinstance(transfer, Transfer)
    assert transfer.session == Session.get(Session.id == 1)
    assert isinstance(transfer.local_path, Path)
    assert transfer.remote_path == remote_path
    assert not transfer.is_file
    assert not transfer.file_size
    assert transfer.status is TransferStatus.ONGOING
    assert isinstance(transfer.batch, Batch)
    assert not transfer.remote_ref
    assert not transfer.uploaded
    assert not transfer.uploaded_size
    assert not transfer.chunk_size
    assert not transfer.replace_blob


def test_manager_reset_transfers(tmp_path, manager):
    paths, _ = create_tree(tmp_path)
    remote_path = "/default-domain/something"

    # Add several paths
    manager.add_all(paths, remote_path)
    assert len(manager.transfers) == len(paths)

    # Now, reset the manager
    assert manager.session == Session.get(Session.id == 1)
    manager.reset()
    # It should have no effect as the session is not finished
    assert manager.session == Session.get(Session.id == 1)

    # Mimic a finish session
    manager.session.started = datetime.now()
    manager.session.finished = datetime.now()
    manager.session.status is TransferStatus.DONE

    # And reset for good!
    manager.reset()
    # A new session is created
    assert manager.session == Session.get(Session.id == 2)
    assert not manager.transfers


def test_manager_start_stop_transfers(
    tmp_path, app, server, manager_factory, obj_factory
):
    manager, engine = manager_factory()
    dt_manager = engine.dt_manager

    # Create a remote folder for our tests
    remote_folder = obj_factory()
    # Grant RW ACLs for the current user
    server.operations.execute(
        command="Document.SetACE",
        input_obj=remote_folder.uid,
        user=engine.remote_user,
        permission="ReadWrite",
        grant=True,
    )

    # Add several paths
    paths, size = create_tree(tmp_path)
    dt_manager.add_all(paths, remote_folder.path)

    # Stopping now has no effect
    assert not dt_manager.is_started
    dt_manager.stop()
    assert not dt_manager.is_started

    # Ensure session times are not set
    assert not dt_manager.session.started
    assert not dt_manager.session.finished
    assert dt_manager.session.status is TransferStatus.ONGOING

    # Simulate a stop() while working

    def should_stop_at_0() -> bool:
        """Stop at the start."""
        # Ensure the session is started
        assert dt_manager.is_started
        assert isinstance(dt_manager.session.started, datetime)

        # Check we cannot start again
        dt_manager.start()

        # Check we cannot reset
        dt_manager.reset()

        # Mimic a call to stop() from the outside
        dt_manager.stop()
        assert not dt_manager.is_started
        return True

    def should_stop_at_4() -> bool:
        """Stop at the 4th upload."""
        # Ensure the session is started
        assert dt_manager.is_started
        assert isinstance(dt_manager.session.started, datetime)

        nonlocal count
        count += 1
        return count >= 4

    with patch.object(dt_manager, "should_stop", new=should_stop_at_0):
        dt_manager.start()
    assert dt_manager.uploaded == 0
    assert dt_manager.progress == 0.0

    count = 0
    with patch.object(dt_manager, "should_stop", new=should_stop_at_4):
        dt_manager.start()
    assert dt_manager.uploaded > 0
    assert dt_manager.progress > 0.0

    # The finished time is still not yet set
    assert not dt_manager.session.finished

    # Now, really process transfers
    date_original = dt_manager.session.started
    dt_manager.start()

    # Check sizes
    assert dt_manager.uploaded == size
    assert dt_manager.progress == 100.0

    # Ensure the started time is not altered
    assert dt_manager.session.started == date_original

    # Ensure the session is completed
    assert not dt_manager.is_started
    assert dt_manager.is_completed
    assert isinstance(dt_manager.session.finished, datetime)
    assert dt_manager.session.status is TransferStatus.DONE

    # Trying to start again is useless
    dt_manager.start()

    # Finally, check the latest transfer (to test SQL models completely)
    transfer = dt_manager.transfers[-1]
    assert transfer.is_file
    assert transfer.batch.uid
    assert transfer == Transfer.get(Transfer.id == transfer.id)
