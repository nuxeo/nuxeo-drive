"""Additional deterministic coverage for :mod:`nxdrive.drive.dao.engine`."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from sqlite3 import OperationalError
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

import nxdrive.drive.dao.engine as engine_module
from nxdrive.drive.client.local import FileInfo
from nxdrive.drive.constants import (
    ROOT,
    UNACCESSIBLE_HASH,
    DirectDownloadStatus,
    TransferStatus,
)
from nxdrive.drive.dao.engine import EngineDAO
from nxdrive.drive.exceptions import UnknownPairState
from nxdrive.drive.objects import DirectDownload, Download, RemoteFileInfo, Upload
from nxdrive.drive.options import Options


FIXED_TIME = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


@pytest.fixture()
def dao(tmp_path):
    """Build a current-schema DAO in a unique database and always close it."""
    instance = EngineDAO(tmp_path / "engine-dao-extra.db")
    try:
        yield instance
    finally:
        instance.dispose()


def _insert_state(
    dao,
    local_path,
    *,
    local_parent_path="/",
    local_name=None,
    remote_ref=None,
    remote_parent_ref=None,
    remote_parent_path="/",
    remote_name=None,
    folderish=False,
    local_state="synchronized",
    remote_state="synchronized",
    pair_state="synchronized",
    local_digest=None,
    remote_digest=None,
    size=0,
    version=0,
    processor=0,
    session=0,
    last_sync_date=None,
    last_remote_updated=FIXED_TIME,
    error_count=0,
    last_error=None,
):
    """Insert a state using the production schema and return its real row."""
    path = Path(local_path) if local_path is not None else None
    parent = (
        Path(local_parent_path) if local_parent_path is not None else None
    )
    name = local_name if local_name is not None else (path.name if path else None)
    remote_name = remote_name if remote_name is not None else name
    cursor = dao._get_write_connection().cursor()
    cursor.execute(
        "INSERT INTO States ("
        "local_path, local_parent_path, local_name, remote_ref, "
        "remote_parent_ref, remote_parent_path, remote_name, folderish, "
        "local_state, remote_state, pair_state, local_digest, remote_digest, "
        "size, version, processor, session, last_sync_date, "
        "last_remote_updated, error_count, last_error, doc_type) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            path,
            parent,
            name,
            remote_ref,
            remote_parent_ref,
            remote_parent_path,
            remote_name,
            folderish,
            local_state,
            remote_state,
            pair_state,
            local_digest,
            remote_digest,
            size,
            version,
            processor,
            session,
            last_sync_date,
            last_remote_updated,
            error_count,
            last_error,
            "Folder" if folderish else "File",
        ),
    )
    return dao.get_state_from_id(cursor.lastrowid)


def _raw_state(dao, row_id):
    row = dao._get_read_connection().cursor().execute(
        "SELECT * FROM States WHERE id = ?", (row_id,)
    ).fetchone()
    return SimpleNamespace(**{key: row[key] for key in row.keys()}) if row else None


def _remote_info(
    name,
    uid,
    parent_uid,
    *,
    folderish=False,
    digest=None,
    modified=FIXED_TIME,
):
    return RemoteFileInfo(
        name=name,
        uid=uid,
        parent_uid=parent_uid,
        path=f"/{name}",
        folderish=folderish,
        last_modification_time=modified,
        creation_time=FIXED_TIME,
        last_contributor="alice",
        digest=digest,
        digest_algorithm="md5" if digest else None,
        download_url=None,
        can_rename=True,
        can_delete=True,
        can_update=not folderish,
        can_create_child=folderish,
        lock_owner=None,
        lock_created=None,
        can_scroll_descendants=folderish,
    )


def _direct_download(
    name,
    *,
    status=DirectDownloadStatus.PENDING,
    created_at="2024-01-02 03:04:05",
    zip_file=None,
    size=100,
    downloaded=0,
    completed_at=None,
):
    return DirectDownload(
        uid=None,
        doc_uid=f"uid-{name}",
        doc_name=name,
        doc_size=size,
        download_path=f"/downloads/{name}",
        server_url="https://server.example.test",
        status=status,
        bytes_downloaded=downloaded,
        total_bytes=size,
        progress_percent=(downloaded / size * 100) if size else 0.0,
        created_at=created_at,
        started_at=None,
        completed_at=completed_at,
        is_folder=bool(zip_file),
        folder_count=1 if zip_file else 0,
        file_count=1,
        retry_count=0,
        last_error=None,
        engine="engine-1",
        zip_file=zip_file,
        selected_items=name,
    )


def _upload(
    path,
    *,
    direct=False,
    status=TransferStatus.ONGOING,
    doc_pair=None,
    filesize=100,
    chunk_size=50,
):
    return Upload(
        uid=None,
        path=Path(path),
        status=status,
        engine="engine-1",
        is_direct_transfer=direct,
        progress=10.0,
        doc_pair=doc_pair,
        filesize=filesize,
        batch={"batchId": f"batch-{Path(path).name}", "blobs": [object()]},
        chunk_size=chunk_size,
        remote_parent_path="/remote",
        remote_parent_ref="remote-parent",
        request_uid=f"request-{Path(path).name}",
    )


def test_migration_downgrade_no_connection_and_release_edges(dao, monkeypatch):
    cursor = dao._get_write_connection().cursor()
    dao._create_table(cursor, "Configuration")

    connection = dao.conn
    dao.conn = None
    with pytest.raises(RuntimeError, match="Unable to connect"):
        dao._migrate_db(24)
    dao.conn = connection

    state = _insert_state(dao, "/locked.txt", processor=41)
    dao.release_state(None)
    assert dao.release_state(41) is None
    assert _raw_state(dao, state.id).processor == 0

    def fail_release(_processor_id):
        raise OperationalError("database is busy")

    monkeypatch.setattr(dao, "release_processor", fail_release)
    assert dao.release_state(42) is None

    monkeypatch.setattr(engine_module, "APP_VERSION", "5.2.8")
    dao._migrate_db(24)
    assert cursor.execute("PRAGMA user_version").fetchone()[0] == 21
    assert cursor.execute(
        "SELECT name FROM sqlite_master WHERE name = 'DirectDownloads'"
    ).fetchone() is None


def test_insert_and_update_local_states_persist_real_file_data(
    dao, tmp_path, monkeypatch
):
    queue = Mock()
    dao.queue_manager = queue

    (tmp_path / "folder").mkdir()
    folder_info = FileInfo(tmp_path, Path("folder"), True, FIXED_TIME)
    folder_id = dao.insert_local_state(folder_info, None)
    assert _raw_state(dao, folder_id).local_digest is None

    large_path = tmp_path / "folder" / "large.bin"
    large_path.write_bytes(b"large")
    large_info = FileInfo(tmp_path, Path("folder/large.bin"), False, FIXED_TIME)
    monkeypatch.setattr(engine_module, "is_large_file", lambda _size: True)
    large_id = dao.insert_local_state(large_info, Path("folder"))
    assert _raw_state(dao, large_id).local_digest == UNACCESSIBLE_HASH

    small_path = tmp_path / "small.txt"
    small_path.write_bytes(b"deterministic contents")
    small_info = FileInfo(tmp_path, Path("small.txt"), False, FIXED_TIME)
    monkeypatch.setattr(engine_module, "is_large_file", lambda _size: False)
    small_id = dao.insert_local_state(small_info, None)
    expected_digest = hashlib.md5(b"deterministic contents").hexdigest()
    assert _raw_state(dao, small_id).local_digest == expected_digest

    _insert_state(
        dao,
        "/synced",
        folderish=True,
        remote_ref="synced-folder",
        remote_parent_ref="root",
    )
    (tmp_path / "synced").mkdir()
    moved_path = tmp_path / "synced" / "moved.txt"
    moved_path.write_bytes(b"new contents")
    moved_info = FileInfo(tmp_path, Path("synced/moved.txt"), False, FIXED_TIME)
    row = dao.get_state_from_id(small_id)
    row.local_state = "modified"
    row.remote_state = "synchronized"
    row.local_digest = hashlib.md5(b"new contents").hexdigest()
    dao.update_local_state(row, moved_info)

    updated = _raw_state(dao, small_id)
    assert updated.local_path == "/synced/moved.txt"
    assert updated.local_parent_path == "/synced"
    assert updated.local_digest == row.local_digest
    assert updated.pair_state == "locally_modified"
    assert updated.version == 1
    queue.push_ref.assert_any_call(small_id, False, "locally_modified")

    later = datetime(2025, 2, 3, tzinfo=timezone.utc)
    moved_info.last_modification_time = later
    dao.update_local_modification_time(row, moved_info)
    dao.update_remote_name(row.id, "server-name.txt")
    updated = _raw_state(dao, row.id)
    assert updated.last_local_updated == "2025-02-03 00:00:00"
    assert updated.remote_name == "server-name.txt"

    row = dao.get_state_from_id(row.id)
    row.local_state = "modified"
    row.remote_state = "synchronized"
    dao.update_local_state(row, moved_info, versioned=False, queue=False)
    assert _raw_state(dao, row.id).version == 1


def test_local_path_rewrites_and_remote_parent_rewrites(dao):
    folder = _insert_state(
        dao,
        "/old",
        folderish=True,
        remote_ref="folder-ref",
        remote_parent_ref="root",
        remote_parent_path="/remote",
    )
    child = _insert_state(
        dao,
        "/old/child.txt",
        local_parent_path="/old",
        remote_ref="child-ref",
        remote_parent_ref="folder-ref",
        remote_parent_path="/remote/folder-ref",
    )
    grandchild = _insert_state(
        dao,
        "/old/sub/grand.txt",
        local_parent_path="/old/sub",
        remote_ref="grand-ref",
        remote_parent_ref="sub-ref",
        remote_parent_path="/remote/folder-ref/sub-ref",
    )
    untouched = _insert_state(dao, "/oldish/file.txt", local_parent_path="/oldish")

    condition = dao._get_recursive_condition(folder)
    assert "remote_parent_path" in condition

    dao.update_local_parent_path(folder, "renamed", Path("/dest"))
    assert _raw_state(dao, folder.id).local_parent_path == "/dest"
    assert _raw_state(dao, child.id).local_path == "/dest/renamed/child.txt"
    assert _raw_state(dao, child.id).local_parent_path == "/dest/renamed"
    assert _raw_state(dao, grandchild.id).local_path == "/dest/renamed/sub/grand.txt"

    dao.replace_local_paths(Path("/dest/renamed"), Path("/target"))
    assert _raw_state(dao, child.id).local_path == "/target/child.txt"
    assert _raw_state(dao, child.id).local_parent_path == "/target"
    assert _raw_state(dao, grandchild.id).local_parent_path == "/target/sub"
    assert _raw_state(dao, untouched.id).local_path == "/oldish/file.txt"

    dao.update_remote_parent_path(folder, "/new-remote")
    assert _raw_state(dao, folder.id).remote_parent_path == "/new-remote"
    assert _raw_state(dao, child.id).remote_parent_path == "/new-remote/folder-ref"
    assert (
        _raw_state(dao, grandchild.id).remote_parent_path
        == "/new-remote/folder-ref/sub-ref"
    )


def test_mark_delete_and_remove_state_trees_persist_expected_scope(dao):
    queue = Mock()
    dao.queue_manager = queue
    dao.newConflict = Mock()

    folder = _insert_state(
        dao,
        "/tree",
        folderish=True,
        remote_ref="tree-ref",
        remote_parent_ref="root",
        remote_parent_path="/remote",
        local_digest="folder-digest",
    )
    child = _insert_state(
        dao,
        "/tree/child.txt",
        local_parent_path="/tree",
        remote_ref="tree-child-ref",
        remote_parent_ref="tree-ref",
        remote_parent_path="/remote/tree-ref",
        local_digest="child-digest",
    )
    folder.pair_state = "remotely_created"
    dao.mark_descendants_remotely_created(folder)
    for row_id in (folder.id, child.id):
        row = _raw_state(dao, row_id)
        assert row.local_digest is None
        assert row.local_name is None
        assert row.remote_state == "created"
        assert row.pair_state == "remotely_created"
    queue.push_ref.assert_called_with(folder.id, True, "remotely_created")

    local_parent = _insert_state(
        dao,
        "/local-delete",
        folderish=True,
        remote_ref="local-delete-ref",
        remote_parent_ref="root",
        remote_parent_path="/remote",
    )
    local_child = _insert_state(
        dao,
        "/local-delete/child",
        local_parent_path="/local-delete",
        remote_ref="local-delete-child",
        remote_parent_ref="local-delete-ref",
        remote_parent_path="/remote/local-delete-ref",
    )
    dao.delete_local_state(local_parent)
    assert _raw_state(dao, local_parent.id).pair_state == "locally_deleted"
    assert _raw_state(dao, local_child.id).pair_state == "locally_deleted"
    queue.interrupt_processors_on.assert_called_with(
        local_parent.local_path, exact_match=False
    )

    local_tree = _insert_state(dao, "/remove-local", folderish=True)
    local_descendant = _insert_state(
        dao, "/remove-local/child", local_parent_path="/remove-local"
    )
    dao.remove_state_children(local_tree)
    assert dao.get_state_from_id(local_tree.id) is not None
    assert dao.get_state_from_id(local_descendant.id) is None

    remote_tree = _insert_state(
        dao,
        "/remove-remote",
        folderish=True,
        remote_ref="remove-remote-ref",
        remote_parent_path="/remote",
    )
    remote_descendant = _insert_state(
        dao,
        "/elsewhere/child",
        local_parent_path="/elsewhere",
        remote_ref="remote-descendant",
        remote_parent_ref="remove-remote-ref",
        remote_parent_path="/remote/remove-remote-ref",
    )
    dao.remove_state_children(remote_tree, remote_recursion=True)
    assert dao.get_state_from_id(remote_descendant.id) is None

    no_recursion = _insert_state(dao, "/single", folderish=True)
    no_recursion_child = _insert_state(
        dao, "/single/child", local_parent_path="/single"
    )
    dao.remove_state(no_recursion, recursive=False)
    assert dao.get_state_from_id(no_recursion.id) is None
    assert dao.get_state_from_id(no_recursion_child.id) is not None

    recursive = _insert_state(dao, "/recursive", folderish=True)
    recursive_child = _insert_state(
        dao, "/recursive/child", local_parent_path="/recursive"
    )
    dao.remove_state(recursive)
    assert dao.get_state_from_id(recursive_child.id) is None

    remote_recursive = _insert_state(
        dao,
        "/remote-recursive",
        folderish=True,
        remote_ref="remote-recursive-ref",
        remote_parent_path="/remote",
    )
    remote_recursive_child = _insert_state(
        dao,
        "/unrelated-local/child",
        local_parent_path="/unrelated-local",
        remote_ref="remote-recursive-child",
        remote_parent_ref="remote-recursive-ref",
        remote_parent_path="/remote/remote-recursive-ref",
    )
    dao.remove_state(remote_recursive, remote_recursion=True)
    assert dao.get_state_from_id(remote_recursive_child.id) is None


def test_remote_state_insert_update_and_lookup_queries(dao):
    queue = Mock()
    dao.queue_manager = queue
    digest = "a" * 32
    info = _remote_info("remote.txt", "remote-1", "root", digest=digest)
    row_id = dao.insert_remote_state(
        info, "", Path("remote.txt"), ROOT
    )
    inserted = dao.get_state_from_id(row_id)
    assert inserted.remote_state == "created"
    assert inserted.pair_state == "remotely_created"
    assert inserted.remote_digest == digest
    queue.push_ref.assert_called_with(row_id, False, "remotely_created")

    assert dao.update_remote_state(inserted, info) is False

    changed_info = _remote_info(
        "remote-renamed.txt",
        "remote-1",
        "new-parent",
        digest="b" * 32,
        modified=datetime(2025, 1, 1, tzinfo=timezone.utc),
    )
    inserted = dao.get_state_from_id(row_id)
    inserted.local_state = "synchronized"
    inserted.remote_state = "modified"
    assert dao.update_remote_state(
        inserted,
        changed_info,
        remote_parent_path="/new-parent-path",
        force_update=True,
    )
    changed = _raw_state(dao, row_id)
    assert changed.remote_name == "remote-renamed.txt"
    assert changed.remote_parent_ref == "new-parent"
    assert changed.remote_parent_path == "/new-parent-path"
    assert changed.remote_digest == "b" * 32
    assert changed.version == 1

    folder = _insert_state(
        dao,
        "/folder",
        folderish=True,
        remote_ref="folder-remote",
        remote_parent_ref="root",
        remote_parent_path="/",
        local_name="old-folder",
        remote_name="old-folder",
    )
    renamed_folder = _remote_info(
        "new-folder", "folder-remote", "root", folderish=True
    )
    assert dao.update_remote_state(
        folder,
        renamed_folder,
        versioned=False,
        queue=False,
        no_digest=True,
    )
    folder_db = _raw_state(dao, folder.id)
    assert folder_db.remote_state == "modified"
    assert folder_db.pair_state == "remotely_modified"
    assert folder_db.version == 0

    first = _insert_state(
        dao,
        "/first",
        remote_ref="prefix-target",
        remote_parent_ref="query-parent",
        remote_parent_path="/query/query-parent",
        remote_state="created",
        local_state="unknown",
        pair_state="remotely_created",
        last_remote_updated=datetime(2020, 1, 1, tzinfo=timezone.utc),
    )
    second = _insert_state(
        dao,
        "/second",
        remote_ref="other-prefix-target",
        remote_parent_ref="query-parent",
        remote_parent_path="/query/query-parent/first",
        last_remote_updated=datetime(2021, 1, 1, tzinfo=timezone.utc),
    )
    root_path = _insert_state(
        dao,
        "/root-path",
        remote_ref="root-path-ref",
        remote_parent_ref="root-path-parent",
        remote_parent_path="",
    )
    assert dao.get_first_state_from_partial_remote("prefix-target").id == first.id
    assert dao.get_state_from_remote_with_path("root-path-ref", "/").id == (
        root_path.id
    )
    assert dao.get_state_from_remote_with_path("prefix-target", "/missing") is None
    assert {row.id for row in dao.get_remote_descendants_from_ref("query-parent")} == {
        first.id,
        second.id,
    }
    assert [row.id for row in dao.get_new_remote_children("query-parent")] == [
        first.id
    ]

    duplicate = _insert_state(
        dao,
        "/duplicate",
        local_name="same.txt",
        remote_ref="dedupe-ref",
        remote_parent_ref="dedupe-parent",
    )
    ignored = _insert_state(
        dao,
        "/ignored",
        local_name="same.txt",
        remote_ref="ignored-ref",
        remote_parent_ref="dedupe-parent",
    )
    assert dao.get_dedupe_pair("same.txt", "dedupe-parent", ignored.id).id == (
        duplicate.id
    )
    assert dao.get_dedupe_pair("missing.txt", "dedupe-parent", ignored.id) is None


def test_direct_transfer_parent_update_and_queue_registration(dao):
    manager = Mock()
    dao.newConflict = Mock()

    dao.queue_many_direct_transfer_items(0)
    ongoing_session = dao.create_session(
        "/remote", "ongoing-ref", 2, "engine-1", "ongoing"
    )
    paused_session = dao.create_session(
        "/remote", "paused-ref", 1, "engine-1", "paused",
        status=TransferStatus.PAUSED,
    )

    parent = _insert_state(
        dao,
        "/a",
        folderish=True,
        local_state="created",
        remote_state="unknown",
        pair_state="locally_created",
    )
    child = _insert_state(
        dao,
        "/a/child.txt",
        local_parent_path="/a",
        local_state="created",
        remote_state="unknown",
        pair_state="locally_created",
    )
    standalone = _insert_state(
        dao,
        "/b.txt",
        local_state="modified",
        remote_state="synchronized",
        pair_state="locally_modified",
    )
    ongoing = _insert_state(
        dao,
        "/c.txt",
        local_state="direct",
        remote_state="unknown",
        pair_state="direct_transfer",
        session=ongoing_session,
    )
    _insert_state(
        dao,
        "/d.txt",
        local_state="direct",
        remote_state="unknown",
        pair_state="direct_transfer",
        session=paused_session,
    )
    _insert_state(dao, "/synced.txt")

    dao.register_queue_manager(manager)
    pushed_ids = {call.args[0] for call in manager.push_ref.call_args_list}
    assert parent.id in pushed_ids
    assert child.id not in pushed_ids
    assert standalone.id in pushed_ids
    assert ongoing.id in pushed_ids

    items = (
        (
            Path("/transfer/folder"),
            Path("/transfer"),
            "folder",
            True,
            0,
            "/remote",
            "remote-ref",
            "Folder",
            "create",
            "unknown",
        ),
        (
            Path("/transfer/folder/file.txt"),
            Path("/transfer/folder"),
            "file.txt",
            False,
            12,
            None,
            None,
            "File",
            "create",
            "todo",
        ),
    )
    previous_max = dao.plan_many_direct_transfer_items(items, ongoing_session)
    manager.push.reset_mock()
    dao.queue_many_direct_transfer_items(previous_max)
    assert manager.push.call_count == 2

    direct_child = dao.get_state_from_local(Path("/transfer/folder/file.txt"))
    dao.update_remote_parent_path_dt(
        Path("/transfer/folder"), "/remote/created-folder", "created-folder-ref"
    )
    updated = _raw_state(dao, direct_child.id)
    assert updated.remote_state == "unknown"
    assert updated.remote_parent_path == "/remote/created-folder"
    assert updated.remote_parent_ref == "created-folder-ref"
    assert updated.processor == 0

    dao._queue_pair_state(standalone.id, False, "conflicted", pair=standalone)
    dao.newConflict.emit.assert_called_once_with(standalone.id)
    dao._queue_pair_state(standalone.id, False, "locally_modified", pair=standalone)
    manager.push_ref.assert_any_call(standalone.id, False, "locally_modified")

    manager.push_ref.reset_mock()
    dao.queue_children(parent)
    manager.push_ref.assert_any_call(child.id, False, "locally_created")


def test_force_conflict_unsynchronize_and_folder_sync_fallback(dao):
    manager = Mock()
    dao.queue_manager = manager
    dao.newConflict = Mock()

    remote = _insert_state(
        dao,
        "/force-remote",
        local_state="modified",
        remote_state="modified",
        pair_state="conflicted",
    )
    assert dao.force_remote(remote)
    assert _raw_state(dao, remote.id).pair_state == "remotely_modified"

    creation = _insert_state(dao, "/force-creation")
    assert dao.force_remote_creation(creation)
    assert _raw_state(dao, creation.id).pair_state == "remotely_created"

    local = _insert_state(dao, "/force-local")
    assert dao.force_local(local)
    assert _raw_state(dao, local.id).pair_state == "locally_resolved"

    stale = _insert_state(dao, "/stale", version=2)
    stale.version = 1
    assert not dao.force_local(stale)

    conflict = _insert_state(dao, "/conflict")
    items_before = dao._items_count
    assert dao.set_conflict_state(conflict)
    assert _raw_state(dao, conflict.id).pair_state == "conflicted"
    assert dao._items_count == items_before - 1
    dao.remove_state(conflict, recursive=False)
    assert not dao.set_conflict_state(conflict)

    normal_unsync = _insert_state(
        dao, "/unsync-normal", local_state="modified", error_count=4
    )
    dao.unsynchronize_state(normal_unsync, "read only")
    normal_db = _raw_state(dao, normal_unsync.id)
    assert normal_db.local_state == "modified"
    assert normal_db.pair_state == "unsynchronized"
    assert normal_db.error_count == 0

    ignored = _insert_state(dao, "/unsync-ignored", error_count=2)
    dao.unsynchronize_state(ignored, "ignored", ignore=True)
    assert _raw_state(dao, ignored.id).local_state == "unsynchronized"

    unsync_folder = _insert_state(
        dao,
        "/filtered",
        folderish=True,
        local_state="unsynchronized",
        remote_state="synchronized",
        pair_state="unsynchronized",
        error_count=3,
        last_error="old error",
    )
    unsync_child = _insert_state(
        dao,
        "/filtered/child.txt",
        local_parent_path="/filtered",
        local_state="unsynchronized",
        remote_state="synchronized",
        pair_state="unsynchronized",
        error_count=3,
        last_error="old error",
    )
    dao.unset_unsychronised(unsync_folder)
    for row_id in (unsync_folder.id, unsync_child.id):
        row = _raw_state(dao, row_id)
        assert row.local_state == "created"
        assert row.remote_state == "unknown"
        assert row.pair_state == "locally_created"
        assert row.error_count == 0
        assert row.last_error is None

    folder = _insert_state(
        dao,
        "/sync-folder",
        folderish=True,
        remote_ref="sync-folder-ref",
        remote_parent_ref="root",
        remote_name="sync-folder",
        version=2,
        local_state="modified",
        remote_state="synchronized",
        pair_state="locally_modified",
    )
    sync_child = _insert_state(
        dao,
        "/sync-folder/child",
        local_parent_path="/sync-folder",
        remote_parent_ref="sync-folder-ref",
        pair_state="locally_modified",
        local_state="modified",
    )
    assert dao.synchronize_state(folder, version=1)
    assert _raw_state(dao, folder.id).pair_state == "synchronized"
    manager.push_ref.assert_any_call(sync_child.id, False, "locally_modified")

    vanished = _insert_state(dao, "/vanished")
    dao.remove_state(vanished, recursive=False)
    assert not dao.synchronize_state(vanished)

    unknown = _insert_state(dao, "/unknown-state")
    unknown.local_state = "impossible"
    unknown.remote_state = "impossible"
    with pytest.raises(UnknownPairState):
        dao._get_pair_state(unknown)


def test_counts_partial_queries_filters_and_scan_paths(dao):
    upload = _insert_state(
        dao,
        "/counts/upload.txt",
        local_parent_path="/counts",
        local_digest="upload-digest",
        remote_digest="upload-digest",
        size=10,
        last_sync_date="2099-01-01 00:00:00",
    )
    dao.update_last_transfer(upload.id, "upload")
    download = _insert_state(
        dao,
        "/counts/download.txt",
        local_parent_path="/counts",
        size=20,
        last_sync_date="2099-01-02 00:00:00",
    )
    dao.update_last_transfer(download.id, "download")
    folder = _insert_state(
        dao,
        "/counts/folder",
        local_parent_path="/counts",
        folderish=True,
        last_sync_date="2099-01-03 00:00:00",
    )
    unsync = _insert_state(
        dao,
        "/counts/unsync.txt",
        local_parent_path="/counts",
        local_state="unsynchronized",
        remote_state="unknown",
        pair_state="unsynchronized",
    )
    _insert_state(
        dao,
        "/counts-prefix.txt",
        local_state="modified",
        remote_state="synchronized",
        pair_state="locally_modified",
    )

    assert dao.get_last_files_count() == 2
    assert dao.get_last_files_count(direction="remote") == 1
    assert dao.get_last_files_count(direction="local", duration=1) == 1
    assert dao.get_sync_count() == 3
    assert dao.get_sync_count(filetype="file") == 2
    assert dao.get_sync_count(filetype="folder") == 1
    assert dao.get_unsynchronized_count() == 1
    assert [row.id for row in dao.get_unsynchronizeds()] == [unsync.id]
    assert dao.get_global_size() == 30
    assert dao.get_count("", table="States") == 5

    strict_ids = {row.id for row in dao.get_states_from_partial_local(Path("counts"))}
    assert upload.id in strict_ids
    assert download.id in strict_ids
    broad_ids = {
        row.id
        for row in dao.get_states_from_partial_local(Path("counts"), strict=False)
    }
    assert strict_ids < broad_ids
    assert folder.id in {row.id for row in dao.get_local_children(Path("counts"))}

    dao.add_path_to_scan("/scan/child")
    dao.add_path_to_scan("/scan")
    dao.add_path_to_scan("/scan")
    assert dao.get_paths_to_scan() == ["/scan/"]
    dao.delete_path_to_scan("/scan")
    assert dao.get_paths_to_scan() == []

    dao.add_path_scanned("/done")
    dao.add_path_scanned("/done")
    assert dao.is_path_scanned("/done")
    dao.clean_scanned()
    assert not dao.is_path_scanned("/done")

    dao.add_filter("/filter")
    dao.add_filter("/filter/child")
    assert dao.is_filter("/filter/child/file")
    assert dao.get_filters() == ["/filter/"]


def test_upload_download_crud_status_fallbacks_and_suspension(dao):
    dao.transferUpdated = Mock()
    dao.directTransferUpdated = Mock()

    download = Download(
        uid=None,
        path=Path("/downloads/regular.bin"),
        status=TransferStatus.ONGOING,
        engine="engine-1",
        progress=5.0,
        doc_pair=101,
        filesize=500,
        tmpname=Path("/tmp/regular.part"),
        url="https://server.example.test/regular.bin",
    )
    dao.save_download(download)
    download = dao.get_download(path=download.path)
    assert download is not None
    assert dao.get_download(uid=download.uid).doc_pair == 101
    assert dao.get_download(doc_pair=101).uid == download.uid
    assert dao.get_download() is None
    assert dao.get_downloads_with_status(TransferStatus.ONGOING) == [download]

    cursor = dao._get_write_connection().cursor()
    cursor.execute(
        "INSERT INTO Downloads (path, status, engine, doc_pair, filesize, tmpname) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (Path("/downloads/legacy.bin"), 5, "engine-1", 102, 1, "/tmp/legacy.part"),
    )
    assert dao.get_download(doc_pair=102).status == TransferStatus.DONE

    upload = _upload("/uploads/regular.bin", doc_pair=201)
    dao.save_upload(upload)
    assert upload.uid
    assert dao.get_upload(uid=upload.uid).doc_pair == 201
    assert dao.get_upload(path=upload.path).uid == upload.uid
    assert dao.get_upload(doc_pair=201).uid == upload.uid
    assert dao.get_upload() is None
    assert dao.get_uploads_with_status(TransferStatus.ONGOING)[0].uid == upload.uid
    upload.batch = {"batchId": "updated", "blobs": [object()]}
    dao.update_upload(upload)
    stored_batch = cursor.execute(
        "SELECT batch FROM Uploads WHERE uid = ?", (upload.uid,)
    ).fetchone().batch
    assert json.loads(stored_batch) == {"batchId": "updated"}

    cursor.execute(
        "INSERT INTO Uploads (path, status, engine, is_direct_transfer, doc_pair, batch) "
        "VALUES (?, ?, ?, 0, ?, ?)",
        (Path("/uploads/legacy.bin"), 5, "engine-1", 202, "{}"),
    )
    assert dao.get_upload(doc_pair=202).status == TransferStatus.DONE

    direct = _upload(
        "/uploads/direct.bin", direct=True, doc_pair=203, filesize=100, chunk_size=25
    )
    dao.save_upload(direct)
    assert dao.get_dt_upload(uid=direct.uid).is_direct_transfer
    assert dao.get_dt_upload(path=direct.path).uid == direct.uid
    assert dao.get_dt_upload(doc_pair=203).uid == direct.uid
    assert dao.get_dt_upload() is None
    assert dao.get_dt_uploads_with_status(TransferStatus.ONGOING)[0].uid == direct.uid
    assert dao.get_dt_uploads_raw(limit=5)[0]["uid"] == direct.uid
    assert dao.get_dt_uploads_raw(limit=5, chunked=True)[0]["uid"] == direct.uid

    download.progress = 37.5
    dao.set_transfer_progress("download", download)
    assert dao.get_download(uid=download.uid).progress == 37.5
    upload.progress = 62.5
    dao.set_transfer_progress("upload", upload)
    assert dao.get_upload(uid=upload.uid).progress == 62.5

    dao.suspend_transfers()
    assert dao.get_download(uid=download.uid).status == TransferStatus.SUSPENDED
    assert dao.get_upload(uid=upload.uid).status == TransferStatus.SUSPENDED
    assert dao.get_dt_upload(uid=direct.uid).status == TransferStatus.SUSPENDED
    dao.transferUpdated.emit.assert_called()
    dao.directTransferUpdated.emit.assert_called()

    dao.transferUpdated.reset_mock()
    dao.directTransferUpdated.reset_mock()
    dao.suspend_transfers()
    dao.transferUpdated.emit.assert_not_called()
    dao.directTransferUpdated.emit.assert_not_called()

    dao.remove_transfer("upload")
    assert dao.get_upload(uid=upload.uid) is not None


def test_session_raw_items_pause_resume_cancel_and_schedule(dao):
    dao.sessionUpdated = Mock()
    dao.directTransferUpdated = Mock()
    dao.queue_manager = Mock()

    ongoing = dao.create_session(
        "/ongoing", "ongoing-ref", 1, "engine-1", "ongoing", scheduled_at="42"
    )
    paused = dao.create_session(
        "/paused",
        "paused-ref",
        1,
        "engine-1",
        "paused",
        status=TransferStatus.PAUSED,
    )
    done = dao.create_session(
        "/done",
        "done-ref",
        1,
        "engine-1",
        "done",
        status=TransferStatus.DONE,
    )
    cancelled = dao.create_session(
        "/cancelled",
        "cancelled-ref",
        1,
        "engine-1",
        "cancelled",
        status=TransferStatus.CANCELLED,
    )
    assert {item["uid"] for item in dao.get_active_sessions_raw()} == {
        ongoing,
        paused,
    }
    assert {item["uid"] for item in dao.get_completed_sessions_raw(limit=5)} == {
        done,
        cancelled,
    }

    dao.change_session_status(999_999, TransferStatus.PAUSED)
    dao.change_session_status(ongoing, TransferStatus.PAUSED)
    assert dao.get_session(ongoing).status == TransferStatus.PAUSED
    dao.reset_session_schedule(ongoing)
    assert str(dao.get_session(ongoing).scheduled_at) == "0"

    item = {"name": "uploaded.txt", "size": 12}
    dao.save_session_item(ongoing, item)
    dao.save_session_item(ongoing, {"name": "second.txt"})
    assert dao.get_session_items(ongoing) == [item, {"name": "second.txt"}]
    assert dao.get_session_items(done) == []

    state = _insert_state(
        dao,
        "/session/file.txt",
        local_parent_path="/session",
        local_state="direct",
        remote_state="unknown",
        pair_state="direct_transfer",
        session=ongoing,
    )
    upload = _upload("/session/file.txt", direct=True, doc_pair=state.id)
    dao.save_upload(upload)
    dao.pause_session(ongoing)
    assert dao.get_session(ongoing).status == TransferStatus.PAUSED
    assert dao.get_dt_upload(uid=upload.uid).status == TransferStatus.PAUSED

    dao.resume_session(ongoing)
    assert dao.get_dt_upload(uid=upload.uid).status == TransferStatus.ONGOING
    dao.queue_manager.push.assert_called_with(dao.get_state_from_id(state.id))

    batches = dao.cancel_session(ongoing)
    assert batches == [{"batchId": "batch-file.txt"}]
    assert dao.get_state_from_id(state.id) is None
    assert dao.get_dt_upload(uid=upload.uid) is None
    assert dao.get_session(ongoing).status == TransferStatus.CANCELLED


def test_direct_download_crud_and_every_status_transition(dao):
    dao.directDownloadUpdated = Mock()
    download = _direct_download("report.pdf")
    uid = dao.save_direct_download(download)
    assert uid == download.uid
    assert dao.get_direct_download(uid).doc_name == "report.pdf"
    assert [item.uid for item in dao.get_direct_downloads()] == [uid]
    assert dao.get_direct_download(999_999) is None
    assert dao.get_direct_downloads_with_status(DirectDownloadStatus.PENDING)[0].uid == uid

    download.doc_name = "renamed.pdf"
    download.doc_size = 200
    download.total_bytes = 200
    download.is_folder = True
    download.folder_count = 2
    download.file_count = 3
    download.selected_items = "a,b,c"
    dao.update_direct_download(download)
    updated = dao.get_direct_download(uid)
    assert updated.doc_name == "renamed.pdf"
    assert updated.doc_size == 200
    assert updated.folder_count == 2

    dao.update_direct_download_progress(uid, 50, 200, 25.0)
    updated = dao.get_direct_download(uid)
    assert (updated.bytes_downloaded, updated.total_bytes, updated.progress_percent) == (
        50,
        200,
        25.0,
    )

    dao.update_direct_download_status(uid, DirectDownloadStatus.IN_PROGRESS)
    assert dao.get_direct_download(uid).started_at is not None
    dao.update_direct_download_status(uid, DirectDownloadStatus.PAUSED)
    assert dao.get_direct_download(uid).status == DirectDownloadStatus.PAUSED
    dao.update_direct_download_status(
        uid, DirectDownloadStatus.FAILED, last_error="network error"
    )
    failed = dao.get_direct_download(uid)
    assert failed.last_error == "network error"
    assert failed.retry_count == 1
    dao.update_direct_download_status(uid, DirectDownloadStatus.CANCELLED)
    assert dao.get_direct_download(uid).completed_at is not None
    dao.update_direct_download_status(uid, DirectDownloadStatus.PENDING)
    assert dao.get_direct_download(uid).status == DirectDownloadStatus.PENDING
    dao.update_direct_download_status(uid, DirectDownloadStatus.COMPLETED)
    completed = dao.get_direct_download(uid)
    assert completed.progress_percent == 100.0
    assert completed.completed_at is not None

    assert dao.delete_completed_direct_downloads() == 1
    assert dao.get_direct_download(uid) is None

    another = _direct_download("delete-me.txt")
    dao.save_direct_download(another)
    dao.delete_direct_download(another.uid)
    assert list(dao.get_direct_downloads()) == []


def test_direct_download_batch_active_completed_and_monitoring_queries(dao):
    records = [
        _direct_download(
            "batch-active.txt",
            status=DirectDownloadStatus.IN_PROGRESS,
            zip_file="active.zip",
            size=100,
            downloaded=25,
        ),
        _direct_download(
            "batch-complete.txt",
            status=DirectDownloadStatus.COMPLETED,
            zip_file="active.zip",
            size=300,
            downloaded=300,
            completed_at="2024-01-02 04:00:00",
        ),
        _direct_download("single-pending.txt"),
        _direct_download(
            "history-failed.txt",
            status=DirectDownloadStatus.FAILED,
            created_at="2024-01-03 03:04:05",
        ),
        _direct_download(
            "history-cancelled.txt",
            status=DirectDownloadStatus.CANCELLED,
            created_at="2024-01-04 03:04:05",
        ),
    ]
    for record in records:
        dao.save_direct_download(record)

    active = dao.get_active_direct_downloads()
    by_zip = {item["zip_file"]: item for item in active}
    assert by_zip["active.zip"]["batch_count"] == 2
    assert by_zip["active.zip"]["total_bytes"] == 400
    assert by_zip["active.zip"]["bytes_downloaded"] == 325
    assert by_zip["active.zip"]["status"] == "IN_PROGRESS"
    assert by_zip[None]["doc_name"] == "single-pending.txt"

    monitoring = dao.get_direct_downloads_for_monitoring(limit=10)
    assert {item["uid"] for item in monitoring} == {
        records[0].uid,
        records[2].uid,
    }
    assert all(item["shadow"] is False for item in monitoring)

    completed = dao.get_completed_direct_downloads(limit=10)
    assert {item["status"] for item in completed} == {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert dao._get_batch_key({"uid": 7}) == "single:7"
    assert dao._get_batch_key({"uid": 7, "zip_file": "files.zip"}) == "zip:files.zip"


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        (["IN_PROGRESS", "FAILED"], "IN_PROGRESS"),
        (["PENDING", "FAILED"], "PENDING"),
        (["PAUSED", "FAILED"], "PAUSED"),
        (["FAILED", "COMPLETED"], "FAILED"),
        (["CANCELLED", "COMPLETED"], "CANCELLED"),
        (["COMPLETED"], "COMPLETED"),
    ],
)
def test_direct_download_aggregate_status_precedence(dao, statuses, expected):
    rows = [
        {
            "uid": index + 1,
            "doc_name": f"file-{index}.txt",
            "total_bytes": 0 if index == 0 else 20,
            "bytes_downloaded": 0 if index == 0 else 10,
            "file_count": 1,
            "folder_count": index,
            "status": status,
            "completed_at": (
                f"2024-01-0{index + 1} 00:00:00" if index else None
            ),
        }
        for index, status in enumerate(statuses)
    ]
    result = dao._aggregate_batch(rows)
    assert result["status"] == expected
    assert result["batch_count"] == len(rows)
    assert result["all_file_names"] == [row["doc_name"] for row in rows]
    assert result["completed_at"] == rows[-1]["completed_at"]
    assert dao._aggregate_batch([]) == {}


def test_direct_download_history_limit_removes_old_terminal_rows(dao, monkeypatch):
    monkeypatch.setitem(
        Options.options, "total_download_history", (2, "manual")
    )
    first = _direct_download(
        "oldest.txt",
        status=DirectDownloadStatus.COMPLETED,
        created_at="2024-01-01 00:00:00",
    )
    second = _direct_download(
        "middle.txt",
        status=DirectDownloadStatus.FAILED,
        created_at="2024-01-02 00:00:00",
    )
    newest = _direct_download(
        "newest.txt",
        status=DirectDownloadStatus.CANCELLED,
        created_at="2024-01-03 00:00:00",
    )
    for record in (first, second, newest):
        dao.save_direct_download(record)

    assert dao.get_direct_download(first.uid) is None
    assert {item.uid for item in dao.get_direct_downloads()} == {
        second.uid,
        newest.uid,
    }
