import os

from .conftest import OneUserTest


class TestLocalStorageIssue(OneUserTest):
    def test_local_invalid_timestamp(self):
        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/")
        self.engine_1.stop()
        self.local_1.make_file("/", "Test.txt", content=b"plop")
        os.utime(self.local_1.abspath("/Test.txt"), (0, 999_999_999_999_999))
        self.engine_1.start()
        self.wait_sync()
        children = self.remote_document_client_1.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == "Test.txt"
