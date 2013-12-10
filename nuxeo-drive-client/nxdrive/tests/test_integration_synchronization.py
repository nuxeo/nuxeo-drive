import os
import time
import urllib2
import socket
import httplib
from datetime import datetime

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient
from nxdrive.model import LastKnownState
from nxdrive.controller import Controller


class TestIntegrationSynchronization(IntegrationTestCase):

    def test_binding_initialization_and_first_sync(self):
        ctl = self.controller_1
        # Create some documents in a Nuxeo workspace and bind this server to a
        # Nuxeo Drive local folder
        self.make_server_tree()
        binding = ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # The root binding operation does not create the local folder
        # yet.
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        local_client = LocalClient(self.local_nxdrive_folder_1)
        self.assertFalse(local_client.exists('/' + self.workspace_title))

        # By default only scan happen, hence their is no information on the
        # state of the documents on the local side (they don't exist there yet)
        states = ctl.children_states(expected_folder)
        self.assertEquals(states, [])

        # Only the root binding is stored in the DB
        self.assertEquals(len(self.get_all_states()), 1)

        # Trigger some scan manually
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)

        # Check the list of files and folders with synchronization pending
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 12)
        remote_names = [p.remote_name for p in pending]
        remote_names.sort()
        self.assertEquals(remote_names, [
            u'Duplicated File.txt',
            u'Duplicated File.txt',
            u'File 1.txt',
            u'File 2.txt',
            u'File 3.txt',
            u'File 4.txt',
            u'File 5.txt',
            u'Folder 1',
            u'Folder 1.1',
            u'Folder 1.2',
            u'Folder 2',
            u'Nuxeo Drive Test Workspace',
        ])

        # It is also possible to restrict the list of pending document to a
        # specific server binding
        self.assertEquals(len(ctl.list_pending(
                          local_folder=self.local_nxdrive_folder_1)), 12)

        # It is also possible to restrict the number of pending tasks
        pending = ctl.list_pending(limit=2)
        self.assertEquals(len(pending), 2)

        # Synchronize the first document (ordered by hierarchy):
        self.assertEquals(syn.synchronize(binding, limit=1), 1)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 11)
        remote_names = [p.remote_name for p in pending]
        remote_names.sort()
        self.assertEquals(remote_names, [
            u'Duplicated File.txt',
            u'Duplicated File.txt',
            u'File 1.txt',
            u'File 2.txt',
            u'File 3.txt',
            u'File 4.txt',
            u'File 5.txt',
            u'Folder 1',
            u'Folder 1.1',
            u'Folder 1.2',
            u'Folder 2',
        ])
        states = ctl.children_states(self.local_nxdrive_folder_1)
        self.assertEquals(states, [
            (u'Nuxeo Drive Test Workspace', u'children_modified'),
        ])

        # The workspace folder is still unknown from the client point
        # of view
        states = ctl.children_states(expected_folder)
        self.assertEquals(states, [])

        # synchronize everything else
        self.assertEquals(syn.synchronize(), 11)
        self.assertEquals(ctl.list_pending(), [])
        states = ctl.children_states(expected_folder)
        expected_states = [
            (u'File 5.txt', 'synchronized'),
            (u'Folder 1', 'synchronized'),
            (u'Folder 2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)

        # The actual content of the file has been updated
        file_5_content = local_client.get_content(
            '/Nuxeo Drive Test Workspace/File 5.txt')
        self.assertEquals(file_5_content, "eee")

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'synchronized'),
            (u'Folder 1.1', 'synchronized'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt'),
            "aaa")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt'),
            "bbb")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt'),
            "ccc")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/File 4.txt'),
            "ddd")

        c1 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt')

        c2 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt')

        self.assertEquals(tuple(sorted((c1, c2))),
                          ("Other content.", "Some content."))

        # Nothing else left to synchronize
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

        # Unbind root and resynchronize: smoke test
        ctl.unbind_root(self.local_nxdrive_folder_1, self.workspace)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

    def test_binding_synchronization_empty_start(self):
        ctl = self.controller_1
        remote_client = self.remote_document_client_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        # Nothing to synchronize by default
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the server
        self.make_server_tree()

        # By default nothing is detected
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's scan manually
        syn.scan_remote(self.local_nxdrive_folder_1)

        # Changes on the remote server have been detected...
        self.assertEquals(len(ctl.list_pending()), 12)

        # ...but nothing is yet visible locally as those files don't exist
        # there yet.
        self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's perform the synchronization
        self.assertEquals(syn.synchronize(limit=100), 12)

        # We should now be fully synchronized
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
        ])
        local_client = LocalClient(self.local_nxdrive_folder_1)
        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt'),
            "aaa")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt'),
            "bbb")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt'),
            "ccc")

        self.assertEquals(local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/File 4.txt'),
            "ddd")

        c1 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt')

        c2 = local_client.get_content(
            '/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt')

        self.assertEquals(tuple(sorted((c1, c2))),
                          ("Other content.", "Some content."))

        # Wait a bit for file time stamps to increase enough: on OSX HFS+ the
        # file modification time resolution is 1s for instance
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)

        # Let do some local and remote changes concurrently
        local_client.delete('/Nuxeo Drive Test Workspace/File 5.txt')
        local_client.update_content(
            '/Nuxeo Drive Test Workspace/Folder 1/File 1.txt', 'aaaa')

        # The remote client use in this test is handling paths relative to
        # the 'Nuxeo Drive Test Workspace'
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt',
                                     'bbbb')
        remote_client.delete('/Folder 2')
        f3 = remote_client.make_folder(self.workspace, 'Folder 3')
        remote_client.make_file(f3, 'File 6.txt', content='ffff')
        local_client.make_folder('/Nuxeo Drive Test Workspace', 'Folder 4')

        # Rescan
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'locally_deleted'),
            (u'Folder 1', u'children_modified'),
            (u'Folder 2', u'children_modified'),  # what do we want for this?
            # Folder 3 is not yet visible has not sync has happen to give it a
            # local path yet
            (u'Folder 4', u'unknown'),
        ])
        # The information on the remote state of Folder 3 has been stored in
        # the database though
        session = ctl.get_session()
        f3_state = session.query(LastKnownState).filter_by(
            remote_name='Folder 3').one()
        self.assertEquals(f3_state.local_path, None)

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'locally_modified'),
            (u'Folder 1.1', 'children_modified'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
        expected_states = [
            (u'File 2.txt', u'remotely_modified'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 2')
        expected_states = [
            (u'Duplicated File.txt', u'remotely_deleted'),
            (u'Duplicated File__1.txt', u'remotely_deleted'),
            (u'File 4.txt', u'remotely_deleted'),
        ]
        self.assertEquals(states, expected_states)

        # Perform synchronization: deleted folder content are not
        # counted in the summary
        self.assertEquals(syn.synchronize(limit=100), 7)

        # We should now be fully synchronized again
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder 1', 'synchronized'),
            (u'Folder 3', 'synchronized'),
            (u'Folder 4', 'synchronized'),
        ])
        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'File 1.txt', 'synchronized'),
            (u'Folder 1.1', 'synchronized'),
            (u'Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        local = LocalClient(expected_folder)
        self.assertEquals(local.get_content(
            '/Folder 1/File 1.txt'),
            "aaaa")
        self.assertEquals(local.get_content(
            '/Folder 1/Folder 1.1/File 2.txt'),
            "bbbb")
        self.assertEquals(local.get_content(
            '/Folder 3/File 6.txt'),
            "ffff")
        self.assertEquals(remote_client.get_content(
            '/Folder 1/File 1.txt'),
            "aaaa")
        self.assertEquals(remote_client.get_content(
            '/Folder 1/Folder 1.1/File 2.txt'),
            "bbbb")
        self.assertEquals(remote_client.get_content(
            '/Folder 3/File 6.txt'),
            "ffff")

        # Rescan: no change to detect we should reach a fixpoint
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder 1', 'synchronized'),
            (u'Folder 3', 'synchronized'),
            (u'Folder 4', 'synchronized'),
        ])

        # Send some binary data that is not valid in utf-8 or ascii
        # (to test the HTTP / Multipart transform layer).
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content('/Folder 1/File 1.txt', "\x80")
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', '\x80')
        syn.scan_local(self.local_nxdrive_folder_1)
        syn.scan_remote(self.local_nxdrive_folder_1)
        self.assertEquals(syn.synchronize(limit=100), 2)
        self.assertEquals(remote_client.get_content('/Folder 1/File 1.txt'),
                          "\x80")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'),
                          "\x80")

    def test_synchronization_modification_on_created_file(self):
        ctl = self.controller_1
        # Regression test: a file is created locally, then modification is
        # detected before first upload
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.assertEquals(ctl.list_pending(), [])

        self.wait()
        syn.loop(delay=0.010, max_loops=1)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder')
        local.make_file('/Folder', 'File.txt', content='Some content.')

        # First local scan (assuming the network is offline):
        syn.scan_local(self.local_nxdrive_folder_1)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', 'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'unknown'),
        ])

        # Wait a bit for file time stamps to increase enough: on most OS
        # the file modification time resolution is 1s
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)

        # Let's modify it offline and rescan locally
        local.update_content('/Folder/File.txt', content='Some content.')
        syn.scan_local(self.local_nxdrive_folder_1)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'locally_modified'),
        ])

        # Assume the computer is back online, the synchronization should occur
        # as if the document was just created and not trigger an update
        self.wait()
        syn.loop(delay=0.010, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'Folder', u'synchronized'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'File.txt', u'synchronized'),
        ])

    def test_synchronization_loop(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        self.wait()

        # Run the full synchronization loop a limited amount of times
        syn.loop(delay=0.010, max_loops=3)

        # All is synchronized
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_synchronization_loop_skip_errors(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        self.wait()
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        self.wait()

        # Detect the files to synchronize but do not perform the
        # synchronization
        syn.scan_remote(self.local_nxdrive_folder_1)
        syn.scan_local(self.local_nxdrive_folder_1)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 12)
        self.assertEquals(pending[0].local_name, 'Folder 3')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].remote_name, 'File 5.txt')
        self.assertEquals(pending[1].pair_state, 'unknown')
        self.assertEquals(pending[2].remote_name, 'Folder 1')
        self.assertEquals(pending[2].pair_state, 'unknown')

        # Simulate synchronization errors
        session = ctl.get_session()
        file_5 = session.query(LastKnownState).filter_by(
            remote_name='File 5.txt').one()
        file_5.last_sync_error_date = datetime.utcnow()
        folder_3 = session.query(LastKnownState).filter_by(
            local_name='Folder 3').one()
        folder_3.last_sync_error_date = datetime.utcnow()
        session.commit()

        # Run the full synchronization loop a limited amount of times
        syn.loop(delay=0, max_loops=3)

        # All errors have been skipped, while the remaining docs have
        # been synchronized
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 2)
        self.assertEquals(pending[0].local_name, 'Folder 3')
        self.assertEquals(pending[0].pair_state, 'unknown')
        self.assertEquals(pending[1].remote_name, 'File 5.txt')
        self.assertEquals(pending[1].pair_state, 'unknown')

        # Reduce the skip delay to retry the sync on pairs in error
        syn.error_skip_period = 0.000001
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_synchronization_offline(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                             self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        # Bound root but nothing is synced yet
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Perform first scan and sync
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()

        # Find various ways to similate network or server failure
        errors = [
            urllib2.URLError('Test error'),
            socket.error('Test error'),
            httplib.HTTPException('Test error'),
        ]
        for error in errors:
            ctl.make_remote_raise(error)
            # Synchronization does not occur but does not fail either
            syn.loop(delay=0, max_loops=1)
            # Only the local change has been detected
            self.assertEquals(len(ctl.list_pending()), 1)

        # Reenable network
        ctl.make_remote_raise(None)
        syn.loop(delay=0, max_loops=2)

        # All is synchronized
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'File 5.txt', u'synchronized'),
            (u'Folder 1', u'synchronized'),
            (u'Folder 2', u'synchronized'),
            (u'Folder 3', u'synchronized'),
        ])

    def test_rebind_without_duplication(self):
        """Check rebinding an existing folder won't duplicate everything"""
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and the server
        local = LocalClient(self.local_nxdrive_folder_1)
        local.make_folder('/', self.workspace_title)
        local.make_folder('/' + self.workspace_title, 'Folder 3')
        self.make_server_tree()
        self.wait()

        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])

        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/File 5.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/File 1.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/File 4.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 3',
             u'synchronized', u'synchronized')
        ])
        self.assertEquals(
            len(local.get_children_info('/Nuxeo Drive Test Workspace')), 4)

        # Unbind: the state database is emptied
        ctl.unbind_server(self.local_nxdrive_folder_1)
        self.assertEquals(self.get_all_states(), [])

        # Previously synchronized files are still there, untouched
        self.assertEquals(
            len(local.get_children_info('/Nuxeo Drive Test Workspace')), 4)

        # Lets rebind the same folder to the same workspace
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn.loop(delay=0, max_loops=3)
        self.assertEquals(ctl.list_pending(), [])

        # Check that the sync that occurs right after the bind automatically
        # detects the file alignments and hence everything is synchronized
        # without duplication
        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/File 5.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/File 1.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.1/File 2.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 1/Folder 1.2/File 3.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/Duplicated File.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/Duplicated File__1.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 2/File 4.txt',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 3',
             u'synchronized', u'synchronized')
        ])
        self.assertEquals(ctl.list_pending(), [])
        # Previously synchronized files are still there, untouched
        self.assertEquals(
            len(local.get_children_info('/Nuxeo Drive Test Workspace')), 4)

    def test_delete_root_folder(self):
        """Check that local delete of root maps to unbind_root on the server"""
        ctl = self.controller_1
        sb = ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                             self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # Let's synchronize the new root
        self.assertEquals(syn.update_synchronize_server(sb), 1)
        self.assertEquals(ctl.list_pending(), [])

        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
        ])

        # Refetching the changes in the server autid log does not see any
        # change
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(syn.update_synchronize_server(sb), 0)
        self.assertEquals(ctl.list_pending(), [])

        # The workspace has been synced
        local = LocalClient(self.local_nxdrive_folder_1)
        self.assertTrue(local.exists('/' + self.workspace_title))

        # Let's create a subfolder and synchronize it
        local.make_folder('/' + self.workspace_title, 'Folder 3')
        self.assertEquals(syn.update_synchronize_server(sb), 1)
        self.assertEquals(ctl.list_pending(), [])

        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 3',
             u'synchronized', u'synchronized'),
        ])

        # Let's delete the root locally
        local.delete('/' + self.workspace_title)
        self.assertFalse(local.exists('/' + self.workspace_title))
        self.assertEquals(syn.update_synchronize_server(sb), 1)

        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
        ])

        # On the server this has been mapped to a root unregistration:
        # the workspace is still there
        self.assertTrue(self.remote_document_client_1.exists('/'))

        # The subfolder has not been deleted on the server
        self.assertTrue(self.remote_document_client_1.exists('/Folder 3'))

        # But the workspace folder is still not there on the client:
        self.assertFalse(local.exists('/' + self.workspace_title))
        self.assertEquals(ctl.list_pending(), [])

        # Synchronizing later does not refetch the workspace as it's not
        # mapped as a sync root.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.assertEquals(syn.update_synchronize_server(sb), 0)
        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
        ])
        self.assertFalse(local.exists('/' + self.workspace_title))

        # We can rebind the root and fetch back its content
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        self.wait()

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])
        self.assertTrue(local.exists('/' + self.workspace_title))
        self.assertTrue(local.exists('/' + self.workspace_title + '/Folder 3'))
        self.assertEquals(self.get_all_states(), [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace/Folder 3',
             u'synchronized', u'synchronized'),
        ])

    def test_conflict_detection_and_renaming(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        # Fetch the workspace sync root
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and synchronize it.
        local = LocalClient(self.local_nxdrive_folder_1)
        local_path = local.make_file('/' + self.workspace_title,
           'Some File.doc', content="Original content.")
        syn.loop(delay=0, max_loops=1)

        # Let's modify it concurrently but with the same content (digest)
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content(local_path, 'Same new content.')

        remote_2 = self.remote_document_client_2
        remote_2.update_content('/Some File.doc', 'Same new content.')

        # Let's synchronize and check the conflict handling: automatic
        # resolution will work for this case/
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0, max_loops=1)
        item_infos = local.get_children_info('/' + self.workspace_title)
        self.assertEquals(len(item_infos), 1)
        self.assertEquals(item_infos[0].name, 'Some File.doc')
        self.assertEquals(local.get_content(local_path), 'Same new content.')

        # Let's trigger another conflict that cannot be resolved
        # automatically:
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.update_content(local_path, 'Local new content.')

        remote_2 = self.remote_document_client_2
        remote_2.update_content('/Some File.doc', 'Remote new content.')
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        # 2 loops are necessary for full conflict handling
        syn.loop(delay=0, max_loops=2)
        item_infos = local.get_children_info('/' + self.workspace_title)
        self.assertEquals(len(item_infos), 2)

        first, second = item_infos
        if first.name == 'Some File.doc':
            version_from_remote, version_from_local = first, second
        else:
            version_from_local, version_from_remote = first, second

        self.assertEquals(version_from_remote.name, 'Some File.doc')
        self.assertEquals(local.get_content(version_from_remote.path),
            'Remote new content.')

        self.assertTrue(version_from_local.name.startswith('Some File ('),
            msg="'%s' was expected to start with 'Some File ('"
                % version_from_local.name)
        self.assertTrue(version_from_local.name.endswith(').doc'),
            msg="'%s' was expected to end with ').doc'"
                % version_from_local.name)
        self.assertEquals(local.get_content(version_from_local.path),
            'Local new content.')

        # Everything is synchronized
        all_states = self.get_all_states()

        self.assertEquals(all_states[:2], [
            (u'/',
             u'synchronized', u'synchronized'),
            (u'/Nuxeo Drive Test Workspace',
             u'synchronized', u'synchronized'),
        ])
        # The filename changes with the date
        self.assertEquals(all_states[2][1:],
            (u'synchronized', u'synchronized'))
        self.assertEquals(all_states[3],
            (u'/Nuxeo Drive Test Workspace/Some File.doc',
             u'synchronized', u'synchronized'))

    def test_synchronize_deep_folders(self):
        # Increase Automation execution timeout for NuxeoDrive.GetChangeSummary
        # because of the recursive parent FileSystemItem adaptation
        ctl = self.controller_1
        ctl.timeout = 40
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # Fetch the workspace sync root
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        # Create a file deep down in the hierarchy
        remote = self.remote_document_client_1

        folder_name = '0123456789'
        folder_depth = 40
        folder = '/'
        for _ in range(folder_depth):
            folder = remote.make_folder(folder, folder_name)

        remote.make_file(folder, "File.odt", content="Fake non-zero content.")

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0, max_loops=5)
        self.assertEquals(ctl.list_pending(), [])

        local = LocalClient(self.local_nxdrive_folder_1)
        expected_folder_path = (
            '/' + self.workspace_title + ('/' + folder_name) * folder_depth)

        expected_file_path = expected_folder_path + '/File.odt'
        self.assertTrue(local.exists(expected_folder_path))
        self.assertTrue(local.exists(expected_file_path))
        self.assertEquals(local.get_content(expected_file_path),
                          "Fake non-zero content.")

        # Delete the nested folder structure on the remote server
        # and synchronize again
        remote.delete('/' + folder_name)

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0, max_loops=5)
        self.assertEquals(ctl.list_pending(), [])

        self.assertFalse(local.exists(expected_folder_path))
        self.assertFalse(local.exists(expected_file_path))

    def test_create_content_in_readonly_area(self):
        # Let's bind a the server but no root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        syn = ctl.synchronizer
        self.wait()

        syn.loop(delay=0.1, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create a subfolder of the main readonly folder
        local = LocalClient(self.local_nxdrive_folder_1)
        local.make_folder('/', 'Folder 3')
        local.make_file('/Folder 3', 'File 1.txt', content='Some content.')
        local.make_folder('/Folder 3', 'Sub Folder 1')
        local.make_file('/Folder 3/Sub Folder 1', 'File 2.txt',
                        content='Some other content.')
        syn.loop(delay=0.1, max_loops=1)

        # Pairs have been created for the subfolder and its content,
        # marked as synchronized
        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized'),
            (u'/Folder 3/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3/Sub Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 3/Sub Folder 1/File 2.txt',
             u'synchronized', u'synchronized'),
        ])
        self.assertEquals(ctl.list_pending(), [])

        # Let's create a file in the main readonly folder
        local.make_file('/', 'A file in a readonly folder.txt',
            content='Some Content')
        syn.loop(delay=0.1, max_loops=1)

        # A pair has been created, marked as synchronized
        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/A file in a readonly folder.txt',
             u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized'),
            (u'/Folder 3/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3/Sub Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 3/Sub Folder 1/File 2.txt',
             u'synchronized', u'synchronized'),
        ])
        self.assertEquals(len(ctl.list_pending(ignore_in_error=300)), 0)

        # Let's create a file and a folder in a folder on which the Write
        # permission has been removed. Thanks to NXP-13119, this permission
        # change will be detected server-side, thus fetched by the client
        # in the remote change summary, and the remote_can_create_child flag
        # on which the synchronizer relies to check if creation is allowed
        # will be set to False and no attempt to create the remote file
        # will be made.

        # Bind root workspace, create local folder and synchronize it remotely
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)

        local = LocalClient(
            os.path.join(self.local_nxdrive_folder_1, self.workspace_title))
        local.make_folder(u'/', u'Readonly folder')
        syn.loop(delay=0.1, max_loops=1)

        remote = self.remote_document_client_1
        self.assertTrue(remote.exists(u'/Readonly folder'))

        # Check remote_can_create_child flag in pair state
        session = ctl.get_session()
        readonly_folder_state = session.query(LastKnownState).filter_by(
            local_name=u'Readonly folder').one()
        self.assertTrue(readonly_folder_state.remote_can_create_child)

        # Make one sync loop to detect remote folder creation triggered
        # by last synchronization and make sure we get a clean state at
        # next change summary
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(readonly_folder_state.remote_can_create_child)

        # Set remote folder as readonly for test user
        readonly_folder_path = self.TEST_WORKSPACE_PATH + u'/Readonly folder'
        op_input = "doc:" + readonly_folder_path
        self.root_remote_client.execute("Document.SetACE",
            op_input=op_input,
            user="nuxeoDriveTestUser_user_1",
            permission="Write",
            grant="false")

        # Wait to make sure permission change is detected.
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(readonly_folder_state.remote_can_create_child)

        # Try to create a local file and folder in the readonly folder,
        # they should not be created remotely.
        local.make_file(u'/Readonly folder', u'File in readonly folder',
                        u"File content")
        local.make_folder(u'/Readonly folder', u'Folder in readonly folder')
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(remote.exists(
            u'/Readonly folder/File in readonly folder'))
        self.assertFalse(remote.exists(
            u'/Readonly folder/Folder in readonly folder'))

    def test_synchronize_special_filenames(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # Fetch the workspace sync root
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        # Create some remote documents with weird filenames
        remote = self.remote_document_client_1

        folder = remote.make_folder(self.workspace,
            u'Folder with forbidden chars: / \\ * < > ? "')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])
        local = LocalClient(
            os.path.join(self.local_nxdrive_folder_1, self.workspace_title))
        folder_names = [i.name for i in local.get_children_info('/')]
        self.assertEquals(folder_names,
            [u'Folder with forbidden chars- - - - - - - -'])

        # create some file on the server
        remote.make_file(folder,
            u'File with forbidden chars: / \\ * < > ? ".doc',
            content="some content")

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0, max_loops=1)
        self.assertEquals(ctl.list_pending(), [])

        file_names = [i.name for i in local.get_children_info(
                      local.get_children_info('/')[0].path)]
        self.assertEquals(file_names,
            [u'File with forbidden chars- - - - - - - -.doc'])

    def test_synchronize_deleted_blob(self):
        # Bind the server and root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create a doc with a blob in the remote root workspace
        # then synchronize
        remote.make_file('/', 'test.odt', 'Some content.')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(local.exists('/test.odt'))

        # Delete the blob from the remote doc then synchronize
        remote.delete_content('/test.odt')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(local.exists('/test.odt'))

    def test_synchronize_paged_delete_detection(self):
        # Initialize a controller with page size = 1 for deleted items
        # detection query
        ctl = Controller(self.nxdrive_conf_folder_1, page_size=1)
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create a remote folder with 2 children then synchronize
        remote.make_folder('/', 'Remote folder',)
        remote.make_file('/Remote folder', 'Remote file 1.odt',
                         'Some content.')
        remote.make_file('/Remote folder', 'Remote file 2.odt',
                         'Other content.')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(local.exists('/Remote folder'))
        self.assertTrue(local.exists('/Remote folder/Remote file 1.odt'))
        self.assertTrue(local.exists('/Remote folder/Remote file 2.odt'))

        # Delete remote folder then synchronize
        remote.delete('/Remote folder')

        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(local.exists('/Remote folder'))
        self.assertFalse(local.exists('/Remote folder/Remote file 1.odt'))
        self.assertFalse(local.exists('/Remote folder/Remote file 2.odt'))

        # Create a local folder with 2 children then synchronize
        local.make_folder('/', 'Local folder')
        local.make_file('/Local folder', 'Local file 1.odt', 'Some content.')
        local.make_file('/Local folder', 'Local file 2.odt', 'Other content.')

        syn.loop(delay=0.1, max_loops=1)
        self.assertTrue(remote.exists('/Local folder'))
        self.assertTrue(remote.exists('/Local folder/Local file 1.odt'))
        self.assertTrue(remote.exists('/Local folder/Local file 2.odt'))

        # Delete local folder then synchronize
        time.sleep(self.OS_STAT_MTIME_RESOLUTION)
        local.delete('/Local folder')

        syn.loop(delay=0.1, max_loops=1)
        self.assertFalse(remote.exists('/Local folder'))
        self.assertFalse(remote.exists('/Local folder/Local file 1.odt'))
        self.assertFalse(remote.exists('/Local folder/Local file 2.odt'))

        # Dispose dedicated Controller instantiated for this test
        ctl.dispose()
