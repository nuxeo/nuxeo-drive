import time
from nose.plugins.skip import SkipTest

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME


class TestDriveEdit(IntegrationTestCase):

    locally_edited_path = ('/default-domain/UserWorkspaces/'
                           + 'nuxeoDriveTestUser-user-1/Collections/'
                           + LOCALLY_EDITED_FOLDER_NAME)

    def test_drive_edit_non_synced_doc(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create file in test workspace (non sync root)
        doc_id = remote.make_file('/', 'test.odt', 'Some content.')

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertEquals(local.get_content('/%s/test.odt'
                                            % LOCALLY_EDITED_FOLDER_NAME),
                          'Some content.')

        # Check Locally Edited collection exists, is registered as a sync root
        # for test user and file is member of it
        self.assertTrue(self.root_remote_client.exists(
                                                    self.locally_edited_path))
        sync_roots = remote.get_roots()
        self.assertEquals(len(sync_roots), 1)
        self.assertEquals(sync_roots[0].path, self.locally_edited_path)
        self.assertTrue(doc_id in
                        self.root_remote_client.get_collection_members(
                                                    self.locally_edited_path))

        # Update locally edited file
        # Let's first sync because of https://jira.nuxeo.com/browse/NXDRIVE-144
        self._sync(syn)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Updated content.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'), 'Updated content.')

        # Drive edit file a second time (should not download a new file but
        # detect the existing one)
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)
        self.assertEquals(len(local.get_children_info('/%s'
                                            % LOCALLY_EDITED_FOLDER_NAME)), 1)
        # Update locally edited file
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Twice updated content.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'),
                          'Twice updated content.')

    def test_drive_edit_synced_doc(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create file in test workspace (sync root)
        doc_id = remote.make_file('/', 'test.odt', 'Some content.')

        # Launch first synchronization
        self._sync(syn)
        self.assertTrue(local.exists('/%s/test.odt' % self.workspace_title))

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertEquals(local.get_content('/%s/test.odt'
                                            % LOCALLY_EDITED_FOLDER_NAME),
                          'Some content.')

        # Update locally edited file
        # Let's first sync because of https://jira.nuxeo.com/browse/NXDRIVE-144
        self._sync(syn)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Content updated from Locally Edited.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'),
                          'Content updated from Locally Edited.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % self.workspace_title),
                                    'Content updated from Locally Edited.')

        # Update file in local sync root
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % self.workspace_title,
                             'Content updated from local sync root.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'),
                          'Content updated from local sync root.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % LOCALLY_EDITED_FOLDER_NAME),
                                    'Content updated from local sync root.')

        # Update file in remote sync root
        remote.update_content('/test.odt',
                             'Content updated from remote sync root.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % self.workspace_title),
                                    'Content updated from remote sync root.')
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % LOCALLY_EDITED_FOLDER_NAME),
                                    'Content updated from remote sync root.')

    def test_drive_edit_doc_becoming_synced(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create file in test workspace (non sync root)
        doc_id = remote.make_file('/', 'test.odt', 'Some content.')

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))

        # Register test workspace as a sync root
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        self._sync(syn)
        self.assertTrue(local.exists('/%s/test.odt' % self.workspace_title))

        # Update file in local sync root
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % self.workspace_title,
                             'Content updated from local sync root.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'),
                          'Content updated from local sync root.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % LOCALLY_EDITED_FOLDER_NAME),
                                    'Content updated from local sync root.')

        # Update locally edited file
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Content updated from Locally Edited.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'),
                          'Content updated from Locally Edited.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % self.workspace_title),
                                    'Content updated from Locally Edited.')

        # Update file in remote sync root
        remote.update_content('/test.odt',
                             'Content updated from remote sync root.')
        self._sync(syn)
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % self.workspace_title),
                                    'Content updated from remote sync root.')
        self.assertEquals(local.get_content('/%s/test.odt'
                                    % LOCALLY_EDITED_FOLDER_NAME),
                                    'Content updated from remote sync root.')

    def test_drive_edit_remote_move_non_sync_root_to_sync_root(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create file in test workspace (non sync root)
        doc_id = remote.make_file('/', 'test.odt', 'Some content.')

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))

        # Update locally edited file
        # Let's first sync because of https://jira.nuxeo.com/browse/NXDRIVE-144
        self._sync(syn)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Updated content.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/test.odt'), 'Updated content.')

        # Register a folder as sync root and remotely move file to it
        sync_root_id = remote.make_folder('/', 'syncRoot')
        ctl.bind_root(self.local_nxdrive_folder_1, sync_root_id)
        self._sync(syn)
        self.assertTrue(local.exists('/syncRoot'))

        remote.move('/test.odt', '/syncRoot')
        self._sync(syn)
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertTrue(local.exists('/syncRoot/test.odt'))

    def test_drive_edit_remote_move_sync_root_to_non_sync_root(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create folder, register it as a sync root and create file inside it
        sync_root_id = remote.make_folder('/', 'syncRoot')
        ctl.bind_root(self.local_nxdrive_folder_1, sync_root_id)
        doc_id = remote.make_file(sync_root_id, 'test.odt', 'Some content.')

        # Launch first synchronization
        self._sync(syn)
        self.assertTrue(local.exists('/syncRoot/test.odt'))

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))

        # Update locally edited file
        # Let's first sync because of https://jira.nuxeo.com/browse/NXDRIVE-144
        self._sync(syn)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Content updated from Locally Edited.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/syncRoot/test.odt'),
                          'Content updated from Locally Edited.')
        self._sync(syn)
        self.assertEquals(local.get_content('/syncRoot/test.odt'),
                          'Content updated from Locally Edited.')

        # Move file to non sync root workspace
        remote.move('/syncRoot/test.odt', self.workspace)
        self._sync(syn)
        self.assertFalse(local.exists('/syncRoot/test.odt'))
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertEquals(len(local.get_children_info('/%s'
                                    % LOCALLY_EDITED_FOLDER_NAME)), 1)

    def test_drive_edit_move_sync_root_to_sync_root(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        local = LocalClient(self.local_nxdrive_folder_1)
        remote = self.remote_document_client_1
        syn = ctl.synchronizer

        # Create 2 folders, register them as sync roots and create file inside first folder
        sync_root_id1 = remote.make_folder('/', 'syncRoot1')
        sync_root_id2 = remote.make_folder('/', 'syncRoot2')
        ctl.bind_root(self.local_nxdrive_folder_1, sync_root_id1)
        ctl.bind_root(self.local_nxdrive_folder_1, sync_root_id2)
        doc_id = remote.make_file(sync_root_id1, 'test.odt', 'Some content.')

        # Launch first synchronization
        self._sync(syn)
        self.assertTrue(local.exists('/syncRoot1/test.odt'))
        self.assertTrue(local.exists('/syncRoot2'))

        # Drive edit file
        ctl.download_edit(self.nuxeo_url, 'default', doc_id, 'test.odt',
                          open_file=False)

        # Check file is downloaded to the Locally Edited folder
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))

        # Update locally edited file
        # Let's first sync because of https://jira.nuxeo.com/browse/NXDRIVE-144
        self._sync(syn)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/%s/test.odt' % LOCALLY_EDITED_FOLDER_NAME,
                             'Content updated from Locally Edited.')
        self._sync(syn, wait_for_async=False)
        self.assertEquals(remote.get_content('/syncRoot1/test.odt'),
                          'Content updated from Locally Edited.')
        self._sync(syn)
        self.assertEquals(local.get_content('/syncRoot1/test.odt'),
                          'Content updated from Locally Edited.')

        # Remotely move file to other sync root
        remote.move('/syncRoot1/test.odt', '/syncRoot2')
        self._sync(syn)
        self.assertFalse(local.exists('/syncRoot1/test.odt'))
        self.assertTrue(local.exists('/syncRoot2/test.odt'))
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertEquals(len(local.get_children_info('/%s'
                                    % LOCALLY_EDITED_FOLDER_NAME)), 1)

        # Locally move back file to other sync root
        local.move('/syncRoot2/test.odt', '/syncRoot1')
        self._sync(syn, wait_for_async=False)
        self.assertFalse(local.exists('/syncRoot2/test.odt'))
        self.assertTrue(local.exists('/syncRoot1/test.odt'))
        self.assertTrue(local.exists('/%s/test.odt'
                                     % LOCALLY_EDITED_FOLDER_NAME))
        self.assertEquals(len(local.get_children_info('/%s'
                                    % LOCALLY_EDITED_FOLDER_NAME)), 1)

    def _sync(self, syn, wait_for_async=True):
        if wait_for_async:
            self.wait_audit_change_finder_if_needed()
            self.wait()
        syn.loop(delay=0, max_loops=1)
