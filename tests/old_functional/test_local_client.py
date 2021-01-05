"""
Test LocalClient with normal FS operations and OS-specific ones (simulated).
See local_client_darwin.py and local_client_windows.py for more information.

See NXDRIVE-742.
"""
import hashlib
import os
from pathlib import Path

import pytest

from nxdrive.constants import ROOT, WINDOWS
from nxdrive.exceptions import DuplicationDisabledError, NotFound

from ..markers import not_linux, windows_only
from ..utils import random_png
from . import LocalTest
from .common import OneUserTest

if WINDOWS:
    import win32api


EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = b"Some text content."
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()


class StubLocalClient:
    """
    All tests goes here. If you need to implement a special behavior for
    one OS, override the test method in the class TestLocalClientSimulation.
    Check TestLocalClientSimulation.test_complex_filenames() for a real
    world example.
    """

    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def test_make_documents(self):
        local = self.local_1
        doc_1 = local.make_file("/", "Document 1.txt")
        assert local.exists(doc_1)
        assert not local.get_content(doc_1)
        doc_1_info = local.get_info(doc_1)
        assert doc_1_info.name == "Document 1.txt"
        assert doc_1_info.path == doc_1
        assert doc_1_info.get_digest() == EMPTY_DIGEST
        assert not doc_1_info.folderish
        assert doc_1_info.size == 0

        doc_2 = local.make_file("/", "Document 2.txt", content=SOME_TEXT_CONTENT)
        assert local.exists(doc_2)
        assert local.get_content(doc_2) == SOME_TEXT_CONTENT
        doc_2_info = local.get_info(doc_2)
        assert doc_2_info.name == "Document 2.txt"
        assert doc_2_info.path == doc_2
        assert doc_2_info.get_digest() == SOME_TEXT_DIGEST
        assert not doc_2_info.folderish
        assert doc_2_info.size > 0

        local.delete(doc_2)
        assert local.exists(doc_1)
        assert not local.exists(doc_2)

        folder_1 = local.make_folder("/", "A new folder")
        assert local.exists(folder_1)
        folder_1_info = local.get_info(folder_1)
        assert folder_1_info.name == "A new folder"
        assert folder_1_info.path == folder_1
        assert folder_1_info.folderish
        # A folder has no size
        assert folder_1_info.size == 0

        doc_3 = local.make_file(folder_1, "Document 3.txt", content=SOME_TEXT_CONTENT)
        local.delete(folder_1)
        assert not local.exists(folder_1)
        assert not local.exists(doc_3)

    def test_get_info_invalid_date(self):
        local = self.local_1
        doc_1 = local.make_file("/", "Document 1.txt")
        os.utime(local.abspath("/Document 1.txt"), (0, 999999999999999))
        doc_1_info = local.get_info(doc_1)
        assert doc_1_info.name == "Document 1.txt"
        assert doc_1_info.path == doc_1
        assert doc_1_info.get_digest() == EMPTY_DIGEST
        assert not doc_1_info.folderish

    def test_complex_filenames(self):
        local = self.local_1
        # create another folder with the same title
        title_with_accents = "\xc7a c'est l'\xe9t\xe9 !"

        folder_1 = local.make_folder("/", title_with_accents)
        folder_1_info = local.get_info(folder_1)
        assert folder_1_info.name == title_with_accents

        # create another folder with the same title
        with pytest.raises(DuplicationDisabledError):
            local.make_folder("/", title_with_accents)

        # Create a long file name with weird chars
        long_filename = "\xe9" * 50 + "%$#!()[]{}+_-=';&^" + ".doc"
        file_1 = local.make_file(folder_1, long_filename)
        file_1 = local.get_info(file_1)
        assert file_1.name == long_filename
        assert file_1.path == folder_1_info.path / long_filename

        # Create a file with invalid chars
        invalid_filename = 'a/b\\c*d:e<f>g?h"i|j.doc'
        escaped_filename = "a-b-c-d-e-f-g-h-i-j.doc"
        file_2 = local.make_file(folder_1, invalid_filename)
        file_2 = local.get_info(file_2)
        assert file_2.name == escaped_filename
        assert file_2.path == folder_1_info.path / escaped_filename

    def test_missing_file(self):
        with pytest.raises(NotFound):
            self.local_1.get_info("/Something Missing")

    @pytest.mark.timeout(30)
    def test_case_sensitivity(self):
        local = self.local_1
        sensitive = local.is_case_sensitive()

        local.make_file("/", "abc.txt")
        if sensitive:
            local.make_file("/", "ABC.txt")
        else:
            with pytest.raises(DuplicationDisabledError):
                local.make_file("/", "ABC.txt")
        assert len(local.get_children_info("/")) == sensitive + 1

    @windows_only
    def test_windows_short_names(self):
        """
        Test 8.3 file name convention:
        https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247(v=vs.85).aspx
        """

        local = self.local_1
        remote = self.remote_document_client_1
        long_name = "a" * 32
        short_name = "AAAAAA~1"

        # Create the folder
        folder = local.make_file("/", long_name)
        with pytest.raises(DuplicationDisabledError):
            local.make_file("/", short_name)
        path = local.abspath(folder)
        assert path.name == long_name

        # Get the short name
        short = win32api.GetShortPathName(str(path))
        assert os.path.basename(short) == short_name

        # Sync and check the short name is nowhere
        self.wait_sync()
        children = remote.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == long_name

    def test_get_children_info(self):
        local = self.local_1
        folder_1 = local.make_folder("/", "Folder 1")
        folder_2 = local.make_folder("/", "Folder 2")
        file_1 = local.make_file("/", "File 1.txt", content=b"foo\n")

        # not a direct child of '/'
        local.make_file(folder_1, "File 2.txt", content=b"bar\n")

        # ignored files
        data = b"baz\n"
        local.make_file("/", ".File 2.txt", content=data)
        local.make_file("/", "~$File 2.txt", content=data)
        local.make_file("/", "File 2.txt~", content=data)
        local.make_file("/", "File 2.txt.swp", content=data)
        local.make_file("/", "File 2.txt.lock", content=data)
        local.make_file("/", "File 2.txt.part", content=data)
        if local.is_case_sensitive():
            local.make_file("/", "File 2.txt.LOCK", content=data)
        else:
            with pytest.raises(DuplicationDisabledError):
                local.make_file("/", "File 2.txt.LOCK", content=data)

        workspace_children = local.get_children_info("/")
        assert len(workspace_children) == 3
        assert workspace_children[0].path == file_1
        assert workspace_children[1].path == folder_1
        assert workspace_children[2].path == folder_2

    def test_deep_folders(self):
        # Check that local client can workaround the default Windows
        # MAX_PATH limit
        local = self.local_1
        folder = "/"
        for _i in range(30):
            folder = local.make_folder(folder, "0123456789")

        # Last Level
        last_level_folder_info = local.get_info(folder)
        assert last_level_folder_info.path == Path("0123456789/" * 30)

        # Create a nested file
        deep_file = local.make_file(folder, "File.txt", content=b"Some Content.")

        # Check the consistency of get_children_info and get_info
        deep_file_info = local.get_info(deep_file)
        deep_children = local.get_children_info(folder)
        assert len(deep_children) == 1
        deep_child_info = deep_children[0]
        assert deep_file_info.name == deep_child_info.name
        assert deep_file_info.path == deep_child_info.path
        assert deep_file_info.get_digest() == deep_child_info.get_digest()

        # Update the file content
        local.update_content(deep_file, b"New Content.")
        assert local.get_content(deep_file) == b"New Content."

        # Delete the folder
        local.delete(folder)
        assert not local.exists(folder)
        assert not local.exists(deep_file)

        # Delete the root folder and descendants
        local.delete("/0123456789")
        assert not local.exists("/0123456789")

    def test_get_new_file(self):
        local = self.local_1
        path, os_path, name = local.get_new_file("/", "Document 1.txt")
        assert path == Path("Document 1.txt")
        assert str(os_path).endswith(
            os.path.join(self.workspace_title, "Document 1.txt")
        )
        assert name == "Document 1.txt"
        assert not local.exists(path)
        assert not os_path.exists()

    def test_get_path(self):
        local = self.local_1
        doc = Path("doc.txt")
        abs_path = self.local_nxdrive_folder_1 / self.workspace_title / doc
        assert local.get_path(abs_path) == doc

        # Encoding test
        assert local.get_path("été.txt") == ROOT

    def test_is_equal_digests(self):
        local = self.local_1
        content = b"joe"
        local_path = local.make_file("/", "File.txt", content=content)
        local_digest = hashlib.md5(content).hexdigest()
        # Equal digests
        assert local.is_equal_digests(local_digest, local_digest, local_path)

        # Different digests with same digest algorithm
        other_content = b"jack"
        remote_digest = hashlib.md5(other_content).hexdigest()
        assert local_digest != remote_digest
        assert not local.is_equal_digests(local_digest, remote_digest, local_path)

        # Different digests with different digest algorithms but same content
        remote_digest = hashlib.sha1(content).hexdigest()
        assert local_digest != remote_digest
        assert local.is_equal_digests(local_digest, remote_digest, local_path)

        # Different digests with different digest algorithms and different
        # content
        remote_digest = hashlib.sha1(other_content).hexdigest()
        assert local_digest != remote_digest
        assert not local.is_equal_digests(local_digest, remote_digest, local_path)

    def test_long_path(self):
        """NXDRIVE-1090: Long path names generates duplicata on folder creation.

        The final tree must be:
        .
        └── llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll
            └── llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll
                └── llllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllllll
                    ├── Par îçi
                    │   └── alive.png
                    └── stone.png
        """

        local = self.local_1
        remote = self.remote_document_client_1
        folder = "l" * 90
        folders = [self.workspace]

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Remotely create 3 levels of folders, path will be > 270 chars
        for _ in range(3):
            folders.append(remote.make_folder(folders[-1], folder))

        # Create a file in it
        remote.make_file(folders[-1], "stone.png", content=random_png())
        picture = "/" + "/".join([folder] * 3) + "/stone.png"
        assert remote.exists(picture)

        # Check the whole tree is OK
        tree_needed = [1] * 4  # number of documents in each folder
        tree_current = [len(remote.get_children_info(fol)) for fol in folders]
        assert tree_needed == tree_current

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists(picture)

        # Locally create a new folder and file in it
        path = "/" + "/".join([folder] * 3)
        local.make_folder(path, "Par îçi")
        path += "/Par îçi"
        local.make_file(path, "alive.png", random_png())
        picture = path + "/alive.png"
        assert local.exists(picture)

        self.wait_sync()

        # Check the whole tree is OK
        tree_needed = [1, 1, 1, 2]  # number of documents in each folder
        tree_current = [len(remote.get_children_info(fol)) for fol in folders]
        assert tree_needed == tree_current

        # Finally, check the last long folder contains only one folder and one file
        children = remote.get_children_info(folders[-1])
        assert children[0].name == "Par îçi"
        assert children[1].name == "stone.png"

        # And ensure the deepest folder "Par îçi" contains the lone file "alive.png"
        child = remote.get_children_info(children[0].uid)
        assert len(child) == 1
        assert child[0].name == "alive.png"


class TestLocalClientNative(StubLocalClient, OneUserTest):
    """
    Test LocalClient using Python commands to make FS operations.
    This will simulate Drive actions.
    """

    def get_local_client(self, path):
        return LocalTest(path)

    @pytest.mark.xfail(
        WINDOWS, raises=OSError, reason="Explorer cannot deal with very long paths"
    )
    def test_deep_folders(self):
        """
        It should fail on Windows:
            WindowsError: [Error 206] The filename or extension is too long
        Explorer cannot deal with very long paths.
        """
        super().test_deep_folders()

    def test_remote_changing_case_accentued_folder(self):
        """
        NXDRIVE-1061: Remote rename of an accentued folder on Windows fails.
        I put this test only here because we need to test the real implementation
        of LocalClient.rename().
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Step 1: remotely create an accentued folder
        root = remote.make_folder(self.workspace, "Projet Hémodialyse")
        folder = remote.make_folder(root, "Pièces graphiques")

        self.wait_sync(wait_for_async=True)
        assert local.exists("/Projet Hémodialyse")
        assert local.exists("/Projet Hémodialyse/Pièces graphiques")

        # Step 2: remotely change the case of the subfolder
        remote.update(folder, properties={"dc:title": "Pièces Graphiques"})

        self.wait_sync(wait_for_async=True)
        children = local.get_children_info("/Projet Hémodialyse")
        assert len(children) == 1
        assert children[0].name == "Pièces Graphiques"


@not_linux(reason="GNU/Linux does not use OS-specific LocalClient.")
class TestLocalClientSimulation(StubLocalClient, OneUserTest):
    """
    Test LocalClient using OS-specific commands to make FS operations.
    This will simulate user actions on:
        - Explorer (Windows)
        - File Manager (macOS)
    """

    @pytest.mark.xfail(
        WINDOWS,
        raises=OSError,
        reason="Explorer cannot find the directory as the path is way to long",
    )
    def test_complex_filenames(self):
        """OSError: [Errno 2] No such file or directory"""
        super().test_complex_filenames()

    @pytest.mark.xfail(
        WINDOWS, reason="Explorer cannot find the directory as the path is too long"
    )
    def test_long_path(self):
        """WindowsError: [Errno 3] The system cannot find the specified file"""
        super().test_long_path()

    @pytest.mark.xfail(
        WINDOWS, raises=OSError, reason="Explorer cannot deal with very long paths"
    )
    def test_deep_folders(self):
        """WindowsError: [Error 206] The filename or extension is too long"""
        super().test_deep_folders()
