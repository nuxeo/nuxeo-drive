import time

from .common import OS_STAT_MTIME_RESOLUTION, TwoUsersTest


class TestVersioning2(TwoUsersTest):
    def test_versioning(self):
        local = self.local_1
        self.engine_1.start()
        remote = self.remote_document_client_2

        # Create a file as user 2
        remote.make_file_with_blob("/", "Test versioning.txt", b"This is version 0")
        self.wait_sync()
        assert remote.exists("/Test versioning.txt")
        doc = self.root_remote.fetch(f"{self.ws.path}/Test versioning.txt")
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 1
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Test versioning.txt")

        # Update it as user 1 => should be versioned
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content("/Test versioning.txt", b"Modified content")
        self.wait_sync()
        doc = self.root_remote.fetch(f"{self.ws.path}/Test versioning.txt")
        self._assert_version(doc, 0, 1)

        # Update it as user 1 => should NOT be versioned
        # since the versioning delay is not passed by
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content("/Test versioning.txt", b"Content twice modified")
        self.wait_sync()
        doc = self.root_remote.fetch(f"{self.ws.path}/Test versioning.txt")
        self._assert_version(doc, 0, 1)

    def _assert_version(self, doc, major, minor):
        assert doc["properties"]["uid:major_version"] == major
        assert doc["properties"]["uid:minor_version"] == minor
