import os
import shutil
import random

from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.tests.common_unit_test import log


class TestLocalMoveFolders(UnitTestCase):

    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    FILE_NAME_PATTERN = 'file%03d.%s'

    def setUp(self):
        """
        1. Create folder a1 in Nuxeo Drive Test Workspace sycn root
        2. Create folder a2 in Nuxeo Drive Test Workspace sycn root
        3. Add 10 image files in a1
        4. Add 10 image files in a2
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        # Create a1 and a2
        self.folder_path_1 = self.local_client_1.make_folder(u'/', u'a1')
        self.folder_path_2 = self.local_client_1.make_folder(u'/', u'a2')

        # Add image files to a1
        abs_folder_path_1 = self.local_client_1._abspath(self.folder_path_1)
        for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1):
            file_name = self.FILE_NAME_PATTERN % (file_num, 'jpg')
            file_path = os.path.join(abs_folder_path_1, file_name)
            self.generate_random_jpg(file_path, random.randint(1000, 3000))
        log.debug('Local test files created in a1')

        # Add image files to a2
        abs_folder_path_2 = self.local_client_1._abspath(self.folder_path_2)
        for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1):
            file_name = self.FILE_NAME_PATTERN % (file_num, 'jpg')
            file_path = os.path.join(abs_folder_path_2, file_name)
            self.generate_random_jpg(file_path, random.randint(1000, 3000))
        log.debug('Local test files created in a2')

        self.engine_1.start()
        self.wait_sync(timeout=60, wait_win=True)

        # Check local files in a1
        self.assertTrue(self.local_client_1.exists('/a1'))
        children_1 = [child.name for child in self.local_client_1.get_children_info('/a1')]
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a1 is different from original (%d)' %
                         (len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_1), set(['file%03d.jpg' % file_num
                                               for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check local files in a2
        self.assertTrue(self.local_client_1.exists('/a2'))
        children_2 = [child.name for child in self.local_client_1.get_children_info('/a2')]
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a2 is different from original (%d)' %
                         (len(children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_2), set(['file%03d.jpg' % file_num
                                               for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check remote files in a1
        a1_remote_id = self.local_client_1.get_remote_id('/a1')
        self.assertIsNotNone(a1_remote_id)
        log.debug("Remote ref of a1: %s", a1_remote_id)
        self.assertTrue(self.remote_file_system_client_1.exists(a1_remote_id))

        remote_children_1 = [child.name for child in self.remote_file_system_client_1.get_children_info(a1_remote_id)]
        self.assertEqual(len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of remote files (%d) in a1 is different from original (%d)' %
                         (len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(remote_children_1), set(['file%03d.jpg' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check remote files in a2
        a2_remote_id = self.local_client_1.get_remote_id('/a2')
        self.assertIsNotNone(a2_remote_id)
        log.debug("Remote ref of a2: %s", a2_remote_id)
        self.assertTrue(self.remote_file_system_client_1.exists(a2_remote_id))

        remote_children_2 = [child.name for child in self.remote_file_system_client_1.get_children_info(a2_remote_id)]
        self.assertEqual(len(remote_children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of remote files (%d) in a2 is different from original (%d)' %
                         (len(remote_children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(remote_children_2), set(['file%03d.jpg' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

    def test_local_move_folder_with_files(self):
        src = self.local_client_1._abspath(self.folder_path_1)
        dst = self.local_client_1._abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync()

        # Check that a1 doesn't exist anymore locally
        self.assertFalse(self.local_client_1.exists('/a1'))

        # Check local files in a2
        self.assertTrue(self.local_client_1.exists('/a2'))
        children_2 = [child.name for child in self.local_client_1.get_children_info('/a2') if not child.folderish]
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a2 is different from original (%d)' %
                         (len(children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_2), set(['file%03d.jpg' % file_num
                                               for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check local files in a2/a1
        self.assertTrue(self.local_client_1.exists('/a2/a1'))
        children_1 = [child.name for child in self.local_client_1.get_children_info('/a2/a1')]
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a1 is different from original (%d)' %
                         (len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_1), set(['file%03d.jpg' % file_num
                                               for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check that a1 doesn't exist anymore remotely
        self.assertEqual(len(self.remote_document_client_1.get_children_info(self.workspace)), 1)

        # Check remote files in a2
        a2_remote_id = self.local_client_1.get_remote_id('/a2')
        self.assertIsNotNone(a2_remote_id)
        log.debug("Remote ref of a2: %s", a2_remote_id)
        self.assertTrue(self.remote_file_system_client_1.exists(a2_remote_id))

        remote_children_2 = [child.name for child in self.remote_file_system_client_1.get_children_info(a2_remote_id)
                             if not child.folderish]
        self.assertEqual(len(remote_children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of remote files (%d) in a2 is different from original (%d)' %
                         (len(remote_children_2), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(remote_children_2), set(['file%03d.jpg' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))
        # Check remote files in a2/a1
        a1_remote_id = self.local_client_1.get_remote_id('/a2/a1')
        self.assertIsNotNone(a1_remote_id)
        log.debug("Remote ref of a1: %s", a1_remote_id)
        self.assertTrue(self.remote_file_system_client_1.exists(a1_remote_id))

        remote_children_1 = [child.name for child in self.remote_file_system_client_1.get_children_info(a1_remote_id)]
        self.assertEqual(len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of remote files (%d) in a1 is different from original (%d)' %
                         (len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(remote_children_1), set(['file%03d.jpg' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))
