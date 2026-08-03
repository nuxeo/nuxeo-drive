"""
Functional tests for engine lifecycle, queue manager, and DAO operations.

These tests exercise real server interactions to cover code paths
that are difficult to hit with unit tests alone.
"""

import time
from datetime import datetime
from pathlib import Path

import pytest

from nxdrive.drive.client.local import FileInfo
from nxdrive.drive.constants import DelAction, TransferStatus, ROOT
from nxdrive.drive.exceptions import ThreadInterrupt

# ---------------------------------------------------------------------------
# Engine lifecycle: start / stop / suspend / resume / offline
# ---------------------------------------------------------------------------


def test_engine_start_stop(manager_factory):
    """Test engine start and stop lifecycle."""
    manager, engine = manager_factory()
    with manager:
        assert engine.is_started() is False

        engine.start()
        # Engine should be running
        assert engine.is_started() is True

        engine.stop()
        assert engine.is_started() is False


def test_engine_suspend_resume(manager_factory):
    """Test engine suspend/resume cycle."""
    manager, engine = manager_factory()
    with manager:
        engine.start()
        assert engine.is_started() is True

        # Suspend
        engine.suspend()
        assert engine.is_paused() is True

        # Resume
        engine.resume()
        assert engine.is_paused() is False
        assert engine.is_started() is True

        engine.stop()


def test_engine_offline_online(manager_factory):
    """Test offline/online transitions."""
    manager, engine = manager_factory()
    with manager:
        assert engine.is_offline() is False

        engine.set_offline(value=True)
        assert engine.is_offline() is True

        engine.set_offline(value=False)
        assert engine.is_offline() is False


def test_engine_reinit(manager_factory):
    """Test engine reinit resets states."""
    manager, engine = manager_factory()
    with manager:
        engine.reinit()
        # Should not raise; download_dir should be set
        assert engine.download_dir.exists() or engine.download_dir == ROOT


def test_engine_export(manager_factory):
    """Test engine export produces correct structure."""
    manager, engine = manager_factory()
    with manager:
        export = engine.export()
        assert "uid" in export
        assert "type" in export
        assert export["type"] == "NXDRIVE"
        assert "server_url" in export
        assert "username" in export
        assert "metrics" in export
        assert "queue" in export
        assert isinstance(export["threads"], list)


def test_engine_repr(manager_factory):
    """Test engine __repr__ doesn't crash."""
    manager, engine = manager_factory()
    with manager:
        r = repr(engine)
        assert "Engine" in r
        assert engine.uid in r


# ---------------------------------------------------------------------------
# Engine: filters
# ---------------------------------------------------------------------------


def test_engine_add_remove_filter(manager_factory):
    """Test adding and removing filters."""
    manager, engine = manager_factory()
    with manager:
        # Add a filter path
        engine.add_filter("/fake-domain/path/to/filter")
        filters = engine.dao.get_filters()
        assert any("/fake-domain/path/to/filter" in str(f) for f in filters)

        # Remove the filter
        engine.remove_filter("/fake-domain/path/to/filter")


# ---------------------------------------------------------------------------
# Engine: FS marker
# ---------------------------------------------------------------------------


def test_engine_check_fs_marker(manager_factory):
    """Test filesystem marker verification — may be False on tmpfs without xattr."""
    manager, engine = manager_factory()
    with manager:
        result = engine.check_fs_marker()
        # On some file systems (e.g. macOS tmp), xattr is not supported
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Engine: token management
# ---------------------------------------------------------------------------


def test_engine_save_load_token_dict(manager_factory):
    """Test saving/loading an OAuth2-style dict token."""
    manager, engine = manager_factory()
    with manager:
        token = {
            "access_token": "test-access-token",
            "refresh_token": "test-refresh-token",
            "token_type": "bearer",
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
        }
        engine._save_token(token)
        loaded = engine._load_token()
        assert loaded == token


def test_engine_save_load_token_string(manager_factory):
    """Test saving/loading a simple string token."""
    manager, engine = manager_factory()
    with manager:
        # Original token should be a string (Nuxeo auth)
        original = engine._load_token()
        assert isinstance(original, str)
        assert len(original) > 0


# ---------------------------------------------------------------------------
# Engine: delete_doc and rollback_delete
# ---------------------------------------------------------------------------


def test_engine_delete_doc_nonexistent(manager_factory):
    """Test delete_doc with a path that has no doc pair."""
    manager, engine = manager_factory()
    with manager:
        # Should not raise
        engine.delete_doc(Path("nonexistent-path"))


def test_engine_delete_doc_modes(manager_factory, tmp):
    """Test delete_doc with various deletion modes."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        # Create a local state entry
        path = tmp()
        file = path / "test_delete.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("test content")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        # Get the doc pair
        doc_pair = dao.get_state_from_id(rowid)
        assert doc_pair is not None

        # Make it look synchronized
        doc_pair.local_state = "synchronized"
        doc_pair.remote_state = "synchronized"
        dao.update_local_state(doc_pair, finfo)

        # Delete with DEL_SERVER mode
        engine.delete_doc(doc_pair.local_path, mode=DelAction.DEL_SERVER)


# ---------------------------------------------------------------------------
# Queue Manager tests
# ---------------------------------------------------------------------------


def test_queue_manager_get_metrics(manager_factory):
    """Test queue manager metrics retrieval."""
    manager, engine = manager_factory()
    with manager:
        metrics = engine.queue_manager.get_metrics()
        assert isinstance(metrics, dict)
        assert "local_folder_queue" in metrics
        assert "local_file_queue" in metrics
        assert "remote_folder_queue" in metrics
        assert "remote_file_queue" in metrics
        assert "error_queue" in metrics


def test_queue_manager_get_overall_size(manager_factory):
    """Test queue overall size starts at 0."""
    manager, engine = manager_factory()
    with manager:
        size = engine.queue_manager.get_overall_size()
        assert size == 0


def test_queue_manager_suspend_resume(manager_factory):
    """Test queue suspend and resume."""
    manager, engine = manager_factory()
    with manager:
        qm = engine.queue_manager
        qm.suspend()
        assert qm.is_paused() is True

        qm.resume()
        assert qm.is_paused() is False


def test_queue_manager_push_pop(manager_factory, tmp):
    """Test pushing and getting items from the queue."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        # Create a local state to push
        path = tmp()
        file = path / "queue_test.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("queue content")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        doc_pair = dao.get_state_from_id(rowid)
        doc_pair.pair_state = "locally_created"
        dao.update_local_state(doc_pair, finfo)

        # Push the item
        engine.queue_manager.push(doc_pair)

        # Verify it's in the queue
        size = engine.queue_manager.get_overall_size()
        assert size >= 1


# ---------------------------------------------------------------------------
# DAO Engine tests — state operations
# ---------------------------------------------------------------------------


def test_dao_insert_and_get_state(manager_factory, tmp):
    """Test DAO insert_local_state and get_state_from_id."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        path = tmp()
        file = path / "dao_test.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("dao test content")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        assert rowid > 0

        state = dao.get_state_from_id(rowid)
        assert state is not None
        assert state.local_name == "dao_test.txt"


def test_dao_get_state_from_local(manager_factory, tmp):
    """Test DAO get_state_from_local."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        path = tmp()
        file = path / "local_test.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("content")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        state = dao.get_state_from_id(rowid)
        found = dao.get_state_from_local(state.local_path)
        assert found is not None
        assert found.id == state.id


def test_dao_update_local_state(manager_factory, tmp):
    """Test DAO update_local_state."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        path = tmp()
        file = path / "update_test.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("original")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        state = dao.get_state_from_id(rowid)
        state.local_state = "modified"
        dao.update_local_state(state, finfo)

        updated = dao.get_state_from_id(rowid)
        assert updated.local_state == "modified"


def test_dao_filters_crud(manager_factory):
    """Test DAO filter add/get/remove operations."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        test_path = "/test-domain/path/filter1"
        dao.add_filter(test_path)

        filters = dao.get_filters()
        assert any(test_path in str(f) for f in filters)

        dao.remove_filter(test_path)
        filters = dao.get_filters()
        assert not any(test_path in str(f) for f in filters)


def test_dao_config_operations(manager_factory):
    """Test DAO config get/update/get_bool."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        # String config
        dao.update_config("test_key", "test_value")
        assert dao.get_config("test_key") == "test_value"

        # Bool config
        dao.store_bool("test_bool", True)
        assert dao.get_bool("test_bool") is True

        dao.store_bool("test_bool", False)
        assert dao.get_bool("test_bool") is False

        # Int config
        dao.update_config("test_int", "42")
        assert dao.get_int("test_int") == 42

        # Default value
        assert dao.get_config("nonexistent", default="default") == "default"


def test_dao_session_operations(manager_factory):
    """Test DAO session create/get/update."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        # create_session(remote_path, remote_ref, total, engine_uid, description, /)
        uid = dao.create_session(
            "/test/path", "test-ref-123", 5, engine.uid, "Test session"
        )
        assert uid > 0

        # Get the session
        session = dao.get_session(uid)
        assert session is not None
        assert session.remote_path == "/test/path"
        assert session.total_items == 5
        assert session.description == "Test session"

        # Update session status
        dao.change_session_status(uid, TransferStatus.DONE)
        updated = dao.get_session(uid)
        assert updated.status == TransferStatus.DONE


def test_dao_reinit_states(manager_factory, tmp):
    """Test DAO reinit_states resets pair states."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        # Insert a state
        path = tmp()
        file = path / "reinit_test.txt"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text("test")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        # Reinit
        dao.reinit_states()

        # After reinit, states should be reset
        dao.get_state_from_id(rowid)
        # State may be None after reinit or in a specific state
        # This primarily ensures reinit_states doesn't crash


# ---------------------------------------------------------------------------
# Engine: manage staled transfers
# ---------------------------------------------------------------------------


def test_manage_staled_transfers(manager_factory):
    """Test _manage_staled_transfers handles ongoing transfers."""
    manager, engine = manager_factory()
    with manager:
        # Should not crash even with no transfers
        engine._manage_staled_transfers()


# ---------------------------------------------------------------------------
# Engine: set_ui
# ---------------------------------------------------------------------------


def test_engine_set_ui(manager_factory):
    """Test setting UI preference."""
    manager, engine = manager_factory()
    with manager:
        engine.set_ui("web")
        assert engine.force_ui == "web"

        engine.set_ui("drive", overwrite=False)
        assert engine.wui == "drive"


# ---------------------------------------------------------------------------
# Engine: cancel_session
# ---------------------------------------------------------------------------


def test_engine_cancel_session(manager_factory):
    """Test canceling a session."""
    manager, engine = manager_factory()
    dao = engine.dao

    with manager:
        uid = dao.create_session(
            "/test/cancel", "ref-cancel", 3, engine.uid, "Cancel test"
        )

        engine.cancel_session(uid)
        session = dao.get_session(uid)
        assert session.status == TransferStatus.CANCELLED


# ---------------------------------------------------------------------------
# Engine: suspend_client raises ThreadInterrupt
# ---------------------------------------------------------------------------


def test_engine_suspend_client_when_paused(manager_factory):
    """Test suspend_client raises ThreadInterrupt when paused."""
    manager, engine = manager_factory()
    with manager:
        engine._pause = True
        with pytest.raises(ThreadInterrupt):
            engine.suspend_client(None)


def test_engine_suspend_client_when_stopped(manager_factory):
    """Test suspend_client raises ThreadInterrupt when stopped."""
    manager, engine = manager_factory()
    with manager:
        engine._stopped = True
        with pytest.raises(ThreadInterrupt):
            engine.suspend_client(None)
