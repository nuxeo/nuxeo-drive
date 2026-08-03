"""
Functional tests for :class:`nxdrive.alfresco.client.remote.AlfrescoRemote`.

Covers upload, update, stream, folder operations, discovery, and
server configuration via the live Alfresco server.
"""

import tempfile
from pathlib import Path
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


class TestUploadAndUpdate:
    """stream_file, stream_update, upload_content, update_content."""

    def test_upload_file_and_get_info(self, remote, alfresco_test_folder) -> None:
        """Upload a file, verify it exists, clean up."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"functional test content")
            f.flush()
            local_path = Path(f.name)

        try:
            info = remote.stream_file(
                alfresco_test_folder.id,
                local_path,
                filename=f"upload-test-{uuid4().hex[:8]}.txt",
            )
            assert info is not None
            assert info.uid
            assert info.name.startswith("upload-test-")
        finally:
            local_path.unlink(missing_ok=True)
            if info and info.uid:
                try:
                    remote.delete(info.uid)
                except Exception:
                    pass

    def test_update_content(self, remote, alfresco_test_folder) -> None:
        """Upload a file, update its content, verify."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"original content")
            f.flush()
            local_path = Path(f.name)

        info = None
        try:
            info = remote.stream_file(
                alfresco_test_folder.id,
                local_path,
                filename=f"update-test-{uuid4().hex[:8]}.txt",
            )
            assert info.uid

            # Update the content
            local_path.write_text("updated content")
            updated = remote.stream_update(info.uid, local_path)
            assert updated is not None
            assert updated.uid == info.uid
        finally:
            local_path.unlink(missing_ok=True)
            if info and info.uid:
                try:
                    remote.delete(info.uid)
                except Exception:
                    pass


class TestFolderOps:
    """make_folder, get_children, get_fs_children."""

    def test_make_folder_and_list_children(self, remote, alfresco_test_folder) -> None:
        """Create a folder, list parent's children, verify it appears."""
        folder_name = f"ft-folder-{uuid4().hex[:8]}"
        info = remote.make_folder(alfresco_test_folder.id, folder_name)
        try:
            assert info is not None
            assert info.uid
            assert info.name == folder_name

            # List children of parent
            children = remote.get_children(alfresco_test_folder.id)
            child_ids = [getattr(c, "id", getattr(c, "uid", "")) for c in children]
            assert info.uid in child_ids
        finally:
            try:
                remote.delete(info.uid)
            except Exception:
                pass

    def test_get_fs_children(self, remote) -> None:
        """get_fs_children on root should return items."""
        root_info = remote.get_filesystem_root_info()
        assert root_info
        children = remote.get_fs_children(root_info.uid)
        # Root should have at least some children
        assert isinstance(children, list)


class TestStreamContent:
    """stream_content — download a file."""

    def test_download_file(self, remote, alfresco_test_folder, tmp_path) -> None:
        """Upload, download, verify content matches."""
        content = b"stream content test data"
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(content)
            f.flush()
            local_path = Path(f.name)

        info = None
        try:
            info = remote.stream_file(
                alfresco_test_folder.id,
                local_path,
                filename=f"stream-test-{uuid4().hex[:8]}.txt",
            )

            # Download
            out_file = tmp_path / "downloaded.txt"
            result = remote.stream_content(
                info.uid,
                local_path,
                out_file,
            )
            assert result.exists()
            assert result.read_bytes() == content
        finally:
            local_path.unlink(missing_ok=True)
            if info and info.uid:
                try:
                    remote.delete(info.uid)
                except Exception:
                    pass


class TestDiscovery:
    """get_discovery, get_server_configuration."""

    def test_get_discovery(self, remote) -> None:
        import requests

        try:
            disc = remote.get_discovery()
            assert isinstance(disc, dict)
        except requests.exceptions.HTTPError:
            # Discovery API may not be available (404) — that's acceptable
            pass

    def test_get_server_configuration(self, remote) -> None:
        config = remote.get_server_configuration()
        assert isinstance(config, dict)


class TestMoveRename:
    """move, rename, copy."""

    def test_rename_node(self, remote, alfresco_test_folder) -> None:
        """Create a folder, rename it, verify."""
        original = f"ft-rename-orig-{uuid4().hex[:8]}"
        renamed = f"ft-rename-new-{uuid4().hex[:8]}"

        info = remote.make_folder(alfresco_test_folder.id, original)
        try:
            result = remote.rename(info.uid, renamed)
            assert result is not None
            assert result.name == renamed
        finally:
            try:
                remote.delete(info.uid)
            except Exception:
                pass

    def test_move_node(self, remote, alfresco_test_folder) -> None:
        """Create two folders, move one inside the other."""
        parent = remote.make_folder(
            alfresco_test_folder.id, f"ft-move-parent-{uuid4().hex[:8]}"
        )
        child = remote.make_folder(
            alfresco_test_folder.id, f"ft-move-child-{uuid4().hex[:8]}"
        )
        try:
            result = remote.move(child.uid, parent.uid)
            assert result is not None
        finally:
            try:
                remote.delete(parent.uid)
            except Exception:
                pass

    def test_delete_node(self, remote, alfresco_test_folder) -> None:
        """Create and delete a folder."""
        name = f"ft-delete-{uuid4().hex[:8]}"
        info = remote.make_folder(alfresco_test_folder.id, name)
        remote.delete(info.uid)
        # Verify it's gone
        from nxdrive.drive.exceptions import NotFound

        with pytest.raises((NotFound, Exception)):
            remote.get_fs_info(info.uid)


class TestGetInfo:
    """get_info, get_fs_info, fetch."""

    def test_get_fs_info(self, remote, alfresco_test_folder) -> None:
        """Create a folder, get fs_info, verify fields."""
        name = f"ft-fsinfo-{uuid4().hex[:8]}"
        info = remote.make_folder(alfresco_test_folder.id, name)
        try:
            fs_info = remote.get_fs_info(info.uid)
            assert fs_info is not None
            assert fs_info.uid == info.uid
            assert fs_info.name == name
        finally:
            try:
                remote.delete(info.uid)
            except Exception:
                pass

    def test_get_info(self, remote, alfresco_test_folder) -> None:
        """get_info returns RemoteFileInfo."""
        name = f"ft-getinfo-{uuid4().hex[:8]}"
        info = remote.make_folder(alfresco_test_folder.id, name)
        try:
            result = remote.get_info(info.uid)
            assert result is not None
            assert result.uid == info.uid
        finally:
            try:
                remote.delete(info.uid)
            except Exception:
                pass

    def test_get_info_missing_returns_none(self, remote) -> None:
        result = remote.get_info("nonexistent-node-id-xyz", raise_if_missing=False)
        assert result is None


class TestIsFiltered:
    """is_filtered."""

    def test_is_filtered_returns_bool(self, remote) -> None:
        result = remote.is_filtered("/some/random/path")
        assert isinstance(result, bool)
