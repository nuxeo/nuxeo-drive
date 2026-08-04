"""
Functional tests for :mod:`nxdrive.alfresco.engine.engine`.

Covers the AlfrescoEngine lifecycle: bind, init_remote, root creation,
filter selection, configuration persistence, conflict resolution, and
metadata URL generation.
"""

from uuid import uuid4

from nxdrive.alfresco.engine.engine import AlfrescoEngine
from nxdrive.drive.constants import ROOT


class TestEngineInit:
    """Engine creation and init_remote."""

    def test_engine_type_is_alfresco(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert isinstance(engine, AlfrescoEngine)
        assert engine.type == "ALFRESCO"

    def test_init_remote_returns_alfresco_remote(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        remote = engine.init_remote()
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        assert isinstance(remote, AlfrescoRemote)

    def test_remote_user_matches(self, manager_factory, alfresco_user) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert engine.remote_user == alfresco_user

    def test_server_url_stored(self, manager_factory, alfresco_url) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert engine.server_url
        assert alfresco_url.rstrip("/") in engine.server_url


class TestBind:
    """Account binding."""

    def test_bind_persists_config(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert engine.dao.get_config("server_url")
        assert engine.dao.get_config("remote_user")

    def test_bind_bad_credentials_raises(
        self, manager_factory, alfresco_url, tmp_path
    ) -> None:
        import pytest

        manager = manager_factory(with_engine=False)
        conf = tmp_path / f"bad-creds-{uuid4().hex[:8]}"
        with pytest.raises(Exception):
            manager.bind_server(
                conf,
                alfresco_url,
                "nonexistent-user-xyz",
                password="wrong-password",
                start_engine=False,
            )

    def test_bind_stores_web_authentication_flag(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # Password-based bind → web_authentication should be False
        assert engine.dao.get_bool("web_authentication") is False


class TestRootCreation:
    """Root pair and check_root."""

    def test_root_state_exists_after_bind(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        root = engine.dao.get_state_from_local(ROOT)
        assert root is not None

    def test_root_has_remote_ref(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        root = engine.dao.get_state_from_local(ROOT)
        assert root is not None
        assert root.remote_ref

    def test_local_folder_created(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert engine.local_folder.is_dir()


class TestFilterSelection:
    """needs_filters_selection and mark_filters_configured."""

    def test_filters_configured_after_bind(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # After a successful bind, filters are marked as configured
        assert engine.dao.get_config("filters_configured") == "1"

    def test_needs_filters_selection_is_false_after_bind(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        assert engine.needs_filters_selection() is False


class TestDiscoveryInfo:
    """_fetch_discovery_info."""

    def test_discovery_info_stored(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # Bind calls _fetch_discovery_info.  If the server exposes the
        # Discovery API, version/edition are populated; otherwise the
        # engine silently skips it (404 is non-fatal).
        version = engine.dao.get_config("alfresco_server_version")
        edition = engine.dao.get_config("alfresco_server_edition")
        # Either both are set or the API was unavailable — both cases are OK.
        assert (version and edition) or (version is None and edition is None)


class TestTicketPersistence:
    """_save_ticket / _load_ticket."""

    def test_save_and_load_ticket(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # Save a test ticket
        engine._save_ticket("test-ticket-abc123")
        loaded = engine._load_ticket()
        assert loaded == "test-ticket-abc123"

    def test_load_ticket_empty_when_not_set(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # Clear ticket
        engine.dao.update_config("alfresco_ticket", "")
        loaded = engine._load_ticket()
        assert loaded == ""


class TestMetadataUrl:
    """get_metadata_url."""

    def test_metadata_url_contains_node_ref(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        node_id = "abcd-1234-efgh-5678"
        url = engine.get_metadata_url(node_id)
        assert "document-details" in url
        assert node_id in url

    def test_metadata_url_strips_alfresco_context(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        url = engine.get_metadata_url("test-id")
        # URL should point to /share/page/document-details
        assert "share/page/document-details" in url


class TestConflictResolver:
    """conflict_resolver — requires a real engine with DAO."""

    def test_conflict_resolver_empty_pair(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        # row_id that doesn't exist → should return without error
        engine.conflict_resolver(999999, emit=False)

    def test_conflict_resolver_folder_matching_uid(self, manager_factory) -> None:
        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        root = engine.dao.get_state_from_local(ROOT)
        if root and root.remote_ref and root.folderish:
            # Set xattr to match remote_ref
            engine.local.set_remote_id(ROOT, root.remote_ref)
            engine.conflict_resolver(root.id, emit=False)
            # After resolving, state should be synchronized
            updated = engine.dao.get_state_from_id(root.id)
            assert updated is not None


class TestSuspendClient:
    """suspend_client."""

    def test_suspend_client_raises_when_paused(self, manager_factory) -> None:
        import pytest
        from nxdrive.drive.exceptions import ThreadInterrupt

        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        engine._pause = True
        with pytest.raises(ThreadInterrupt):
            engine.suspend_client()


class TestCreateProcessor:
    """create_processor returns AlfrescoProcessor."""

    def test_create_processor(self, manager_factory) -> None:
        from unittest.mock import MagicMock

        from nxdrive.alfresco.engine.processor import AlfrescoProcessor

        manager = manager_factory(with_engine=True)
        engine = next(iter(manager.engines.values()))
        proc = engine.create_processor(MagicMock())
        assert isinstance(proc, AlfrescoProcessor)
