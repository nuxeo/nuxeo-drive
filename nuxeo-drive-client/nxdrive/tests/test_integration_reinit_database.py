import os
import time
import shutil

from nxdrive.tests.common import IntegrationTestCase
from nxdrive.controller import Controller
from nxdrive.model import LastKnownState


class TestIntegrationReinitDatabase(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationReinitDatabase, self).setUp()
        self.syn, self.local, self.remote = self.init_default_drive()
        self.ctl = self.controller_1
        # Make a folder and a file
        self.remote.make_folder('/', 'Test folder')
        self.remote.make_file('/Test folder', 'Test.txt',
                              'This is some content')
        self.test_remote_folder_id = self.remote.get_info('/Test folder').uid
        # Wait for synchro
        self._synchronize()
        # Verify that all is synchronize
        self.assertTrue(self.local.exists('/Test folder'),
                        'Local folder should exist')
        self.assertTrue(self.local.exists('/Test folder/Test.txt'),
                        'Local file should exist')
        # Destroy database
        self._reinit_database()

    def _check_states(self):
        rows = self.controller_1.get_session().query(LastKnownState).all()
        for row in rows:
            self.assertEquals(row.pair_state, 'synchronized')

    def _reinit_database(self):
        # Close database
        self.ctl.dispose()
        # Destroy configuration folder
        shutil.rmtree(self.nxdrive_conf_folder_1)
        os.mkdir(self.nxdrive_conf_folder_1)
        # Recreate a controller
        self.ctl = Controller(self.nxdrive_conf_folder_1)
        self.ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        self.ctl.bind_root(self.local_nxdrive_folder_1, self.workspace)
        self.syn = self.ctl.synchronizer

    def _synchronize(self, loops=1):
        time.sleep(self.AUDIT_CHANGE_FINDER_TIME_RESOLUTION)
        self.wait()
        self.syn.loop(delay=0.1, max_loops=loops)

    def test_synchronize_folderish_and_same_digest(self):
        # Reload sync
        self._synchronize()
        # Check everything is synchronized
        self._check_states()

    def test_synchronize_remote_change(self):
        # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt',
                                   'Content has changed')
        # Sync
        self._synchronize()
        # Check everything is synchronized
        self._check_states()
        # Assert content has changed
        self.assertEquals(self.local.get_content('/Test folder/Test.txt'),
                          'Content has changed', 'Content should be the same')

    def test_synchronize_local_change(self):
        # Modify the local file
        self.local.update_content('/Test folder/Test.txt',
                                   'Content has changed')
        # Sync
        self._synchronize()
        # Check everything is synchronized
        self._check_states()
        # Assert content has changed
        self.assertEquals(self.remote.get_content('/Test folder/Test.txt'),
                          'Content has changed', 'Content should be the same')

    def test_synchronize_remote_and_local_change(self):
                # Modify the remote file
        self.remote.update_content('/Test folder/Test.txt',
                                   'Content has remote changed')
        # Modify the local file
        self.local.update_content('/Test folder/Test.txt',
                                   'Content has local changed')
        # Sync
        self._synchronize()
        # As a conflict has been raised 2 files local should be present
        self.assertEqual(len(self.local.get_children_info("/Test folder")), 2)
        self.assertEqual(len(self.remote.get_children_info(
                                            self.test_remote_folder_id)), 1)

        # end the conflict resolution by upload the second local file to server
        self._synchronize(3)
        self.assertEqual(len(self.local.get_children_info("/Test folder")), 2)
        self.assertEqual(len(self.remote.get_children_info(
                                            self.test_remote_folder_id,
                                            types=('File', 'Note'))), 2)
