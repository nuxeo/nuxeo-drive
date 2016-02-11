from nxdrive.tests.common_unit_test import UnitTestCase
from nxdrive.tests import RemoteTestClient
from nxdrive.client.remote_filtered_file_system_client import RemoteFilteredFileSystemClient


class TestLocalStorageSpaceIssue(UnitTestCase):

    def test_synchronize_no_space_left_on_device(self):
        local = self.local_client_1
        remote = self.remote_document_client_1

        # Synchronize root workspace
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/'))
        self.engine_1.stop()

        # Create a file in the remote root workspace
        remote.make_file('/', 'test_KO.odt', 'Some large content.')

        # Synchronize simulating a "No space left on device" error
        self.engine_1.remote_filtered_fs_client_factory = RemoteTestClient
        self.engine_1.invalidate_client_cache()
        error = IOError("No space left on device")
        self.engine_1.get_remote_client().make_download_raise(error)
        self.engine_1.start()
        # By default engine will not consider being syncCompleted because of the blacklist
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False, enforce_errors=False)
        # Temporary download file (.nxpart) should be created locally but not renamed then removed
        # Synchronization should not fail: doc pair should be blacklisted and there should be 1 error
        self.assertNxPart('/', name='test_KO.odt', present=False)
        self.assertFalse(local.exists('/test_KO.odt'))
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        self.assertEquals(len(states_in_error), 1)
        self.assertEquals(states_in_error[0].remote_name, 'test_KO.odt')

        # Create another file in the remote root workspace
        remote.make_file('/', 'test_OK.odt', 'Some small content.')

        # Synchronize without simulating any error
        self.engine_1.get_remote_client().make_download_raise(None)
        self.engine_1.remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient
        self.engine_1.invalidate_client_cache()
        self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False, enforce_errors=False)
        # Remote file should be created locally
        self.assertTrue(local.exists('/test_OK.odt'))
        # Blacklisted file should be ignored as delay (60 seconds by default)
        # is not expired and there should still be 1 error
        self.assertFalse(local.exists('/test_KO.odt'))
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        self.assertEquals(len(states_in_error), 1)
        self.assertEquals(states_in_error[0].remote_name, 'test_KO.odt')

        # Retry to synchronize blacklisted file still simulating a "No space left on device" error
        self.engine_1.remote_filtered_fs_client_factory = RemoteTestClient
        self.engine_1.invalidate_client_cache()
        self.engine_1.get_remote_client().make_download_raise(error)
        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(timeout=5, fail_if_timeout=False, enforce_errors=False)
        # Doc pair should be blacklisted again and there should still be 1 error
        self.assertNxPart('/', name='test_KO.odt', present=False)
        self.assertFalse(local.exists('/test_KO.odt'))
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        self.assertEquals(len(states_in_error), 1)
        self.assertEquals(states_in_error[0].remote_name, 'test_KO.odt')

        # Synchronize without simulating any error, as if space had been made
        # available on device
        self.engine_1.get_remote_client().make_download_raise(None)
        self.engine_1.remote_filtered_fs_client_factory = RemoteFilteredFileSystemClient
        self.engine_1.invalidate_client_cache()
        # Re-queue pairs in error
        self.queue_manager_1.requeue_errors()
        self.wait_sync(enforce_errors=False)
        # Previously blacklisted file should be created locally and there should be no more errors left
        self.assertNxPart('/', name='test_KO.odt', present=False)
        self.assertTrue(local.exists('/test_KO.odt'))
        states_in_error = self.engine_1.get_dao().get_errors(limit=0)
        self.assertEquals(len(states_in_error), 0)
