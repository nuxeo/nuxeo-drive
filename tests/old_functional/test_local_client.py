# coding: utf-8
"""
Test LocalClient with normal FS operations and OS-specific ones (simulated).
See local_client_darwin.py and local_client_windows.py for more information.

See NXDRIVE-742.
"""
import os

import pytest

from nxdrive.constants import WINDOWS
from nxdrive.exceptions import DuplicationDisabledError

from ..markers import not_linux, windows_only
from ..utils import random_png
from . import LocalTest
from .common import OneUserTest

if WINDOWS:
    import win32api


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
        WINDOWS, reason="Explorer cannot find the directory as the path is too long"
    )
    def test_long_path(self):
        """WindowsError: [Errno 3] The system cannot find the specified file"""
        super().test_long_path()
