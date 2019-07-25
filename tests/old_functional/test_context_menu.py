import os
from os.path import isfile

import pytest
from nxdrive.constants import MAC

from .common import OneUserTest


class TestContextMenu(OneUserTest):
    def setUp(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def test_copy_share_link(self):
        """It will test the copy/paste clipboard stuff."""

        if MAC and "JENKINS_URL" in os.environ:
            pytest.skip(
                "macOS 10.11+ limitation: it's not possible to call CFPasteboardCreate when"
                " there is no pasteboard, i.e. when the computer is on the loginwindow."
                " See NXDRIVE-1794 for details."
            )

        manager = self.manager_1
        local = self.local_1

        # Document does not inexist
        with pytest.raises(ValueError):
            manager.ctx_copy_share_link("/a folder/a file.bin")

        # Document exists
        local.make_folder("/", "a folder")
        file = local.make_file("/a folder", "a file.bin", content=b"something")
        self.wait_sync()
        path = local.abspath(file)
        assert isfile(path)
        url = manager.ctx_copy_share_link(path)
        assert url.startswith("http")
        assert manager.osi.cb_get() == url

    def test_get_metadata_infos(self):
        """This will test "Access online" and "Edit metadata" entries."""
        manager = self.manager_1
        local = self.local_1

        # Document does not inexist
        with pytest.raises(ValueError):
            manager.get_metadata_infos("/a folder/a file.bin")

        # Document exists
        local.make_folder("/", "a folder")
        file = local.make_file("/a folder", "a file.bin", content=b"something")
        self.wait_sync()
        path = local.abspath(file)
        assert isfile(path)

        # "Access online" entry
        url = manager.get_metadata_infos(path)
        assert url.startswith("http")

        # "Edit metadata" entry
        url_edit = manager.get_metadata_infos(path, edit=True)
        assert url.startswith("http")
        assert url_edit != url
