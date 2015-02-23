import os
import time
from nose.plugins.skip import SkipTest

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client import LocalClient


class TestIntegrationLocalStorageSpaceIssue(IntegrationTestCase):

    def test_synchronize_no_space_left_on_device(self):
        raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Bind the server and root workspace
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)

        # Launch first synchronization
        self.wait()
        syn = ctl.synchronizer
        syn.loop(delay=0.1, max_loops=1)

        # Get local and remote clients
        local = LocalClient(os.path.join(self.local_nxdrive_folder_1,
                                         self.workspace_title))
        remote = self.remote_document_client_1

        # Create a file in the remote root workspace
        remote.make_file('/', 'test_KO.odt', 'Some large content.')
        self.wait()

        # Synchronize simulating a "No space left on device" error
        error = IOError("No space left on device")
        ctl.make_local_raise(error)
        syn.loop(delay=0.1, max_loops=1)
        # Temporary download file (.nxpart) should be created locally but not
        # renamed and synchronization should not fail: doc pair should be
        # blacklisted and there should be 1 pending item
        self.assertTrue(local.exists('/.test_KO.odt.nxpart'))
        self.assertFalse(local.exists('/test_KO.odt'))
        self.assertEquals(len(ctl.list_pending()), 1)

        # Create another file in the remote root workspace
        remote.make_file('/', 'test_OK.odt', 'Some small content.')
        self.wait()

        # Synchronize without simulating any error
        ctl.make_local_raise(None)
        syn.loop(delay=0.1, max_loops=1)
        # Remote file should be created locally
        self.assertTrue(local.exists('/test_OK.odt'))
        # Blacklisted file should be ignored as delay (300 seconds by default)
        # is not expired, temporary download file from previously failed
        # synchronization should still be there and there should still be 1
        # pending item
        self.assertTrue(local.exists('/.test_KO.odt.nxpart'))
        self.assertFalse(local.exists('/test_KO.odt'))
        self.assertEquals(len(ctl.list_pending()), 1)

        # Retry to synchronize blacklisted file still simulating a "No space
        # left on device" error
        ctl.make_local_raise(error)
        # Reduce error skip delay to retry synchronization of pairs in error
        syn.error_skip_period = 1.0
        syn.loop(delay=0.1, max_loops=1)
        # Temporary download file (.nxpart) should be overridden but still not
        # renamed, doc pair should be blacklisted again and there should still
        # be 1 pending item
        self.assertTrue(local.exists('/.test_KO.odt.nxpart'))
        self.assertFalse(local.exists('/test_KO.odt'))
        self.assertEquals(len(ctl.list_pending()), 1)
        # In the test workspace there should be 2 files but only 1 child taken
        # into account by the local client as it ignores .nxpart suffixed files
        self.assertEquals(len(os.listdir(os.path.join(
                                            self.local_nxdrive_folder_1,
                                            self.workspace_title))), 2)
        self.assertEquals(len(local.get_children_info('/')), 1)

        # Synchronize without simulating any error, as if space had been made
        # available on device
        ctl.make_local_raise(None)
        # Wait for error skip delay to retry synchronization of pairs in error
        time.sleep(syn.error_skip_period)
        syn.loop(delay=0.1, max_loops=1)
        # Previously blacklisted file should be created locally, temporary
        # download file should not be there anymore and there should be no
        # pending items left
        self.assertTrue(local.exists('/test_KO.odt'))
        self.assertFalse(local.exists('/.test_KO.odt.nxpart'))
        self.assertEquals(len(ctl.list_pending()), 0)
        # In the test workspace there should be 2 files and 2 children taken
        # into account by the local client
        self.assertEquals(len(os.listdir(os.path.join(
                                            self.local_nxdrive_folder_1,
                                            self.workspace_title))), 2)
        self.assertEquals(len(local.get_children_info('/')), 2)
