#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""What keeps the first pass (and so new local files) waiting, and how it ends.

Covers skipping folders that cannot be listed, retrying them later, and
telling the user why new local files are held back.
"""

import json
from pathlib import Path
from threading import Lock, RLock
from unittest.mock import MagicMock, Mock, call, patch

import pytest
from alfresco.exceptions import AlfrescoError
from alfresco.exceptions import AuthenticationError as AlfrescoAuthError
from alfresco.exceptions import ForbiddenError
from alfresco.exceptions import NetworkError as AlfrescoNetworkError
from alfresco.exceptions import NotFoundError, ServerError

from nxdrive.alfresco.client.device_sync import (
    CONF_BOOTSTRAPPED_FOR,
    DeviceSyncProvisioner,
)
from nxdrive.alfresco.engine.pending_unfiltered import (
    CONF_PENDING_UNFILTERED,
    add_pending_unfiltered,
    load_pending_unfiltered,
    remove_pending_unfiltered,
    snapshot_pending_unfiltered,
)
from nxdrive.alfresco.engine.processor import AlfrescoProcessor
from nxdrive.alfresco.engine.skipped_folders import (
    CONF_SKIPPED_FOLDERS,
    HELD_UNDER_SKIPPED_FOLDER,
    LISTING_FAILED_ERROR,
    find_blocking_skipped_folder,
    find_skipped_ancestor,
    is_under,
    load_skipped_folders,
    save_skipped_folders,
    skipped_folder_pairs,
    skipped_folder_rows,
)
from nxdrive.alfresco.engine.watcher.remote_watcher import (
    FIRST_PASS_NETWORK,
    FIRST_PASS_NOTIFY_AFTER,
    FIRST_PASS_SCAN,
    FIRST_PASS_SERVER,
    FIRST_PASS_UNAVAILABLE,
    MAX_LISTING_FAILURES,
    AlfrescoRemoteWatcher,
)
from nxdrive.drive.constants import ROOT
from nxdrive.drive.notification import (
    DefaultNotificationService,
    FirstPassPendingNotification,
    Notification,
    NotificationService,
)
from nxdrive.drive.objects import RemoteFileInfo


def _watcher():
    engine = MagicMock()
    dao = MagicMock()
    dao.get_config.return_value = None
    dao.is_path_scanned.return_value = False
    dao.get_paths_to_scan.return_value = []
    dao.get_remote_children.return_value = []
    with patch.object(AlfrescoRemoteWatcher, "__init__", return_value=None):
        watcher = AlfrescoRemoteWatcher(engine, dao)
    watcher.engine = engine
    watcher.dao = dao
    watcher._interact = MagicMock()
    watcher._listing_failures = {}
    watcher._skipped_folders = set()
    watcher._next_skipped_retry = 0.0
    watcher._failure_reason = ""
    watcher._first_pass_failures = 0
    watcher._first_pass_notice = ""
    watcher._is_filtered_path = MagicMock(return_value=False)
    return watcher


def _folder(uid="folder-1", name="Folder"):
    info = MagicMock(spec=RemoteFileInfo)
    info.uid = uid
    info.name = name
    info.folderish = True
    info.path = f"/Company Home/{name}"
    return info


def _pair(*, root=False, last_error=None):
    pair = MagicMock()
    pair.local_path = ROOT if root else MagicMock()
    pair.remote_parent_path = ""
    pair.remote_ref = "folder-1"
    pair.last_error = last_error
    pair.folderish = True
    pair.pair_state = "synchronized"
    pair.remote_state = "synchronized"
    return pair


def _list_fails_with(watcher, exc):
    watcher.engine.remote.client.nodes.iter_children.side_effect = exc


# -- Listing a folder ---------------------------------------------------------


class TestListChildren:
    def test_missing_folder_has_no_children(self):
        watcher = _watcher()
        _list_fails_with(watcher, NotFoundError("gone"))

        assert watcher._list_children(watcher.engine.remote, _folder()) == []

    def test_other_errors_are_raised_for_the_caller_to_count(self):
        watcher = _watcher()
        _list_fails_with(watcher, ForbiddenError("no"))

        with pytest.raises(ForbiddenError):
            watcher._list_children(watcher.engine.remote, _folder())

    def test_network_give_up_is_reported_as_a_network_problem(self):
        watcher = _watcher()
        _list_fails_with(watcher, AlfrescoNetworkError("down"))

        with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"):
            assert watcher._list_children(watcher.engine.remote, _folder()) is None

        assert watcher._failure_reason == FIRST_PASS_NETWORK


# -- Skipping folders that cannot be listed -----------------------------------


class TestSkipUnreadableFolder:
    def test_forbidden_folder_is_skipped_at_once(self):
        watcher = _watcher()
        _list_fails_with(watcher, ForbiddenError("no"))
        pair = _pair()
        watcher.dao.get_remote_children.return_value = [MagicMock(remote_ref="kid")]

        assert watcher._scan_remote_recursive(pair, _folder()) is True

        # Counted as walked so the seed can complete ...
        watcher.dao.add_path_scanned.assert_called_once_with("folder-1")
        watcher.dao.add_path_to_scan.assert_not_called()
        # ... without treating its known content as deleted on the server.
        watcher.dao.delete_remote_state.assert_not_called()
        # ... listed for the user, and remembered for a later retry.
        watcher.dao.increase_error.assert_called_once()
        assert watcher.dao.increase_error.call_args.args[1] == LISTING_FAILED_ERROR
        watcher.engine.queue_manager.push_error.assert_called_once_with(pair)
        assert watcher._skipped_folders == {"folder-1"}
        watcher.dao.update_config.assert_called_with(
            CONF_SKIPPED_FOLDERS, json.dumps(["folder-1"])
        )

    def test_other_errors_are_retried_for_a_few_cycles_first(self):
        watcher = _watcher()
        _list_fails_with(watcher, ServerError("500"))
        pair = _pair()

        for _ in range(MAX_LISTING_FAILURES - 1):
            assert watcher._scan_remote_recursive(pair, _folder()) is False
        watcher.dao.increase_error.assert_not_called()
        assert watcher.dao.add_path_to_scan.call_count == MAX_LISTING_FAILURES - 1

        assert watcher._scan_remote_recursive(pair, _folder()) is True
        assert watcher._skipped_folders == {"folder-1"}
        assert "folder-1" not in watcher._listing_failures

    def test_network_failures_never_skip_a_folder(self):
        """An outage would otherwise skip whole parts of the tree."""
        watcher = _watcher()
        _list_fails_with(watcher, AlfrescoNetworkError("down"))

        with patch("nxdrive.alfresco.engine.watcher.remote_watcher.sleep"):
            for _ in range(MAX_LISTING_FAILURES + 1):
                assert watcher._scan_remote_recursive(_pair(), _folder()) is False

        assert not watcher._skipped_folders
        assert not watcher._listing_failures

    def test_the_sync_root_is_never_skipped(self):
        watcher = _watcher()
        _list_fails_with(watcher, ForbiddenError("no"))

        for _ in range(MAX_LISTING_FAILURES + 1):
            assert watcher._scan_remote_recursive(_pair(root=True), _folder()) is False

        assert not watcher._skipped_folders
        watcher.dao.increase_error.assert_not_called()

    def test_auth_errors_still_propagate(self):
        watcher = _watcher()
        _list_fails_with(watcher, AlfrescoAuthError("expired"))

        with pytest.raises(AlfrescoAuthError):
            watcher._scan_remote_recursive(_pair(), _folder())

    def test_error_is_reported_only_once(self):
        watcher = _watcher()
        _list_fails_with(watcher, ForbiddenError("no"))

        watcher._scan_remote_recursive(
            _pair(last_error=LISTING_FAILED_ERROR), _folder()
        )

        watcher.dao.increase_error.assert_not_called()

    def test_a_readable_folder_is_forgotten_and_its_error_cleared(self):
        watcher = _watcher()
        watcher._skipped_folders = {"folder-1"}
        watcher._listing_failures = {"folder-1": 2}
        watcher.engine.remote.client.nodes.iter_children.return_value = []
        pair = _pair(last_error=LISTING_FAILED_ERROR)

        assert watcher._scan_remote_recursive(pair, _folder()) is True

        assert not watcher._skipped_folders
        assert not watcher._listing_failures
        watcher.dao.reset_error.assert_called_once_with(pair)
        watcher.dao.update_config.assert_called_with(CONF_SKIPPED_FOLDERS, None)


class TestSkippedFoldersPersistence:
    def test_loaded_from_the_database(self):
        watcher = _watcher()
        watcher.dao.get_config.return_value = json.dumps(["a", "b"])

        assert watcher._load_skipped_folders() == {"a", "b"}

    @pytest.mark.parametrize("raw", [None, "", "not json", "42"])
    def test_unreadable_or_missing_value_means_none(self, raw):
        watcher = _watcher()
        watcher.dao.get_config.return_value = raw

        assert watcher._load_skipped_folders() == set()


class TestRetrySkippedFolders:
    def _ready(self, watcher):
        watcher._skipped_folders = {"folder-1"}
        pair = _pair(last_error=LISTING_FAILED_ERROR)
        watcher.dao.get_states_from_remote.return_value = [pair]
        watcher.engine.remote._node_to_remote_file_info.return_value = _folder()
        return pair

    def test_nothing_to_do_without_skipped_folders(self):
        watcher = _watcher()

        watcher._retry_skipped_folders()

        watcher.engine.remote.get_node.assert_not_called()

    def test_runs_at_most_once_per_interval(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher.engine.remote.client.nodes.iter_children.side_effect = ServerError("x")

        watcher._retry_skipped_folders()
        watcher._retry_skipped_folders()

        watcher.engine.remote.get_node.assert_called_once()

    def test_readable_again_is_walked_and_forgotten(self):
        watcher = _watcher()
        pair = self._ready(watcher)
        watcher.engine.remote.client.nodes.iter_children.return_value = []

        watcher._retry_skipped_folders()

        assert not watcher._skipped_folders
        watcher.dao.reset_error.assert_called_once_with(pair)

    def test_still_failing_stays_skipped_without_a_new_error(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher.engine.remote.client.nodes.iter_children.side_effect = ServerError("x")

        watcher._retry_skipped_folders()

        assert watcher._skipped_folders == {"folder-1"}
        watcher.dao.increase_error.assert_not_called()

    def test_deleted_on_the_server_is_forgotten(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher.engine.remote.get_node.side_effect = NotFoundError("gone")

        watcher._retry_skipped_folders()

        assert not watcher._skipped_folders

    def test_no_longer_synced_is_forgotten(self):
        watcher = _watcher()
        watcher._skipped_folders = {"folder-1"}
        watcher.dao.get_states_from_remote.return_value = []

        watcher._retry_skipped_folders()

        assert not watcher._skipped_folders
        watcher.engine.remote.get_node.assert_not_called()

    def test_now_filtered_is_forgotten(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher._is_filtered_path.return_value = True

        watcher._retry_skipped_folders()

        assert not watcher._skipped_folders
        watcher.engine.remote.client.nodes.iter_children.assert_not_called()

    def test_unexpected_errors_are_absorbed(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher.engine.remote.get_node.side_effect = RuntimeError("boom")

        watcher._retry_skipped_folders()

        assert watcher._skipped_folders == {"folder-1"}

    def test_auth_errors_propagate(self):
        watcher = _watcher()
        self._ready(watcher)
        watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")

        with pytest.raises(AlfrescoAuthError):
            watcher._retry_skipped_folders()


# -- Telling the user ----------------------------------------------------------


def _polling_watcher():
    watcher = _watcher()
    watcher.engine.queue_manager.get_overall_size.return_value = 0
    watcher.updated = MagicMock()
    watcher.initiate = MagicMock()
    watcher.empty_polls = 0
    watcher.first_pass_done = False
    watcher._provisioner = MagicMock(provisioned=True)
    watcher._bootstrap_if_needed = MagicMock(return_value=True)
    watcher._apply_unfiltered = MagicMock()
    watcher._retry_skipped_folders = MagicMock()
    watcher._poll_device_sync = MagicMock(return_value=True)
    watcher._scan_local_changes = MagicMock()
    watcher._sweep_lock_conflicts = MagicMock()
    return watcher


def _fail_first_passes(watcher, times):
    for _ in range(times):
        watcher._handle_changes(first_pass=True)


class TestFailureReason:
    def test_incomplete_seed(self):
        watcher = _polling_watcher()
        watcher._bootstrap_if_needed.return_value = False

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == FIRST_PASS_SCAN

    def test_undrained_feed(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == FIRST_PASS_SERVER

    def test_network_error_while_polling(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = AlfrescoNetworkError("down")

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == FIRST_PASS_NETWORK

    def test_other_error_while_polling(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = RuntimeError("boom")

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == FIRST_PASS_SERVER

    def test_auth_error_has_no_reason(self):
        """It has its own notification."""
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = AlfrescoAuthError("expired")

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == ""

    @pytest.mark.parametrize(
        "amp_missing, network_error, expected",
        [
            (True, False, FIRST_PASS_UNAVAILABLE),
            (False, True, FIRST_PASS_NETWORK),
            (False, False, FIRST_PASS_SERVER),
        ],
    )
    def test_provisioning_failure(self, amp_missing, network_error, expected):
        watcher = _polling_watcher()
        watcher._provisioner = MagicMock(
            provisioned=False, amp_missing=amp_missing, network_error=network_error
        )
        watcher._provisioner.provision.return_value = False
        watcher.dao.get_state_from_local.return_value = MagicMock(remote_ref="root")

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == expected

    def test_waiting_for_folder_selection_has_no_reason(self):
        watcher = _polling_watcher()
        watcher._provisioner = None
        watcher.dao.get_state_from_local.return_value = None

        watcher._handle_changes(first_pass=True)

        assert watcher._failure_reason == ""


class TestFirstPassNotice:
    def test_not_shown_for_a_single_failure(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False

        _fail_first_passes(watcher, FIRST_PASS_NOTIFY_AFTER - 1)

        watcher.engine.firstPassBlocked.emit.assert_not_called()

    def test_shown_once_failures_repeat(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False

        _fail_first_passes(watcher, FIRST_PASS_NOTIFY_AFTER + 2)

        watcher.engine.firstPassBlocked.emit.assert_called_once_with(FIRST_PASS_SERVER)

    def test_updated_when_the_reason_changes(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False
        _fail_first_passes(watcher, FIRST_PASS_NOTIFY_AFTER)

        watcher._poll_device_sync.side_effect = AlfrescoNetworkError("down")
        watcher._handle_changes(first_pass=True)

        assert watcher.engine.firstPassBlocked.emit.call_args_list[-1].args == (
            FIRST_PASS_NETWORK,
        )

    def test_cleared_when_the_first_pass_completes(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False
        _fail_first_passes(watcher, FIRST_PASS_NOTIFY_AFTER)

        watcher._poll_device_sync.return_value = True
        watcher._handle_changes(first_pass=True)

        watcher.engine.firstPassCompleted.emit.assert_called_once()
        assert watcher._first_pass_notice == ""
        assert watcher._first_pass_failures == 0

    def test_nothing_to_clear_when_nothing_was_shown(self):
        watcher = _polling_watcher()

        watcher._handle_changes(first_pass=True)

        watcher.engine.firstPassCompleted.emit.assert_not_called()

    def test_later_passes_never_notify(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.return_value = False

        for _ in range(FIRST_PASS_NOTIFY_AFTER + 1):
            watcher._handle_changes(first_pass=False)

        watcher.engine.firstPassBlocked.emit.assert_not_called()

    def test_auth_failures_never_notify(self):
        watcher = _polling_watcher()
        watcher._poll_device_sync.side_effect = AlfrescoAuthError("expired")

        _fail_first_passes(watcher, FIRST_PASS_NOTIFY_AFTER + 1)

        watcher.engine.firstPassBlocked.emit.assert_not_called()


# -- Device Sync probe -----------------------------------------------------------


def _provisioner():
    dao = MagicMock()
    dao.get_config.return_value = None
    return DeviceSyncProvisioner(MagicMock(), dao, device_os="macos")


class TestProbeOutcome:
    def test_amp_missing(self):
        prov = _provisioner()
        prov.remote.device_sync_available.return_value = False

        assert prov.provision("root") is False
        assert prov.amp_missing is True
        assert prov.network_error is False

    def test_network_error(self):
        prov = _provisioner()
        prov.remote.device_sync_available.side_effect = AlfrescoNetworkError("down")

        assert prov.provision("root") is False
        assert prov.network_error is True
        assert prov.amp_missing is False

    def test_other_transport_error(self):
        prov = _provisioner()
        prov.remote.device_sync_available.side_effect = AlfrescoError("500")

        assert prov.provision("root") is False
        assert prov.network_error is False
        assert prov.amp_missing is False

    def test_reset_on_every_attempt(self):
        prov = _provisioner()
        prov.remote.device_sync_available.return_value = False
        prov.provision("root")

        prov.remote.device_sync_available.side_effect = AlfrescoNetworkError("down")
        prov.provision("root")

        assert prov.amp_missing is False
        assert prov.network_error is True


# -- Notification ------------------------------------------------------------------


class TestFirstPassPendingNotification:
    @patch("nxdrive.drive.notification.Translator")
    def test_content(self, mock_translator):
        mock_translator.get.side_effect = lambda key: f"<{key}>"

        notif = FirstPassPendingNotification("eng1", FIRST_PASS_NETWORK)

        assert notif.uid == "FIRST_PASS_PENDING_eng1"
        assert notif.title == "<FIRST_PASS_PENDING>"
        assert notif.description == "<FIRST_PASS_PENDING_NETWORK>"
        assert notif.level == Notification.LEVEL_WARNING
        assert notif.is_unique()
        assert notif.is_systray()
        assert not notif.is_persistent()

    @pytest.mark.parametrize(
        "reason",
        [
            FIRST_PASS_UNAVAILABLE,
            FIRST_PASS_SERVER,
            FIRST_PASS_NETWORK,
            FIRST_PASS_SCAN,
        ],
    )
    def test_every_reason_is_translated(self, reason):
        i18n = Path(__file__).parents[3] / "nxdrive" / "drive" / "data" / "i18n"
        labels = json.loads((i18n / "i18n.json").read_text(encoding="utf-8"))
        assert f"FIRST_PASS_PENDING_{reason.upper()}" in labels
        assert "FIRST_PASS_PENDING" in labels
        assert f"ERROR_REASON_{LISTING_FAILED_ERROR}" in labels


class TestNotificationServiceFirstPass:
    @pytest.fixture
    def service(self):
        manager = Mock()
        manager.dao.get_notifications.return_value = []
        with patch.object(NotificationService, "__init__", lambda self, m: None):
            svc = DefaultNotificationService.__new__(DefaultNotificationService)
            svc._manager = manager
            svc._lock = Lock()
            svc._notifications = {}
            svc.dao = manager.dao
            svc.newNotification = Mock()
            svc.discardNotification = Mock()
            svc.triggerNotification = Mock()
        return svc

    @patch("nxdrive.drive.notification.Translator")
    def test_blocked_sends_the_notification(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock(uid="eng1")

        with patch.object(service, "sender", return_value=engine):
            service._firstPassBlocked(FIRST_PASS_SCAN)

        assert "FIRST_PASS_PENDING_eng1" in service._notifications

    @patch("nxdrive.drive.notification.Translator")
    def test_completed_discards_it(self, mock_translator, service):
        mock_translator.get.return_value = "translated"
        engine = Mock(uid="eng1")

        with patch.object(service, "sender", return_value=engine):
            service._firstPassBlocked(FIRST_PASS_SCAN)
            service._firstPassCompleted()

        assert "FIRST_PASS_PENDING_eng1" not in service._notifications
        service.discardNotification.emit.assert_called_once_with(
            "FIRST_PASS_PENDING_eng1"
        )

    def test_no_sender_is_ignored(self, service):
        with patch.object(service, "sender", return_value=None):
            service._firstPassBlocked(FIRST_PASS_SCAN)
            service._firstPassCompleted()

        service.newNotification.emit.assert_not_called()
        service.discardNotification.emit.assert_not_called()


# -- Holding local changes under skipped folders ----------------------------------


def _row(
    local_path,
    *,
    pair_state="locally_created",
    last_error=None,
    error_count=0,
    folderish=False,
    remote_state="synchronized",
):
    pair = MagicMock()
    pair.local_path = Path(local_path)
    pair.pair_state = pair_state
    pair.last_error = last_error
    pair.error_count = error_count
    pair.folderish = folderish
    pair.remote_state = remote_state
    return pair


def _dao_with_skipped(skipped_paths):
    """A DAO whose skipped folders are at *skipped_paths* (uid == path)."""
    dao = MagicMock()
    dao.get_config.side_effect = lambda key, **_: (
        json.dumps(sorted(skipped_paths)) if key == CONF_SKIPPED_FOLDERS else None
    )
    dao.get_states_from_remote.side_effect = lambda uid: (
        [_row(uid, pair_state="synchronized", folderish=True)]
        if uid in skipped_paths
        else []
    )
    return dao


class TestSkippedFolderHelpers:
    def test_save_and_load_round_trip(self):
        dao = MagicMock()
        save_skipped_folders(dao, {"b", "a"})
        dao.update_config.assert_called_once_with(
            CONF_SKIPPED_FOLDERS, json.dumps(["a", "b"])
        )
        dao.get_config.return_value = dao.update_config.call_args.args[1]
        assert load_skipped_folders(dao) == {"a", "b"}

    def test_saving_nothing_clears_the_key(self):
        dao = MagicMock()
        save_skipped_folders(dao, set())
        dao.update_config.assert_called_once_with(CONF_SKIPPED_FOLDERS, None)

    @pytest.mark.parametrize(
        "path, expected",
        [
            ("X", True),
            ("X/new.txt", True),
            ("X/sub/deep.txt", True),
            ("X2/new.txt", False),  # A sibling sharing the prefix is not inside.
            ("Y/new.txt", False),
            ("new.txt", False),
        ],
    )
    def test_is_under(self, path, expected):
        assert is_under(Path(path), Path("X")) is expected

    def test_find_skipped_ancestor(self):
        dao = _dao_with_skipped({"X"})

        assert find_skipped_ancestor(dao, Path("X/sub/new.txt")).local_path == Path("X")
        assert find_skipped_ancestor(dao, Path("Y/new.txt")) is None

    def test_skipped_folders_no_longer_synced_are_ignored(self):
        dao = _dao_with_skipped(set())
        dao.get_config.side_effect = None
        dao.get_config.return_value = json.dumps(["gone"])

        assert skipped_folder_pairs(dao) == []


def _processor(skipped_paths):
    engine = MagicMock()
    engine.queue_manager.get_error_threshold.return_value = 3
    proc = AlfrescoProcessor(engine, MagicMock(return_value=None))
    proc.dao = _dao_with_skipped(skipped_paths)
    return proc


class TestProcessorHold:
    @pytest.mark.parametrize(
        "pair_state",
        ["locally_created", "locally_modified", "locally_moved", "locally_deleted"],
    )
    def test_local_changes_under_a_skipped_folder_are_held(self, pair_state):
        proc = _processor({"X"})
        pair = _row("X/new.txt", pair_state=pair_state)

        assert proc._hold_under_skipped_folder(pair) is True

        proc.dao.increase_error.assert_called_once_with(
            pair, HELD_UNDER_SKIPPED_FOLDER, details="X", incr=4
        )
        # Kept out of the retry queue: only the watcher releases it.
        proc.engine.queue_manager.push_error.assert_not_called()

    def test_nothing_is_sent_to_the_server(self):
        proc = _processor({"X"})
        handler = MagicMock()

        proc._handle_doc_pair_sync(_row("X/new.txt"), handler)

        handler.assert_not_called()

    def test_server_changes_are_not_held(self):
        """Downloading into the folder cannot overwrite anything on the server."""
        proc = _processor({"X"})

        assert (
            proc._hold_under_skipped_folder(
                _row("X/doc.txt", pair_state="remotely_created")
            )
            is False
        )

    def test_other_folders_are_not_held(self):
        proc = _processor({"X"})

        assert proc._hold_under_skipped_folder(_row("Y/new.txt")) is False
        proc.dao.increase_error.assert_not_called()

    def test_already_held_is_not_counted_again(self):
        proc = _processor({"X"})
        pair = _row("X/new.txt", last_error=HELD_UNDER_SKIPPED_FOLDER, error_count=4)

        assert proc._hold_under_skipped_folder(pair) is True
        proc.dao.increase_error.assert_not_called()

    def test_no_skipped_folders(self):
        proc = _processor(set())

        assert proc._hold_under_skipped_folder(_row("X/new.txt")) is False


class TestReleaseHeldPairs:
    def _watcher(self, skipped, held):
        watcher = _watcher()
        watcher._skipped_folders = set(skipped)
        watcher.dao = _dao_with_skipped(set(skipped))
        watcher.dao.get_states_with_error.return_value = held
        return watcher

    def test_items_under_a_readable_folder_are_released(self):
        held = [_row("X/a.txt"), _row("X/sub/b.txt")]
        watcher = self._watcher(set(), held)

        watcher._release_held_pairs()

        watcher.dao.get_states_with_error.assert_called_once_with(
            HELD_UNDER_SKIPPED_FOLDER
        )
        assert watcher.dao.reset_error.call_count == 2

    def test_items_under_a_still_skipped_folder_stay_held(self):
        held_x, held_y = _row("X/a.txt"), _row("Y/b.txt")
        watcher = self._watcher({"X"}, [held_x, held_y])

        watcher._release_held_pairs()

        watcher.dao.reset_error.assert_called_once_with(held_y)

    def test_forgetting_a_folder_releases_its_items(self):
        held = _row("X/a.txt")
        watcher = self._watcher({"X"}, [held])

        watcher._forget_skipped("X", _row("X", pair_state="synchronized"))

        watcher.dao.reset_error.assert_called_with(held)

    def test_every_retry_interval_releases_left_over_items(self):
        """E.g. held just as its folder was released, or before a restart."""
        held = _row("X/a.txt")
        watcher = self._watcher(set(), [held])

        watcher._retry_skipped_folders()

        watcher.dao.reset_error.assert_called_once_with(held)

    def test_a_folder_that_still_fails_keeps_its_items_held(self):
        held = _row("X/a.txt")
        watcher = self._watcher({"X"}, [held])
        watcher.engine.remote._node_to_remote_file_info.return_value = _folder(uid="X")
        watcher.engine.remote.client.nodes.iter_children.side_effect = ServerError("x")

        watcher._retry_skipped_folders()

        assert watcher._skipped_folders == {"X"}
        watcher.dao.reset_error.assert_not_called()


# -- Restoring a folder after a cancelled local deletion -------------------------


class TestRestoredFolderOnTheWatcherThread:
    def _watcher(self):
        watcher = _watcher()
        watcher._unfiltered_nodes = set()
        watcher._unfiltered_needs_scan = False
        watcher._next_check = 0.0
        info = _folder(uid="node-1")
        info.parent_uid = "root-id"
        watcher.engine.remote._node_to_remote_file_info.return_value = info
        watcher.dao.get_state_from_local.return_value = MagicMock(
            remote_ref="root-id", remote_parent_path="", local_path=ROOT
        )
        restored = _row("X", pair_state="remotely_created")
        watcher.dao.get_normal_state_from_remote.return_value = restored
        watcher._reconcile_child = MagicMock(return_value=restored)
        watcher._scan_remote_recursive = MagicMock(return_value=True)
        return watcher, info, restored

    def test_queued_then_walked_on_the_next_cycle(self):
        watcher, info, restored = self._watcher()

        watcher.queue_unfiltered("X", ["node-1"])
        assert watcher._unfiltered_nodes == {"node-1"}
        assert watcher._next_check > 0  # Brought forward.

        watcher._apply_unfiltered()

        watcher._scan_remote_recursive.assert_called_once_with(
            restored, info, force=True
        )
        assert not watcher._unfiltered_nodes

    def test_a_partial_walk_is_retried_without_a_full_reseed(self):
        """A re-seed would skip what an unfinished seed already checkpointed."""
        watcher, info, restored = self._watcher()
        watcher._scan_remote_recursive.side_effect = [False, True]

        watcher.queue_unfiltered("X", ["node-1"])
        watcher._apply_unfiltered()

        assert watcher._unfiltered_nodes == {"node-1"}
        assert (CONF_BOOTSTRAPPED_FOR, None) not in [
            c.args for c in watcher.dao.update_config.call_args_list
        ]

        watcher._apply_unfiltered()

        assert watcher._scan_remote_recursive.call_args_list == [
            call(restored, info, force=True),
            call(restored, info, force=True),
        ]
        assert not watcher._unfiltered_nodes

    def test_a_login_error_is_raised_and_the_folder_kept_for_later(self):
        """Raised into _do_handle_changes(), which asks the user to log in."""
        watcher, _, _ = self._watcher()
        watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")

        watcher.queue_unfiltered("X", ["node-1"])
        with pytest.raises(AlfrescoAuthError):
            watcher._apply_unfiltered()

        assert watcher._unfiltered_nodes == {"node-1"}

    def test_a_fetch_failure_is_retried_on_the_next_cycle(self):
        watcher, _, _ = self._watcher()
        watcher.engine.remote.get_node.side_effect = RuntimeError("boom")

        watcher.queue_unfiltered("X", ["node-1"])
        watcher._apply_unfiltered()

        assert watcher._unfiltered_nodes == {"node-1"}

    def test_no_node_id_means_a_full_reseed(self):
        watcher, _, _ = self._watcher()

        watcher.queue_unfiltered("X", [])
        watcher._apply_unfiltered()

        watcher.dao.update_config.assert_any_call(CONF_BOOTSTRAPPED_FOR, None)
        watcher._scan_remote_recursive.assert_not_called()


# -- PR review: deleting a folder that contains a skipped folder (#5) ------------


class TestFolderDeletionOverSkippedFolder:
    def test_deleting_a_parent_of_a_skipped_folder_is_held(self):
        proc = _processor({"A/B"})
        pair = _row("A", pair_state="locally_deleted", folderish=True)

        assert proc._hold_under_skipped_folder(pair) is True
        assert proc.dao.increase_error.call_args.kwargs["details"] == str(Path("A/B"))

    def test_deleting_the_sync_parent_of_a_deep_skipped_folder_is_held(self):
        proc = _processor({"A/B/C"})
        pair = _row("A", pair_state="locally_deleted", folderish=True)

        assert proc._hold_under_skipped_folder(pair) is True

    def test_moving_a_parent_of_a_skipped_folder_is_not_held(self):
        """A move keeps the unread content intact on the server."""
        proc = _processor({"A/B"})
        pair = _row("A2", pair_state="locally_moved", folderish=True)

        assert proc._hold_under_skipped_folder(pair) is False

    def test_deleting_an_unrelated_folder_is_not_held(self):
        proc = _processor({"A/B"})
        pair = _row("A2", pair_state="locally_deleted", folderish=True)

        assert proc._hold_under_skipped_folder(pair) is False

    def test_deleting_a_file_next_to_a_skipped_folder_is_not_held(self):
        proc = _processor({"A/B"})
        pair = _row("A/file.txt", pair_state="locally_deleted")

        assert proc._hold_under_skipped_folder(pair) is False

    def test_release_keeps_the_parent_deletion_held(self):
        held = _row(
            "A",
            pair_state="locally_deleted",
            folderish=True,
            last_error=HELD_UNDER_SKIPPED_FOLDER,
        )
        watcher = _watcher()
        watcher._skipped_folders = {"A/B"}
        watcher.dao = _dao_with_skipped({"A/B"})
        watcher.dao.get_states_with_error.return_value = [held]

        watcher._release_held_pairs()

        watcher.dao.reset_error.assert_not_called()

    def test_release_frees_the_parent_deletion_once_readable(self):
        held = _row(
            "A",
            pair_state="locally_deleted",
            folderish=True,
            last_error=HELD_UNDER_SKIPPED_FOLDER,
        )
        watcher = _watcher()
        watcher._skipped_folders = set()
        watcher.dao = _dao_with_skipped(set())
        watcher.dao.get_states_with_error.return_value = [held]

        watcher._release_held_pairs()

        watcher.dao.reset_error.assert_called_once_with(held)

    def test_find_blocking_skipped_folder_prefers_the_ancestor(self):
        dao = _dao_with_skipped({"A", "A/B/C"})
        pair = _row("A/B", pair_state="locally_deleted", folderish=True)

        assert find_blocking_skipped_folder(dao, pair).local_path == Path("A")


# -- PR review: resolving a skipped id to the right row (#2) ---------------------


class TestSkippedFolderRows:
    def test_only_synced_folder_rows_are_kept(self):
        dao = MagicMock()
        folder = _row("X", pair_state="synchronized", folderish=True)
        dao.get_states_from_remote.return_value = [
            _row("X.txt", pair_state="synchronized"),
            _row("Old", pair_state="remotely_deleted", folderish=True),
            _row(
                "Gone",
                pair_state="synchronized",
                folderish=True,
                remote_state="deleted",
            ),
            folder,
        ]

        assert skipped_folder_rows(dao, "uid") == [folder]

    def test_every_candidate_holds_local_changes(self):
        dao = MagicMock()
        dao.get_config.return_value = json.dumps(["uid"])
        first = _row("X", pair_state="synchronized", folderish=True)
        second = _row("Y", pair_state="synchronized", folderish=True)
        dao.get_states_from_remote.return_value = [first, second]

        assert skipped_folder_pairs(dao) == [first, second]
        assert find_skipped_ancestor(dao, Path("Y/new.txt")) is second

    def test_ambiguous_folder_is_not_retried(self):
        watcher = _watcher()
        watcher._skipped_folders = {"uid"}
        watcher.dao.get_states_from_remote.return_value = [
            _row("X", pair_state="synchronized", folderish=True),
            _row("Y", pair_state="synchronized", folderish=True),
        ]

        watcher._retry_skipped_folders()

        watcher.engine.remote.get_node.assert_not_called()
        assert watcher._skipped_folders == {"uid"}


# -- PR review: keep the error on a skipped folder created locally (#7) ----------


class TestKeepSkippedFolderError:
    def _processor(self, skipped):
        proc = _processor(set())
        proc.dao.get_config.side_effect = lambda key, **_: (
            json.dumps(sorted(skipped)) if key == CONF_SKIPPED_FOLDERS else None
        )
        return proc

    def _after(self, **kwargs):
        after = _row("X", pair_state="synchronized", folderish=True, **kwargs)
        after.remote_ref = "uid"
        return after

    def test_error_cleared_by_the_handler_is_put_back(self):
        proc = self._processor({"uid"})
        before = _row("X", pair_state="remotely_created", folderish=True)
        before.last_error = LISTING_FAILED_ERROR
        before.last_error_details = "Not allowed to read this folder"
        after = self._after()

        proc._keep_skipped_folder_error(before, after)

        proc.dao.increase_error.assert_called_once_with(
            after,
            LISTING_FAILED_ERROR,
            details="Not allowed to read this folder",
            incr=4,
        )

    def test_a_generic_reason_when_none_was_recorded(self):
        proc = self._processor({"uid"})

        proc._keep_skipped_folder_error(
            _row("X", pair_state="remotely_created", folderish=True), self._after()
        )

        assert proc.dao.increase_error.call_args.kwargs["details"]

    def test_nothing_to_do_when_the_error_is_still_there(self):
        proc = self._processor({"uid"})

        proc._keep_skipped_folder_error(
            MagicMock(), self._after(last_error=LISTING_FAILED_ERROR)
        )

        proc.dao.increase_error.assert_not_called()

    def test_nothing_to_do_for_a_folder_that_is_not_skipped(self):
        proc = self._processor(set())

        proc._keep_skipped_folder_error(MagicMock(), self._after())

        proc.dao.increase_error.assert_not_called()

    def test_files_are_ignored(self):
        proc = self._processor({"uid"})
        after = self._after()
        after.folderish = False

        proc._keep_skipped_folder_error(MagicMock(), after)

        proc.dao.increase_error.assert_not_called()


# -- PR review: pending fetches survive a restart (#4) ---------------------------


def _config_dao():
    """A MagicMock DAO whose configuration really persists."""
    dao = MagicMock()
    store = {}
    dao.lock = RLock()
    dao.get_config.side_effect = lambda key, default=None: store.get(key) or default
    dao.update_config.side_effect = lambda key, value: store.__setitem__(key, value)
    dao.store = store
    return dao


class TestPendingUnfiltered:
    def test_round_trip(self):
        dao = _config_dao()

        first = add_pending_unfiltered(dao, ["b", "a"])
        add_pending_unfiltered(dao, ["c"])
        remove_pending_unfiltered(dao, {"a": first})

        assert load_pending_unfiltered(dao) == ({"b", "c"}, False)

    def test_each_request_gets_a_new_generation(self):
        dao = _config_dao()

        first = add_pending_unfiltered(dao, ["a"])
        second = add_pending_unfiltered(dao, ["a"])

        assert second > first
        assert snapshot_pending_unfiltered(dao).nodes == {"a": second}

    def test_a_newer_request_survives_the_older_removal(self):
        dao = _config_dao()
        older = add_pending_unfiltered(dao, ["a"])
        add_pending_unfiltered(dao, ["a"])  # Saved while the older one was fetched.

        remove_pending_unfiltered(dao, {"a": older})

        assert load_pending_unfiltered(dao) == ({"a"}, False)

    def test_full_scan_flag_sticks_until_its_request_is_handled(self):
        dao = _config_dao()

        owed = add_pending_unfiltered(dao, [], full_scan=True)
        newer = add_pending_unfiltered(dao, ["a"])
        remove_pending_unfiltered(dao, {"a": newer})
        assert load_pending_unfiltered(dao) == (set(), True)

        remove_pending_unfiltered(dao, {}, full_scan=owed)
        assert load_pending_unfiltered(dao) == (set(), False)

    def test_a_newer_full_scan_request_survives(self):
        dao = _config_dao()
        older = add_pending_unfiltered(dao, [], full_scan=True)
        add_pending_unfiltered(dao, [], full_scan=True)

        remove_pending_unfiltered(dao, {}, full_scan=older)

        assert load_pending_unfiltered(dao) == (set(), True)

    def test_nothing_pending_clears_the_key(self):
        dao = _config_dao()

        gen = add_pending_unfiltered(dao, ["a"])
        remove_pending_unfiltered(dao, {"a": gen})

        assert dao.store[CONF_PENDING_UNFILTERED] is None

    def test_value_written_before_generations_is_still_read(self):
        dao = _config_dao()
        dao.store[CONF_PENDING_UNFILTERED] = json.dumps(
            {"nodes": ["a"], "full_scan": False}
        )

        assert load_pending_unfiltered(dao) == ({"a"}, False)
        add_pending_unfiltered(dao, ["b"])
        assert load_pending_unfiltered(dao) == ({"a", "b"}, False)

    @pytest.mark.parametrize(
        "raw", ["not json", "[]", '{"nodes": 1}', "42", '{"nodes": {}}']
    )
    def test_unreadable_value_means_nothing_pending(self, raw):
        dao = _config_dao()
        dao.store[CONF_PENDING_UNFILTERED] = raw

        assert load_pending_unfiltered(dao) == (set(), False)


class TestPendingUnfilteredInTheWatcher:
    def _watcher(self):
        watcher, _, restored = TestRestoredFolderOnTheWatcherThread()._watcher()
        config = _config_dao()
        watcher.dao.lock = config.lock
        watcher.dao.get_config.side_effect = config.get_config.side_effect
        watcher.dao.update_config.side_effect = config.update_config.side_effect
        watcher.store = config.store
        return watcher

    def test_queued_ids_are_saved(self):
        watcher = self._watcher()

        watcher.queue_unfiltered("X", ["node-1"])

        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)

    def test_fetched_ids_are_removed(self):
        watcher = self._watcher()
        watcher.queue_unfiltered("X", ["node-1"])

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == (set(), False)

    def test_failed_fetches_stay_saved(self):
        watcher = self._watcher()
        watcher.engine.remote.get_node.side_effect = RuntimeError("boom")
        watcher.queue_unfiltered("X", ["node-1"])

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)

    def test_login_errors_keep_them_saved(self):
        watcher = self._watcher()
        watcher.engine.remote.get_node.side_effect = AlfrescoAuthError("expired")
        watcher.queue_unfiltered("X", ["node-1"])

        with pytest.raises(AlfrescoAuthError):
            watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)

    def test_a_full_reseed_clears_everything(self):
        watcher = self._watcher()
        watcher.queue_unfiltered("X", ["node-1"])
        watcher.queue_unfiltered("Y", [])

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == (set(), False)

    def test_a_request_saved_during_the_fetch_is_kept(self):
        """E.g. the same folder restored again while its first fetch runs."""
        watcher = self._watcher()
        watcher.queue_unfiltered("X", ["node-1"])

        def newer_request_meanwhile(*_, **__):
            add_pending_unfiltered(watcher.dao, ["node-1"])
            return True

        watcher._scan_remote_recursive.side_effect = newer_request_meanwhile

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)

    def test_a_request_queued_during_the_fetch_is_fetched_next(self):
        """Its signal reaches queue_unfiltered() via _interact() mid-walk."""
        watcher = self._watcher()
        watcher.queue_unfiltered("X", ["node-1"])

        def queued_meanwhile(*_, **__):
            watcher.queue_unfiltered("X", ["node-1"])
            return True

        watcher._scan_remote_recursive.side_effect = queued_meanwhile
        watcher._apply_unfiltered()

        assert watcher._unfiltered_nodes == {"node-1"}
        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)

        watcher._scan_remote_recursive.side_effect = None
        watcher._scan_remote_recursive.return_value = True
        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == (set(), False)

    def test_a_request_saved_during_a_reseed_decision_is_kept(self):
        watcher = self._watcher()
        watcher.queue_unfiltered("Y", [])
        real_update = watcher.dao.update_config.side_effect

        def save_meanwhile(key, value):
            real_update(key, value)
            if key == CONF_BOOTSTRAPPED_FOR:
                add_pending_unfiltered(watcher.dao, ["node-9"])

        watcher.dao.update_config.side_effect = save_meanwhile

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == ({"node-9"}, False)

    def test_a_partial_walk_keeps_the_request_saved(self):
        watcher = self._watcher()
        watcher._scan_remote_recursive.return_value = False
        watcher.queue_unfiltered("X", ["node-1"])

        watcher._apply_unfiltered()

        assert load_pending_unfiltered(watcher.dao) == ({"node-1"}, False)
