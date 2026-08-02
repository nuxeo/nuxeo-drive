"""
Functional tests for the remote client (nxdrive/nuxeo/client/remote_client.py).

These tests exercise real server interactions to cover code paths
that require actual HTTP calls to Nuxeo.
"""

from pathlib import Path

import pytest
from nuxeo.models import Document

from nxdrive.drive.exceptions import NotFound
from nxdrive.drive.objects import RemoteFileInfo
from nxdrive.drive.options import Options

# ---------------------------------------------------------------------------
# Remote client: basic operations
# ---------------------------------------------------------------------------


def test_remote_exists(manager_factory, obj_factory):
    """Test remote.exists() with UID lookup."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        # Create doc accessible by the engine user
        doc = obj_factory(
            title="test_exists_doc_ft",
            enable_sync=False,
            user=remote.user_id,
        )

        # By UID
        assert remote.exists(doc.uid) is True
        assert remote.exists("00000000-0000-0000-0000-999999999999") is False


def test_remote_exists_in_parent(manager_factory, obj_factory):
    """Test exists_in_parent for folderish and non-folderish documents."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        folder = obj_factory(title="parent_folder_exists_ft", user=remote.user_id)

        # Create a child document
        obj_factory(
            title="child_doc_ft",
            nature="File",
            parent=folder.path,
            user=remote.user_id,
        )

        # Check child exists
        assert remote.exists_in_parent(folder.uid, "child_doc_ft", False) is True
        assert remote.exists_in_parent(folder.uid, "nonexistent_child", False) is False


def test_remote_escape_special_chars(manager_factory):
    """Test Remote.escape handles special characters."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        # Single quotes
        assert remote.escape("it's") == r"it\'s"
        # Line feeds
        assert remote.escape("line\nfeed") == r"line\\nfeed"
        # Carriage returns
        assert remote.escape("cr\rreturn") == r"cr\\rreturn"


def test_remote_escape_carriage_return(manager_factory):
    """Test Remote.escapeCarriageReturn."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        assert remote.escapeCarriageReturn("foo\rbar") == r"foo\\rbar"
        assert remote.escapeCarriageReturn("foo\nbar") == r"foo\\nbar"


def test_remote_personal_space(manager_factory):
    """Test personal_space retrieval."""
    manager, engine = manager_factory()
    with manager:
        space = engine.remote.personal_space()
        assert isinstance(space, Document)
        assert space.path is not None


def test_remote_execute_not_found(manager_factory):
    """Test that execute raises NotFound for 404 responses."""
    manager, engine = manager_factory()
    with manager:
        with pytest.raises(NotFound):
            engine.remote.execute(
                command="Document.Fetch",
                params={"value": "/nonexistent/path/00000000"},
            )


def test_remote_request_token(manager_factory):
    """Test that auth token is available after bind."""
    manager, engine = manager_factory()
    with manager:
        # After bind, we should have a valid token
        token = engine._load_token()
        assert token is not None
        assert len(str(token)) > 0


# ---------------------------------------------------------------------------
# Remote client: document operations
# ---------------------------------------------------------------------------


def test_remote_query(manager_factory, obj_factory):
    """Test remote.query for NXQL queries."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        doc = obj_factory(title="query_test_doc_ft", user=remote.user_id)

        result = remote.query(f"SELECT * FROM Document WHERE ecm:uuid = '{doc.uid}'")
        assert result["totalSize"] == 1


def test_remote_fetch(manager_factory, obj_factory):
    """Test remote.fetch by UID."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        doc = obj_factory(title="fetch_test_doc_ft", user=remote.user_id)

        fetched = remote.fetch(doc.uid)
        assert fetched["uid"] == doc.uid
        assert fetched["title"] == "fetch_test_doc_ft"


# ---------------------------------------------------------------------------
# Remote client: get_fs_info and get_fs_children
# ---------------------------------------------------------------------------


def test_remote_get_fs_info(manager_factory, obj_factory):
    """Test get_fs_info retrieves RemoteFileInfo for a sync root."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        # The sync root should be accessible
        root_state = engine.dao.get_state_from_local(Path("/"))
        if root_state and root_state.remote_ref:
            info = remote.get_fs_info(root_state.remote_ref)
            assert isinstance(info, RemoteFileInfo)
            assert info.uid is not None


def test_remote_get_fs_children(manager_factory, obj_factory):
    """Test get_fs_children returns children of a folder."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        root_state = engine.dao.get_state_from_local(Path("/"))
        if root_state and root_state.remote_ref:
            children = remote.get_fs_children(root_state.remote_ref)
            assert isinstance(children, list)


# ---------------------------------------------------------------------------
# Remote client: scroll_descendants
# ---------------------------------------------------------------------------


def test_remote_scroll_descendants(manager_factory, obj_factory):
    """Test scroll_descendants for remote scanning."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        root_state = engine.dao.get_state_from_local(Path("/"))
        if root_state and root_state.remote_ref:
            result = remote.scroll_descendants(
                root_state.remote_ref, None, batch_size=10
            )
            assert "scroll_id" in result
            assert "descendants" in result
            assert isinstance(result["descendants"], list)


# ---------------------------------------------------------------------------
# Remote client: custom metrics headers
# ---------------------------------------------------------------------------


@Options.mock()
def test_remote_custom_global_metrics(manager_factory):
    """Test custom global metrics contain expected keys."""
    manager, engine = manager_factory()
    with manager:
        metrics = engine.remote.custom_global_metrics
        assert isinstance(metrics, dict)
        assert "feature.direct_edit" in metrics


@Options.mock()
def test_remote_reload_global_headers(manager_factory):
    """Test reloading global headers updates metrics."""
    manager, engine = manager_factory()
    with manager:
        from nxdrive.drive.metrics.constants import GLOBAL_METRICS

        engine.remote.reload_global_headers()
        headers = engine.remote.client.headers
        assert GLOBAL_METRICS in headers


# ---------------------------------------------------------------------------
# Remote client: proxy
# ---------------------------------------------------------------------------


def test_remote_set_proxy_none(manager_factory):
    """Test setting proxy to None (direct connection)."""
    manager, engine = manager_factory()
    with manager:
        # Should not raise
        engine.remote.set_proxy(None)


# ---------------------------------------------------------------------------
# Remote client: expand_sync_root_name
# ---------------------------------------------------------------------------


@Options.mock()
def test_remote_expand_sync_root_name(manager_factory, obj_factory):
    """Test expand_sync_root_name adds parent folder names."""
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        # Create nested folders
        parent = obj_factory(title="level0", enable_sync=True, user=remote.user_id)
        obj_factory(title="level1", parent=parent.path, user=remote.user_id)

        # Get FS info for the child and try expand
        root_state = engine.dao.get_state_from_local(Path("/"))
        if root_state and root_state.remote_ref:
            children = remote.get_fs_children(root_state.remote_ref)
            # If we have children, verify expand doesn't crash
            for ch in children:
                if hasattr(ch, "uid") and "WORKSPACE_ROOT" in str(
                    getattr(ch, "uid", "")
                ):
                    expanded = remote.expand_sync_root_name(ch)
                    assert expanded is not None
