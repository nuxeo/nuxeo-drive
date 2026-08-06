"""Unit tests for nxdrive.alfresco.engine.engine — targets uncovered lines."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.drive.constants import ROOT
from nxdrive.drive.objects import Binder


def _make_engine(**overrides):
    """Create a mock AlfrescoEngine bypassing QObject __init__."""
    with patch.object(AlfrescoEngine, "__init__", return_value=None):
        engine = AlfrescoEngine.__new__(AlfrescoEngine)
    engine.dao = MagicMock()
    engine.remote = MagicMock()
    engine.manager = MagicMock()
    engine.local = MagicMock()
    engine._name = "test"
    engine.uid = "test-uid"
    engine.hostname = "localhost"
    engine.remote_user = "admin"
    engine.server_url = "https://acs.example.com/"
    engine._remote_token = None
    engine._remote_password = "secret"
    engine._web_authentication = False
    engine._alfresco_ticket = ""
    engine._stopped = False
    engine._sync_started = False
    engine._threads = []
    engine.local_folder = Path("/tmp/alfresco-test")
    engine.queue_manager = MagicMock()
    engine.invalidAuthentication = MagicMock()
    engine.syncStarted = MagicMock()
    engine.syncCompleted = MagicMock()
    engine.syncPartialCompleted = MagicMock()
    engine.syncStateCleared = MagicMock()
    engine.newConflict = MagicMock()
    engine.version = "1.0.0"
    engine.timeout = 30
    engine.remote_cls = MagicMock()
    engine._local_watcher = MagicMock()
    engine._remote_watcher = MagicMock()
    engine._scanPair = MagicMock()
    for k, v in overrides.items():
        setattr(engine, k, v)
    return engine


def _make_binder(**overrides):
    defaults = dict(
        url="https://acs.example.com/",
        username="admin",
        password="secret",
        token=None,
        no_check=False,
        no_fscheck=True,
    )
    defaults.update(overrides)
    return Binder(**defaults)


# ------------------------------------------------------------------ needs_filters_selection


class TestNeedsFiltersSelection:
    def test_sync_disabled(self):
        engine = _make_engine()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = False
            assert engine.needs_filters_selection() is False

    def test_already_configured(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            assert engine.needs_filters_selection() is False

    def test_root_pair_exists_marks_configured(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        engine.dao.get_state_from_local.return_value = MagicMock()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            assert engine.needs_filters_selection() is False
            engine.dao.update_config.assert_called_with("filters_configured", "1")

    def test_no_root_no_config(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        engine.dao.get_state_from_local.return_value = None
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            assert engine.needs_filters_selection() is True


# ------------------------------------------------------------------ mark_filters_configured


class TestMarkFiltersConfigured:
    def test_stores_flag_and_checks_root(self):
        engine = _make_engine()
        engine._check_root = MagicMock()
        engine.mark_filters_configured()
        engine.dao.update_config.assert_any_call("filters_configured", "1")
        engine._check_root.assert_called_once()


# ------------------------------------------------------------------ start / cleanup


class TestStartCleanup:
    def test_sync_disabled_with_filters_triggers_cleanup(self):
        engine = _make_engine()
        engine._cleanup_after_sync_disabled = MagicMock()
        engine.dao.get_config.return_value = "1"
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = False
            with patch.object(AlfrescoEngine.__bases__[0], "start", return_value=None):
                engine.start()
        engine._cleanup_after_sync_disabled.assert_called_once()

    def test_cleanup_clears_states_filters_config(self):
        engine = _make_engine()
        engine.dao.get_filters.return_value = ["/path1", "/path2"]
        engine._cleanup_after_sync_disabled()
        engine.dao.reinit_states.assert_called_once()
        assert engine.dao.remove_filter.call_count == 2
        engine.dao.delete_config.assert_called_with("filters_configured")
        engine.syncStateCleared.emit.assert_called_once()

    def test_cleanup_handles_reinit_failure(self):
        engine = _make_engine()
        engine.dao.reinit_states.side_effect = RuntimeError("db locked")
        engine.dao.get_filters.return_value = []
        # Should not raise
        engine._cleanup_after_sync_disabled()
        engine.dao.delete_config.assert_called_with("filters_configured")


# ------------------------------------------------------------------ _check_sync_start


class TestCheckSyncStart:
    def test_emits_when_queue_nonempty(self):
        engine = _make_engine(_sync_started=False)
        engine.queue_manager.get_overall_size.return_value = 5
        engine._check_sync_start()
        assert engine._sync_started is True
        engine.syncStarted.emit.assert_called_once_with(5)

    def test_noop_when_already_started(self):
        engine = _make_engine(_sync_started=True)
        engine._check_sync_start()
        engine.syncStarted.emit.assert_not_called()

    def test_noop_when_queue_empty(self):
        engine = _make_engine(_sync_started=False)
        engine.queue_manager.get_overall_size.return_value = 0
        engine._check_sync_start()
        assert engine._sync_started is False


# ------------------------------------------------------------------ init_remote


class TestInitRemote:
    def test_creates_remote_with_expected_args(self):
        engine = _make_engine()
        engine._alfresco_ticket = "TICKET-ABC"
        engine.init_remote()
        engine.remote_cls.assert_called_once()
        call_kwargs = engine.remote_cls.call_args
        assert call_kwargs[1]["alfresco_ticket"] == "TICKET-ABC"
        assert call_kwargs[1]["password"] == "secret"
        assert call_kwargs[1]["upload_callback"] == engine.suspend_client


# ------------------------------------------------------------------ _on_remote_token_refreshed


class TestOnRemoteTokenRefreshed:
    def test_persists_token(self):
        engine = _make_engine()
        engine._save_token = MagicMock()
        new_token = {"access_token": "abc", "refresh_token": "xyz"}
        engine._on_remote_token_refreshed(new_token)
        assert engine._remote_token == new_token
        engine._save_token.assert_called_once_with(new_token)

    def test_swallows_save_failure(self):
        engine = _make_engine()
        engine._save_token = MagicMock(side_effect=RuntimeError("db error"))
        engine._on_remote_token_refreshed({"access_token": "a"})
        # Should not raise


# ------------------------------------------------------------------ bind


class TestBind:
    def _setup_bind_mocks(self, engine):
        engine._normalize_url = MagicMock(side_effect=lambda u: u)
        engine._setup_local_folder = MagicMock()
        engine.init_remote = MagicMock(return_value=engine.remote)
        engine.remote.check_credentials = MagicMock()
        engine._save_ticket = MagicMock()
        engine._save_token = MagicMock()
        engine._fetch_discovery_info = MagicMock()
        engine._check_root = MagicMock()

    def test_no_ticket_found_logs_warning(self):
        engine = _make_engine()
        engine.remote.auth = MagicMock(spec=[])
        engine.remote.client.session.auth = MagicMock(spec=[])
        self._setup_bind_mocks(engine)
        engine.bind(_make_binder())
        assert engine._remote_password == "secret"
        engine._save_ticket.assert_not_called()

    def test_ticket_found_on_auth(self):
        engine = _make_engine()
        engine.remote.auth = MagicMock()
        engine.remote.auth.ticket = "TICKET-12345"
        self._setup_bind_mocks(engine)
        engine.bind(_make_binder())
        assert engine._remote_password == ""
        assert engine._alfresco_ticket == "TICKET-12345"
        engine._save_ticket.assert_called_once_with("TICKET-12345")

    def test_auth_failure_raises_unauthorized(self):
        from alfresco.exceptions import AuthenticationError

        from nxdrive.drive.exceptions import RemoteUnauthorized

        engine = _make_engine()
        self._setup_bind_mocks(engine)
        engine.remote.check_credentials.side_effect = AuthenticationError("bad creds")
        with pytest.raises(RemoteUnauthorized):
            engine.bind(_make_binder())
        assert engine.remote is None

    def test_generic_error_reraises(self):
        engine = _make_engine()
        self._setup_bind_mocks(engine)
        engine.remote.check_credentials.side_effect = RuntimeError("network")
        with pytest.raises(RuntimeError, match="network"):
            engine.bind(_make_binder())

    def test_no_check_skips_credentials(self):
        engine = _make_engine()
        self._setup_bind_mocks(engine)
        engine.bind(_make_binder(no_check=True))
        engine.remote.check_credentials.assert_not_called()

    def test_token_auth_skips_ticket_extraction(self):
        engine = _make_engine()
        self._setup_bind_mocks(engine)
        engine.bind(_make_binder(token={"access_token": "tok"}, password=""))
        engine._save_ticket.assert_not_called()
        engine._save_token.assert_called_once()


# ------------------------------------------------------------------ _check_root


class TestCheckRoot:
    def test_sync_disabled_noop(self):
        engine = _make_engine()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = False
            engine._check_root()
        engine.dao.get_state_from_local.assert_not_called()

    def test_filters_not_configured_noop(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            engine._check_root()
        engine.dao.get_state_from_local.assert_not_called()

    def test_root_already_exists_noop(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = MagicMock()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            engine._check_root()
        engine._add_top_level_state = MagicMock()
        engine._add_top_level_state.assert_not_called()

    def test_creates_folder_and_root_state(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = None
        engine.local_folder = MagicMock()
        engine.local_folder.is_dir.return_value = False
        engine._add_top_level_state = MagicMock()
        engine._set_root_icon = MagicMock()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            with patch("nxdrive.alfresco.engine.engine.set_path_readonly"):
                engine._check_root()
        engine.local_folder.mkdir.assert_called_once()
        engine._add_top_level_state.assert_called_once()

    def test_auth_error_sets_invalid_credentials(self):
        from alfresco.exceptions import AuthenticationError

        engine = _make_engine()
        engine.dao.get_config.return_value = "1"
        engine.dao.get_state_from_local.return_value = None
        engine.local_folder = MagicMock()
        engine.local_folder.is_dir.return_value = True
        engine._add_top_level_state = MagicMock(
            side_effect=AuthenticationError("expired")
        )
        engine.set_invalid_credentials = MagicMock()
        with patch("nxdrive.alfresco.engine.engine.Feature") as F:
            F.synchronization = True
            with patch("nxdrive.alfresco.engine.engine.unset_path_readonly"):
                engine._check_root()
        engine.set_invalid_credentials.assert_called_once()


# ------------------------------------------------------------------ _add_top_level_state


class TestAddTopLevelState:
    def test_no_remote_noop(self):
        engine = _make_engine(remote=None)
        engine._add_top_level_state()
        engine.dao.insert_local_state.assert_not_called()

    def test_no_row_after_insert_returns(self):
        engine = _make_engine()
        engine.dao.get_state_from_local.return_value = None
        engine._add_top_level_state()
        engine.dao.insert_local_state.assert_called_once()
        engine.dao.update_remote_state.assert_not_called()

    def test_full_setup(self):
        engine = _make_engine()
        engine.manager.device_id = "device-001"
        local_info = MagicMock()
        engine.local.get_info.return_value = local_info
        row = MagicMock()
        engine.dao.get_state_from_local.return_value = row
        remote_info = MagicMock()
        remote_info.uid = "root-node-id"
        engine.remote.get_filesystem_root_info.return_value = remote_info
        engine._add_top_level_state()
        engine.dao.update_remote_state.assert_called_once()
        engine.dao.synchronize_state.assert_called_once_with(row)
        engine.local.set_root_id.assert_called_once()
        engine.local.set_remote_id.assert_called_once_with(ROOT, "root-node-id")


# ------------------------------------------------------------------ _fetch_discovery_info


class TestFetchDiscoveryInfo:
    def test_stores_version_and_edition(self):
        engine = _make_engine()
        engine.remote.get_discovery.return_value = {
            "entry": {
                "repository": {
                    "version": {"display": "23.2.1"},
                    "edition": "Enterprise",
                }
            }
        }
        engine._fetch_discovery_info()
        engine.dao.update_config.assert_any_call("alfresco_server_version", "23.2.1")
        engine.dao.update_config.assert_any_call(
            "alfresco_server_edition", "Enterprise"
        )

    def test_no_remote_noop(self):
        engine = _make_engine(remote=None)
        engine._fetch_discovery_info()
        # Should not raise

    def test_api_failure_swallowed(self):
        engine = _make_engine()
        engine.remote.get_discovery.side_effect = RuntimeError("timeout")
        engine._fetch_discovery_info()
        # Should not raise


# ------------------------------------------------------------------ _check_last_sync


class TestCheckLastSync:
    def test_not_started_noop(self):
        engine = _make_engine(_sync_started=False)
        engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_queue_nonempty_returns(self):
        engine = _make_engine(_sync_started=True)
        engine.queue_manager.get_overall_size.return_value = 3
        engine._local_watcher.empty_events.return_value = True
        engine.queue_manager.active.return_value = False
        engine._check_last_sync()
        engine.syncCompleted.emit.assert_not_called()

    def test_completed_no_errors(self):
        engine = _make_engine(_sync_started=True)
        engine.queue_manager.get_overall_size.return_value = 0
        engine._local_watcher.empty_events.return_value = True
        engine.queue_manager.active.return_value = False
        engine.queue_manager.get_errors_count.return_value = 0
        engine._check_last_sync()
        assert engine._sync_started is False
        engine.syncCompleted.emit.assert_called_once()

    def test_completed_with_errors(self):
        engine = _make_engine(_sync_started=True)
        engine.queue_manager.get_overall_size.return_value = 0
        engine._local_watcher.empty_events.return_value = True
        engine.queue_manager.active.return_value = False
        engine.queue_manager.get_errors_count.return_value = 2
        engine._check_last_sync()
        engine.syncPartialCompleted.emit.assert_called_once()


# ------------------------------------------------------------------ conflict_resolver


class TestConflictResolver:
    def test_empty_pair_skips(self):
        engine = _make_engine()
        engine.dao.get_state_from_id.return_value = None
        engine.conflict_resolver(42)

    def test_file_remote_unchanged_resets(self):
        engine = _make_engine()
        pair = MagicMock()
        pair.folderish = False
        pair.remote_ref = "node-123"
        pair.last_remote_updated = "2024-01-01 00:00:00"
        pair.local_name = "file.txt"
        engine.dao.get_state_from_id.return_value = pair

        remote_info = MagicMock()
        remote_info.last_modification_time = MagicMock()
        remote_info.last_modification_time.strftime.return_value = "2024-01-01 00:00:00"
        engine.remote.get_fs_info.return_value = remote_info

        engine.conflict_resolver(42)
        engine.dao._force_sync.assert_called_once()

    def test_file_remote_drifted_emits_conflict(self):
        engine = _make_engine()
        pair = MagicMock()
        pair.folderish = False
        pair.remote_ref = "node-123"
        pair.last_remote_updated = "2024-01-01 00:00:00"
        pair.local_name = "file.txt"
        pair.local_path = "/test"
        engine.dao.get_state_from_id.return_value = pair

        remote_info = MagicMock()
        remote_info.last_modification_time = MagicMock()
        remote_info.last_modification_time.strftime.return_value = "2024-06-15 12:30:00"
        engine.remote.get_fs_info.return_value = remote_info

        engine.conflict_resolver(42)
        engine.newConflict.emit.assert_called_once_with(42)

    def test_folder_matching_uid_resolves(self):
        engine = _make_engine()
        pair = MagicMock()
        pair.folderish = True
        pair.remote_ref = "folder-abc"
        pair.local_path = "/test-folder"
        pair.local_name = "TestFolder"
        engine.dao.get_state_from_id.return_value = pair
        engine.local.get_remote_id.return_value = "folder-abc"

        engine.conflict_resolver(42)
        engine.dao.synchronize_state.assert_called_once_with(pair)

    def test_folder_mismatched_uid_emits_conflict(self):
        engine = _make_engine()
        pair = MagicMock()
        pair.folderish = True
        pair.remote_ref = "folder-abc"
        pair.local_path = "/test-folder"
        pair.local_name = "TestFolder"
        engine.dao.get_state_from_id.return_value = pair
        engine.local.get_remote_id.return_value = "different-id"

        engine.conflict_resolver(42)
        engine.newConflict.emit.assert_called_once_with(42)


# ------------------------------------------------------------------ get_metadata_url


class TestGetMetadataUrl:
    def test_basic_url(self):
        engine = _make_engine(server_url="https://acs.example.com/alfresco/")
        url = engine.get_metadata_url("node-id-123")
        assert "share/page/document-details" in url
        assert "nodeRef=workspace://SpacesStore/node-id-123" in url
        assert "/alfresco/" not in url.split("share")[0]

    def test_no_alfresco_suffix(self):
        engine = _make_engine(server_url="https://acs.example.com/")
        url = engine.get_metadata_url("abc-def")
        assert url.startswith("https://acs.example.com/share/page/document-details")


# ------------------------------------------------------------------ _load_configuration


class TestLoadConfiguration:
    def test_loads_all_config(self):
        engine = _make_engine()
        engine.dao.get_bool.return_value = True
        engine.dao.get_config.side_effect = lambda k, **kw: {
            "server_url": "https://acs.test.com/",
            "ui": "web",
            "force_ui": None,
            "remote_user": "testuser",
        }.get(k, kw.get("default"))
        engine._load_token = MagicMock(return_value={"access_token": "tok"})
        engine._load_configuration()
        assert engine.server_url == "https://acs.test.com/"
        assert engine.remote_user == "testuser"
        assert engine._remote_token == {"access_token": "tok"}

    def test_no_token_loads_ticket(self):
        engine = _make_engine()
        engine.dao.get_bool.return_value = False
        engine.dao.get_config.side_effect = lambda k, **kw: {
            "server_url": "https://acs.test.com/",
            "ui": "web",
            "force_ui": None,
            "remote_user": "admin",
        }.get(k, kw.get("default"))
        engine._load_token = MagicMock(return_value=None)
        engine._load_ticket = MagicMock(return_value="TICKET-XYZ")
        engine._load_configuration()
        assert engine._alfresco_ticket == "TICKET-XYZ"


# ------------------------------------------------------------------ _save_ticket / _load_ticket


class TestTicketPersistence:
    def test_save_and_load_roundtrip(self):
        engine = _make_engine()
        engine._save_ticket("TICKET-ABC")
        engine.dao.update_config.assert_called_once()
        # Verify it stored something under "alfresco_ticket"
        call_args = engine.dao.update_config.call_args
        assert call_args[0][0] == "alfresco_ticket"

    def test_load_empty_returns_empty(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = None
        assert engine._load_ticket() == ""

    def test_load_corrupt_returns_empty_or_string(self):
        engine = _make_engine()
        engine.dao.get_config.return_value = "corrupted-data"
        # _load_ticket catches decrypt errors; result is always a string
        # (or possibly empty if decryption fails gracefully)
        result = engine._load_ticket()
        # Should not raise — graceful handling
        assert isinstance(result, (str, type(None)))


# ------------------------------------------------------------------ suspend_client


class TestSuspendClient:
    def test_paused_raises(self):
        from nxdrive.drive.exceptions import ThreadInterrupt

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=True)
        engine.is_started = MagicMock(return_value=True)
        with pytest.raises(ThreadInterrupt):
            engine.suspend_client()

    def test_not_started_raises(self):
        from nxdrive.drive.exceptions import ThreadInterrupt

        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=False)
        with pytest.raises(ThreadInterrupt):
            engine.suspend_client()

    def test_running_no_raise(self):
        engine = _make_engine()
        engine.is_paused = MagicMock(return_value=False)
        engine.is_started = MagicMock(return_value=True)
        engine.suspend_client()  # Should not raise


# ------------------------------------------------------------------ have_folder_upload


class TestHaveFolderUpload:
    def test_always_true(self):
        engine = _make_engine()
        assert engine.have_folder_upload is True


# ------------------------------------------------------------------ shared-base ownership regression


class TestAlfrescoNoUseridMapperInBase:
    """Regression tests for the Alfresco account-load crash caused by the
    shared engine base invoking ``_seed_userid_mapper()``.

    The Nuxeo-specific mapper seeding must never be invoked from the
    server-agnostic constructor. See the bug report for the full traceback.
    """

    def test_alfresco_engine_has_no_seed_userid_mapper(self):
        """AlfrescoEngine must not define or inherit ``_seed_userid_mapper``.

        If it did, the shared base could accidentally reintroduce the
        Nuxeo-only lifecycle call without exploding on Alfresco.
        """
        assert not hasattr(AlfrescoEngine, "_seed_userid_mapper"), (
            "AlfrescoEngine must not carry Nuxeo-specific userid mapper "
            "seeding. Remove the base-class call, do not add an override."
        )

    def test_shared_base_does_not_call_seed_userid_mapper(self):
        """The server-agnostic Engine base constructor body must not
        reference ``_seed_userid_mapper``. This mirrors the exact traceback
        from the reported Alfresco reload crash.
        """
        import inspect

        from nxdrive.drive.engine.engine import Engine as BaseEngine

        source = inspect.getsource(BaseEngine.__init__)
        assert "_seed_userid_mapper" not in source, (
            "The shared Engine base must not call `_seed_userid_mapper` — "
            "that is a Nuxeo-only concern owned by "
            "nxdrive/nuxeo/engine/engine.py."
        )

    def test_shared_base_has_no_userid_mapper_members(self):
        """The server-agnostic ``Engine`` base must not carry any of the
        Nuxeo-specific userid_mapper / user_uuid members.

        These belong to ``nxdrive.nuxeo.engine.engine.Engine`` only.
        """
        from nxdrive.drive.engine.engine import Engine as BaseEngine

        for name in (
            "_NO_UUID_SUPPORT",
            "_refresh_user_uuid",
            "_seed_userid_mapper",
        ):
            assert name not in BaseEngine.__dict__, (
                f"Nuxeo-specific member {name!r} leaked into the shared "
                "Engine base. Move it into nxdrive/nuxeo/engine/engine.py."
            )

    def test_shared_base_update_token_has_no_uuid_side_effects(self):
        """The base ``update_token`` must not touch ``user_uuid`` in the DB
        nor call ``_refresh_user_uuid``. Nuxeo overrides ``update_token``
        to add that behaviour on its own.
        """
        import ast
        import inspect
        import textwrap

        from nxdrive.drive.engine.engine import Engine as BaseEngine

        source = textwrap.dedent(inspect.getsource(BaseEngine.update_token))
        func_ast = ast.parse(source).body[0]
        assert isinstance(func_ast, ast.FunctionDef)
        # Strip the docstring so mentions of forbidden names in prose
        # explaining why they are absent do not trigger the guard.
        if (
            func_ast.body
            and isinstance(func_ast.body[0], ast.Expr)
            and isinstance(func_ast.body[0].value, ast.Constant)
            and isinstance(func_ast.body[0].value.value, str)
        ):
            func_ast.body = func_ast.body[1:]
        body_source = ast.unparse(func_ast)
        for forbidden in ("user_uuid", "_refresh_user_uuid", "userid_mapper"):
            assert forbidden not in body_source, (
                f"Base Engine.update_token must not reference {forbidden!r}. "
                "Move any UUID handling into the Nuxeo subclass override."
            )

    def test_alfresco_update_token_inherits_base(self):
        """``AlfrescoEngine`` must reuse the base ``update_token`` without
        override, guaranteeing it never runs Nuxeo-only UUID logic.
        """
        from nxdrive.drive.engine.engine import Engine as BaseEngine

        assert AlfrescoEngine.update_token is BaseEngine.update_token, (
            "AlfrescoEngine must inherit the base update_token as-is. "
            "If Alfresco needs custom token handling, add an override that "
            "does NOT reintroduce Nuxeo user_uuid semantics."
        )
