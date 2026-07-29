from .common import OneUserTest


class TestCopy(OneUserTest):
    def test_synchronize_remote_copy(self):
        local = self.local_1
        remote = self.remote_document_client_1

        # Create a file and a folder in the remote root workspace
        remote.make_file("/", "test.odt", content=b"Some content.")
        remote.make_folder("/", "Test folder")

        # Launch ndrive and check synchronization
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert local.exists("/")
        assert local.exists("/Test folder")
        assert local.exists("/test.odt")

        # Copy the file to the folder remotely
        remote.copy("/test.odt", "/Test folder")

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        assert local.exists("/test.odt")
        assert local.get_content("/test.odt") == b"Some content."
        assert local.exists("/Test folder/test.odt")
        assert local.get_content("/Test folder/test.odt") == b"Some content."
