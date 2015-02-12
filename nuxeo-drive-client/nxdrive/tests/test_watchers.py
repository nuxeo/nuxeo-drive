'''
@author: Remi Cattiau
'''
from nxdrive.tests.common_unit_test import UnitTestCase


class TestWatchers(UnitTestCase):

    def test_local_scan(self):
        files, folders = self.make_local_tree()
        self.queue_manager_1.pause()
        self.engine_1.start()
        self._interact(1)
        metrics = self.queue_manager_1.get_metrics()
        # Only one file is in the root
        self.assertEquals(metrics["total_queue"], 1)
        self.assertEquals(metrics["local_folder_queue"], 1)
        self.assertEquals(metrics["local_file_queue"], 0)
        self.assertEquals(metrics["remote_file_queue"], 0)
        self.assertEquals(metrics["remote_folder_queue"], 0)
        res = self.engine_1.get_dao().get_states_from_partial_local('/')
        # With root
        self.assertEquals(len(res), folders + files + 1)

    def test_reconcile_scan(self):
        files, folders = self.make_local_tree()
        self.make_server_tree()
        self.queue_manager_1.pause()
        self.engine_1.start()
        self._interact(10)
        metrics = self.queue_manager_1.get_metrics()
        # Remote as one more file
        self.assertEquals(metrics["total_queue"], 2)
        self.assertEquals(metrics["local_folder_queue"], 1)
        self.assertEquals(metrics["local_file_queue"], 0)
        self.assertEquals(metrics["remote_file_queue"], 1)
        self.assertEquals(metrics["remote_folder_queue"], 0)
        self.assertEquals(self.engine_1.get_dao().get_sync_count(), folders + files + 1)
        # Verify it has been reconcile
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
        self._interact(10)
        # Metrics should be the same as the local scan
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
        self._interact(1)
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["total_queue"], 0)
        self.assertEquals(metrics["local_folder_queue"], 0)
        self.assertEquals(metrics["local_file_queue"], 0)
        self.assertEquals(metrics["remote_file_queue"], 0)
        self.assertEquals(metrics["remote_folder_queue"], 0)
        files, folders = self.make_local_tree()
        self._interact(1)
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["total_queue"], 1)
        self.assertEquals(metrics["local_folder_queue"], 1)
        self.assertEquals(metrics["local_file_queue"], 0)
        self.assertEquals(metrics["remote_file_queue"], 0)
        self.assertEquals(metrics["remote_folder_queue"], 0)
        res = self.engine_1.get_dao().get_states_from_partial_local('/')
        # With root
        self.assertEquals(len(res), folders + files + 1)

    def _delete_folder_1(self):
        path = '/' + self.workspace_title + '/Folder 1'
        self.local_client_1.delete_final(path)
        self._interact(1)
        return path + '/'

    def test_local_watchdog_delete_non_synced(self):
        # Test the deletion after first local scan
        self.test_local_scan()
        path = self._delete_folder_1()
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEquals(len(children), 0)

    def test_local_scan_delete_non_synced(self):
        # Test the deletion after first local scan
        self.test_local_scan()
        self.engine_1.stop()
        self._interact(1)
        path = self._delete_folder_1()
        self.engine_1.start()
        self._interact(1)
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEquals(len(children), 0)

    def test_local_watchdog_delete_synced(self):
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        path = self._delete_folder_1()
        self._interact(1)
        child = self.engine_1.get_dao().get_state_from_local(path[:-1])
        self.assertEqual(child.pair_state, 'locally_deleted')
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEqual(len(children), 5)
        for child in children:
            self.assertEqual(child.pair_state, 'parent_locally_deleted')

    def test_local_scan_delete_synced(self):
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        self.engine_1.stop()
        self._interact(1)
        path = self._delete_folder_1()
        self.engine_1.start()
        self._interact(1)
        child = self.engine_1.get_dao().get_state_from_local(path[:-1])
        self.assertEqual(child.pair_state, 'locally_deleted')
        children = self.engine_1.get_dao().get_states_from_partial_local(path)
        self.assertEqual(len(children), 5)
        for child in children:
            self.assertEqual(child.pair_state, 'parent_locally_deleted')
