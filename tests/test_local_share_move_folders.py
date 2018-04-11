# coding: utf-8
import os
import shutil
from logging import getLogger

from mock import patch

from nxdrive.engine.watcher.remote_watcher import RemoteWatcher
from .common_unit_test import UnitTestCase

log = getLogger(__name__)
wait_for_security_update = False
src = None
dst = None
original_get_changes = RemoteWatcher._get_changes


def mock_get_changes(self, *args, **kwargs):
    global wait_for_security_update 
    global src
    global dst
    if wait_for_security_update:
        summary = original_get_changes(self, *args, **kwargs)
        for event in summary['fileSystemChanges']:
            if event['eventId'] == 'securityUpdated':
                shutil.move(src, dst)
        return summary
    return original_get_changes(self, *args, **kwargs)

class TestLocalShareMoveFolders(UnitTestCase):

    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    FILE_NAME_PATTERN = 'file%03d.%s'

    def setUp(self):
        """
        1. Create folder a1 in Nuxeo Drive Test Workspace sycn root
        2. Create folder a2 in Nuxeo Drive Test Workspace sycn root
        3. Add 10 image files in a1
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        # Create a1 and a2
        self.folder_path_1 = self.local_client_1.make_folder(u'/', u'a1')
        self.folder_path_2 = self.local_client_1.make_folder(u'/', u'a2')

        # Add image files to a1
        abs_folder_path_1 = self.local_client_1.abspath(self.folder_path_1)
        for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1):
            file_name = self.FILE_NAME_PATTERN % (file_num, 'png')
            file_path = os.path.join(abs_folder_path_1, file_name)
            self.generate_random_png(file_path)
        log.debug('Local test files created in a1')

        self.engine_1.start()
        self.wait_sync(timeout=60, wait_win=True)

        # Check local files in a1
        self.assertTrue(self.local_client_1.exists('/a1'))
        children_1 = [child.name for child in self.local_client_1.get_children_info('/a1')]
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a1 is different from original (%d)' %
                         (len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_1), set(['file%03d.png' % file_num
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
        self.assertEqual(set(remote_children_1), set(['file%03d.png' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))
    @patch.object(RemoteWatcher, '_get_changes', mock_get_changes)  
    def test_local_share_move_folder_with_files(self):
        global wait_for_security_update
        admin_remote_client = self.root_remote_client
                     
        global src
        src = self.local_client_1.abspath(self.folder_path_1)
        
        global dst
        dst = self.local_client_1.abspath(self.folder_path_2)
    
        wait_for_security_update = True                                        
        op_input = self.local_client_1.get_remote_id('/a1').split('#')[-1]
        admin_remote_client.execute("Document.AddPermission",
                                    url = admin_remote_client.rest_api_url + 'automation/Document.AddPermission',
                                    op_input=op_input,
                                    username=self.user_2,
                                    permission="Everything",
                                    grant="true")        

        self.wait_sync(enforce_errors=True)
        
        wait_for_security_update = False
                
        # Sync after move operation
        self.wait_sync(enforce_errors=True)
        # Check that a1 doesn't exist anymore locally
        self.assertFalse(self.local_client_1.exists('/a1'))

        # Check local files in a2/a1
        self.assertTrue(self.local_client_1.exists('/a2/a1'))
        children_1 = [child.name for child in self.local_client_1.get_children_info('/a2/a1')]
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of local files (%d) in a1 is different from original (%d)' %
                         (len(children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(children_1), set(['file%03d.png' % file_num
                                               for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))

        # Check that a1 doesn't exist anymore remotely
        self.assertEqual(len(self.remote_document_client_1.get_children_info(self.workspace)), 1)


        # Check remote files in a2/a1
        a1_remote_id = self.local_client_1.get_remote_id('/a2/a1')
        self.assertIsNotNone(a1_remote_id)
        log.debug("Remote ref of a1: %s", a1_remote_id)
        self.assertTrue(self.remote_file_system_client_1.exists(a1_remote_id))

        remote_children_1 = [child.name for child in self.remote_file_system_client_1.get_children_info(a1_remote_id)]
        self.assertEqual(len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES,
                         'Number of remote files (%d) in a1 is different from original (%d)' %
                         (len(remote_children_1), self.NUMBER_OF_LOCAL_IMAGE_FILES))
        self.assertEqual(set(remote_children_1), set(['file%03d.png' % file_num
                                                      for file_num in range(1, self.NUMBER_OF_LOCAL_IMAGE_FILES + 1)]))
        
        # As Admin create a folder inside a1
        parent_folder_uid = admin_remote_client.make_folder(a1_remote_id.split('#')[-1], 'inside_a1')
        
        self.wait_sync(fail_if_timeout=True)
        
        # Check that a1 doesn't exist anymore locally
        self.assertTrue(self.local_client_1.exists('/a2/a1/inside_a1'))
