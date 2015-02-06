'''
@author: Remi Cattiau
'''
from nxdrive.tests.common_unit_test import UnitTestCase
from time import sleep
from PyQt4 import QtCore

class Slots(QtCore.QObject):
    @QtCore.pyqtSlot()
    def engine_started(self):
        print "Engine started"


class TestLocalWatcher(UnitTestCase):

    def test_local_scan(self):
        test = Slots()
        files, folders = self.make_local_tree()
        self.queue_manager_1.pause()
        self.engine_1._start.connect(test.engine_started)
        self.engine_1.start()
        self._interact(1)
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["total_queue"], folders + files)
        self.assertEquals(metrics["local_folder_queue"], folders)
        self.assertEquals(metrics["local_file_queue"], files)

    def test_reconcile_scan(self):
        test = Slots()
        files, folders = self.make_local_tree()
        self.make_server_tree()
        self.queue_manager_1.pause()
        self.engine_1._start.connect(test.engine_started)
        self.engine_1.start()
        self._interact(10)
        metrics = self.queue_manager_1.get_metrics()
        print "%r" % metrics
        queue = self.get_full_queue(self.queue_manager_1.get_local_file_queue())
        print "QUEUE: %r" % queue
        # Remote as one more file
        self.assertEquals(metrics["total_queue"], folders + files + 1)
        self.assertEquals(metrics["local_folder_queue"], folders)
        self.assertEquals(metrics["local_file_queue"], files)
        self.assertEquals(metrics["remote_file_queue"], 1)
        # Verify it has been reconcile
        queue = self.get_full_queue(self.queue_manager_1.get_local_file_queue())
        for item in queue:
            self.assertEqual(item.pair_state, "synchronized")
        queue = self.get_full_queue(self.queue_manager_1.get_local_folder_queue())
        for item in queue:
            self.assertEqual(item.pair_state, "synchronized")

    def test_remote_scan(self):
        test = Slots()
        files, folders = self.make_server_tree()
        # Add the workspace folder
        folders = folders + 1
        self.queue_manager_1.pause()
        self.engine_1._start.connect(test.engine_started)
        self.engine_1.start()
        self._interact(10)
        # Metrics should be the same as the local scan
        metrics = self.queue_manager_1.get_metrics()
        self.assertEquals(metrics["total_queue"], folders + files)
        self.assertEquals(metrics["remote_folder_queue"], folders)
        self.assertEquals(metrics["remote_file_queue"], files)
