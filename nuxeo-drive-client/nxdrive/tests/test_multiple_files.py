'''
Created on Jul 29, 2015

@author: constantinm
Adapted to Drive
'''

from common_unit_test import UnitTestCase
from nxdrive.tests.common_unit_test import log
from nose.plugins.skip import SkipTest

import os
import shutil


class MultipleFilesTestCase(UnitTestCase):
    FILE_CONTENT = """
        Lorem ipsum dolor sit amet, consectetur adipiscing elit. Ut egestas condimentum egestas.
        Vestibulum ut facilisis neque, eu finibus mi. Proin ac massa sapien. Sed mollis posuere erat vel malesuada.
        Nulla non dictum nulla. Quisque eu porttitor leo. Nunc auctor vitae risus non dapibus. Integer rhoncus laoreet varius.
        Donec pulvinar dapibus finibus. Suspendisse vitae diam quam. Morbi tincidunt arcu nec ultrices consequat.
        Nunc ornare turpis pellentesque augue laoreet, non sollicitudin lectus aliquam.
        Sed posuere vel arcu ut elementum. In dictum commodo nibh et blandit. Vivamus sed enim sem.
        Nunc interdum rhoncus eros gravida vestibulum. Suspendisse sit amet feugiat mauris, eget tristique est.
        Ut efficitur mauris quis tortor laoreet semper. Pellentesque eu tincidunt tortor, malesuada rutrum massa.
        Class aptent taciti sociosqu ad litora torquent per conubia nostra, per inceptos himenaeos.
        Duis gravida, turpis at pulvinar dictum, arcu lacus dapibus nisl, eget luctus metus sapien id turpis.
        Donec consequat gravida diam at bibendum. Vivamus tincidunt congue nisi, quis finibus eros tincidunt nec.
        Aenean ut leo non nulla sodales dapibus. Quisque sit amet vestibulum urna.
        Vivamus imperdiet sed elit eu aliquam. Maecenas a ultrices diam. Praesent dapibus interdum orci pellentesque tempor.
        Morbi a luctus dui. Integer nec risus sit amet turpis varius lobortis. Vestibulum at ligula ut purus vestibulum pharetra.
        Fusce est libero, tristique in magna sed, ullamcorper consectetur justo. Aliquam erat volutpat.
        Mauris sollicitudin neque sit amet augue congue, a ornare mi iaculis. Praesent vestibulum laoreet urna, at sodales
        velit cursus iaculis.
        Sed quis enim hendrerit, viverra leo placerat, vestibulum nulla. Vestibulum ligula nisi, semper et cursus eu, gravida at enim.
        Vestibulum vel auctor augue. Aliquam pulvinar diam at nunc efficitur accumsan. Proin eu sodales quam.
        Quisque consectetur euismod mauris, vel efficitur lorem placerat ac. Integer facilisis non felis ut posuere.
        Vestibulum vitae nisi vel odio vehicula luctus. Nunc sagittis eu risus sed feugiat.
        Nunc magna dui, auctor id luctus vel, gravida eget sapien. Donec commodo, risus et tristique hendrerit, est tortor
        molestie ex, in tristique dui augue vel mauris. Nam sagittis diam sit amet sapien fermentum, quis congue tellus venenatis.
        Donec facilisis diam eget elit tempus, ut tristique mi congue. Ut ut consectetur ex. Ut non tortor eleifend,
        feugiat felis et, pretium quam. Pellentesque at orci in lorem placerat tincidunt eget quis purus.
        Donec orci odio, luctus ut sagittis nec, congue sit amet ex. Donec arcu diam, fermentum ac porttitor consectetur,
        blandit et diam. Vivamus efficitur erat nec justo vestibulum fringilla. Mauris quis dictum elit, eget tempus ex.
        """

    NUMBER_OF_LOCAL_FILES = 100
    SYNC_TIMEOUT = 10000 # in seconds

    '''
        1. create folder 'My Docs/a1' with 100 files in it
        2. create folder 'My Docs/a2'
    '''
    def setUp(self):
        super(MultipleFilesTestCase, self).setUp()

        log.debug('*** enter CSPII7977TestCase.setUp()')
        log.debug('*** engine1 starting')
        self.engine_1.start()
        self.wait_sync()
        log.debug('*** engine 1 synced')
        log.debug("full local root path %s", self.local_client_1.get_info("/"))

        # create  folder a1
        self.local_client_1.make_folder("/", ur'a1')
        self.folder_path_1 = os.path.join("/", 'a1')
        # add 100 files in folder 'My Docs/a1'
        for file_num in range(1, self.NUMBER_OF_LOCAL_FILES+1):
            self.local_client_1.make_file(self.folder_path_1, 'local%04d.txt' % file_num, self.FILE_CONTENT)
        log.debug('local test files created')
        # create  folder a2
        self.local_client_1.make_folder("/", ur'a2')
        self.folder_path_2 = os.path.join("/", 'a2')
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** exit CSPII7977TestCase.setUp()')

    def test_move_and_copy_paste_folder(self):
        raise SkipTest("Disable for beta release, need to create similar test with less weird case to check simpler behavior")
        """
        Move folder 'My Docs/a1' under 'My Docs/a2'.
        Then copy 'My Docs/a2/a1' back under 'My Docs', so files are both in
        'My Docs/a1' and 'My Docs/a2/a1'.
        """
        log.debug('*** enter CSPII7977TestCase.test_move_and_copy_paste_folder()')
        # move 'a1' under 'a2'
        src = self.local_client_1._abspath(self.folder_path_1)
        dst = self.local_client_1._abspath(self.folder_path_2)
        log.debug("*** shutil move")
        shutil.move(src, dst)
        # check that 'My Docs/a1' does not exist anymore
        self.assertFalse(self.local_client_1.exists(self.folder_path_1))
        # check that 'My Docs/a2/a1' now exists
        self.assertTrue(self.local_client_1.exists(os.path.join(self.folder_path_2, 'a1')))
        log.debug('*** shutil copy')
        # copy the 'My Docs/a2/a1' tree back under 'My Docs'
        shutil.copytree(self.local_client_1._abspath(os.path.join(self.folder_path_2, 'a1')),
                        self.local_client_1._abspath(self.folder_path_1))
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** engine 1 synced')
        if self.queue_manager_1.get_errors_count() > 0:
            self.queue_manager_1.requeue_errors()
            # Sleep error timer
            from time import sleep
            log.debug("*** force blacklisted items")
            sleep(2)
            self.wait_sync(timeout=self.SYNC_TIMEOUT)

        # expect '/a2/a1' to contain the files
        self.assertTrue(os.path.exists(self.local_client_1._abspath(os.path.join(self.folder_path_2, 'a1'))))
        children_1 = os.listdir(self.local_client_1._abspath(os.path.join(self.folder_path_2, 'a1')))
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_FILES,
                         'number of local files (%d) in "%s" is different from original (%d)' %
                         (len(children_1), os.path.join(self.folder_path_2, 'a1'), self.NUMBER_OF_LOCAL_FILES))
        self.assertEqual(set(children_1), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES+1)]),
                                                'file names are different')
        # expect 'My Docs/a1' to contain also the files
        self.assertTrue(os.path.exists(self.local_client_1._abspath(self.folder_path_1)))
        children_2 = os.listdir(self.local_client_1._abspath(self.folder_path_1))
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_FILES,
                         'number of local files (%d)in "%s" is different from original (%d)' %
                         (len(children_2), self.folder_path_1, self.NUMBER_OF_LOCAL_FILES))
        self.assertEqual(set(children_2), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES+1)]),
                                                'file names are different')
        # verify the remote one
        a1copy_uid = self.local_client_1.get_remote_id('/a1')
        a1_uid = self.local_client_1.get_remote_id('/a2/a1')
        try:
            log.debug("/a2/a1 and /a1: %s/%s", a1_uid, a1copy_uid)
            children_1 = self.remote_file_system_client_1.get_children_info(a1_uid)
            children_2 = self.remote_file_system_client_1.get_children_info(a1copy_uid)
            log.debug("Children1: %r", children_1)
            log.debug("Children2: %r", children_2)
        except:
            pass
        self.assertEqual(len(children_1), self.NUMBER_OF_LOCAL_FILES,
                         'number of remote files (%d) in "%s" is different from original (%d)' %
                         (len(children_1), os.path.join(self.folder_path_2, 'a1'), self.NUMBER_OF_LOCAL_FILES))
        children_1_name = set()
        for child in children_1:
            children_1_name.add(child.name)
        self.assertEqual(set(children_1_name), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES+1)]),
                                                'file names are different')
        self.assertEqual(len(children_2), self.NUMBER_OF_LOCAL_FILES,
                         'number of remote files (%d) in "%s" is different from original (%d)' %
                         (len(children_2), os.path.join(self.folder_path_2, 'a1'), self.NUMBER_OF_LOCAL_FILES))
        children_2_name = set()
        for child in children_2:
            children_2_name.add(child.name)
        self.assertEqual(set(children_2_name), set(['local%04d.txt' % file_num
                                              for file_num in range(1, self.NUMBER_OF_LOCAL_FILES+1)]),
                                                'file names are different')
        log.debug('*** exit CSPII7977TestCase.test_move_and_copy_paste_folder()')