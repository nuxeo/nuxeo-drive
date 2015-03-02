'''
@author: Remi Cattiau
'''
import sys
from nxdrive.tests.common_unit_test import UnitTestCase
from nose.plugins.skip import SkipTest


class TestWatchers(UnitTestCase):

    def test_local_scan(self):
        files, folders = self.make_local_tree()
        self.queue_manager_1.pause()
        self.engine_1.start()
        self.wait_remote_scan()
        metrics = self.queue_manager_1.get_metrics()

        # Workspace should have been reconcile
        self.assertEquals(metrics["total_queue"], 4)
        self.assertEquals(metrics["local_folder_queue"], 3)
        self.assertEquals(metrics["local_file_queue"], 1)
        res = self.engine_1.get_dao().get_states_from_partial_local('/')
        # With root
        self.assertEquals(len(res), folders + files + 1)

    def test_reconcile_scan(self):
        if sys.platform == 'win32':
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        files, folders = self.make_local_tree()
        self.make_server_tree()
        self.queue_manager_1.pause()
        self.engine_1.start()
        self.wait_remote_scan()
        # Remote as one more file
        self.assertEquals(self.engine_1.get_dao().get_sync_count(), folders + files + 1)
        # Verify it has been reconcile and all items in queue are sync
        queue = self.get_full_queue(self.queue_manager_1.get_local_file_queue())
        for item in queue:
            self.assertEqual(item.pair_state, "synchronized")
        queue = self.get_full_queue(self.queue_manager_1.get_local_folder_queue())
        for item in queue:
            self.assertEqual(item.pair_state, "synchronized")

    def test_remote_scan(self):
        files, folders = self.make_server_tree()
        # Add the workspace folder
        folders = folders + 1
        self.queue_manager_1.pause()
        self.engine_1.start()
        self.wait_remote_scan()
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["total_queue"], 1)
        self.assertEquals(metrics["remote_folder_queue"], 1)
        self.assertEquals(metrics["remote_file_queue"], 0)
        self.assertEquals(metrics["local_file_queue"], 0)
        self.assertEquals(metrics["local_folder_queue"], 0)
        res = self.engine_1.get_dao().get_states_from_partial_local('/')
        # With root
        self.assertEquals(len(res), folders + files + 1)

    def test_local_watchdog_creation(self):
        # Test the creation after first local scan
        self.queue_manager_1.pause()
        self.engine_1.start()
        self.wait_remote_scan()
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["local_folder_queue"], 0)
        self.assertEquals(metrics["local_file_queue"], 0)
        files, folders = self.make_local_tree()
        self.wait_sync(2, fail_if_timeout=False)
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["local_folder_queue"], 2)
        self.assertEquals(metrics["local_file_queue"], 1)
        res = self.engine_1.get_dao().get_states_from_partial_local('/')
        # With root
        self.assertEquals(len(res), folders + files + 1)

    def _delete_folder_1(self):
        path = '/Folder 1'
        self.local_client_1.delete_final(path)
        if sys.platform == 'win32':
            from time import sleep
            from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
            sleep(WIN_MOVE_RESOLUTION_PERIOD + 1)
        self.wait_sync(1, fail_if_timeout=False)
        return '/' + self.workspace_title + path + '/'

    def test_local_watchdog_delete_non_synced(self):
        # Test the deletion after first local scan
        self.test_local_scan()
        path = self._delete_folder_1()
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEquals(len(children), 0)

    def test_local_scan_delete_non_synced(self):
        if sys.platform == 'win32':
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Test the deletion after first local scan
        self.test_local_scan()
        self.engine_1.stop()
        path = self._delete_folder_1()
        self.engine_1.start()
        self.wait_sync(1, fail_if_timeout=False)
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEquals(len(children), 0)

    def test_local_watchdog_delete_synced(self):
        if sys.platform == 'win32':
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        path = self._delete_folder_1()
        child = self.engine_1.get_dao().get_state_from_local(path[:-1])
        self.assertEqual(child.pair_state, 'locally_deleted')
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEqual(len(children), 5)
        for child in children:
            self.assertEqual(child.pair_state, 'parent_locally_deleted')

    def test_local_scan_delete_synced(self):
        if sys.platform == 'win32':
            raise SkipTest("WIP in https://jira.nuxeo.com/browse/NXDRIVE-170")
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        self.engine_1.stop()
        path = self._delete_folder_1()
        self.engine_1.start()
        self.wait_sync(1, fail_if_timeout=False)
        child = self.engine_1.get_dao().get_state_from_local(path[:-1])
        self.assertEqual(child.pair_state, 'locally_deleted')
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEqual(len(children), 5)
        for child in children:
            self.assertEqual(child.pair_state, 'parent_locally_deleted')
