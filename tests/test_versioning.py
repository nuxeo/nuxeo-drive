# coding: utf-8
import time

from .common import OS_STAT_MTIME_RESOLUTION, TEST_WORKSPACE_PATH, UnitTestCase


class TestVersioning(UnitTestCase):

    def test_versioning(self):
        local = self.local_1
        self.engine_1.start()
        root_remote = self.root_remote
        remote = self.remote_document_client_2

        # Create a file as user 2
        remote.make_file('/', 'Test versioning.txt',
                         content=b'This is version 0')
        assert remote.exists('/Test versioning.txt')
        doc = root_remote.fetch(TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 0)

        # Synchronize it for user 1
        self.wait_sync(wait_for_async=True)
        assert local.exists('/Test versioning.txt')

        # Update it as user 1 => should be versioned
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test versioning.txt', b'Modified content')
        self.wait_sync()
        doc = root_remote.fetch(TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

        # Update it as user 1 => should NOT be versioned
        # since the versioning delay is not passed by
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Test versioning.txt',b'Content twice modified')
        self.wait_sync()
        doc = root_remote.fetch(TEST_WORKSPACE_PATH + '/Test versioning.txt')
        self._assert_version(doc, 0, 1)

    def test_version_restore(self):
        remote = self.remote_document_client_1
        local = self.local_1

        self.engine_1.start()

        # Create a remote doc
        doc = remote.make_file(self.workspace, 'Document to restore.txt',
                               content=b'Initial content.')
        self.wait_sync(wait_for_async=True)
        assert local.exists('/Document to restore.txt')
        assert (local.get_content('/Document to restore.txt')
                == b'Initial content.')

        # Create version 1.0, update content, then restore version 1.0
        remote.create_version(doc, 'Major')
        remote.update_content(doc, b'Updated content.')
        self.wait_sync(wait_for_async=True)
        assert (local.get_content('/Document to restore.txt')
                == b'Updated content.')
        version_uid = remote.get_versions(doc)[0][0]
        remote.restore_version(version_uid)
        self.wait_sync(wait_for_async=True)
        assert (local.get_content('/Document to restore.txt')
                == b'Initial content.')

    def _assert_version(self, doc, major, minor):
        assert doc['properties']['uid:major_version'] == major
        assert doc['properties']['uid:minor_version'] == minor
