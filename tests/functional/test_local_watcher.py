"""
Functional test for nxdrive/engine/watcher/local_watcher.py
"""
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import patch

import pytest

from nxdrive.client.local.base import FileInfo
from nxdrive.engine.watcher.local_watcher import LocalWatcher
from tests.markers import not_mac


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


# def test_execute_watchdog(manager_factory):
#     # This test needs to be completed after sometime, to avoid triggering infinite loop
#     '''
#     watchdog_queue is NOT empty
#     '''
#     from nxdrive.exceptions import ThreadInterrupt

#     manager, engine = manager_factory()
#     print(manager_factory())
#     remote = engine.remote
#     dao = remote.dao
#     local_watcher = LocalWatcher(engine, dao)
#     with patch("nxdrive.client.local.base.LocalClientMixin.exists") as mock_exists,\
#         patch("nxdrive.engine.workers.Worker._interact") as mock_interact,\
#         patch("nxdrive.engine.watcher.local_watcher.LocalWatcher.handle_watchdog_event") as mock_handle:
#         mock_exists.return_value = True
#         mock_interact.return_value = True
#         mock_interact.side_effect = ThreadInterrupt("dummy_interrupt_process")
#         mock_handle.return_value = None
#         local_watcher.watchdog_queue.put(item="data",block=False,timeout=1.0)
#         with pytest.raises(ThreadInterrupt) as ex:
#             local_watcher._execute()
#         assert ex.exconly() == 'nxdrive.exceptions.ThreadInterrupt: dummy_interrupt_process'


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
        local_watcher.get_creation_time(Path("tests/resources/files/testFile.txt"))
        == 9565868
    )


def test_scan_recursive(manager_factory):
    from nxdrive.client.local.base import LocalClientMixin

    class Mock_Local_Client(LocalClientMixin):
        def __init__(self) -> None:
            super().__init__(Path())
            self.abs_path = Path("dummy_absolute_path")

        def abspath(self, ref: Path) -> Path:
            return self.abs_path

        def get_children_info(self, ref: Path) -> List[FileInfo]:
            file_info = FileInfo(
                Path(""), Path("dummy_local_path"), False, datetime.now()
            )
            file_info2 = FileInfo(
                Path(""), Path("dummy_local_path2"), False, datetime.now()
            )
            return [file_info, file_info2]

        def get_remote_id(self, ref: Path, /, *, name: str = "ndrive") -> str:
            return "remote_id"

        def exists(self, ref: Path) -> bool:
            return True

        def is_case_sensitive(self) -> bool:
            return False

    class Mock_DAO:
        def __init__(self):
            self.db_children = []
            self.doc_pairs = [self, self]
            self.local_name = "dummy_local_name"
            self.local_path = "dummy_local_path"
            self.pair_state = "dummy_pair_state"
            self.processor = 0
            self.remote_name = "dummy_remote_name"
            self.remote_path = "dummy_remote_path"
            self.remote_ref = "dummy_remote_ref"
            self.remote_state = "dummy_remote_state"

        def get_local_children(self, path: Path):
            self.db_children.append(self)
            return self.db_children

        def get_new_remote_children(self, id: str):
            return self.doc_pairs

        def get_normal_state_from_remote(self, ref: str):
            return self.doc_pairs[0]

        def update_local_state(self, pair, child):
            pass

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    mock_file_info = FileInfo(
        Path(""), Path("tests/resources/files/testFile.txt"), False, datetime.now()
    )
    with patch(
        "nxdrive.engine.watcher.local_watcher.LocalWatcher.get_creation_time"
    ) as mock_creation_time:
        mock_creation_time.return_value = 2000
        local_watcher.dao = Mock_DAO()
        local_watcher.local = Mock_Local_Client()
        assert local_watcher._scan_recursive(mock_file_info, recursive=False) is None
