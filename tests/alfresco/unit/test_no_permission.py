#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Changes the server refuses for lack of permission (HTTP 403).

The QA log showed an upload into a folder the user may not write to being
retried every 60 seconds forever as an "Unhandled error". Drive now reads the
user's permissions from the server, lists a refused change in the Errors with
a clear reason, and retries it every 10 minutes from the skipped files.
"""

import json
from pathlib import Path
from threading import RLock
from unittest.mock import MagicMock, Mock, patch

import pytest
from alfresco.exceptions import AuthenticationError, ForbiddenError, NetworkError
from alfresco.models.node import Node

from nxdrive.alfresco.client.remote import NODE_FIELDS, AlfrescoRemote, _permissions
from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.alfresco.engine.skipped_files import (
    CONF_SKIPPED_FILES,
    NO_PERMISSION_ERROR,
    SKIPPED_FILE_RETRY_INTERVAL,
    add_skipped_file,
    load_skipped_files,
    remove_skipped_files,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import AlfrescoRemoteWatcher
from nxdrive.drive.exceptions import NotFound, ThreadInterrupt


def _config_dao():
    """A MagicMock DAO whose configuration really persists."""
    dao = MagicMock()
    store = {}
    dao.lock = RLock()
    dao.get_config.side_effect = lambda key, default=None: store.get(key) or default
    dao.update_config.side_effect = lambda key, value: store.__setitem__(key, value)
    dao.store = store
    return dao


# -- Reading permissions from the server --------------------------------------


def _node(ops=None, *, folder=True):
    entry = {"id": "n", "name": "N", "isFolder": folder, "isFile": not folder}
    if ops is not None:
        entry["allowableOperations"] = ops
    return Node.from_json({"entry": entry})


class TestPermissions:
    def test_the_node_fetches_ask_for_them(self):
        assert "allowableOperations" in NODE_FIELDS

    def test_read_only_folder(self):
        assert _permissions(_node([], folder=True)) == {
            "can_rename": False,
            "can_delete": False,
            "can_update": False,
            "can_create_child": False,
        }

    def test_writable_folder(self):
        perms = _permissions(_node(["create", "update", "delete"], folder=True))
        assert perms["can_create_child"] is True
        assert perms["can_update"] is False  # Folders have no content.
        assert perms["can_rename"] is True
        assert perms["can_delete"] is True

    def test_writable_file(self):
        perms = _permissions(_node(["update", "delete"], folder=False))
        assert perms["can_update"] is True
        assert perms["can_create_child"] is False

    def test_unknown_means_allowed_as_before(self):
        """The 403 handling remains the safety net."""
        assert _permissions(_node(None, folder=True)) == {
            "can_rename": True,
            "can_delete": True,
            "can_update": False,
            "can_create_child": True,
        }

    def test_mapped_into_the_remote_file_info(self):
        info = AlfrescoRemote._node_to_remote_file_info(_node([], folder=True))
        assert info.can_create_child is False


class TestLoginAndPermissionErrorsAreNotNotFound:
    """Disguised as NotFound, they dropped the change as "no longer exists"."""

    def _remote(self, error):
        remote = AlfrescoRemote.__new__(AlfrescoRemote)
        remote.server_url = "http://repo/"
        remote.client = MagicMock()
        remote.client.nodes.get.side_effect = error
        return remote

    @pytest.mark.parametrize("error", [ForbiddenError("no"), AuthenticationError("x")])
    def test_get_fs_info_lets_them_through(self, error):
        with pytest.raises(type(error)):
            self._remote(error).get_fs_info("node")

    @pytest.mark.parametrize("error", [ForbiddenError("no"), AuthenticationError("x")])
    def test_get_info_lets_them_through(self, error):
        with pytest.raises(type(error)):
            self._remote(error).get_info("node")

    def test_other_errors_are_still_not_found(self):
        with pytest.raises(NotFound):
            self._remote(NetworkError("down")).get_fs_info("node")


# -- The skipped files list -----------------------------------------------------


class TestSkippedFilesList:
    def test_add_load_remove(self):
        dao = _config_dao()

        add_skipped_file(dao, 3)
        add_skipped_file(dao, 1)
        add_skipped_file(dao, 3)
        assert load_skipped_files(dao) == {1, 3}
        assert dao.store[CONF_SKIPPED_FILES] == "[1, 3]"

        remove_skipped_files(dao, [3, 99])
        assert load_skipped_files(dao) == {1}

        remove_skipped_files(dao, [1])
        assert dao.store[CONF_SKIPPED_FILES] is None

    @pytest.mark.parametrize("raw", ["not json", '"7"', '{"a": 1}', '["x"]'])
    def test_unreadable_value_means_none(self, raw):
        dao = _config_dao()
        dao.store[CONF_SKIPPED_FILES] = raw

        assert load_skipped_files(dao) == set()

    def test_the_reason_is_translated(self):
        for folder in ("nxdrive/data/i18n", "nxdrive/drive/data/i18n"):
            labels = json.loads(
                (Path(__file__).parents[3] / folder / "i18n.json").read_text(
                    encoding="utf-8"
                )
            )
            assert "permission" in labels[f"ERROR_REASON_{NO_PERMISSION_ERROR}"]


# -- The processor ----------------------------------------------------------------


@pytest.fixture
def engine():
    engine = Mock()
    engine.uid = "qa-uid"
    engine.queue_manager.get_error_threshold = Mock(return_value=3)
    engine.dao = _config_dao()
    return engine


def _pair(row_id=8, *, last_error=None, error_count=0):
    pair = Mock()
    pair.id = row_id
    pair.local_name = "call-of-duty.jpg"
    pair.local_path = Path("Sites/Contracts/call-of-duty.jpg")
    pair.pair_state = "locally_created"
    pair.size = 0
    pair.last_error = last_error
    pair.error_count = error_count
    return pair


def _run(engine, pair, error):
    items = iter([pair])
    processor = AlfrescoProcessor(engine, lambda *_, **__: next(items, None))
    processor.dao = engine.dao
    processor._get_next_doc_pair = Mock(side_effect=lambda item: item)
    processor.check_pair_state = Mock(return_value=True)
    processor.remove_void_transfers = Mock()
    processor._handle_doc_pair_sync = Mock(side_effect=error)
    processor._synchronize_locally_created = Mock()
    processor._execute()
    return processor


FORBIDDEN = ForbiddenError("[HTTP 403] Access Denied.", status=403)


class TestForbiddenUpload:
    def test_listed_in_errors_with_its_reason_and_skipped(self, engine):
        pair = _pair()

        processor = _run(engine, pair, FORBIDDEN)

        engine.dao.increase_error.assert_called_once()
        args, kwargs = engine.dao.increase_error.call_args
        assert args == (pair, NO_PERMISSION_ERROR)
        assert "403" in kwargs["details"]
        assert kwargs["incr"] == 4  # Past the threshold: in the Errors list.
        engine.queue_manager.push_error.assert_called_once_with(pair)
        assert load_skipped_files(engine.dao) == {8}
        processor.remove_void_transfers.assert_called_once_with(pair)

    def test_no_traceback_and_no_unknown_error(self, engine):
        with patch("nxdrive.alfresco.engine.processor.log") as log:
            _run(engine, _pair(), FORBIDDEN)

        log.exception.assert_not_called()
        assert all(
            call.args[1] != "UNKNOWN"
            for call in engine.dao.increase_error.call_args_list
        )

    def test_a_refused_retry_keeps_it_listed_without_a_new_notification(self, engine):
        pair = _pair(last_error=NO_PERMISSION_ERROR, error_count=4)

        _run(engine, pair, FORBIDDEN)

        engine.dao.increase_error.assert_not_called()
        engine.queue_manager.push_error.assert_not_called()
        assert load_skipped_files(engine.dao) == {8}

    def test_a_manual_retry_notifies_again(self, engine):
        """ "Retry" in the Errors clears the error first."""
        _run(engine, _pair(last_error=None, error_count=0), FORBIDDEN)

        engine.queue_manager.push_error.assert_called_once()


class TestStorePermissions:
    def _processor(self, engine):
        processor = AlfrescoProcessor(engine, Mock(return_value=None))
        processor.dao = engine.dao
        return processor

    def test_fresh_permissions_are_recorded(self, engine):
        processor = self._processor(engine)
        pair = Mock(
            id=5,
            remote_can_rename=1,
            remote_can_delete=1,
            remote_can_update=1,
            remote_can_create_child=1,
        )
        info = Mock(
            can_rename=False, can_delete=False, can_update=False, can_create_child=False
        )

        processor._store_permissions(pair, info)

        engine.dao.update_remote_permissions.assert_called_once_with(5, info)
        assert pair.remote_can_create_child is False

    def test_unchanged_permissions_are_not_written(self, engine):
        processor = self._processor(engine)
        pair = Mock(
            id=5,
            remote_can_rename=1,
            remote_can_delete=1,
            remote_can_update=0,
            remote_can_create_child=1,
        )
        info = Mock(
            can_rename=True, can_delete=True, can_update=False, can_create_child=True
        )

        processor._store_permissions(pair, info)

        engine.dao.update_remote_permissions.assert_not_called()


# -- The remote watcher -------------------------------------------------------------


def _watcher():
    engine = MagicMock()
    dao = _config_dao()
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher(engine, dao)
    watcher.engine = engine
    watcher.dao = dao
    watcher._next_skipped_files_retry = 0.0
    return watcher


def _row(row_id, last_error=NO_PERMISSION_ERROR):
    return Mock(id=row_id, last_error=last_error, local_path=Path(f"f{row_id}"))


class TestRetrySkippedFiles:
    def test_listed_files_still_refused_are_queued_with_their_error(self):
        watcher = _watcher()
        add_skipped_file(watcher.dao, 1)
        add_skipped_file(watcher.dao, 2)
        rows = {1: _row(1), 2: _row(2, last_error=None)}  # 2 got synced since.
        watcher.dao.get_state_from_id.side_effect = rows.get
        watcher.dao.get_states_with_error.return_value = [rows[1]]

        watcher._retry_skipped_files()

        watcher.engine.queue_manager.push.assert_called_once_with(rows[1])
        # Kept in the Errors: the error is not cleared for an automatic retry.
        watcher.dao.reset_error.assert_not_called()
        # The processor re-adds it if refused again.
        assert load_skipped_files(watcher.dao) == set()

    def test_a_refusal_during_the_retry_is_kept_on_the_list(self):
        watcher = _watcher()
        add_skipped_file(watcher.dao, 1)
        watcher.dao.get_state_from_id.return_value = _row(1)
        watcher.dao.get_states_with_error.return_value = []
        watcher.engine.queue_manager.push.side_effect = lambda _: add_skipped_file(
            watcher.dao, 1
        )

        watcher._retry_skipped_files()

        assert load_skipped_files(watcher.dao) == {1}

    def test_an_error_missing_from_the_list_is_retried_too(self):
        watcher = _watcher()
        row = _row(4)
        watcher.dao.get_state_from_id.return_value = row
        watcher.dao.get_states_with_error.return_value = [row]

        watcher._retry_skipped_files()

        watcher.dao.get_states_with_error.assert_called_once_with(NO_PERMISSION_ERROR)
        watcher.engine.queue_manager.push.assert_called_once_with(row)

    def test_runs_at_most_once_per_interval(self):
        watcher = _watcher()
        watcher.dao.get_states_with_error.return_value = []

        with patch(
            "nxdrive.alfresco.engine.watcher.remote_watcher.monotonic",
            return_value=1000.0,
        ):
            watcher._retry_skipped_files()
            watcher._retry_skipped_files()

        assert watcher.dao.get_states_with_error.call_count == 1
        assert watcher._next_skipped_files_retry == 1000.0 + SKIPPED_FILE_RETRY_INTERVAL


class TestChangeFeedKeepsPermissions:
    def _info(self):
        return AlfrescoRemote._change_to_remote_file_info(
            Mock(
                node_id="n",
                name="N",
                path="/N",
                parent_id="p",
                is_folder=True,
                modified_at=None,
                is_locked=False,
            )
        )

    def test_stored_permissions_win_over_the_feed_defaults(self):
        pair = Mock(
            remote_can_rename=0,
            remote_can_delete=0,
            remote_can_update=0,
            remote_can_create_child=0,
        )

        info = AlfrescoRemoteWatcher._keep_stored_permissions(self._info(), pair)

        assert info.can_create_child is False
        assert info.can_rename is False

    def test_rows_without_stored_permissions_keep_the_feed_values(self):
        pair = Mock(
            remote_can_rename=None,
            remote_can_delete=None,
            remote_can_update=None,
            remote_can_create_child=None,
        )

        info = AlfrescoRemoteWatcher._keep_stored_permissions(self._info(), pair)

        assert info.can_create_child is True


def test_a_stop_request_is_not_taken_for_a_refusal(engine):
    with pytest.raises(ThreadInterrupt):
        _run(engine, _pair(), ThreadInterrupt())

    engine.dao.increase_error.assert_not_called()
