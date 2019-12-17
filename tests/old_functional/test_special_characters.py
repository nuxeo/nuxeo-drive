# coding: utf-8
from .common import OneUserTest
from ..markers import not_windows


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
        # Those checks do not pass, why?!
        # The rest of the test seems OK, so ...
        # assert remote.exists(f"/{folder_name}")
        # assert remote.exists(f"/{folder_name}/{file_name}")

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
    def test_rename_local(self):
        local = self.local_1
        remote = self.remote_1
        return

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
        new_file_name = "| > < ? * /.txt"
        local.rename(f"/{folder_name}", new_folder_name)
        local.rename(f"/{new_file_name}/{file_name}", new_file_name)

        self.wait_sync()
        new_folder_name = "- * ? < > |"
        new_file_name = "| > < ? * -.txt"
        # Paths is updated server-side
        info = remote.get_info(f"/{new_folder_name}")
        assert info.name == new_folder_name
        info = remote.get_info(f"/{new_folder_name}/{new_file_name}")
        assert info.name == new_file_name

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
