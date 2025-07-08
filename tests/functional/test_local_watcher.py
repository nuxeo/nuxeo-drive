"""
Functional test for nxdrive/engine/watcher/local_watcher.py
"""

from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Cursor
from typing import List
from unittest.mock import patch

import pytest
from watchdog.events import FileSystemEvent

from nxdrive.client.local.base import FileInfo, LocalClientMixin
from nxdrive.engine.watcher.local_watcher import LocalWatcher
from nxdrive.objects import DocPair
from tests.markers import not_mac, windows_only


class Mock_Local_Client(LocalClientMixin):
    def __init__(self) -> None:
        super().__init__(Path())
        self.abs_path = Path("dummy_absolute_path")
        self.default_file_info: FileInfo | None = FileInfo(
            Path(""), Path("dummy_local_path"), False, datetime.now(), digest_func="md5"
        )
        self.equal_digest = True
        self.exist = True
        self.ignored = True
        self.local_info = True
        self.path = Path("")
        self.remote_id = "remote_ref"
        self.temp = True

    def abspath(self, ref: Path) -> Path:
        return self.abs_path

    def get_children_info(self, ref: Path) -> List[FileInfo]:
        file_info = FileInfo(
            Path(""), Path("dummy_local_path"), False, datetime.now(), digest_func="md5"
        )
        file_info2 = FileInfo(
            Path(""),
            Path("dummy_local_path2"),
            False,
            datetime.now(),
            digest_func="md5",
        )
        return [file_info, file_info2]

    def get_info(self, ref: Path, /, *, check: bool = True) -> FileInfo:
        return self.default_file_info

    def get_path(self, target: Path) -> Path:
        return self.path

    def get_remote_id(self, ref: Path, /, *, name: str = "ndrive") -> str:
        return self.remote_id

    def exists(self, ref: Path) -> bool:
        return self.exist

    def is_case_sensitive(self) -> bool:
        return False

    def is_equal_digests(
        self,
        local_digest: str | None,
        remote_digest: str | None,
        local_path: Path,
        /,
        *,
        remote_digest_algorithm: str = None,
    ) -> bool:
        return self.equal_digest

    def is_ignored(self, parent_ref: Path, file_name: str) -> bool:
        return self.ignored

    def is_temp_file(self, path) -> bool:
        return self.temp

    def remove_remote_id(
        self, ref: Path, /, *, name: str = "ndrive", cleanup: bool = False
    ) -> None:
        return None

    def set_remote_id(
        self, ref: Path, remote_id: bytes | str, /, *, name: str = "ndrive"
    ) -> None:
        return None

    def try_get_info(self, ref: Path) -> FileInfo | None:
        return self.default_file_info


class Mock_DAO:
    def __init__(self):
        self.acquired_state = "DocPair_object"
        self.db_children = []
        self.doc_pairs = [self, self]
        self.folderish = False
        self.id = 1
        self.local_digest = "md6"
        self.last_local_updated = "2025-07-04 11:41:23"
        self.local_name = "dummy_local_name"
        self.local_path = Path("dummy_local_path")
        self.local_state = "dummy_local_state"
        self.pair_index: int = (
            2  # To control the index of doc_pair received from get_state_from_local
        )
        self.pair_state = "dummy_pair_state"
        self.processor = 0
        self.remote_can_create_child = False
        self.remote_name = "dummy_remote_name"
        self.remote_path = "dummy_remote_path"
        self.remote_ref = "dummy_remote_ref"
        self.remote_state = "dummy_remote_state"
        self.version = 1

    def acquire_state(self, thread_id, doc_pair_id):
        return self.acquired_state

    def get_local_children(self, path: Path):
        self.db_children.append(self)
        mock_dao2 = Mock_DAO()
        mock_dao2.local_name = "dummy_local_name2"
        self.db_children.append(mock_dao2)
        return self.db_children

    def get_new_remote_children(self, id: str):
        return self.doc_pairs

    def get_normal_state_from_remote(self, ref: str):
        return self.doc_pairs[0]

    def get_state_from_id(self, id: int):
        return self.doc_pairs[0]

    def get_state_from_local(self, path):
        if self.pair_index != -1:
            mock_dao = Mock_DAO()
            mock_dao.pair_state = "unsynchronized"
            self.doc_pairs.append(mock_dao)
            return self.doc_pairs[self.pair_index]
        else:
            mock_client_path = Mock_Local_Client().path
            # return a doc_pair when the path passed is the parent
            if mock_client_path.parent == path:
                return self.doc_pairs[0]
            return

    def insert_local_state(self, child, path):
        return 2

    def _queue_pair_state(
        self, id: int, folderish: bool, pair_state: str, pair: DocPair
    ):
        pass

    def release_state(self, thread_id):
        pass

    def remove_state(self, doc_pair):
        return None

    def replace_local_paths(self, old_path, new_path):
        pass

    def update_local_state(self, pair, child, versioned=False):
        pass

    def unsynchronize_state(self, row, last_error):
        pass


@not_mac(reason="Failure on mac")
def test_execute(manager_factory):
    """
    watchdog_queue is empty
    """
    from nxdrive.exceptions import ThreadInterrupt

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    with patch(
        "nxdrive.client.local.base.LocalClientMixin.exists"
    ) as mock_exists, patch("nxdrive.engine.workers.Worker._interact") as mock_interact:
        mock_exists.return_value = True
        mock_interact.return_value = True
        mock_interact.side_effect = ThreadInterrupt("dummy_interrupt_process")
        local_watcher.watchdog_queue.put(item="data", block=False, timeout=1.0)
        with pytest.raises(ThreadInterrupt) as ex:
            local_watcher._execute()
        assert (
            ex.exconly()
            == "nxdrive.exceptions.ThreadInterrupt: dummy_interrupt_process"
        )


@not_mac(reason="Failing on MacOS")
def test_update_local_status(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher._update_local_status() is None


def test_win_queue_empty(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.win_queue_empty() is True


def test_get_win_queue_size(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.get_win_queue_size() == 0


def test_win_delete_check(manager_factory):
    from time import time

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._win_delete_interval = int(round(time() * 1000) - 20000)
    assert local_watcher._win_delete_check() is None


def test_win_folder_scan_empty(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.win_folder_scan_empty() is True


def test_get_win_folder_scan_size(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.get_win_folder_scan_size() == 0


def test_win_folder_scan_check(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._win_folder_scan_interval = 100000
    assert local_watcher._win_folder_scan_check() is None


def test_win_dequeue_folder_scan(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert isinstance(local_watcher, LocalWatcher)


def test_scan(manager_factory):
    from nxdrive.feature import Feature

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    Feature.synchronization = True
    with patch(
        "nxdrive.client.local.base.LocalClientMixin.get_info"
    ) as mock_info, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._scan_recursive"
    ) as mock_recursive:
        mocked_file = FileInfo(
            Path(""), Path("tests/resources/files/testFile.txt"), False, datetime.now()
        )
        mock_recursive.return_value = None
        mock_info.return_value = mocked_file
        assert local_watcher._scan() is None


def test_scan_handle_deleted_files(manager_factory):
    class Mock_Doc_Pair:
        def __init__(self) -> None:
            self.local_path = ""

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    mock_doc_pair = Mock_Doc_Pair()
    with patch("nxdrive.engine.engine.Engine.delete_doc") as mock_delete:
        local_watcher._delete_files = {"file1": mock_doc_pair, "file2": mock_doc_pair}
        local_watcher._protected_files = {"file1": True}
        print("delete_files", local_watcher._protected_files)
        mock_delete.return_value = None
        assert local_watcher._scan_handle_deleted_files() is None


def test_get_metrics(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.get_metrics() is not None


def test_scan_pair(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_path = Path("")
    local_watcher._delete_files = {}
    # with info
    with patch(
        "nxdrive.client.local.base.LocalClientMixin.try_get_info"
    ) as mock_info, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._scan_handle_deleted_files"
    ) as mock_delete:
        mock_info.return_value = FileInfo(
            Path(""), Path("tests/resources/files/testFile.txt"), False, datetime.now()
        )
        mock_delete.return_value = None
        assert local_watcher.scan_pair(local_path) is None
    # without info
    assert local_watcher.scan_pair(local_path) is None


def test_empty_events(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.empty_events() is True


def test_get_creation_time(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert (
        local_watcher.get_creation_time(Path("tests/resources/files/testFile.txt")) > 0
    )


def test_scan_recursive(manager_factory):
    """
    if child_name not in children
    """

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    mock_file_info = FileInfo(
        Path(""), Path("tests/resources/files/testFile.txt"), False, datetime.now()
    )
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_remove_transfers:
        mock_creation_time.return_value = 2000
        mock_remove_transfers.return_value = None
        local_watcher.dao = Mock_DAO()
        local_watcher.local = Mock_Local_Client()
        local_watcher._delete_files = {}
        assert local_watcher._scan_recursive(mock_file_info, recursive=False) is None


def test_scan_recursive_2(manager_factory):
    """
    if child_name in children
    """
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    mock_file_info = FileInfo(
        Path(""), Path("tests/resources/files/testFile.txt"), False, datetime.now()
    )
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_remove_transfers:
        mock_creation_time.return_value = 2000
        mock_dao = Mock_DAO()
        mock_local_client = Mock_Local_Client()
        mock_dao.local_name = "dummy_local_path"
        mock_remove_transfers.return_value = None
        local_watcher.dao = mock_dao
        local_watcher.local = mock_local_client
        local_watcher._protected_files = {}
        local_watcher._delete_files = {}
        assert local_watcher._scan_recursive(mock_file_info, recursive=False) is None


def test_setup_watchdog(manager_factory):
    from nxdrive.feature import Feature

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    Feature.synchronization = True
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher._setup_watchdog() is None


def test_stop_watchdog(manager_factory):
    """
    Observer created
    """
    from nxdrive.feature import Feature

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    Feature.synchronization = True
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._setup_watchdog()
    assert local_watcher._stop_watchdog() is None


def test_stop_watchdog2(manager_factory):
    """
    Observer not created
    """
    from nxdrive.feature import Feature

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    Feature.synchronization = True
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher._stop_watchdog() is None


def test_handle_watchdog_delete(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    mock_client = Mock_Local_Client()
    # abspath.parent.exists == False
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void:
        assert local_watcher._handle_watchdog_delete(mock_doc_pair) is None
    # abspath.parent.exists == True
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void:
        mock_void.return_value = None
        local_watcher.local = mock_client
        assert local_watcher._handle_watchdog_delete(mock_doc_pair) is None


def test_handle_delete_on_known_pair(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._delete_events = {}
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    # self.local.exists == True
    # not remote_id
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_client.remote_id = ""
    local_watcher.local = mock_client
    assert local_watcher._handle_delete_on_known_pair(mock_doc_pair) is None
    # self.local.exists == False
    mock_client = Mock_Local_Client()
    mock_client.exist = False
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._handle_watchdog_delete"
    ) as mock_watchdog_delete:
        mock_watchdog_delete.return_value = None
        assert local_watcher._handle_delete_on_known_pair(mock_doc_pair) is None


def test_handle_move_on_known_pair(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_rel_path = Path("")
    # ignore == True
    with patch(
        "nxdrive.engine.watcher.local_watcher.is_generated_tmp_file"
    ) as mock_temp:
        mock_temp.return_value = (True, True)
        assert (
            local_watcher._handle_move_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # ignore == False
    # pair and pair.remote_ref == remote_ref
    # local_info == FileInfo
    # not doc_pair.folderish and pair.local_digest == digest
    # doc_pair.id != pair.id
    mock_doc_pair.folderish = False
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "TO_COMPUTE"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_move_on_known_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # ignore == False
    # pair and pair.remote_ref == remote_ref
    # local_info == FileInfo
    mock_doc_pair.folderish = True
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_move_on_known_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # ignore == False
    # pair and pair.remote_ref != remote_ref
    # local_info == None
    mock_doc_pair.folderish = True
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.default_file_info = None
    mock_client.remote_id = "dummy_remote_ref"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_move_on_known_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # ignore == False
    # pair and pair.remote_ref != remote_ref
    # local_info == FileInfo
    # is_text_edit_tmp_file == True
    mock_doc_pair.folderish = True
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref2"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.is_text_edit_tmp_file"
    ) as mock_edit_tmp:
        mock_edit_tmp.return_value = True
        assert (
            local_watcher._handle_move_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # ignore == False
    # pair and pair.remote_ref != remote_ref
    # local_info == FileInfo
    # is_text_edit_tmp_file == False
    mock_doc_pair.folderish = True
    mock_doc_pair.local_path = Path("tests/resources/files/testFile.txt")
    mock_doc_pair.remote_name = "dummy_remote_name"
    mock_doc_pair.remote_parent_ref = "dummy_parent_ref"
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref2"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.is_text_edit_tmp_file"
    ) as mock_edit_tmp, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void:
        mock_edit_tmp.return_value = False
        mock_void.return_value = None
        assert (
            local_watcher._handle_move_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # ignore == False
    # pair and pair.remote_ref != remote_ref
    # local_info == FileInfo
    # is_text_edit_tmp_file == False
    # doc_pair.remote_name == local_info.name
    # doc_pair.remote_parent_ref == remote_parent_ref
    # rel_parent_path == doc_pair.local_path.parent
    mock_doc_pair.folderish = True
    mock_doc_pair.local_path = Path("")
    mock_doc_pair.remote_name = "dummy_remote_name"
    mock_doc_pair.remote_parent_ref = "dummy_remote_ref2"
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref2"
    mock_client.default_file_info.name = "dummy_remote_name"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.is_text_edit_tmp_file"
    ) as mock_edit_tmp, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void:
        mock_edit_tmp.return_value = False
        mock_void.return_value = None
        assert (
            local_watcher._handle_move_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # ignore == False
    # pair and pair.remote_ref != remote_ref
    # local_info == FileInfo
    # is_text_edit_tmp_file == False
    # WINDOWS == True
    mock_doc_pair.folderish = True
    mock_doc_pair.local_path = Path("tests/resources/files/testFile.txt")
    mock_doc_pair.remote_name = "dummy_remote"
    mock_doc_pair.remote_parent_ref = "dummy_remote_ref2"
    mock_dao = Mock_DAO()
    mock_dao.id = 2
    mock_dao.local_digest = "dummy_digest"
    mock_dao.pair_index = 0
    mock_client = Mock_Local_Client()
    mock_client.remote_id = "dummy_remote_ref2"
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.is_text_edit_tmp_file"
    ) as mock_edit_tmp, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void:
        mock_edit_tmp.return_value = False
        mock_void.return_value = None
        local_watcher._windows_folder_scan_delay = 10
        local_watcher._folder_scan_events = {
            Path("tests/resources/files/testFile.txt"): (10.0, mock_doc_pair)
        }
        assert (
            local_watcher._handle_move_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )


def test_handle_watchdog_event_on_known_pair(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    # if acquired_pair == DocPair
    # evt.event_type == "deleted"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "deleted"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_dao.acquired_state = mock_dao
    local_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._handle_delete_on_known_pair"
    ) as mock_delete:
        mock_delete.return_value = True
        assert (
            local_watcher._handle_watchdog_event_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # if acquired_pair == DocPair
    # evt.event_type != "deleted"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_dao.acquired_state = mock_dao
    local_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._handle_watchdog_event_on_known_acquired_pair"
    ) as mock_acquired:
        mock_acquired.return_value = True
        assert (
            local_watcher._handle_watchdog_event_on_known_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # acquired_pair == None
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_dao.acquired_state = ""
    local_watcher.dao = mock_dao
    assert (
        local_watcher._handle_watchdog_event_on_known_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )


def test_handle_watchdog_event_on_known_acquired_pair(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    local_watcher = LocalWatcher(engine, dao)
    # local_info == None
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.default_file_info = None
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # local_info != None
    # remote_ref == None or ''
    # local_info.get_digest() == doc_pair.local_digest
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.remote_id = ""
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # local_info != None
    # remote_ref == None or ''
    # local_info.get_digest() != doc_pair.local_digest
    # folderish == True
    mock_doc_pair.local_digest = "dummy_digest"
    mock_doc_pair.folderish = True
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.remote_id = ""
    local_watcher.dao = dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # local_info != None
    # remote_ref != None
    # folderish == False
    # doc_pair.pair_state == "synchronized"
    # doc_pair.local_digest == digest
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "synchronized"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    local_watcher.dao = dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # local_info != None
    # remote_ref != None
    # folderish == False
    # doc_pair.pair_state == "synchronized"
    # doc_pair.local_digest != digest
    mock_doc_pair.local_digest = "dummy_digest"
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "synchronized"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void_transfer:
        mock_void_transfer.return_value = None
        assert (
            local_watcher._handle_watchdog_event_on_known_acquired_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )
    # evt.event_type == "modified"
    # local_info.size != doc_pair.size
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "unsynchronized"
    mock_doc_pair.size = 20
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.default_file_info.size = 25
    local_watcher.dao = dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # evt.event_type == "modified"
    # local_info.size == doc_pair.size
    # doc_pair.local_digest == UNACCESSIBLE_HASH
    mock_doc_pair.local_digest = "TO_COMPUTE"
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "unsynchronized"
    mock_doc_pair.size = 20
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.default_file_info.size = 20
    local_watcher.dao = dao
    local_watcher.local = mock_client
    assert (
        local_watcher._handle_watchdog_event_on_known_acquired_pair(
            mock_doc_pair, mock_file_system, mock_rel_path
        )
        is None
    )
    # evt.event_type == "modified"
    # local_info.size == doc_pair.size
    # doc_pair.local_digest != UNACCESSIBLE_HASH
    # original_info
    mock_doc_pair.local_digest = "random_string"
    mock_doc_pair.folderish = False
    mock_doc_pair.pair_state = "unsynchronized"
    mock_doc_pair.size = 20
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_rel_path = Path("")
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    mock_client.default_file_info.size = 20
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.remove_void_transfers"
    ) as mock_void_transfer:
        mock_void_transfer.return_value = None
        assert (
            local_watcher._handle_watchdog_event_on_known_acquired_pair(
                mock_doc_pair, mock_file_system, mock_rel_path
            )
            is None
        )


def test_handle_watchdog_root_event(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    # evt.event_type == "deleted"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "deleted"
    assert local_watcher.handle_watchdog_root_event(mock_file_system) is None
    # evt.event_type == "moved"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    assert local_watcher.handle_watchdog_root_event(mock_file_system) is None


def test_handle_watchdog_event(manager_factory):
    import errno

    from nxdrive.exceptions import ThreadInterrupt

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    # evt.src_path == ""
    mock_file_system = FileSystemEvent(
        src_path="", dest_path="dummy_dest_path", is_synthetic=False
    )
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type == "moved"
    mock_file_system = FileSystemEvent(
        src_path="dummy_path", dest_path="dummy_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # client.get_path(src_path) == ROOT
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_dao = Mock_DAO()
    mock_local_client = Mock_Local_Client()
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type != "moved" and client.is_ignored == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_dao = Mock_DAO()
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # client.is_temp_file == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_dao = Mock_DAO()
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # doc_pair == True and doc_pair.pair_state == "unsynchronized"
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "deleted"
    mock_dao = Mock_DAO()
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # doc_pair == True and doc_pair.pair_state != unsynchronized
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.local_state = "deleted"
    mock_dao.pair_state = "locally_deleted"
    mock_dao.pair_index = 0
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # doc_pair == True and evt.event_type == "moved"
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    mock_dao = Mock_DAO()
    mock_dao.pair_state = "locally_deleted"
    mock_dao.pair_index = 0
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # doc_pair == True and no subcondition passes
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_state = "locally_deleted"
    mock_dao.pair_index = 0
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type == "deleted"
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "deleted"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type == "moved" and client.is_ignored == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = True
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type == "moved" and client.is_ignored == False
    # local_info.remote_ref != ""
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = False
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher._handle_move_on_known_pair"
    ) as mock_move_known_pair:
        mock_move_known_pair.return_value = None
        assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type == "moved" and client.is_ignored == False
    # local_info.remote_ref == ""
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "moved"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = ""
    mock_local_client.default_file_info.folderish = True
    mock_local_client.exist = False
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.scan_pair"
    ) as mock_scan:
        mock_scan.return_value = None
        assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type not in ("created", "modified")
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "dummy_type"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified") and local_info == None
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info = None
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor > 0
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.processor = 1
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor == 0
    # client.exists == False
    # dst_parent.remote_can_create_child == False
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = False
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor == 0
    # client.exists == False
    # dst_parent.remote_can_create_child == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_dao.remote_can_create_child = True
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = False
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor > 0
    # client.exists == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.side_effect = [100, 200]
        assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor > 0
    # client.exists == True
    # moved == False
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.return_value = 100
        assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # evt.event_type in ("created", "modified")
    # local_info != None and local.remote_ref != None
    # from_pair.processor > 0
    # client.exists == True
    # moved == False and local_info.folderish == True
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.default_file_info.folderish = True
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time, patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.scan_pair"
    ) as mock_scan_pair:
        mock_creation_time.return_value = 100
        mock_scan_pair.return_value = None
        assert local_watcher.handle_watchdog_event(mock_file_system) is None

    # raising ThreadInterrupt Exception
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.return_value = 100
        mock_creation_time.side_effect = ThreadInterrupt(
            "Custom ThreadInterrupt exception"
        )
        with pytest.raises(ThreadInterrupt) as ex:
            local_watcher.handle_watchdog_event(mock_file_system)
        assert str(ex.value) == "Custom ThreadInterrupt exception"
    # raising OSError Exception
    # evt.event_type == created
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "created"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.return_value = 100
        mock_error = OSError("Custom OSError exception")
        mock_error.errno = errno.EEXIST
        mock_creation_time.side_effect = mock_error
        assert local_watcher.handle_watchdog_event(mock_file_system) is None
    # raising OSError Exception
    # evt.event_type != created
    mock_file_system = FileSystemEvent(
        src_path="dummy_src_path", dest_path="dummy_dest_path", is_synthetic=False
    )
    mock_file_system.event_type = "modified"
    mock_dao = Mock_DAO()
    mock_dao.pair_index = -1
    mock_dao.pair_state = "dummy_pair_state"
    mock_local_client = Mock_Local_Client()
    mock_local_client.default_file_info.remote_ref = "dummy_remote_ref"
    mock_local_client.exist = True
    mock_local_client.path = Path("tests")
    mock_local_client.ignored = False
    mock_local_client.temp = False
    local_watcher.dao = mock_dao
    local_watcher.local = mock_local_client
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.return_value = 100
        mock_error = OSError("Custom OSError exception")
        mock_error.errno = errno.EEXIST
        mock_creation_time.side_effect = mock_error
        assert local_watcher.handle_watchdog_event(mock_file_system) is None


@windows_only(reason="On Windows, another recursive scan is triggered")
def test_schedule_win_folder_scan(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    mock_dao = Mock_DAO()
    mock_client = Mock_Local_Client()
    local_watcher.dao = mock_dao
    local_watcher.local = mock_client
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = DocPair(cursor, ())
    # _win_folder_scan_interval <= 0 or _windows_folder_scan_delay <= 0
    local_watcher._win_folder_scan_interval = 0
    local_watcher._windows_folder_scan_delay = 0
    assert local_watcher._schedule_win_folder_scan(mock_doc_pair) is None
    # _win_folder_scan_interval > 0 and _windows_folder_scan_delay > 0
    mock_client.default_file_info.last_modification_time = datetime.now()
    mock_doc_pair.id = 1
    mock_doc_pair.local_path = Path("dummy_local_path")
    mock_doc_pair.local_parent_path = Path("dummy_parent_path")
    mock_doc_pair.remote_ref = "dummy_remote_ref"
    mock_doc_pair.local_state = "dummy_local_state"
    mock_doc_pair.remote_state = "dummy_remote_state"
    mock_doc_pair.pair_state = "dummy_pair_state"
    mock_doc_pair.last_error = "dummy_last_error"
    local_watcher._win_folder_scan_interval = 10
    local_watcher._windows_folder_scan_delay = 10
    local_watcher._folder_scan_events = {
        Path("dummy_local_path"): (10.0, mock_doc_pair)
    }
    assert local_watcher._schedule_win_folder_scan(mock_doc_pair) is None
