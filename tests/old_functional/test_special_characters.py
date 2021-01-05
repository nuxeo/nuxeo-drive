import pytest

from nxdrive.constants import MAC

from ..markers import not_windows
from .common import OneUserTest


class TestSpecialCharacters(OneUserTest):
    @not_windows(reason="Explorer prevents using those characters")
    def test_create_local(self):
        local = self.local_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        folder = local.make_folder("/", "/ * ? < > |")
        local.make_file(folder, "| > < ? * /.txt", content=b"This is a test file")
        self.wait_sync()

        folder_name = "- - - - - -"
        file_name = "- - - - - -.txt"
        # Check the remote folder
        children = remote.get_children(self.ws.path)["entries"]
        assert len(children) == 1
        assert children[0]["title"] == folder_name
        # Check the remote file
        children = remote.get_children(children[0]["path"])["entries"]
        assert len(children) == 1
        assert children[0]["title"] == file_name

        new_folder_name = "abcd"
        new_file_name = "efgh.txt"
        local.rename(f"/{folder_name}", new_folder_name)
        local.rename(f"/{new_folder_name}/{file_name}", new_file_name)
        self.wait_sync()

        # Paths is updated server-side
        info = remote.get_info(f"/{new_folder_name}")
        assert info.name == new_folder_name
        info = remote.get_info(f"/{new_folder_name}/{new_file_name}")
        assert info.name == new_file_name

    @not_windows(reason="Explorer prevents using those characters")
    @pytest.mark.xfail(reason="NXDRIVE-2498", condition=MAC)
    def test_rename_local(self):
        local = self.local_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        folder_name = "abcd"
        file_name = "efgh.txt"
        folder = local.make_folder("/", folder_name)
        local.make_file(folder, file_name, content=b"This is a test file")

        self.wait_sync()
        assert remote.exists(f"/{folder_name}")
        assert remote.exists(f"/{folder_name}/{file_name}")

        new_folder_name = "/ * ? < > |"
        new_folder_name_expected = "- - - - - -"
        new_file_name = "| > < ? * /.txt"
        new_file_name_expected = "- - - - - -.txt"
        local.rename(f"/{folder_name}", new_folder_name)
        local.rename(f"/{new_folder_name_expected}/{file_name}", new_file_name)
        self.wait_sync()

        # Paths is updated server-side
        info = remote.get_info(f"/{new_folder_name_expected}")
        assert info.name == new_folder_name_expected
        info = remote.get_info(f"/{new_folder_name_expected}/{new_file_name_expected}")
        assert info.name == new_file_name_expected

    def test_create_remote(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        folder = remote.make_folder("/", "/ * ? < > |")
        remote.make_file(folder, "| > < ? * /.txt", content=b"This is a test file")
        self.wait_sync(wait_for_async=True)

        folder_name = "- - - - - -"
        file_name = "- - - - - -.txt"
        assert local.exists(f"/{folder_name}")
        assert local.exists(f"/{folder_name}/{file_name}")
