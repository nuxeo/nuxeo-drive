from .conftest import OneUserTest


class TestVersioning(OneUserTest):
    def test_version_restore(self):
        remote = self.remote_document_client_1
        local = self.local_1

        self.engine_1.start()

        # Create a remote doc
        doc = remote.make_file(
            self.workspace, "Document to restore.txt", content=b"Initial content."
        )
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Document to restore.txt")
        assert local.get_content("/Document to restore.txt") == b"Initial content."

        # Create version 1.0, update content, then restore version 1.0
        remote.create_version(doc, "Major")
        remote.update(doc, properties={"note:note": "Updated content."})
        self.wait_sync(wait_for_async=True)
        assert local.get_content("/Document to restore.txt") == b"Updated content."
        version_uid = remote.get_versions(doc)[0][0]
        remote.restore_version(version_uid)
        self.wait_sync(wait_for_async=True)
        assert local.get_content("/Document to restore.txt") == b"Initial content."
