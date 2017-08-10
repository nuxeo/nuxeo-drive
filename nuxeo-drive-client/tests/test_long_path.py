# coding: utf-8
import os
import sys

from nxdrive.logging_config import get_logger
from nxdrive.utils import safe_long_path
from tests.common_unit_test import UnitTestCase

if sys.platform == 'win32':
    import win32api


log = get_logger(__name__)

# Number of chars in path c://.../Nuxeo.. is approx 96 chars
FOLDER_A = 'A' * 90
FOLDER_B = 'B' * 90
FOLDER_C = 'C' * 90
FOLDER_D = 'D' * 50


class TestLongPath(UnitTestCase):
    def setUp(self):
        UnitTestCase.setUp(self)
        self.local_1 = self.local_client_1
        self.remote_1 = self.remote_document_client_1
        log.info("Create a folder AAAA... (90 chars) in server")
        self.folder_a = self.remote_1.make_folder("/", FOLDER_A)
        self.folder_b = self.remote_1.make_folder(self.folder_a, FOLDER_B)
        self.folder_c = self.remote_1.make_folder(self.folder_b, FOLDER_C)
        self.remote_1.make_file(self.folder_c, "File1.txt", "Sample Content")

    def tearDown(self):
        log.info("Delete the folder AAA... in server")
        self.remote_1.delete(self.folder_a, use_trash=False)
        UnitTestCase.tearDown(self)

    def test_long_path(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        parent_path = os.path.join(self.local_1.abspath('/'),
                                   FOLDER_A, FOLDER_B, FOLDER_C, FOLDER_D)
        log.info("Creating folder with path: %s", parent_path)
        if sys.platform == 'win32' and not os.path.exists(parent_path):
            log.debug('Add \\\\?\\ prefix to path %r', parent_path)
            parent_path = safe_long_path(parent_path)
        os.makedirs(parent_path)

        if sys.platform == 'win32':
            log.info("Convert path of FOLDER_D\File2.txt to short path format")
            parent_path = win32api.GetShortPathName(parent_path)

        new_file = os.path.join(parent_path, "File2.txt")
        log.info("Creating file with path: %s", new_file)
        with open(new_file, "w") as f:
            f.write("Hello world")

        self.wait_sync(wait_for_async=True, timeout=45, fail_if_timeout=False)
        remote_children_of_c = self.remote_1.get_children_info(self.folder_c)
        children_names = [item.name for item in remote_children_of_c]
        log.warn("Verify if FOLDER_D is uploaded to server")
        self.assertIn(FOLDER_D, children_names)
        folder_d = [item.uid for item in remote_children_of_c if item.name == FOLDER_D][0]
        remote_children_of_d = self.remote_1.get_children_info(folder_d)
        children_names = [item.name for item in remote_children_of_d]
        log.warn("Verify if FOLDER_D\File2.txt is uploaded to server")
        self.assertIn('File2.txt', children_names)

    def test_setup_on_long_path(self):
        """ NXDRIVE 689: Fix error when adding a new account when installation
            path is greater than 245 characters.
        """

        self.engine_1.stop()
        self.engine_1.reinit()

        # On Mac, avoid permission denied error
        self.engine_1.get_local_client().clean_xattr_root()

        test_folder_len = 245 - len(str(self.local_nxdrive_folder_1))
        test_folder = 'A' * test_folder_len

        self.local_nxdrive_folder_1 = os.path.join(self.local_nxdrive_folder_1,
                                                   test_folder)
        self.assertTrue(len(self.local_nxdrive_folder_1) > 245)

        self.manager_1.unbind_all()
        self.engine_1 = self.manager_1.bind_server(
                self.local_nxdrive_folder_1, self.nuxeo_url, self.user_2,
                self.password_2, start_engine=False)

        self.engine_1.start()
        self.engine_1.stop()
