# coding: utf-8
from nxdrive.constants import WINDOWS

from .common import UnitTestCase


class TestSpecialCharacters(UnitTestCase):
    def test_create_local(self):
        local = self.local_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        local.make_folder("/", "/ * ? < > |")
        local.make_file("/", "| > < ? * /.txt", content=b"This is a test file")

        self.wait_sync()
        folder_name = "- - - - - -" if WINDOWS else "- * ? < > |"
        assert remote.exists(f"/{folder_name}")

        file_name = "- - - - - -.txt" if WINDOWS else "| > < ? * -.txt"
        assert remote.exists(f"/{file_name}")

        new_folder_name = "abcd"
        new_file_name = "efgh.txt"
        local.rename(f"/{folder_name}", new_folder_name)
        local.rename(f"/{file_name}", new_file_name)

        self.wait_sync()
        # Paths don't change server-side
        info = remote.get_info(f"/{folder_name}")
        assert info.name == new_folder_name
        info = remote.get_info(f"/{file_name}")
        assert info.name == new_file_name

    def test_rename_local(self):
        local = self.local_1
        remote = self.remote_1
        return

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        folder_name = "abcd"
        file_name = "efgh.txt"
        local.make_folder("/", folder_name)
        local.make_file("/", file_name, content=b"This is a test file")

        self.wait_sync()
        assert remote.exists(f"/{folder_name}")
        assert remote.exists(f"/{file_name}")

        new_folder_name = "/ * ? < > |"
        new_file_name = "| > < ? * /.txt"
        local.rename(f"/{folder_name}", new_folder_name)
        local.rename(f"/{file_name}", new_file_name)

        self.wait_sync()
        new_folder_name = "- - - - - -" if WINDOWS else "- * ? < > |"
        new_file_name = "- - - - - -.txt" if WINDOWS else "| > < ? * -.txt"
        # Paths don't change server-side
        info = remote.get_info(f"/{folder_name}")
        assert info.name == new_folder_name
        info = remote.get_info(f"/{file_name}")
        assert info.name == new_file_name

    def test_create_remote(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        remote.make_folder("/", "/ * ? < > |")
        remote.make_file("/", "| > < ? * /.txt", content=b"This is a test file")

        self.wait_sync()
        folder_name = "- - - - - -" if WINDOWS else "- * ? < > |"
        assert local.exists(f"/{folder_name}")

        file_name = "- - - - - -.txt" if WINDOWS else "| > < ? * -.txt"
        assert local.exists(f"/{file_name}")
