# coding: utf-8
import os
from unittest import skip

from tests.common import IntegrationTestCase


@skip('NXDRIVE-170: WIP')
class TestIntegrationLocalRootDeletion(IntegrationTestCase):

    """
    def setUp(self):
        super(TestIntegrationLocalRootDeletion, self).setUp()

        self.sb_1 = self.controller_1.bind_server(
            self.local_nxdrive_folder_1,
            self.nuxeo_url, self.user_1, self.password_1)

        self.controller_1.bind_root(self.local_nxdrive_folder_1,
            self.workspace)

        # Deactivate Watchdog as it prevents the Nuxeo Drive folder from being
        # well removed later on by shutil.rmtree, thus re-created by the
        # synchronizer during rollback if activated.
        def no_watchdog():
            return False
        self.controller_1.use_watchdog = no_watchdog

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)

        self.sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                       self.workspace_title)
        self.local_client_1 = LocalClient(self.sync_root_folder_1)

        self.local_client_1.make_file('/', u'Original File 1.txt',
            content=u'Some Content 1'.encode('utf-8'))

        self.local_client_1.make_file('/', u'Original File 2.txt',
            content=u'Some Content 2'.encode('utf-8'))

        self.local_client_1.make_folder(u'/', u'Original Folder 1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.1')
        self.local_client_1.make_folder(
            u'/Original Folder 1', u'Sub-Folder 1.2')
        self.local_client_1.make_file(u'/Original Folder 1',
            u'Original File 1.1.txt',
            content=u'Some Content 1'.encode('utf-8'))  # Same content as OF1

        self.local_client_1.make_folder('/', 'Original Folder 2')
        self.local_client_1.make_file('/Original Folder 2',
            u'Original File 3.txt',
            content=u'Some Content 3'.encode('utf-8'))

        self.controller_1.synchronizer.update_synchronize_server(self.sb_1)
        self.local_client_1.unlock_path(self.sync_root_folder_1)
        # Force the write mode under Windows
        import stat
        if os.access(self.local_nxdrive_folder_1, os.W_OK):
            os.chmod(self.local_nxdrive_folder_1,
                     stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP |
                     stat.S_IRUSR | stat.S_IWGRP | stat.S_IWUSR)
        shutil.rmtree(self.local_nxdrive_folder_1, False)
    """

    def test_without_rollback(self):
        sb, ctl = self.sb_1, self.controller_1
        ctl.synchronizer.update_synchronize_server(sb)
        self.assertFalse(os.path.exists(self.local_nxdrive_folder_1))
        self.assertFalse(sb in ctl.list_server_bindings())

    def test_with_rollback(self):
        sb, ctl = self.sb_1, self.controller_1

        def rollback():
            return True
        ctl.local_rollback = rollback

        ctl.synchronizer.update_synchronize_server(sb)
        self.assertTrue(os.path.exists(self.local_nxdrive_folder_1))
        sb = ctl.list_server_bindings()[0]
        ctl.synchronizer.update_synchronize_server(sb)
        self.assertTrue(os.path.exists(self.sync_root_folder_1))
