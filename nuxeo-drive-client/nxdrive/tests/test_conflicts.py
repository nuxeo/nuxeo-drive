import os
import time

from nxdrive.tests.common import OS_STAT_MTIME_RESOLUTION
from nxdrive.tests.common_unit_test import UnitTestCase


class TestConflicts(UnitTestCase):

    def setUp(self):
        super(TestConflicts, self).setUp()
        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#' + self.workspace)
        self.file_id = self.remote_file_system_client_1.make_file(self.workspace_id, 'test.txt', 'Some content').uid
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_engine_2=True)
        self.assertTrue(self.local_client_1.exists('/test.txt'))
        self.assertTrue(self.local_client_2.exists('/test.txt'))

    def test_self_conflict(self):
        remote = self.remote_file_system_client_1
        local =  self.local_client_1
        # Update content on both sides by the same user, remote last
        remote.update_content(self.file_id, 'Remote update')
        local.update_content('/test.txt', 'Local update')
        self.wait_sync()

        self.assertEquals(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEquals(local.get_content('/test.txt'), 'Local update')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 1)
        self.assertEquals(remote_children[0].uid, self.file_id)
        self.assertEquals(remote_children[0].name, 'test.txt')
        self.assertEquals(remote.get_content(remote_children[0].uid), 'Remote update')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

        # Update content on both sides by the same user, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self.wait_sync()

        self.assertEquals(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEquals(local.get_content('/test.txt'), 'Local update 2')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 1)
        self.assertEquals(remote_children[0].uid, self.file_id)
        self.assertEquals(remote_children[0].name, 'test.txt')
        self.assertEquals(remote.get_content(remote_children[0].uid), 'Remote update 2')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

    def test_real_conflict(self):
        local = self.local_client_1
        remote = self.remote_file_system_client_2

        # Update content on both sides by different users, remote last
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Race condition is still possible
        remote.update_content(self.file_id, 'Remote update')
        local.update_content('/test.txt', 'Local update')
        self.wait_sync()

        self.assertEquals(remote.get_content(self.file_id), 'Remote update')
        self.assertEquals(local.get_content('/test.txt'), 'Local update')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

        # Update content on both sides by different users, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self.wait_sync()

        self.assertEquals(remote.get_content(self.file_id), 'Remote update 2')
        self.assertEquals(local.get_content('/test.txt'), 'Local update 2')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

    def test_conflict_on_lock(self):
        doc_uid = self.file_id.split("#")[-1]
        local = self.local_client_1
        remote = self.remote_file_system_client_2
        self.remote_document_client_2.lock(doc_uid)
        local.update_content('/test.txt', 'Local update')
        self.wait_sync()
        self.assertEquals(local.get_content('/test.txt'), 'Local update')
        self.assertEquals(remote.get_content(self.file_id), 'Some content')
        remote.update_content(self.file_id, 'Remote update')
        self.wait_sync()
        self.assertEquals(local.get_content('/test.txt'), 'Local update')
        self.assertEquals(remote.get_content(self.file_id), 'Remote update')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")
        self.remote_document_client_2.unlock(doc_uid)
        self.wait_sync()
        self.assertEquals(local.get_content('/test.txt'), 'Local update')
        self.assertEquals(remote.get_content(self.file_id), 'Remote update')
        self.assertEquals(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")
