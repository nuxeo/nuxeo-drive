'''
@author: Remi Cattiau
'''
import unittest
import time
from nxdrive.engine.dao.alchemy import AlchemyDAO
from nxdrive.engine.watcher.local_watcher import LocalWatcher
from nxdrive.tests.common import IntegrationTestCase

class LocalWatcherTest(IntegrationTestCase):

    benchmark = u'/Users/looping/nuxeo/sources/nuxeo/addons/nuxeo-drive/tools/benchmark/benchmark_files'

    def setUp(self):
        super(LocalWatcherTest, self).setUp()
        self.session = self.controller_1.get_session()
        self.controller_1.synchronizer.test_delay = 0
        self.sb_1 = self.controller_1.bind_server(
            self.benchmark,
            self.nuxeo_url, self.user_1, self.password_1)
        self.watchdog = False
        results = list()
        start = time.time()
        # Without watchdog
        #for i in range(0, 3):
        self.old_scan()
        end = time.time()
        results.append("W/O watchdog: %d" % (end - start))
        self.watchdog = True
        self.controller_1.unbind_all()
        self.sb_1 = self.controller_1.bind_server(
            self.benchmark,
            self.nuxeo_url, self.user_1, self.password_1)
        start = time.time()
        # With watchdog
        #for i in range(0, 3):
        self.old_scan()
        end = time.time()
        results.append("W watchdog: %d" % (end - start))
        self.controller_1.unbind_all()
        self.sb_1 = self.controller_1.bind_server(
            self.benchmark,
            self.nuxeo_url, self.user_1, self.password_1)

        dao = AlchemyDAO(self.benchmark, self.session)
        watcher = LocalWatcher(dao, self.benchmark, self.controller_1)
        start = time.time()
        for i in range(0, 3):
            watcher.scan()
        end = time.time()
        results.append("New: %d" % (end - start))
        for line in results:
            print line

    def old_scan(self):
        if self.watchdog and not self.first_pass:
            self.controller_1.synchronizer.watchdog_local(self.sb_1, session=self.session)
        else:
            self.first_pass = False
            self.controller_1.synchronizer.scan_local(self.sb_1, session=self.session)

    def testName(self):
        pass


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()