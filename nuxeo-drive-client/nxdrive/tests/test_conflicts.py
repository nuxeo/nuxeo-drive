import os
import time

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nose.plugins.skip import SkipTest


class TestConflicts(IntegrationTestCase):

    def setUp(self):
        super(TestConflicts, self).setUp()
        # Mark workspace as sync root for user 1 and create file inside it
        self.remote_document_client_1.register_as_root(self.workspace)
        toplevel_folder_info = self.remote_file_system_client_1.get_filesystem_root_info()
        self.workspace_id = self.remote_file_system_client_1.get_children_info(toplevel_folder_info.uid)[0].uid
        self.file_id = self.remote_file_system_client_1.make_file(self.workspace_id, 'test.txt', 'Some content')

    def test_self_conflict(self):
        ctl = self.controller_1
        sb = ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        if not ctl.get_top_level_state(self.local_nxdrive_folder_1).last_remote_modifier:
            raise SkipTest("Self-conflict automatic resolution not implemented in Nuxeo Platform %s"
                           % sb.server_version)
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_file_system_client_1
        syn = ctl.synchronizer

        # Launch first synchronization
        self._sync(syn)
        self.assertTrue(local.exists('/test.txt'))

        # Update content on both sides by the same user, remote last
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update')
        remote.update_content(self.file_id, 'Remote update')
        self._sync(syn, max_loops=2)

        self.assertEquals(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEquals(local.get_content('/test.txt'), 'Remote update')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 1)
        self.assertEquals(remote_children[0].uid, self.file_id)
        self.assertEquals(remote_children[0].name, 'test.txt')
        self.assertEquals(remote.get_content(remote_children[0].uid), 'Remote update')

        # Update content on both sides by the same user, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self._sync(syn, max_loops=2)

        self.assertEquals(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEquals(local.get_content('/test.txt'), 'Local update 2')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 1)
        self.assertEquals(remote_children[0].uid, self.file_id)
        self.assertEquals(remote_children[0].name, 'test.txt')
        self.assertEquals(remote.get_content(remote_children[0].uid), 'Local update 2')

    def test_real_conflict(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_file_system_client_2
        syn = ctl.synchronizer

        # Mark workspace as sync root for user2
        self.remote_document_client_2.register_as_root(self.workspace)

        # Launch first synchronization
        self._sync(syn)
        self.assertTrue(local.exists('/test.txt'))

        # Update content on both sides by different users, remote last
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update')
        remote.update_content(self.file_id, 'Remote update')
        self._sync(syn, max_loops=2)

        local_children = local.get_children_info('/')
        self.assertEquals(len(local_children), 2)
        child1 = local_children[0]
        child2 = local_children[1]
        self.assertTrue(child1.path.startswith('/test (%s' % self.user_1))
        self.assertEquals(local.get_content(child1.path), 'Local update')
        self.assertEquals(child2.path, '/test.txt')
        self.assertEquals(local.get_content(child2.path), 'Remote update')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 2)
        child1 = remote_children[0]
        child2 = remote_children[1]
        self.assertEquals(child1.name, 'test.txt')
        self.assertEquals(remote.get_content(child1.uid), 'Remote update')
        self.assertTrue(child2.name.startswith('test (%s' % self.user_1))
        self.assertEquals(remote.get_content(child2.uid), 'Local update')

        # Update content on both sides, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self._sync(syn, max_loops=2)

        local_children = local.get_children_info('/')
        self.assertEquals(len(local_children), 3)
        child1 = local_children[0]
        child2 = local_children[1]
        child3 = local_children[2]
        self.assertTrue(child1.path.startswith('/test (%s' % self.user_1))
        self.assertTrue(local.get_content(child1.path).startswith('Local update'))
        self.assertTrue(child2.path.startswith('/test (%s' % self.user_1))
        self.assertTrue(local.get_content(child2.path).startswith('Local update'))
        self.assertEquals(child3.path, '/test.txt')
        self.assertEquals(local.get_content(child3.path), 'Remote update 2')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEquals(len(remote_children), 3)
        child1 = remote_children[0]
        child2 = remote_children[1]
        child3 = remote_children[2]
        self.assertEquals(child1.name, 'test.txt')
        self.assertEquals(remote.get_content(child1.uid), 'Remote update 2')
        self.assertTrue(child2.name.startswith('test (%s' % self.user_1))
        self.assertTrue(remote.get_content(child2.uid).startswith('Local update'))
        self.assertTrue(child3.name.startswith('test (%s' % self.user_1))
        self.assertTrue(remote.get_content(child3.uid).startswith('Local update'))

    def _sync(self, syn, max_loops=1, wait_for_async=True):
        if wait_for_async:
            self.wait_audit_change_finder_if_needed()
            self.wait()
        syn.loop(delay=0, max_loops=max_loops)
