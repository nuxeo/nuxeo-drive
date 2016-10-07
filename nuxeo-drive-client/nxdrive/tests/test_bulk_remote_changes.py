'''
Created on 12-Aug-2016

@author: dgraja

Technical Background: GetChildren API can throw error due to network issues or server load. 
    GetChildren API is also called when processing remote events.

Issue: When processing remote event, a error in GetChildren API (for a folder) call 
    results in drive failing to process the remaining remote events in the queue.

Fix: Handle the error in GetChildren API gracefully and re-queue same folder again for another remote scan

Testing: This issue can be testing by simulating network of the API using mock framework
    1. Emulate the GetChildren API error by mocking the RemoteFileSystemClient.get_children_info method
    2. The mocked method will raise an exception on demand to simulate the server side / network errors

Note: searching for the following regular expression in log file will filter the manual test case: 
    STEP:|VERIFY:|Error:

'''

from mock import patch
from urllib2 import URLError
import nxdrive
from nxdrive.tests.common_unit_test import log, UnitTestCase
from nxdrive.client.remote_file_system_client import RemoteFileSystemClient
from nxdrive.tests.common import TEST_DEFAULT_DELAY
from time import sleep


network_error = 0
original_get_children_info = RemoteFileSystemClient.get_children_info


def mock_get_children_info(self, *args, **kwargs):
    global network_error
    if network_error > 0:
        network_error = network_error - 1
        # simulate a network error during the call to NuxeoDrive.GetChildren
        raise URLError("Network error simulated for NuxeoDrive.GetChildren ")
    return original_get_children_info(self, *args, **kwargs)


class TestBulkRemoteChanges(UnitTestCase):
    '''
       Test Bulk Remote Changes when network error happen 
       mock_get_children_info will simulate network error when required.
       test_many_changes method will make server side changes, simulate error for GetChildren API 
           and still verify if all remote changes are successfully synced
    '''
    def setUp(self):
        super(TestBulkRemoteChanges, self).setUp()
        self.last_sync_date = None
        self.last_event_log_id = None
        self.last_root_definitions = None
        # Initialize last event log id (lower bound)
        self.wait()
    
    def step(self, msg, *args, **kwargs):
        """
            Can be used to explain a test case STEP. 
            Helpful in reverse engineering manual test case from integration test case
        """
        log.warn("\nSTEP: " + msg, *args, **kwargs)

    def confirm(self, msg, *args, **kwargs):
        """
            Can be used to explain a criteria to VERIFY. 
            Helpful in reverse engineering manual test case from integration test case
        """
        log.warn("\nVERIFY: " + msg, *args, **kwargs)

    @patch.object(nxdrive.client.remote_file_system_client.RemoteFileSystemClient, 'get_children_info', mock_get_children_info)
    def test_many_changes(self):
        """
            Objective: The objective is to make a lot of remote changes (including a folder modified) and 
            wait for nuxeo-drive to successfully sync even if network error happens
            
            1. Configure drive and wait for sync
            2. Create 3 folders folder1, folder2 and shared
            3. Create files inside the 3 folders: folder1/file1.txt, folder2/file2.txt, 
                shared/readme1.txt, shared/readme2.txt
            4. Wait for 3 folders, 4 folder to sync to local PC
            5. Check the 3 folders and 4 files are synced to local PC
            6. Trigger simulation of network error for GetChildren API using the mock (2 successive failures)
            7. Do the following changes in DM side in same order:
                I.   Create 'folder1/sample1.txt'
                II.  Delete 'shared' folder, and immediately restore 'shared' folder
                IV.  Restore 'shared/readme1.txt'
                V.   Create 'shared/readme3.txt'
                VI.  Create 'folder2/sample2.txt'
            8. Wait for remote changes to sync for unaffected folders folder1 and folder2 
            9. Check that folder1/sample1.txt and folder2/sample2.txt are synced to local PC
            10. Sleep for two remote scan attempts (to compenstate for two network failures)
            11. Check if two files 'shared/readme1.txt' and 'shared/readme3.txt' are synced to local PC
             
        """
        global network_error
        remote_client = self.remote_document_client_1
        local_client = self.local_client_1
        
        
        self.engine_1.start()
        self.step("1. Configure drive and wait for sync")
        self.wait_sync(wait_for_async=True)
        
        # create some folders on the server
        self.step("2. Create 3 folders folder1, folder2 and shared")
        folder1 = remote_client.make_folder(self.workspace, u"folder1")
        shared = remote_client.make_folder(self.workspace, u"shared")
        folder2 = remote_client.make_folder(self.workspace, u"folder2")
        
        self.step("3. Create files inside the 3 folders: folder1/file1.txt, folder2/file2.txt, shared/readme1.txt, shared/readme2.txt")
        readme1 = remote_client.make_file(shared, "Readme1.txt", "This is a readme file")
        readme2 = remote_client.make_file(shared, "Readme2.txt", "This is a readme file")
        remote_client.make_file(folder1, "file1.txt", "This is a sample file1")
        remote_client.make_file(folder2, "file2.txt", "This is a sample file2")
        
        self.step("4. Wait for 3 folders, 4 folder to sync to local PC")
        self.wait_sync(wait_for_async=True)
        
        self.confirm("5. Check the 3 folders and 4 files are synced to local PC " +
                     "/folder1/file1.txt, /folder2/file2.txt, /shared/readme1.txt, /shared/readme2.txt")
        self.assertTrue(local_client.exists('/folder1'), "'/folder1' should sync")
        self.assertTrue(local_client.exists('/folder2'), "'/folder1' should sync")
        self.assertTrue(local_client.exists('/shared'), "'/shared' folder should sync")
        self.assertTrue(local_client.exists('/folder1/file1.txt'), "'/folder1/file1.txt' should sync")
        self.assertTrue(local_client.exists('/folder2/file2.txt'), "'/folder2/file2.txt' should sync")
        self.assertTrue(local_client.exists('/shared/readme1.txt'), "'/shared/readme1.txt' should sync")
        self.assertTrue(local_client.exists('/shared/readme2.txt'), "'/shared/readme2.txt' should sync")

        # Simulate network error for GetChildren API twice
        # This is to ensure drive will eventually recover even after multiple failures of GetChildren API
        self.step("6. Trigger simulation of network error for GetChildren API using the mock (2 successive failures)")
        network_error = 2
        self.step("7. Do the following changes in DM side in this order => Create 'folder1/sample1.txt', " +
                " Delete 'shared' folder, and immediately restore 'shared' folder, Restore 'shared/readme1.txt'" + 
                " Create 'shared/readme3.txt', Create 'folder2/sample2.txt'")
        remote_client.make_file(folder1, "sample1.txt", "This is a another sample file1")
        self.remote_document_client_2.register_as_root(shared)
        # Delete folder 'shared'
        remote_client.delete(shared)
        # Restore folder 'shared' from trash
        remote_client.undelete(shared)
        # restore file 'shared/readme1.txt' from trash
        remote_client.undelete(readme1)
        remote_client.make_file(shared, "readme3.txt", "This is a another shared file")
        remote_client.make_file(folder2, "sample2.txt", "This is a another sample file2")
        
        self.step("8. Wait for remote changes to sync for unaffected folders folder1 and folder2")
        self.wait_sync(wait_for_async=True)
        
        self.confirm("9. Check that folder1/sample1.txt and folder2/sample2.txt are synced to local PC")
        self.assertTrue(local_client.exists('/folder2/sample2.txt'), "'/folder2/sample2.txt' should sync")
        self.assertTrue(local_client.exists('/folder1/sample1.txt'), "'/folder1/sample1.txt' should sync")
        
        # Although sync failed for one folder, GetChangeSummary will return zero event in successive calls
        # We need to wait two remote scans, so sleep for TEST_DEFAULT_DELAY * 2
        self.step("10. Sleep for two remote scan attempts (to compenstate for two network failures)")
        sleep(TEST_DEFAULT_DELAY * 2)
        self.confirm("11. Check if two files 'shared/readme1.txt' and 'shared/readme3.txt' are synced to local PC")
        self.assertTrue(local_client.exists('/shared/readme1.txt'), "'/shared/readme1.txt' should sync")
        self.assertTrue(local_client.exists('/shared/readme3.txt'), "'/shared/readme3.txt' should sync")
