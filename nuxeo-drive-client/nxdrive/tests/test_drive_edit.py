import os
import time
from nose.plugins.skip import SkipTest

from nxdrive.client import LocalClient
from nxdrive.client.common import LOCALLY_EDITED_FOLDER_NAME
from nxdrive.tests.common_unit_test import UnitTestCase

DRIVE_EDIT_XATTR_NAMES = ['ndrive', 'nxdriveedit', 'nxdriveeditdigest', 'nxdriveeditname']


class TestDriveEdit(UnitTestCase):

    locally_edited_path = ('/default-domain/UserWorkspaces/'
                           + 'nuxeoDriveTestUser-user-1/Collections/'
                           + LOCALLY_EDITED_FOLDER_NAME)

    def setUpApp(self):
        super(TestDriveEdit, self).setUpApp()
        self.drive_edit = self.manager_1.get_drive_edit()
        self.drive_edit.driveEditUploadCompleted.connect(self.app.sync_completed)
        self.drive_edit.start()

        self.remote = self.remote_document_client_1
        self.local = LocalClient(os.path.join(self.nxdrive_conf_folder_1, 'edit'))

    def tearDownApp(self):
        self.drive_edit.stop()
        super(TestDriveEdit, self).tearDownApp()

    def test_filename_encoding(self):
        filename = u'Mode op\xe9ratoire.txt'
        doc_id = self.remote.make_file('/', filename, 'Some content.')

        # Linux / Win + Chrome: quoted utf-8 encoded
        browser_filename = 'Mode%20op%C3%A9ratoire.txt'
        self._drive_edit_update(doc_id, filename, browser_filename, 'Win + Chrome')

        # Win + IE: unquoted utf-8 encoded
        browser_filename = 'Mode op\xc3\xa9ratoire.txt'
        self._drive_edit_update(doc_id, filename, browser_filename, 'Win + IE')

        # Win + FF: quoted string containing unicode
        browser_filename = 'Mode%20op\xe9ratoire.txt'
        self._drive_edit_update(doc_id, filename, browser_filename, 'Win + FF')

        # OSX + Chrome / OSX + FF: quoted utf-8 encoded, except for white spaces!
        browser_filename = 'Mode op%C3%A9ratoire.txt'
        self._drive_edit_update(doc_id, filename, browser_filename, 'OS X + Chrome or FF')

    def _office_locker(self, path):
        return os.path.join(os.path.dirname(path), "~$" + os.path.basename(path)[2:])

    def _openoffice_locker(self, path):
        return os.path.join(os.path.dirname(path), ".~lock." + os.path.basename(path)[2:])

    #def test_autolock_office(self):
    #    self._autolock(self._office_locker)

    #def test_autolock_openoffice(self):
    # LibreOffice as well
    #    self._autolock(self._openoffice_locker)

    def _autolock(self, locker):
        global called_open, lock_file
        called_open = False
        filename = u'Document.docx'
        doc_id = self.remote.make_file('/', filename, 'Some content.')
        def open_local_file (path):
            global called_open, lock_file
            called_open = True
            # Lock file
            lock_file = locker(path)
            with open(lock_file, 'w') as f:
                f.write("plop")
        self.manager_1.open_local_file = open_local_file
        self.manager_1.set_drive_edit_auto_lock(1)
        self.drive_edit._manager.open_local_file = open_local_file
        self.drive_edit.edit(self.nuxeo_url, doc_id, filename=filename, user=self.user_1)
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.assertTrue(called_open, "Should have called open_local_file")
        # Should be able to test lock
        self.assertTrue(self.remote_restapi_client_1.is_locked(doc_id))
        os.remove(lock_file)
        self.wait_sync(timeout=2, fail_if_timeout=False)
        # Should be unlock
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))
        self.manager_1.set_drive_edit_auto_lock(0)
        with open(lock_file, 'w') as f:
            f.write("plop")
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))

    def _drive_edit_update(self, doc_id, filename, browser_filename, content):
        # Download file
        local_path = '/%s/%s' % (doc_id, filename)
        self.drive_edit._prepare_edit(self.nuxeo_url, doc_id, browser_filename)
        self.assertTrue(self.local.exists(local_path))
        self.wait_sync(timeout=2, fail_if_timeout=False)
        self.local.delete_final(local_path)

        # Update file content
        self.local.update_content(local_path, content)
        self.wait_sync()
        self.assertEquals(self.remote.get_content('/' + filename), content)
