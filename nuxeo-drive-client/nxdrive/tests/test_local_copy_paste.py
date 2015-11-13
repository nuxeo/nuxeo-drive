from common_unit_test import UnitTestCase
from nxdrive.tests.common_unit_test import log
import os
import sys
import shutil


class TestLocalCopyPaste(UnitTestCase):
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

    NUMBER_OF_LOCAL_TEXT_FILES = 10
    NUMBER_OF_LOCAL_IMAGE_FILES = 10
    NUMBER_OF_LOCAL_FILES_TOTAL = NUMBER_OF_LOCAL_TEXT_FILES + NUMBER_OF_LOCAL_IMAGE_FILES
    FILE_NAME_PATTERN = 'file%03d.%s'
    TEST_DOC_RESOURCE = 'cat.jpg'
    FOLDER_1 = u'A'
    FOLDER_2 = u'B'
    SYNC_TIMEOUT = 100  # in seconds

    '''
        1. create folder 'Nuxeo Drive Test Workspace/A' with 100 files in it
        2. create folder 'Nuxeo Drive Test Workspace/B'
    '''

    def setUp(self):
        super(TestLocalCopyPaste, self).setUp()

        log.debug('*** enter TestLocalCopyPaste.setUp() ***')
        log.debug('*** engine1 starting ***')
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        log.debug('*** engine1 synced ***')
        log.debug("full local root path %s", self.local_root_client_1.get_info("/"))
        self.assertTrue(self.local_root_client_1.exists('/Nuxeo Drive Test Workspace'),
                        "Nuxeo Drive Test Workspace should be sync")

        # create  folder A
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", self.FOLDER_1)
        self.folder_path_1 = os.path.join("/Nuxeo Drive Test Workspace", self.FOLDER_1)

        # add text files in folder 'Nuxeo Drive Test Workspace/A'
        self.local_files_list = []
        for file_num in range(1, self.NUMBER_OF_LOCAL_TEXT_FILES + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, 'txt')
            self.local_root_client_1.make_file(self.folder_path_1, filename, self.FILE_CONTENT)
            self.local_files_list.append(filename)

        test_resources_path = self._get_test_resources_path()
        if test_resources_path is None:
            test_resources_path = 'tests/resources'
        self.test_doc_path = os.path.join(test_resources_path, TestLocalCopyPaste.TEST_DOC_RESOURCE)

        # add image files in folder 'Nuxeo Drive Test Workspace/A'
        abs_folder_path_1 = self.local_root_client_1._abspath(self.folder_path_1)
        for file_num in range(self.NUMBER_OF_LOCAL_TEXT_FILES + 1, self.NUMBER_OF_LOCAL_FILES_TOTAL + 1):
            filename = self.FILE_NAME_PATTERN % (file_num, os.path.splitext(self.TEST_DOC_RESOURCE)[1])
            dst_path = os.path.join(abs_folder_path_1, filename)
            shutil.copyfile(self.test_doc_path, dst_path)
            self.local_files_list.append(filename)
        log.debug('local test files created in Nuxeo Drive Test Workspace/A')

        # create  folder B
        self.local_root_client_1.make_folder("/Nuxeo Drive Test Workspace", self.FOLDER_2)
        self.folder_path_2 = os.path.join("/Nuxeo Drive Test Workspace", self.FOLDER_2)
        self.wait_sync()

        # get remote folders reference ids
        self.remote_ref_1 = self.local_root_client_1.get_remote_id(self.folder_path_1)
        self.remote_ref_2 = self.local_root_client_1.get_remote_id(self.folder_path_2)
        self.assertTrue(self.remote_file_system_client_1.exists(self.remote_ref_1),
                        'remote folder for %s does not exist' % self.folder_path_1)
        self.assertTrue(self.remote_file_system_client_1.exists(self.remote_ref_2),
                        'remote folder for %s does not exist' % self.folder_path_2)
        log.debug('*** exit TestLocalCopyPaste.setUp() ***')

    def tearDown(self):
        log.debug('*** enter TestLocalCopyPaste.tearDown() ***')
        # list content of folder A
        abs_folder_path_1 = self.local_root_client_1._abspath(self.folder_path_1)
        log.debug('content of folder "%s"', abs_folder_path_1)
        for f in os.listdir(abs_folder_path_1):
            log.debug(f)

        # list content of folder B
        abs_folder_path_2 = self.local_root_client_1._abspath(self.folder_path_2)
        log.debug('content of folder "%s"', abs_folder_path_2)
        for f in os.listdir(abs_folder_path_2):
            log.debug(f)

        # remove local folders
        try:
            self.local_root_client_1.delete_final(self.folder_path_1)
            self.local_root_client_1.delete_final(self.folder_path_2)
        except:
            pass
        self.wait_sync()
        super(TestLocalCopyPaste, self).tearDown()
        log.debug('*** exit TestLocalCopyPaste.tearDown() ***')

    def test_local_copy_paste_files(self):
        log.debug('*** enter TestLocalCopyPaste.test_local_copy_paste_files() ***')
        # copy all children (files) of A to B
        src = self.local_root_client_1._abspath(self.folder_path_1)
        dst = self.local_root_client_1._abspath(self.folder_path_2)
        for f in os.listdir(src):
            shutil.copy(os.path.join(src, f), dst)
        self.wait_sync(timeout=self.SYNC_TIMEOUT)
        log.debug('*** engine1 synced ***')

        # expect local 'Nuxeo Drive Test Workspace/A' to contain all the files
        abs_folder_path_1 = self.local_root_client_1._abspath(self.folder_path_1)
        self.assertTrue(os.path.exists(abs_folder_path_1))
        children_1 = os.listdir(abs_folder_path_1)
        postcondition1 = len(children_1) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition1_error = 'number of local files (%d) in "%s" is different from original (%d)' % \
                               (len(children_1), self.folder_path_1, self.NUMBER_OF_LOCAL_FILES_TOTAL)
        local_files_expected = set(self.local_files_list)
        local_files_actual = set(children_1)
        postcondition2 = local_files_actual == local_files_expected
        postcondition2_error = 'file names in "%s" are different, e.g. duplicate files (renamed)' % self.folder_path_1
        if not postcondition2:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(local_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(local_files_actual))
            postcondition2_error += '\nunexpected files:\n%s\n\nmissing files\n%s' % (unexpected_actual_files,
                                                                                      missing_expected_files)

        # expect local 'Nuxeo Drive Test Workspace/B' to contain also the same files
        abs_folder_path_2 = self.local_root_client_1._abspath(self.folder_path_2)
        self.assertTrue(os.path.exists(abs_folder_path_2))
        children_2 = os.listdir(abs_folder_path_2)
        postcondition3 = len(children_2) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition3_error = 'number of local files (%d) in "%s" is different from original (%d)' % \
                               (len(children_2), self.folder_path_2, self.NUMBER_OF_LOCAL_FILES_TOTAL)

        local_files_actual = set(children_2)
        postcondition4 = local_files_actual == local_files_expected
        postcondition4_error = 'file names in "%s" are different, e.g. duplicate files (renamed)' % self.folder_path_2
        if not postcondition4:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(local_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(local_files_actual))
            postcondition4_error += '\nunexpected files:\n%s\n\nmissing files:\n%s' % (unexpected_actual_files,
                                                                                       missing_expected_files)

        # expect remote 'Nuxeo Drive Test Workspace/A' to contain all the files
        # just compare the names
        remote_children_1 = [remote_info.name
                             for remote_info in self.remote_file_system_client_1.get_children_info(self.remote_ref_1)]

        postcondition5 = len(remote_children_1) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition5_error = 'number of remote files (%d) in "%s" is different from original (%d)' % \
                               (len(remote_children_1), self.remote_ref_1, self.NUMBER_OF_LOCAL_FILES_TOTAL)
        remote_files_expected = set(self.local_files_list)
        remote_files_actual = set(remote_children_1)
        postcondition6 = remote_files_actual == remote_files_expected
        postcondition6_error = ('remote file names in "%s" are different, e.g. duplicate files (renamed)'
                                % self.remote_ref_1)
        if not postcondition6:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(remote_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(remote_files_actual))
            postcondition6_error += '\nunexpected files:\n%s\n\nmissing files\n%s' % (unexpected_actual_files,
                                                                                      missing_expected_files)

        # expect remote 'Nuxeo Drive Test Workspace/B' to contain all the files
        # just compare the names
        remote_children_2 = [remote_info.name
                             for remote_info in self.remote_file_system_client_1.get_children_info(self.remote_ref_2)]

        postcondition7 = len(remote_children_2) == self.NUMBER_OF_LOCAL_FILES_TOTAL
        postcondition7_error = 'number of remote files (%d) in "%s" is different from original (%d)' % \
                               (len(remote_children_2), self.remote_ref_2, self.NUMBER_OF_LOCAL_FILES_TOTAL)
        remote_files_expected = set(self.local_files_list)
        remote_files_actual = set(remote_children_2)
        postcondition8 = remote_files_actual == remote_files_expected
        postcondition8_error = ('remote file names in "%s" are different, e.g. duplicate files (renamed)'
                                % self.remote_ref_2)
        if not postcondition8:
            unexpected_actual_files = '\n'.join(local_files_actual.difference(remote_files_expected))
            missing_expected_files = '\n'.join(local_files_expected.difference(remote_files_actual))
            postcondition6_error += '\nunexpected files:\n%s\n\nmissing files\n%s' % (unexpected_actual_files,
                                                                                      missing_expected_files)

        # output the results before asserting
        if not postcondition1:
            log.debug(postcondition1_error)
        if not postcondition2:
            log.debug(postcondition2_error)
        if not postcondition3:
            log.debug(postcondition3_error)
        if not postcondition4:
            log.debug(postcondition4_error)
        if not postcondition5:
            log.debug(postcondition5_error)
        if not postcondition6:
            log.debug(postcondition6_error)
        if not postcondition7:
            log.debug(postcondition7_error)
        if not postcondition8:
            log.debug(postcondition8_error)

        self.assertTrue(postcondition1, postcondition1_error)
        self.assertTrue(postcondition2, postcondition2_error)
        self.assertTrue(postcondition3, postcondition3_error)
        self.assertTrue(postcondition4, postcondition4_error)
        self.assertTrue(postcondition5, postcondition5_error)
        self.assertTrue(postcondition6, postcondition6_error)
        self.assertTrue(postcondition7, postcondition7_error)
        self.assertTrue(postcondition8, postcondition8_error)
        log.debug('*** exit TestLocalCopyPaste.test_local_copy_paste_files() ***')

    def _get_test_resources_path(self):
        try:
            module = sys.modules[self.__module__]
            test_resources_path = os.path.join(os.path.dirname(module.__file__), 'resources')
            return test_resources_path
        except Exception as e:
            log.error('path error: ', e)
