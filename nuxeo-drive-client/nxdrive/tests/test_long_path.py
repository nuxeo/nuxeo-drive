'''
Created on Dec 22, 2016

@author: mkeshava
@author: dgraja

'''
from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.logging_config import get_logger
import os
import sys


log = get_logger(__name__)
if sys.platform == "win32":
    import win32api


# number of chars in path c://.../Nuxeo.. is approx 96 chars
FOLDER_A = "A" * (90)
FOLDER_B = "B" * (90)
FOLDER_C = "C" * (90)
FOLDER_D = "D" * (50)


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

    def test_long_Path(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        base_folder_path = self.local_1._abspath("/")
        if sys.platform == "win32":
            if not os.path.exists(base_folder_path):
                log.info("prefix the path with \\\\?\\ in windows platform")
                base_folder_path = "\\\\?\\" + base_folder_path
        # Creating new folder under "/CCCCCCC.../"
        parent_path = os.path.join(base_folder_path,
                                   FOLDER_A, FOLDER_B, FOLDER_C)
        if sys.platform == 'win32':
            if not os.path.exists(parent_path):
                log.info("prefix the path with \\\\?\\ in windows platform")
                parent_path = "\\\\?\\" + parent_path
            log.info("Convert path of FOLDER_D to short path format")
            parent_path = win32api.GetShortPathName(parent_path)
        new_folder_path = os.path.join(parent_path, FOLDER_D)
        log.info("Creating folder with path: %s", new_folder_path)
        os.makedirs(new_folder_path)
        if sys.platform == 'win32':
            log.info("Convert path of FOLDER_D\File2.txt to short path format")
            new_folder_path = win32api.GetShortPathName(new_folder_path)

        new_file_path = os.path.join(new_folder_path, "File2.txt")
        log.info("Creating file with path: %s", new_file_path)
        with open(new_file_path, "w") as f:
            f.write("Hello world")

        self.wait_sync(wait_for_async=True, timeout=45, fail_if_timeout=False)
        remote_children_of_c = self.remote_1.get_children_info(self.folder_c)
        children_names = [item.name for item in remote_children_of_c]
        log.warn("Verify if FOLDER_D is uploaded to server")
        self.assertTrue(FOLDER_D in children_names,
                        "FOLDER_D should be uploaded to server")
        folder_d = [item.uid for item in remote_children_of_c if item.name == FOLDER_D][0]
        remote_children_of_d = self.remote_1.get_children_info(folder_d)
        children_names = [item.name for item in remote_children_of_d]
        log.warn("Verify if FOLDER_D\File2.txt is uploaded to server")
        self.assertTrue("File2.txt" in children_names,
                        "FOLDER_D/File2.txt should be uploaded to server")
