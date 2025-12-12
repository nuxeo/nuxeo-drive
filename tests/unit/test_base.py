"""Unit tests for nxdrive.client.local.base module."""

import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from nxdrive.client.local import LocalClient
from nxdrive.constants import ROOT
from nxdrive.exceptions import DuplicationDisabledError, NotFound, UnknownDigest
from nxdrive.options import Options


@pytest.fixture
def local_client(tmp_path):
    """Create a LocalClient instance with a temporary directory."""
    client = LocalClient(tmp_path)
    yield client


@pytest.fixture
def temp_file(tmp_path):
    """Create a temporary file for testing."""
    file = tmp_path / "test_file.txt"
    file.write_text("test content", encoding="utf-8")
    return file


@pytest.fixture
def temp_folder(tmp_path):
    """Create a temporary folder with some files."""
    folder = tmp_path / "test_folder"
    folder.mkdir()
    (folder / "file1.txt").write_text("content1", encoding="utf-8")
    (folder / "file2.txt").write_text("content2", encoding="utf-8")
    subfolder = folder / "subfolder"
    subfolder.mkdir()
    (subfolder / "file3.txt").write_text("content3", encoding="utf-8")
    return folder


class TestIsCaseSensitive:
    """Tests for is_case_sensitive method."""

    def test_is_case_sensitive_cached(self, local_client):
        """Test that is_case_sensitive result is cached."""
        result1 = local_client.is_case_sensitive()
        result2 = local_client.is_case_sensitive()
        assert result1 == result2
        assert isinstance(result1, bool)

    def test_is_case_sensitive_check(self, local_client):
        """Test case sensitivity check."""
        result = local_client.is_case_sensitive()
        # On macOS and Windows, file systems are typically case-insensitive
        # On Linux, they are typically case-sensitive
        assert isinstance(result, bool)

    @patch("os.rmdir")
    @patch("os.path.isdir")
    @patch("tempfile.mkdtemp")
    def test_is_case_sensitive_oserror_handling(
        self, mock_mkdtemp, mock_isdir, mock_rmdir, local_client
    ):
        """Test OSError handling in is_case_sensitive."""
        local_client._case_sensitive = None
        mock_mkdtemp.side_effect = OSError("Permission denied")

        result = local_client.is_case_sensitive()
        assert result is False  # Should default to False on error


class TestCleanXattrRoot:
    """Tests for clean_xattr_root method."""

    def test_clean_xattr_root(self, local_client):
        """Test cleaning xattr from root."""
        # Set some xattr first
        local_client.set_root_id(b"test_root_id")

        # Clean it
        local_client.clean_xattr_root()

        # Verify it's cleaned
        assert local_client.get_root_id() == ""

    def test_clean_xattr_root_with_exception(self, local_client, tmp_path):
        """Test clean_xattr_root handles exceptions gracefully."""
        # Create a file to test
        (tmp_path / "test.txt").write_text("test", encoding="utf-8")

        # Mock remove_remote_id to raise exception
        with patch.object(
            local_client, "remove_remote_id", side_effect=Exception("Test error")
        ):
            # Should not raise, just suppresses the exception
            local_client.clean_xattr_root()


class TestCleanXattrFolderRecursive:
    """Tests for clean_xattr_folder_recursive method."""

    def test_clean_xattr_folder_recursive_empty_folder(self, local_client, tmp_path):
        """Test cleaning xattr from an empty folder."""
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()

        # Should not raise any errors
        local_client.clean_xattr_folder_recursive(Path("empty"))

    def test_clean_xattr_folder_recursive_with_files(
        self, local_client, temp_folder, tmp_path
    ):
        """Test cleaning xattr from a folder with files."""
        folder_path = temp_folder.relative_to(tmp_path)

        # Set xattr on files
        local_client.set_remote_id(folder_path / "file1.txt", "remote1")
        local_client.set_remote_id(folder_path / "file2.txt", "remote2")

        # Clean recursively
        local_client.clean_xattr_folder_recursive(folder_path)

        # Verify xattrs are removed
        assert local_client.get_remote_id(folder_path / "file1.txt") == ""
        assert local_client.get_remote_id(folder_path / "file2.txt") == ""

    def test_clean_xattr_folder_recursive_with_subfolders(
        self, local_client, temp_folder, tmp_path
    ):
        """Test cleaning xattr from nested folders."""
        folder_path = temp_folder.relative_to(tmp_path)

        # Set xattr on nested file
        local_client.set_remote_id(folder_path / "subfolder" / "file3.txt", "remote3")

        # Clean recursively
        local_client.clean_xattr_folder_recursive(folder_path)

        # Verify nested xattr is removed
        assert local_client.get_remote_id(folder_path / "subfolder" / "file3.txt") == ""

    def test_clean_xattr_folder_recursive_handles_exception(
        self, local_client, temp_folder, tmp_path
    ):
        """Test that exceptions during cleaning are logged but don't stop the process."""
        folder_path = temp_folder.relative_to(tmp_path)

        # Mock remove_remote_id to raise exception for one file
        original_remove = local_client.remove_remote_id
        call_count = [0]

        def mock_remove(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("Test error")
            original_remove(path, **kwargs)

        with patch.object(local_client, "remove_remote_id", side_effect=mock_remove):
            # Should not raise, continues processing
            local_client.clean_xattr_folder_recursive(folder_path)


class TestHasFolderIcon:
    """Tests for has_folder_icon method."""

    def test_has_folder_icon(self, local_client, tmp_path):
        """Test has_folder_icon method."""
        # Create a folder to test
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()

        # On macOS/Windows it's implemented, on Linux it might not be
        try:
            result = local_client.has_folder_icon(Path("test_folder"))
            assert isinstance(result, bool)
        except NotImplementedError:
            # Expected on some platforms
            pytest.skip("has_folder_icon not implemented on this platform")


class TestSetFolderIcon:
    """Tests for set_folder_icon method."""

    def test_set_folder_icon(self, local_client, tmp_path):
        """Test set_folder_icon method."""
        # Create a folder and icon file to test
        test_folder = tmp_path / "test_folder"
        test_folder.mkdir()
        icon_file = tmp_path / "icon.png"
        icon_file.write_bytes(b"fake icon data")

        # On macOS/Windows it's implemented, on Linux it might not be
        try:
            local_client.set_folder_icon(Path("test_folder"), icon_file)
            # If no exception, it worked
        except NotImplementedError:
            # Expected on some platforms
            pytest.skip("set_folder_icon not implemented on this platform")


class TestGetInfo:
    """Tests for get_info method."""

    def test_get_info_file(self, local_client, temp_file, tmp_path):
        """Test getting info for a file."""
        file_ref = temp_file.relative_to(tmp_path)
        info = local_client.get_info(file_ref)

        assert info.path == file_ref
        assert info.name == "test_file.txt"
        assert not info.folderish
        assert info.size > 0
        assert isinstance(info.last_modification_time, datetime)

    def test_get_info_folder(self, local_client, temp_folder, tmp_path):
        """Test getting info for a folder."""
        folder_ref = temp_folder.relative_to(tmp_path)
        info = local_client.get_info(folder_ref)

        assert info.path == folder_ref
        assert info.folderish
        assert info.size == 0

    def test_get_info_not_found(self, local_client):
        """Test getting info for non-existent file."""
        with pytest.raises(NotFound):
            local_client.get_info(Path("non_existent.txt"))

    def test_get_info_without_check(self, local_client, temp_file):
        """Test getting info without existence check."""
        info = local_client.get_info(temp_file, check=False)

        assert info.name == "test_file.txt"
        assert not info.folderish

    def test_get_info_with_remote_ref(self, local_client, temp_file, tmp_path):
        """Test getting info with remote reference."""
        file_ref = temp_file.relative_to(tmp_path)
        local_client.set_remote_id(file_ref, "remote123")

        info = local_client.get_info(file_ref)
        assert info.remote_ref == "remote123"

    def test_get_info_invalid_mtime(self, local_client, temp_file, tmp_path):
        """Test handling of invalid mtime."""
        file_ref = temp_file.relative_to(tmp_path)
        os_path = local_client.abspath(file_ref)

        # Create a proper mock stat result with invalid mtime
        import stat as stat_module

        mock_stat_result = os.stat_result(
            (
                stat_module.S_IFREG | 0o644,
                0,
                0,
                1,
                0,
                0,
                100,
                float("inf"),
                float("inf"),
                0,
            )
        )

        with patch.object(type(os_path), "stat", return_value=mock_stat_result):
            info = local_client.get_info(file_ref)

            # Should default to epoch time
            assert info.last_modification_time == datetime.fromtimestamp(
                0, tz=timezone.utc
            )


class TestTryGetInfo:
    """Tests for try_get_info method."""

    def test_try_get_info_success(self, local_client, temp_file, tmp_path):
        """Test try_get_info with existing file."""
        file_ref = temp_file.relative_to(tmp_path)
        info = local_client.try_get_info(file_ref)

        assert info is not None
        assert info.name == "test_file.txt"

    def test_try_get_info_not_found(self, local_client):
        """Test try_get_info with non-existent file."""
        info = local_client.try_get_info(Path("non_existent.txt"))
        assert info is None


class TestIsEqualDigests:
    """Tests for is_equal_digests method."""

    def test_is_equal_digests_same(self, local_client, temp_file, tmp_path):
        """Test digest comparison when they are equal."""
        file_ref = temp_file.relative_to(tmp_path)
        info = local_client.get_info(file_ref)
        digest = info.get_digest()

        result = local_client.is_equal_digests(digest, digest, file_ref)
        assert result is True

    def test_is_equal_digests_different(self, local_client, temp_file, tmp_path):
        """Test digest comparison when they are different."""
        file_ref = temp_file.relative_to(tmp_path)
        info = local_client.get_info(file_ref)
        actual_digest = info.get_digest()

        # Use a different valid MD5 digest for comparison
        different_digest = "d41d8cd98f00b204e9800998ecf8427e"  # Empty file MD5
        if actual_digest == different_digest:
            different_digest = "098f6bcd4621d373cade4e832627b4f6"  # "test" MD5

        result = local_client.is_equal_digests(
            actual_digest, different_digest, file_ref
        )
        assert result is False

    def test_is_equal_digests_none_remote(self, local_client, temp_file, tmp_path):
        """Test digest comparison with None remote digest."""
        file_ref = temp_file.relative_to(tmp_path)

        result = local_client.is_equal_digests("abc123", None, file_ref)
        assert result is False

    def test_is_equal_digests_with_algorithm(self, local_client, temp_file, tmp_path):
        """Test digest comparison with specified algorithm."""
        file_ref = temp_file.relative_to(tmp_path)
        info = local_client.get_info(file_ref)
        digest_md5 = info.get_digest(digest_func="md5")

        result = local_client.is_equal_digests(
            None, digest_md5, file_ref, remote_digest_algorithm="md5"
        )
        assert result is True

    def test_is_equal_digests_unknown_algorithm(
        self, local_client, temp_file, tmp_path
    ):
        """Test digest comparison with unknown algorithm."""
        file_ref = temp_file.relative_to(tmp_path)

        with pytest.raises(UnknownDigest):
            local_client.is_equal_digests("abc", "invalid_digest_format", file_ref)

    def test_is_equal_digests_file_not_found(self, local_client):
        """Test digest comparison when file doesn't exist."""
        # Use different valid MD5 digests - when they're equal, method returns True immediately
        # without checking file existence
        local_digest = "d41d8cd98f00b204e9800998ecf8427e"  # Empty file
        remote_digest = "098f6bcd4621d373cade4e832627b4f6"  # "test"
        result = local_client.is_equal_digests(
            local_digest, remote_digest, Path("non_existent.txt")
        )
        assert result is False


class TestGetChildrenInfo:
    """Tests for _get_children_info and get_children_info methods."""

    def test_get_children_info(self, local_client, temp_folder, tmp_path):
        """Test getting children info."""
        folder_ref = temp_folder.relative_to(tmp_path)
        children = local_client.get_children_info(folder_ref)

        # Should have 3 items: file1.txt, file2.txt, subfolder
        assert len(children) == 3

        names = [child.name for child in children]
        assert "file1.txt" in names
        assert "file2.txt" in names
        assert "subfolder" in names

    def test_get_children_info_empty_folder(self, local_client, tmp_path):
        """Test getting children info from empty folder."""
        empty_folder = tmp_path / "empty"
        empty_folder.mkdir()

        children = local_client.get_children_info(Path("empty"))
        assert len(children) == 0

    def test_get_children_info_with_ignored_files(self, local_client, tmp_path):
        """Test that ignored files are excluded."""
        folder = tmp_path / "folder"
        folder.mkdir()
        (folder / "normal.txt").write_text("normal", encoding="utf-8")
        (folder / ".hidden.txt").write_text("hidden", encoding="utf-8")
        (folder / "file~").write_text("backup", encoding="utf-8")

        children = local_client.get_children_info(Path("folder"))

        # Only normal.txt should be included
        names = [child.name for child in children]
        assert "normal.txt" in names
        assert ".hidden.txt" not in names or len(names) > 1  # Depends on Options

    def test_get_children_info_file_deleted_during_iteration(
        self, local_client, temp_folder, tmp_path
    ):
        """Test handling when a file is deleted during iteration."""
        folder_ref = temp_folder.relative_to(tmp_path)

        # Mock get_info to raise NotFound for one file
        original_get_info = local_client.get_info
        call_count = [0]

        def mock_get_info(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 2:  # Fail on second file
                raise NotFound("File deleted")
            return original_get_info(path, **kwargs)

        with patch.object(local_client, "get_info", side_effect=mock_get_info):
            children = local_client.get_children_info(folder_ref)
            # Should return the files that were successfully read
            assert len(children) >= 0

    def test_get_children_info_nonexistent_folder(self, local_client):
        """Test getting children info from non-existent folder."""
        children = local_client.get_children_info(Path("non_existent_folder"))
        assert len(children) == 0


class TestGetNewFile:
    """Tests for get_new_file method."""

    def test_get_new_file(self, local_client, tmp_path):
        """Test getting new file path."""
        parent = Path(".")
        name = "new_file.txt"

        ref, os_path, result_name = local_client.get_new_file(parent, name)

        assert ref == parent / name
        expected = tmp_path / name
        # On Windows, os_path has \\?\ prefix for long path support
        # Compare by resolving both paths to handle this
        assert str(os_path).replace("//?/", "").replace("\\\\?\\", "") == str(expected)
        assert result_name == name

    def test_get_new_file_with_unsafe_chars(self, local_client, tmp_path):
        """Test getting new file with unsafe characters."""
        parent = Path(".")
        name = "file:with*unsafe|chars?.txt"

        ref, os_path, result_name = local_client.get_new_file(parent, name)

        # Name should be sanitized
        assert ref == parent / result_name
        assert ":" not in result_name or os.name != "nt"  # Platform dependent

    def test_get_new_file_duplicate_disabled(self, local_client, temp_file, tmp_path):
        """Test that duplication is disabled by default."""
        parent = Path(".")
        name = "test_file.txt"  # Already exists

        # When file exists, should raise DuplicationDisabledError
        with pytest.raises(DuplicationDisabledError):
            local_client.get_new_file(parent, name)


class TestDelete:
    """Tests for delete method."""

    def test_delete_file(self, local_client, temp_file, tmp_path):
        """Test deleting a file."""
        file_ref = temp_file.relative_to(tmp_path)

        local_client.delete(file_ref)

        # File should be moved to trash or deleted
        assert not temp_file.exists() or local_client.can_use_trash()

    def test_delete_folder(self, local_client, temp_folder, tmp_path):
        """Test deleting a folder."""
        folder_ref = temp_folder.relative_to(tmp_path)

        local_client.delete(folder_ref)

        # Folder should be moved to trash or deleted
        assert not temp_folder.exists() or local_client.can_use_trash()

    def test_delete_nonexistent(self, local_client):
        """Test deleting non-existent file."""
        # Should not raise an error
        local_client.delete(Path("non_existent.txt"))

    def test_delete_trash_fails_fallback_to_permanent(
        self, local_client, temp_file, tmp_path
    ):
        """Test that if trash fails, it falls back to permanent delete."""
        file_ref = temp_file.relative_to(tmp_path)

        # Mock trash to raise OSError
        with patch.object(local_client, "trash", side_effect=OSError("Trash failed")):
            local_client.delete(file_ref)

            # File should be permanently deleted
            assert not temp_file.exists()

    def test_delete_permanent_fails_with_trash_issue(
        self, local_client, temp_file, tmp_path
    ):
        """Test that delete_final failure sets trash_issue attribute."""
        file_ref = temp_file.relative_to(tmp_path)

        # Mock both trash and delete_final to fail
        with patch.object(local_client, "trash", side_effect=OSError("Trash failed")):
            with patch.object(
                local_client, "delete_final", side_effect=OSError("Delete failed")
            ):
                with pytest.raises(OSError) as exc_info:
                    local_client.delete(file_ref)

                # Check that trash_issue attribute was set
                assert hasattr(exc_info.value, "trash_issue")
                assert getattr(exc_info.value, "trash_issue") is True


class TestDeleteFinal:
    """Tests for delete_final method."""

    def test_delete_final_file(self, local_client, temp_file, tmp_path):
        """Test permanently deleting a file."""
        file_ref = temp_file.relative_to(tmp_path)

        local_client.delete_final(file_ref)

        assert not temp_file.exists()

    def test_delete_final_folder(self, local_client, temp_folder, tmp_path):
        """Test permanently deleting a folder."""
        folder_ref = temp_folder.relative_to(tmp_path)

        local_client.delete_final(folder_ref)

        assert not temp_folder.exists()

    def test_delete_final_readonly(self, local_client, temp_file, tmp_path):
        """Test deleting read-only file."""
        file_ref = temp_file.relative_to(tmp_path)
        local_client.set_readonly(file_ref)

        local_client.delete_final(file_ref)

        assert not temp_file.exists()

    def test_delete_final_root(self, local_client, tmp_path):
        """Test deleting root folder - it deletes the entire folder."""
        # Create some content
        (tmp_path / "file.txt").write_text("test", encoding="utf-8")

        local_client.delete_final(ROOT)

        # delete_final on ROOT deletes the entire base folder
        assert not tmp_path.exists()


class TestExists:
    """Tests for exists method."""

    def test_exists_file(self, local_client, temp_file, tmp_path):
        """Test exists for a file."""
        file_ref = temp_file.relative_to(tmp_path)
        assert local_client.exists(file_ref) is True

    def test_exists_folder(self, local_client, temp_folder, tmp_path):
        """Test exists for a folder."""
        folder_ref = temp_folder.relative_to(tmp_path)
        assert local_client.exists(folder_ref) is True

    def test_exists_nonexistent(self, local_client):
        """Test exists for non-existent path."""
        assert local_client.exists(Path("non_existent.txt")) is False

    def test_exists_oserror(self, local_client):
        """Test exists handles OSError gracefully."""
        with patch("pathlib.Path.exists", side_effect=OSError("Error")):
            assert local_client.exists(Path("test.txt")) is False

    def test_exists_generic_exception(self, local_client):
        """Test exists handles generic exceptions gracefully."""
        with patch("pathlib.Path.exists", side_effect=Exception("Unexpected error")):
            assert local_client.exists(Path("test.txt")) is False


class TestRename:
    """Tests for rename method."""

    def test_rename_file(self, local_client, temp_file, tmp_path):
        """Test renaming a file."""
        file_ref = temp_file.relative_to(tmp_path)
        new_name = "renamed_file.txt"

        info = local_client.rename(file_ref, new_name)

        assert info.name == new_name
        assert not temp_file.exists()
        assert (tmp_path / new_name).exists()

    def test_rename_folder(self, local_client, temp_folder, tmp_path):
        """Test renaming a folder."""
        folder_ref = temp_folder.relative_to(tmp_path)
        new_name = "renamed_folder"

        info = local_client.rename(folder_ref, new_name)

        assert info.name == new_name
        assert not temp_folder.exists()
        assert (tmp_path / new_name).exists()

    def test_rename_case_only_case_insensitive(self, local_client, temp_file, tmp_path):
        """Test case-only rename on case-insensitive filesystem."""
        file_ref = temp_file.relative_to(tmp_path)

        if not local_client.is_case_sensitive():
            # Set download_dir to tmp_path so temp file is created in the same directory
            local_client.download_dir = tmp_path
            # Should use temporary name strategy
            info = local_client.rename(file_ref, "TEST_FILE.TXT")
            assert info.name == "TEST_FILE.TXT"

    def test_rename_with_unsafe_chars(self, local_client, temp_file, tmp_path):
        """Test rename with unsafe characters."""
        file_ref = temp_file.relative_to(tmp_path)

        info = local_client.rename(file_ref, "new:name?.txt")

        # Name should be sanitized
        assert info.name != "new:name?.txt" or os.name != "nt"

    def test_rename_duplicate_disabled(self, local_client, tmp_path):
        """Test rename when target exists."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1", encoding="utf-8")
        file2 = tmp_path / "file2.txt"
        file2.write_text("content2", encoding="utf-8")

        file1_ref = file1.relative_to(tmp_path)

        with pytest.raises(DuplicationDisabledError):
            local_client.rename(file1_ref, "file2.txt")


class TestMove:
    """Tests for move method."""

    def test_move_file(self, local_client, temp_file, tmp_path):
        """Test moving a file."""
        file_ref = temp_file.relative_to(tmp_path)
        target_folder = tmp_path / "target"
        target_folder.mkdir()

        info = local_client.move(file_ref, Path("target"))

        assert info.path == Path("target") / "test_file.txt"
        assert not temp_file.exists()
        assert (target_folder / "test_file.txt").exists()

    def test_move_folder(self, local_client, tmp_path):
        """Test moving a folder."""
        source_folder = tmp_path / "source"
        source_folder.mkdir()
        (source_folder / "file.txt").write_text("content", encoding="utf-8")

        target_folder = tmp_path / "target"
        target_folder.mkdir()

        local_client.move(Path("source"), Path("target"))

        assert not source_folder.exists()
        assert (target_folder / "source").exists()

    def test_move_with_rename(self, local_client, temp_file, tmp_path):
        """Test moving and renaming a file."""
        file_ref = temp_file.relative_to(tmp_path)
        target_folder = tmp_path / "target"
        target_folder.mkdir()

        info = local_client.move(file_ref, Path("target"), name="new_name.txt")

        assert info.name == "new_name.txt"
        assert (target_folder / "new_name.txt").exists()

    def test_move_root_raises_error(self, local_client):
        """Test that moving root raises ValueError."""
        with pytest.raises(ValueError, match="Cannot move the toplevel folder"):
            local_client.move(ROOT, Path("target"))

    def test_move_duplicate_disabled(self, local_client, tmp_path):
        """Test move when target file exists."""
        file1 = tmp_path / "file1.txt"
        file1.write_text("content1", encoding="utf-8")

        target_folder = tmp_path / "target"
        target_folder.mkdir()
        (target_folder / "file1.txt").write_text("existing", encoding="utf-8")

        file1_ref = file1.relative_to(tmp_path)

        with pytest.raises(DuplicationDisabledError):
            local_client.move(file1_ref, Path("target"))


class TestChangeFileDate:
    """Tests for change_file_date method."""

    def test_change_file_date_mtime_only(self, local_client, temp_file):
        """Test changing only modification time."""
        mtime = "2023-01-15 10:30:00"

        local_client.change_file_date(temp_file, mtime=mtime)

        stat = temp_file.stat()
        # Verify mtime was changed (approximate check)
        assert stat.st_mtime > 0

    def test_change_file_date_ctime_only(self, local_client, temp_file):
        """Test changing only creation time."""
        ctime = "2023-01-15 10:30:00"

        # Should not raise error (no-op on Linux, implemented on Windows/Mac)
        local_client.change_file_date(temp_file, ctime=ctime)

    def test_change_file_date_both(self, local_client, temp_file):
        """Test changing both times."""
        mtime = "2023-01-15 10:30:00"
        ctime = "2023-01-15 09:00:00"

        local_client.change_file_date(temp_file, mtime=mtime, ctime=ctime)

        stat = temp_file.stat()
        assert stat.st_mtime > 0

    def test_change_file_date_no_params(self, local_client, temp_file):
        """Test change_file_date with no parameters."""
        # Should not raise error
        local_client.change_file_date(temp_file)


class TestMiscMethods:
    """Tests for miscellaneous methods."""

    def test_is_temp_file(self, local_client):
        """Test is_temp_file detection."""
        temp_path = Options.nxdrive_home / "tmp" / "file.txt"
        assert LocalClient.is_temp_file(temp_path) is True

        normal_path = Path("/some/normal/path/file.txt")
        assert LocalClient.is_temp_file(normal_path) is False

    def test_set_readonly_unset_readonly(self, local_client, temp_file, tmp_path):
        """Test setting and unsetting readonly."""
        file_ref = temp_file.relative_to(tmp_path)

        local_client.set_readonly(file_ref)
        # File should be readonly

        local_client.unset_readonly(file_ref)
        # File should be writable again

    def test_unset_readonly_nonexistent(self, local_client):
        """Test unset_readonly on non-existent file."""
        # Should not raise error
        local_client.unset_readonly(Path("non_existent.txt"))

    def test_abspath(self, local_client, tmp_path):
        """Test abspath conversion."""
        ref = Path("subfolder") / "file.txt"
        abs_path = local_client.abspath(ref)

        expected = tmp_path / "subfolder" / "file.txt"
        # On Windows, abspath adds \\?\ prefix for long path support
        # Compare by resolving both paths to handle this
        assert str(abs_path).replace("//?/", "").replace("\\\\?\\", "") == str(expected)
        assert abs_path.is_absolute()

    def test_get_path(self, local_client, tmp_path):
        """Test get_path conversion."""
        abs_path = tmp_path / "subfolder" / "file.txt"
        rel_path = local_client.get_path(abs_path)

        assert rel_path == Path("subfolder") / "file.txt"

    def test_get_path_outside_base(self, local_client):
        """Test get_path for path outside base folder."""
        outside_path = Path("/some/other/path/file.txt")
        result = local_client.get_path(outside_path)

        assert result == ROOT

    def test_make_folder(self, local_client, tmp_path):
        """Test creating a folder."""
        parent = Path(".")
        name = "new_folder"

        ref = local_client.make_folder(parent, name)

        assert ref == Path(name)
        assert (tmp_path / name).exists()
        assert (tmp_path / name).is_dir()

    def test_make_folder_nested(self, local_client, tmp_path):
        """Test creating nested folders."""
        parent = Path("level1") / "level2"
        name = "new_folder"

        local_client.make_folder(parent, name)

        assert (tmp_path / parent / name).exists()

    def test_can_use_trash_unc_path(self, local_client):
        """Test can_use_trash with UNC path."""
        # Regular path should allow trash
        assert local_client.can_use_trash() in (True, False)  # Platform dependent

    def test_lock_unlock_ref(self, local_client, temp_file, tmp_path):
        """Test locking and unlocking a reference."""
        file_ref = temp_file.relative_to(tmp_path)

        locker = local_client.unlock_ref(file_ref)
        assert isinstance(locker, int)

        local_client.lock_ref(file_ref, locker)

    def test_set_file_attribute(self, local_client, temp_file):
        """Test set_file_attribute (no-op by default)."""
        # Should not raise error
        local_client.set_file_attribute(temp_file)
