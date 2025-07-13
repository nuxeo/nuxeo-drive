"""
Functional tests for nxdrive/engine/watcher/remote_watcher.py
"""

from collections import namedtuple
from pathlib import Path
from sqlite3 import Connection, Cursor
from unittest.mock import patch

import pytest

from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
from nxdrive.exceptions import ThreadInterrupt
from nxdrive.objects import DocPair, RemoteFileInfo
from tests.functional.mocked_classes import (
    Mock_DAO,
    Mock_Doc_Pair,
    Mock_Engine,
    Mock_Local_Client,
    Mock_Remote,
    Mock_Remote_File_Info,
)


def test_get_metrics(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    assert isinstance(remote_watcher.get_metrics(), dict)


def test_execute(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    with pytest.raises(ThreadInterrupt) as ex:
        remote_watcher._execute()
    assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")


def test_scan_remote(manager_factory):
    from nxdrive.exceptions import NotFound

    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
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
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 0
    mock_remote = Mock_Remote()
    remote_watcher.dao = mock_dao
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_changes:
        mock_remove_void.return_value = None
        mock_changes.return_value = None
        assert remote_watcher.scan_remote(from_state=mock_doc_pair) is None
    # exception NotFound
    mock_dao = Mock_DAO()
    mock_dao.pair_index = 0
    mock_remote = Mock_Remote()
    remote_watcher.dao = mock_dao
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void:
        mock_remove_void.return_value = None
        mock_remove_void.side_effect = NotFound("Custom NotFound Exception")
        assert remote_watcher.scan_remote(from_state=mock_doc_pair) is None


def test_scan_pair(manager_factory):
    """
    For _scan_pair
    """
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    # remote_path is None
    assert remote_watcher._scan_pair(None) is None
    # remote is not None
    # dao.is_filter == True
    mock_dao = Mock_DAO()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    assert remote_watcher._scan_pair("dummy_remote_path") is None
    # remote is not None
    # dao.is_filter == False
    # doc_pair is not None
    mock_dao = Mock_DAO()
    mock_dao.get_states.extend([mock_dao.mocked_doc_pair])
    mock_dao.filter = False
    mock_remote = Mock_Remote()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.remote = mock_remote
    assert remote_watcher._scan_pair("tests/resources/files/") is None
    # remote is not None
    # dao.is_filter == False
    # doc_pair is None
    # os.path.dirname(child_info.path) == remote_parent_path
    mock_dao = Mock_DAO()
    mock_dao.filter = False
    mock_dao.mocked_doc_pair.remote_parent_path = "tests/resources"
    mock_dao.mocked_doc_pair.remote_ref = "files"
    mock_dao.get_states.extend([None, mock_dao.mocked_doc_pair])
    mock_remote = Mock_Remote()
    mock_remote.path = "tests/resources/files/"
    mock_remote.folderish = True
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._do_scan_remote"
    ) as mock_scan_remote:
        mock_scan_remote.return_value = None
        assert remote_watcher._scan_pair("tests/resources/files/") is None
    # remote is not None
    # dao.is_filter == False
    # doc_pair is None
    # os.path.dirname(child_info.path) != remote_parent_path
    mock_dao = Mock_DAO()
    mock_dao.filter = False
    mock_dao.mocked_doc_pair.remote_parent_path = "tests/resources"
    mock_dao.mocked_doc_pair.remote_ref = "files2"
    mock_dao.get_states.extend([None, mock_dao.mocked_doc_pair])
    mock_remote = Mock_Remote()
    mock_remote.path = "tests/resources/files/"
    mock_remote.folderish = True
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_scan_remote.return_value = None
        assert remote_watcher._scan_pair("tests/resources/files/") is None


def test_check_modified(manager_factory):
    manager, engine = manager_factory()
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
    mock_doc_pair.remote_can_delete = True
    mock_doc_pair.remote_can_rename = True
    mock_doc_pair.remote_can_update = False
    mock_doc_pair.remote_can_create_child = True
    mock_doc_pair.remote_name = "doc_pair_remote"
    mock_doc_pair.remote_digest = "doc_pair_digest"
    mock_doc_pair.remote_parent_ref = "doc_pair_remote_parent_ref"
    mock_remote_file_info = Mock_Remote_File_Info()
    assert RemoteWatcher._check_modified(mock_doc_pair, mock_remote_file_info) is True


def test_scan_remote_scroll(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    # remote_parent_path is None
    assert (
        remote_watcher._scan_remote_scroll(
            mock_doc_pair, mock_remote_file_info, moved=False
        )
        is None
    )
    # remote_parent_path is not None
    # moved == True
    # not parent_pair
    # to_process != []
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote = Mock_Remote()
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._init_scan_remote"
    ) as mock_init_scan, patch(
        "nxdrive.client.remote_client.Remote.scroll_descendants"
    ) as mock_scroll_descendants, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact:
        mock_init_scan.return_value = "dummy_remote_parent_path"
        mock_remote2 = Mock_Remote()
        mock_remote2.descendants["descendants"] = False
        mock_scroll_descendants.side_effect = [
            mock_remote.descendants,
            mock_remote2.descendants,
        ]
        mock_interact.return_value = True
        assert (
            remote_watcher._scan_remote_scroll(
                mock_doc_pair, mock_remote_file_info, moved=True
            )
            is None
        )
    # remote_parent_path is not None
    # moved == True
    # self.filtered(descendant_info) == True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote = Mock_Remote()
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._init_scan_remote"
    ) as mock_init_scan, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.filtered"
    ) as mock_filtered:
        mock_init_scan.return_value = "dummy_remote_parent_path"
        mock_filtered.return_value = True
        mock_interact.side_effect = [None, ThreadInterrupt("Custom thread interrupt")]
        with pytest.raises(ThreadInterrupt) as ex:
            remote_watcher._scan_remote_scroll(
                mock_doc_pair, mock_remote_file_info, moved=True
            )
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")
    # remote_parent_path is not None
    # moved == True
    # dao.is_filter(descendant_info.path) == True
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote = Mock_Remote()
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._init_scan_remote"
    ) as mock_init_scan, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.dao.engine.EngineDAO.is_filter"
    ) as mock_filter:
        mock_init_scan.return_value = "dummy_remote_parent_path"
        mock_interact.side_effect = [None, ThreadInterrupt("Custom thread interrupt")]
        mock_filter.return_value = True
        with pytest.raises(ThreadInterrupt) as ex:
            remote_watcher._scan_remote_scroll(
                mock_doc_pair, mock_remote_file_info, moved=True
            )
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")
    # remote_parent_path is not None
    # moved == True
    # descendant_info.digest == "notInBinaryStore"
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote = Mock_Remote()
    mock_remote.descendants["descendants"][0].digest = "notInBinaryStore"
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._init_scan_remote"
    ) as mock_init_scan, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact:
        mock_init_scan.return_value = "dummy_remote_parent_path"
        mock_interact.side_effect = [None, ThreadInterrupt("Custom thread interrupt")]
        with pytest.raises(ThreadInterrupt) as ex:
            remote_watcher._scan_remote_scroll(
                mock_doc_pair, mock_remote_file_info, moved=True
            )
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")
    # remote_parent_path is not None
    # moved == False
    # descendant_info.uid in descendants
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote = Mock_Remote()
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._init_scan_remote"
    ) as mock_init_scan, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.dao.engine.EngineDAO.get_remote_descendants"
    ) as mock_remote_descendants, patch(
        "nxdrive.dao.engine.EngineDAO.update_remote_state"
    ) as mock_remote_state, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_void_tranfers:
        mock_init_scan.return_value = "dummy_remote_parent_path"
        mock_interact.side_effect = [None, ThreadInterrupt("Custom thread interrupt")]
        mock_remote_state.return_value = True
        mock_void_tranfers.return_value = None
        mock_doc_pair2 = Mock_Doc_Pair(cursor, ())
        mock_doc_pair2.remote_ref = "dummy_uid"
        mock_remote_descendants.return_value = [mock_doc_pair2]
        with pytest.raises(ThreadInterrupt) as ex:
            remote_watcher._scan_remote_scroll(
                mock_doc_pair, mock_remote_file_info, moved=False
            )
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")


def test_init_scan_remote(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    # remote_info.folderish == False
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    assert (
        remote_watcher._init_scan_remote(mock_doc_pair, mock_remote_file_info) is None
    )
    # remote_info.folderish == True
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.folderish = True
    remote_watcher = RemoteWatcher(engine, dao)
    assert (
        remote_watcher._init_scan_remote(mock_doc_pair, mock_remote_file_info)
        == "dummy_remote_parent_path/dummy_uid"
    )
    # remote_info.folderish == True
    # dao.is_path_scanned == True
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.folderish = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch("nxdrive.dao.engine.EngineDAO.is_path_scanned") as mock_path_scanned:
        mock_path_scanned.return_value = True
        assert (
            remote_watcher._init_scan_remote(mock_doc_pair, mock_remote_file_info)
            is None
        )


def test_find_remote_child_match_or_create(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    # parent_pair.last_error == "DEDUP"
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.last_error = "DEDUP"
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    assert (
        remote_watcher._find_remote_child_match_or_create(
            mock_doc_pair, mock_remote_file_info
        )
        is None
    )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == DocPair
    mock_dao = Mock_DAO()
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    assert (
        remote_watcher._find_remote_child_match_or_create(
            mock_doc_pair, mock_remote_file_info
        )
        is None
    )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is None
    # parent_pair is not None
    # engine.local.exists == True
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_dao.pair_index = 0
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.uid = "remote_ref"
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    assert (
        remote_watcher._find_remote_child_match_or_create(
            mock_doc_pair, mock_remote_file_info
        )
        is None
    )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is not None
    # child_pair.remote_ref is not None
    # child_pair.remote_ref != child_info.uid
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    assert (
        remote_watcher._find_remote_child_match_or_create(
            mock_doc_pair, mock_remote_file_info
        )
        is None
    )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is not None
    # child_pair.remote_ref is not None
    # child_pair.remote_ref == child_info.uid
    # child_pair.folderish == child_info.folderish
    # engine.local.is_equal_digests == True
    # child_pair.local_path != local_path
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_client.equal_digest = True
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.uid = (
        "dummy_remote_ref"  # Matching with child_pair.remote_ref
    )
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void:
        mock_remove_void.return_value = None
        assert (
            remote_watcher._find_remote_child_match_or_create(
                mock_doc_pair, mock_remote_file_info
            )
            is None
        )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is not None
    # child_pair.remote_ref is not None
    # child_pair.remote_ref == child_info.uid
    # child_pair.folderish == child_info.folderish
    # engine.local.is_equal_digests == True
    # child_pair.local_path == local_path
    # synced == True
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_client.equal_digest = True
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_dao.pair_index = 1
    mock_dao.local_path = Path("dummy_local_path/dummy_name")
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.uid = (
        "dummy_remote_ref"  # Matching with child_pair.remote_ref
    )
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void:
        mock_remove_void.return_value = None
        assert (
            remote_watcher._find_remote_child_match_or_create(
                mock_doc_pair, mock_remote_file_info
            )
            is None
        )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is not None
    # child_pair.remote_ref is not None
    # child_pair.remote_ref == child_info.uid
    # child_pair.folderish == child_info.folderish
    # engine.local.is_equal_digests == True
    # child_pair.local_path == local_path
    # synced == False
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_client.equal_digest = True
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_dao.local_path = Path("dummy_local_path/dummy_name")
    mock_dao.pair_index = 1
    mock_dao.synchronize = False
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.uid = (
        "dummy_remote_ref"  # Matching with child_pair.remote_ref
    )
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void:
        mock_remove_void.return_value = None
        assert (
            remote_watcher._find_remote_child_match_or_create(
                mock_doc_pair, mock_remote_file_info
            )
            is None
        )
    # parent_pair.last_error != "DEDUP"
    # dao.get_normal_state_from_remote == None
    # child_pair is not None
    # child_pair.remote_ref is not None
    # child_pair.remote_ref == child_info.uid
    # child_pair.folderish == child_info.folderish
    # engine.local.is_equal_digests == False
    mock_client = Mock_Local_Client()
    mock_client.exist = True
    mock_client.equal_digest = False
    mock_dao = Mock_DAO()
    mock_dao.doc_pairs[0] = None
    mock_dao.local_path = Path("dummy_local_path/dummy_name")
    mock_dao.pair_index = 1
    mock_dao.synchronize = False
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    mock_remote_file_info.uid = (
        "dummy_remote_ref"  # Matching with child_pair.remote_ref
    )
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.dao = mock_dao
    remote_watcher.engine.local = mock_client
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_remove_void:
        mock_remove_void.return_value = None
        assert (
            remote_watcher._find_remote_child_match_or_create(
                mock_doc_pair, mock_remote_file_info
            )
            is None
        )


def test_handle_readonly(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    # doc_pair.is_readonly == False
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    remote_watcher = RemoteWatcher(engine, dao)
    assert remote_watcher._handle_readonly(mock_doc_pair) is None
    # doc_pair.is_readonly == True
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_doc_pair.local_path = Path.cwd() / Path("tests/resources/files/testFile.txt")
    mock_doc_pair.read_only = True
    remote_watcher = RemoteWatcher(engine, dao)
    assert remote_watcher._handle_readonly(mock_doc_pair) is None


def test_partial_full_scan(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    # path == "/"
    mock_path = "/"
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_scan_remote.return_value = None
        assert remote_watcher._partial_full_scan(mock_path) is None
    # path != "/"
    mock_path = "dummy_path"
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._scan_pair"
    ) as mock_scan_pair:
        mock_scan_pair.return_value = None
        assert remote_watcher._partial_full_scan(mock_path) is None


def test_check_offline(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    # engine.is_offline == False
    mock_engine = Mock_Engine()
    remote_watcher = RemoteWatcher(mock_engine, dao)
    assert remote_watcher._check_offline() is False
    # engine.is_offline == True
    # online == True
    mock_engine = Mock_Engine()
    mock_engine.offline = True
    mock_engine.remote.client.reachable = True
    remote_watcher = RemoteWatcher(mock_engine, dao)
    assert remote_watcher._check_offline() is False


def test_handle_changes(manager_factory):
    from datetime import datetime

    from nuxeo.exceptions import BadQuery, HTTPError, Unauthorized

    from nxdrive.exceptions import ScrollDescendantsError
    from nxdrive.options import Feature

    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    # not Feature.synchronization
    # first_pass == True
    Feature.synchronization = None
    remote_watcher = RemoteWatcher(engine, dao)
    assert remote_watcher._handle_changes(True) is True
    # not Feature.synchronization
    # first_pass == False
    Feature.synchronization = None
    remote_watcher = RemoteWatcher(engine, dao)
    assert remote_watcher._handle_changes(False) is False
    # Feature.synchronization
    # _check_offline == True
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline:
        mock_offline.return_value = True
        assert remote_watcher._handle_changes(False) is False
    # Feature.synchronization
    # _check_offline == False
    # first_pass == True
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.return_value = None
        assert remote_watcher._handle_changes(True) is True
    # Feature.synchronization
    # _check_offline == False
    # first_pass == False
    # full_scan is not None
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher._last_remote_full_scan = datetime.now()
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.dao.engine.EngineDAO.get_config"
    ) as mock_config, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._partial_full_scan"
    ) as mock_partial_scan:
        mock_offline.return_value = False
        mock_config.return_value = "dummy_config"
        mock_partial_scan.return_value = None
        assert remote_watcher._handle_changes(False) is False
    # Feature.synchronization
    # _check_offline == False
    # first_pass == False
    # full_scan is None
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher._last_remote_full_scan = datetime.now()
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.dao.engine.EngineDAO.get_paths_to_scan"
    ) as mock_paths, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._partial_full_scan"
    ) as mock_partial_scan, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._update_remote_states"
    ) as mock_update_remote_states:
        mock_offline.return_value = False
        mock_paths.side_effect = [["path1"], ["path2"], None]
        mock_partial_scan.return_value = None
        mock_update_remote_states.return_value = None
        assert remote_watcher._handle_changes(False) is True
    # BadQuery
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = BadQuery("Custom Bad Query")
        with pytest.raises(BadQuery) as ex:
            remote_watcher._handle_changes(False)
        assert str(ex.exconly()).startswith("nuxeo.exceptions.BadQuery")
    # ScrollDescendantsError
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = ScrollDescendantsError(
            "Custom ScrollDescendantsError Exception"
        )
        assert remote_watcher._handle_changes(False) is False
    # Unauthorized
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = Unauthorized()
        assert remote_watcher._handle_changes(False) is False
    # OSError
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = OSError()
        assert remote_watcher._handle_changes(False) is False
    # HTTPError
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = HTTPError(status=504)
        assert remote_watcher._handle_changes(False) is False
    # ThreadInterrupt
    # Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = ThreadInterrupt("Custom ThreadInterrupt")
        with pytest.raises(ThreadInterrupt) as ex:
            remote_watcher._handle_changes(False)
        assert str(ex.exconly()).startswith("nxdrive.exceptions.ThreadInterrupt")
    # Exception
    Feature.synchronization = True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._check_offline"
    ) as mock_offline, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.scan_remote"
    ) as mock_scan_remote:
        mock_offline.return_value = False
        mock_scan_remote.side_effect = Exception("Custom Exception")
        assert remote_watcher._handle_changes(False) is False


def test_call_and_measure_gcs(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    assert isinstance(remote_watcher._call_and_measure_gcs(), dict)


def test_get_changes(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    assert isinstance(remote_watcher._get_changes(), dict)
    # not isinstance(summary, dict)
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._call_and_measure_gcs"
    ) as mock_measure_gc:
        mock_measure_gc.return_value = []
        assert remote_watcher._get_changes() is None
    # root_defs is None
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._call_and_measure_gcs"
    ) as mock_measure_gc:
        mock_measure_gc.return_value = {"activeSynchronizationRootDefinitions": None}
        assert remote_watcher._get_changes() is None


def test_force_remote_scan(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    remote_watcher = RemoteWatcher(engine, dao)
    cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
    mock_doc_pair = Mock_Doc_Pair(cursor, ())
    mock_remote_file_info = Mock_Remote_File_Info()
    # remote_path is None
    # force_recursion == True
    assert (
        remote_watcher._force_remote_scan(
            mock_doc_pair, mock_remote_file_info, remote_path=None, force_recursion=True
        )
        is None
    )
    # remote_path is not None
    # force_recursion == False
    assert (
        remote_watcher._force_remote_scan(
            mock_doc_pair,
            mock_remote_file_info,
            remote_path="remote_path",
            force_recursion=False,
        )
        is None
    )


def test_update_remote_states(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao
    # not summary
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary:
        mock_summary.return_value = None
        assert remote_watcher._update_remote_states() is None
    # summary..get("hasTooManyChanges") == True
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary:
        mock_summary.return_value = {"hasTooManyChanges": True}
        assert remote_watcher._update_remote_states() is None
    # not summary.get("fileSystemChanges")
    remote_watcher = RemoteWatcher(engine, dao)
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary:
        mock_summary.return_value = {"fileSystemChanges": False}
        assert remote_watcher._update_remote_states() is None
    # "fileSystemChanges" == True
    # fs_item is not None and new_info is not None
    mock_dao = Mock_DAO()
    mock_remote = Mock_Remote()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    remote_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.objects.RemoteFileInfo.from_dict"
    ) as mock_from_dict, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.filtered"
    ) as mock_filtered:
        mock_summary.return_value = {
            "fileSystemChanges": [
                {"eventDate": 30, "fileSystemItem": {"digest": "notInBinaryStore"}},
                {
                    "eventDate": 20,
                    "eventId": "deleted",
                    "fileSystemItem": {"digest": "md5"},
                    "fileSystemItemId": 2,
                },
                {
                    "eventDate": 10,
                    "eventId": "deleted",
                    "fileSystemItem": {"digest": "md5"},
                    "fileSystemItemId": 1,
                },
            ]
        }
        mock_interact.return_value = None
        mock_from_dict.return_value = "data"
        mock_filtered.side_effect = [True, False]
        assert remote_watcher._update_remote_states() is None
    # "fileSystemChanges" == True
    # fs_item is None
    # doc_pair.last_error == "DEDUP"
    mock_dao = Mock_DAO()
    mock_remote = Mock_Remote()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    remote_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.objects.RemoteFileInfo.from_dict"
    ) as mock_from_dict, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.filtered"
    ) as mock_filtered, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_void_transfers:
        mock_summary.return_value = {
            "fileSystemChanges": [
                {"eventDate": 30, "fileSystemItem": {"digest": "notInBinaryStore"}},
                {
                    "eventDate": 20,
                    "eventId": "deleted",
                    "fileSystemItemId": 2,
                },
                {
                    "eventDate": 10,
                    "eventId": "deleted",
                    "fileSystemItemId": 1,
                },
            ]
        }
        mock_interact.return_value = None
        mock_from_dict.return_value = "data"
        mock_filtered.side_effect = [True, False]
        mock_void_transfers.return_value = None
        assert remote_watcher._update_remote_states() is None
    # "fileSystemChanges" == True
    # fs_item is None
    # doc_pair.last_error != "DEDUP"
    mock_dao = Mock_DAO()
    mock_dao.last_error = "dummy_last_error"
    mock_remote = Mock_Remote()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    remote_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.objects.RemoteFileInfo.from_dict"
    ) as mock_from_dict, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.filtered"
    ) as mock_filtered, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_void_transfers:
        mock_summary.return_value = {
            "fileSystemChanges": [
                {"eventDate": 30, "fileSystemItem": {"digest": "notInBinaryStore"}},
                {
                    "eventDate": 20,
                    "eventId": "deleted",
                    "fileSystemItemId": 2,
                },
                {
                    "eventDate": 10,
                    "eventId": "deleted",
                    "fileSystemItemId": 1,
                },
            ]
        }
        mock_interact.return_value = None
        mock_from_dict.return_value = "data"
        mock_filtered.side_effect = [True, False]
        mock_void_transfers.return_value = None
        assert remote_watcher._update_remote_states() is None
    # "fileSystemChanges" == True
    # fs_item is None
    # doc_pair.last_error != "DEDUP"
    mock_dao = Mock_DAO()
    mock_remote = Mock_Remote()
    remote_watcher = RemoteWatcher(engine, dao)
    remote_watcher.engine.remote = mock_remote
    remote_watcher.dao = mock_dao
    with patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._get_changes"
    ) as mock_summary, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher._interact"
    ) as mock_interact, patch(
        "nxdrive.objects.RemoteFileInfo.from_dict"
    ) as mock_from_dict, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.filtered"
    ) as mock_filtered, patch(
        "nxdrive.engine.watcher.remote_watcher.RemoteWatcher.remove_void_transfers"
    ) as mock_void_transfers:
        mock_summary.return_value = {
            "fileSystemChanges": [
                {"eventDate": 40, "fileSystemItem": {"digest": "notInBinaryStore"}},
                {
                    "eventDate": 30,
                    "eventId": "deleted",
                    "fileSystemItemId": "item3",
                },
                {
                    "eventDate": 20,
                    "eventId": "securityUpdated",
                    "fileSystemItemId": "item2",
                },
                {
                    "eventDate": 10,
                    "eventId": "securityUpdated",
                    "fileSystemItemId": "item1",
                },
            ]
        }
        mock_interact.return_value = None
        mock_from_dict.return_value = "data"
        mock_filtered.side_effect = [True, True, False]
        mock_void_transfers.return_value = None
        assert remote_watcher._update_remote_states() is None


def test_sync_root_name(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao

    docpair = namedtuple(
        "DocPair",
        "local_path, local_parent_path, remote_ref, local_state, \
            remote_state, pair_state, last_error, remote_parent_path",
        defaults=(
            ".",
            ".",
            "org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#",
            "synchronized",
            "synchronized",
            "synchronized",
            None,
            "",
        ),
    )

    remote_path = "/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#"

    test_watcher = RemoteWatcher(engine, dao)

    def get_changes():
        return eval(
            '{ "type": "test", "fileSystemChanges": [ { "repositoryId": "default", \
                "eventId": "securityUpdated", "eventDate": 1681875648592, "docUuid": \
                    "a7e4ce2a-e4a7-432a-b5e1-62b354606929", "fileSystemItem": {"id": \
                        "defaultSyncRootFolderItemFactory#default#a7e4ce2a-e4a7-432a-\
                        b5e1-62b354606929-test", "parentId": "org.nuxeo.drive.service.\
                            impl.DefaultTopLevelFolderItemFactory#", "name": "ROY", \
                            "folder": True, "creator": "Administrator", \
                                "lastContributor": "Administrator", \
                                    "creationDate": 1681875486061, \
                                        "lastModificationDate": 1681875528408, \
                                            "canRename": True, "canDelete": True, \
                                                "lockInfo": None, "path": "/org.nuxeo.\
                                                    drive.service.impl.DefaultTopLevelFolder\
                                                        ItemFactory#/defaultSyncRootFolderItemFactory\
                                                        #default#a7e4ce2a-e4a7-432a-b5e1-62b354606929-test",\
                                                         "userName": "Administrator", "canCreateChild": True,\
                                                              "canScrollDescendants": True }, "fileSystemItemId": \
                                                                "defaultSyncRootFolderItemFactory#default#a7e4ce2a-\
                                                                e4a7-432a-b5e1-62b354606929-test", \
                                                                    "fileSystemItemName": "ROY" } ]\
                                                                    , "syncDate": 1681875652000, "upp\
                                                                        erBound": 7834,\
                                                                          "hasTooManyChanges": True, \
                                                                            "activeSynchronizationRootDe\
                                                                            finitions": "default:ffed6ec7-\
                                                                                b6d3-41a7-ba10-801b7678a5\
                                                                                84-test,default:a7e4ce2a-e4a7-432a-b5e1-62b35460692\
                                                                                    9-test,default:db4e8005-c7aa-4f26-937b-23476e85\
                                                                                        2223-test,default:47176834-992d-4d81-9ce1-a\
                                                                                            51b7841d648-test" }'
        )

    def init_scan_remote(doc_pair, remote_info):
        return remote_path

    def get_children(arg):
        return []

    def get_states_from_remote_(path):
        return [docpair]

    def update_remote_state_(*args, **kwargs):
        return False

    def unset_unsychronised_(*args):
        return

    def _force_remote_scan_(*args, **kwargs):
        return

    def get_state_from_id_(*args):
        return None

    def _find_remote_child_match_or_create_(parent_pair, new_info):
        assert "test" in new_info.id
        return None

    update_remote_states = test_watcher._update_remote_states

    scan_remote = test_watcher._scan_remote_recursive

    with patch.object(test_watcher, "_get_changes", new=get_changes):
        info = update_remote_states

    assert info is not None

    remote_info = RemoteFileInfo.from_dict(
        eval(
            '{"id": "defaultSyncRootFolderItemFactory#default\
                                                #a7e4ce2a-e4a7-432a-b5e1-62b354606929-test",\
                                                "parentId": "org.nuxeo.drive.service.impl.\
                                                DefaultTopLevelFolderItemFactory#",\
                                                "name": "ROY",\
                                                "folder": True,\
                                                "creator": "Administrator",\
                                                "lastContributor": "Administrator",\
                                                "creationDate": 1681875486061,\
                                                "lastModificationDate": 1681875528408,\
                                                "canRename": True,\
                                                "canDelete": True,\
                                                "lockInfo": None,\
                                                "path": "/org.nuxeo.drive.service.\
                                                impl.DefaultTopLevelFolderItemFactory\
                                                #/defaultSyncRootFolderItemFactory#default\
                                                #a7e4ce2a-e4a7-432a-b5e1-62b354606929-test",\
                                                "userName": "Administrator",\
                                                 "canCreateChild": True,\
                                                "canScrollDescendants": True\
                                                }'
        )
    )

    def get_fs_children_(*args):
        return [remote_info]

    def interact():
        return

    def do_scan_remote(*args, **kwargs):
        return

    def add_scanned(path):
        assert path == remote_path

    def find_remote_child_match_or_create(*args):
        return (
            namedtuple(
                "DocPair",
                "local_path, local_parent_path, remote_ref, local_state, remote_state, pair_state, last_error",
                defaults=(
                    ".",
                    ".",
                    "org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#",
                    "synchronized",
                    "synchronized",
                    "synchronized",
                    None,
                ),
            ),
            True,
        )

    with patch.object(test_watcher, "_init_scan_remote", new=init_scan_remote):
        with patch.object(test_watcher, "_interact", new=interact):
            with patch.object(
                test_watcher,
                "_find_remote_child_match_or_create",
                new=find_remote_child_match_or_create,
            ):
                with patch.object(test_watcher, "_do_scan_remote", new=do_scan_remote):
                    with patch.object(dao, "add_path_scanned", new=add_scanned):
                        with patch.object(dao, "get_remote_children", new=get_children):
                            with patch.object(
                                engine.remote, "get_fs_children", new=get_fs_children_
                            ):
                                scan_remote(docpair, remote_info)

    with patch.object(test_watcher, "_get_changes", new=get_changes):
        with patch.object(test_watcher, "_force_remote_scan", new=_force_remote_scan_):
            with patch.object(
                test_watcher,
                "_find_remote_child_match_or_create",
                new=_find_remote_child_match_or_create_,
            ):
                with patch.object(
                    dao, "get_states_from_remote", new=get_states_from_remote_
                ):
                    with patch.object(
                        dao, "update_remote_state", new=update_remote_state_
                    ):
                        with patch.object(
                            dao, "unset_unsychronised", new=unset_unsychronised_
                        ):
                            with patch.object(
                                dao, "get_state_from_id", new=get_state_from_id_
                            ):
                                update_remote_states
