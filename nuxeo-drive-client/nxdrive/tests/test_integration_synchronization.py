import os
import time
import urllib2
import socket
import httplib

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationSynchronization(IntegrationTestCase):

    def test_binding_initialization_and_first_sync(self):
        ctl = self.controller_1
        # Create some documents in a Nuxeo workspace and bind this server to a
        # Nuxeo Drive local folder
        self.make_server_tree()
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        # The binding operation creates a new local folder with the Workspace name
        # and scan both sides (server and local independently)
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        local = LocalClient(expected_folder)
        self.assertEquals(len(local.get_children_info('/')), 0)

        # By default only scan happen, hence their is no information on the state
        # of the documents on the local side (they don't exist there yet)
        states = ctl.children_states(expected_folder)
        self.assertEquals(states, [])

        # However some (unaligned data has already been scanned)
        self.assertEquals(len(self.get_all_states()), 12)

        # Check the list of files and folders with synchronization pending
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 11)  # the root is already synchronized
        self.assertEquals(pending[0].remote_name, 'File 5.txt')
        self.assertEquals(pending[1].remote_name, 'Folder 1')
        self.assertEquals(pending[2].remote_name, 'File 1.txt')
        self.assertEquals(pending[3].remote_name, 'Folder 1.1')
        self.assertEquals(pending[4].remote_name, 'File 2.txt')
        self.assertEquals(pending[5].remote_name, 'Folder 1.2')
        self.assertEquals(pending[6].remote_name, 'File 3.txt')
        self.assertEquals(pending[7].remote_name, 'Folder 2')
        self.assertEquals(pending[8].remote_name, 'Duplicated File.txt')
        self.assertEquals(pending[9].remote_name, 'Duplicated File.txt')
        self.assertEquals(pending[10].remote_name, 'File 4.txt')

        # It is also possible to restrict the list of pending document to a
        # specific root
        self.assertEquals(len(ctl.list_pending(local_root=expected_folder)), 11)

        # It is also possible to restrict the number of pending tasks
        pending = ctl.list_pending(limit=2)
        self.assertEquals(len(pending), 2)

        # Synchronize the first 2 documents:
        self.assertEquals(syn.synchronize(limit=2), 2)
        pending = ctl.list_pending()
        self.assertEquals(len(pending), 9)
        self.assertEquals(pending[0].remote_name, 'File 1.txt')
        self.assertEquals(pending[1].remote_name, 'Folder 1.1')
        self.assertEquals(pending[2].remote_name, 'File 2.txt')
        self.assertEquals(pending[3].remote_name, 'Folder 1.2')
        self.assertEquals(pending[4].remote_name, 'File 3.txt')
        self.assertEquals(pending[5].remote_name, 'Folder 2')
        self.assertEquals(pending[6].remote_name, 'Duplicated File.txt')
        self.assertEquals(pending[7].remote_name, 'Duplicated File.txt')
        self.assertEquals(pending[8].remote_name, 'File 4.txt')

        states = ctl.children_states(expected_folder)
        expected_states = [
            (u'/File 5.txt', 'synchronized'),
            (u'/Folder 1', 'children_modified'),
        ]
        self.assertEquals(states, expected_states)

        # The actual content of the file has been updated
        self.assertEquals(local.get_content('/File 5.txt'), "eee")

        # The content of Folder 1 is still unknown from a local path point of view
        states = ctl.children_states(expected_folder + '/Folder 1')
        self.assertEquals(states, [])

        # synchronize everything else
        self.assertEquals(syn.synchronize(), 9)
        self.assertEquals(ctl.list_pending(), [])
        states = ctl.children_states(expected_folder)
        expected_states = [
            (u'/File 5.txt', 'synchronized'),
            (u'/Folder 1', 'synchronized'),
            (u'/Folder 2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'/Folder 1/File 1.txt', 'synchronized'),
            (u'/Folder 1/Folder 1.1', 'synchronized'),
            (u'/Folder 1/Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        self.assertEquals(local.get_content('/Folder 1/File 1.txt'), "aaa")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbb")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.2/File 3.txt'), "ccc")
        self.assertEquals(local.get_content('/Folder 2/File 4.txt'), "ddd")
        self.assertEquals(local.get_content('/Folder 2/Duplicated File.txt'),
                     "Some content.")
        self.assertEquals(local.get_content('/Folder 2/Duplicated File__1.txt'),
                     "Other content.")

        # Nothing else left to synchronize
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

        # Unbind root and resynchronize: smoke test
        ctl.unbind_root(expected_folder)
        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)
        self.assertEquals(ctl.list_pending(), [])

    def test_binding_synchronization_empty_start(self):
        ctl = self.controller_1
        remote_client = self.remote_client_1
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
        #self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's scan manually
        session = ctl.get_session()
        syn.scan_remote(expected_folder, session)

        # Changes on the remote server have been detected...
        self.assertEquals(len(ctl.list_pending()), 11)

        # ...but nothing is yet visible locally as those files don't exist
        # there yet.
        self.assertEquals(ctl.children_states(expected_folder), [])

        # Let's perform the synchronization
        self.assertEquals(syn.synchronize(limit=100), 11)

        # We should now be fully synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/File 5.txt', u'synchronized'),
            (u'/Folder 1', u'synchronized'),
            (u'/Folder 2', u'synchronized'),
        ])
        local = LocalClient(expected_folder)
        self.assertEquals(local.get_content('/Folder 1/File 1.txt'), "aaa")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbb")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.2/File 3.txt'), "ccc")
        self.assertEquals(local.get_content('/Folder 2/File 4.txt'), "ddd")
        self.assertEquals(local.get_content('/Folder 2/Duplicated File.txt'),
                     "Some content.")
        self.assertEquals(local.get_content('/Folder 2/Duplicated File__1.txt'),
                     "Other content.")

        # Wait a bit for file time stamps to increase enough: on most OS the file
        # modification time resolution is 1s
        time.sleep(1.0)

        # Let do some local and remote changes concurrently
        local.delete('/File 5.txt')
        local.update_content('/Folder 1/File 1.txt', 'aaaa')
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', 'bbbb')
        remote_client.delete('/Folder 2')
        f3 = remote_client.make_folder(self.workspace, 'Folder 3')
        remote_client.make_file(f3, 'File 6.txt', content='ffff')
        local.make_folder('/', 'Folder 4')

        # Rescan
        syn.scan_local(expected_folder, session)
        syn.scan_remote(expected_folder, session)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/File 5.txt', u'locally_deleted'),
            (u'/Folder 1', u'children_modified'),
            (u'/Folder 2', u'children_modified'),  # what do we want for this?
            # Folder 3 is not yet visible has not sync has happen to give it a
            # local path yet
            (u'/Folder 4', u'unknown'),
        ])
        # It is possible to fetch the full children states of the root though:
        full_states = ctl.children_states(expected_folder, full_states=True)
        self.assertEquals(len(full_states), 5)
        self.assertEquals(full_states[0][0].remote_name, 'Folder 3')
        self.assertEquals(full_states[0][1], 'children_modified')

        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'/Folder 1/File 1.txt', 'locally_modified'),
            (u'/Folder 1/Folder 1.1', 'children_modified'),
            (u'/Folder 1/Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
        expected_states = [
            (u'/Folder 1/Folder 1.1/File 2.txt', u'remotely_modified'),
        ]
        self.assertEquals(states, expected_states)
        states = ctl.children_states(expected_folder + '/Folder 2')
        expected_states = [
            (u'/Folder 2/Duplicated File.txt', u'remotely_deleted'),
            (u'/Folder 2/Duplicated File__1.txt', u'remotely_deleted'),
            (u'/Folder 2/File 4.txt', u'remotely_deleted'),
        ]
        self.assertEquals(states, expected_states)

        # Perform synchronization
        self.assertEquals(syn.synchronize(limit=100), 10)

        # We should now be fully synchronized again
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/Folder 1', 'synchronized'),
            (u'/Folder 3', 'synchronized'),
            (u'/Folder 4', 'synchronized'),
        ])
        states = ctl.children_states(expected_folder + '/Folder 1')
        expected_states = [
            (u'/Folder 1/File 1.txt', 'synchronized'),
            (u'/Folder 1/Folder 1.1', 'synchronized'),
            (u'/Folder 1/Folder 1.2', 'synchronized'),
        ]
        self.assertEquals(states, expected_states)
        self.assertEquals(local.get_content('/Folder 1/File 1.txt'), "aaaa")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbbb")
        self.assertEquals(local.get_content('/Folder 3/File 6.txt'), "ffff")
        self.assertEquals(remote_client.get_content('/Folder 1/File 1.txt'),
                     "aaaa")
        self.assertEquals(remote_client.get_content('/Folder 1/Folder 1.1/File 2.txt'),
                     "bbbb")
        self.assertEquals(remote_client.get_content('/Folder 3/File 6.txt'),
                     "ffff")

        # Rescan: no change to detect we should reach a fixpoint
        syn.scan_local(expected_folder, session)
        syn.scan_remote(expected_folder, session)
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/Folder 1', 'synchronized'),
            (u'/Folder 3', 'synchronized'),
            (u'/Folder 4', 'synchronized'),
        ])

        # Send some binary data that is not valid in utf-8 or ascii (to test the
        # HTTP / Multipart transform layer).
        time.sleep(1.0)
        local.update_content('/Folder 1/File 1.txt', "\x80")
        remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', '\x80')
        syn.scan_local(expected_folder, session)
        syn.scan_remote(expected_folder, session)
        self.assertEquals(syn.synchronize(limit=100), 2)
        self.assertEquals(remote_client.get_content('/Folder 1/File 1.txt'), "\x80")
        self.assertEquals(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "\x80")

    def test_synchronization_modification_on_created_file(self):
        ctl = self.controller_1
        # Regression test: a file is created locally, then modification is detected
        # before first upload
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder')
        local.make_file('/Folder', 'File.txt', content='Some content.')

        # First local scan (assuming the network is offline):
        syn.scan_local(expected_folder)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/Folder', 'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'/Folder/File.txt', u'unknown'),
        ])

        # Wait a bit for file time stamps to increase enough: on most OS the file
        # modification time resolution is 1s
        time.sleep(1.0)

        # Let's modify it offline and rescan locally
        local.update_content('/Folder/File.txt', content='Some content.')
        syn.scan_local(expected_folder)
        self.assertEquals(len(ctl.list_pending()), 2)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/Folder', u'children_modified'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'/Folder/File.txt', u'locally_modified'),
        ])

        # Assume the computer is back online, the synchronization should occur as if
        # the document was just created and not trigger an update
        syn.loop(full_local_scan=True, full_remote_scan=True, delay=0.010,
                 max_loops=1, fault_tolerant=False)
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/Folder', u'synchronized'),
        ])
        self.assertEquals(ctl.children_states(expected_folder + '/Folder'), [
            (u'/Folder/File.txt', u'synchronized'),
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

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Run the full synchronization loop a limited amount of times
        syn.loop(full_local_scan=True, full_remote_scan=True, delay=0.010,
                 max_loops=3, fault_tolerant=False)

        # All is synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/File 5.txt', u'synchronized'),
            (u'/Folder 1', u'synchronized'),
            (u'/Folder 2', u'synchronized'),
            (u'/Folder 3', u'synchronized'),
        ])

    def test_synchronization_offline(self):
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer
        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])
        self.assertEquals(syn.synchronize(), 0)

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Find various ways to similate network or server failure
        errors = [
            urllib2.URLError('Test error'),
            socket.error('Test error'),
            httplib.HTTPException('Test error'),
        ]
        for error in errors:
            ctl.make_remote_raise(error)
            # Synchronization does not occur but does not fail either
            syn.loop(full_local_scan=True, full_remote_scan=True, delay=0,
                     max_loops=1, fault_tolerant=False)
            # Only the local change has been detected
            self.assertEquals(len(ctl.list_pending()), 1)

        # Reenable network
        ctl.make_remote_raise(None)
        syn.loop(full_local_scan=True, full_remote_scan=True, delay=0,
                 max_loops=1, fault_tolerant=False)

        # All is synchronized
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(ctl.children_states(expected_folder), [
            (u'/File 5.txt', u'synchronized'),
            (u'/Folder 1', u'synchronized'),
            (u'/Folder 2', u'synchronized'),
            (u'/Folder 3', u'synchronized'),
        ])

    def test_rebind_without_duplication(self):
        """Check that rebinding an existing folder will not duplicate everything"""
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        syn = ctl.synchronizer

        expected_folder = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)

        self.assertEquals(ctl.list_pending(), [])

        # Let's create some document on the client and the server
        local = LocalClient(expected_folder)
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        syn.loop(full_local_scan=True, full_remote_scan=True, delay=0,
                 max_loops=1, fault_tolerant=False)
        self.assertEquals(len(ctl.list_pending()), 0)

        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/File 5.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 1/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1/File 2.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2/File 3.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File__1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/File 4.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized')
        ])
        self.assertEquals(len(local.get_children_info('/')), 4)

        # Unbind: the state database is emptied
        ctl.unbind_server(self.local_nxdrive_folder_1)
        self.assertEquals(self.get_all_states(), [])

        # Previously synchronized files are still there, untouched
        self.assertEquals(len(local.get_children_info('/')), 4)

        # Lets rebind the same folder to the same workspace
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Check that the bind that occurrs right after the bind automatically
        # detects the file alignments and hence everything is synchronized without
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(self.get_all_states(), [
            (u'/', u'synchronized', u'synchronized'),
            (u'/File 5.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1', u'synchronized', u'synchronized'),
            (u'/Folder 1/File 1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.1/File 2.txt', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2', u'synchronized', u'synchronized'),
            (u'/Folder 1/Folder 1.2/File 3.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/Duplicated File__1.txt', u'synchronized', u'synchronized'),
            (u'/Folder 2/File 4.txt', u'synchronized', u'synchronized'),
            (u'/Folder 3', u'synchronized', u'synchronized')
        ])
        self.assertEquals(len(ctl.list_pending()), 0)
        self.assertEquals(len(local.get_children_info('/')), 4)
