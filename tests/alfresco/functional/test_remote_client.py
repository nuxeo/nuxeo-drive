"""Functional tests for :class:`nxdrive.alfresco.client.remote.AlfrescoRemote`.

These tests hit a live Alfresco server. When the server is unreachable
or environment variables are missing, they are auto-skipped by the
parent ``conftest.py``'s ``pytest_collection_modifyitems`` hook.
"""

from uuid import uuid4

import pytest

from nxdrive.alfresco.client.remote import AlfrescoRemote


@pytest.fixture()
def remote(alfresco_url, alfresco_user, alfresco_password):
    """Live ``AlfrescoRemote`` client. Password-based auth."""
    r = AlfrescoRemote(
        alfresco_url,
        alfresco_user,
        f"device-{uuid4().hex[:8]}",
        "0.0.0-test",
        password=alfresco_password,
    )
    try:
        yield r
    finally:
        r.close()


class TestCredentials:
    def test_check_credentials_returns_person_entry(self, remote) -> None:
        person = remote.check_credentials()
        # Alfresco People API returns a dict with an ``id`` field.
        assert person
        assert "id" in person or "person" in person


class TestNodesReadOnly:
    """Read-only smoke tests against the server."""

    def test_get_root_node(self, remote) -> None:
        root = remote.get_root_node()
        assert root is not None
        assert getattr(root, "id", "") != ""

    def test_get_filesystem_root_info(self, remote) -> None:
        info = remote.get_filesystem_root_info()
        assert info is not None
        assert getattr(info, "uid", "")


class TestFolderLifecycle:
    """Create → list → rename → delete a folder end-to-end."""

    def test_create_and_delete_folder(self, remote, alfresco_test_folder):
        name = f"ndt-tmp-{uuid4().hex[:8]}"
        folder = remote.make_folder(alfresco_test_folder.id, name)
        try:
            children = remote.get_children(alfresco_test_folder.id)
            assert any(getattr(c, "id", "") == folder.uid for c in children)
        finally:
            remote.delete(folder.uid)

    def test_rename_folder(self, remote, alfresco_test_folder):
        original = f"ndt-orig-{uuid4().hex[:8]}"
        renamed = f"ndt-new-{uuid4().hex[:8]}"
        folder = remote.make_folder(alfresco_test_folder.id, original)
        try:
            info = remote.rename(folder.uid, renamed)
            assert info is not None
        finally:
            remote.delete(folder.uid)
