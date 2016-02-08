"""Common test utilities"""
import os
import unittest
import sys
import tempfile

from nxdrive.client import RemoteDocumentClient
from nxdrive.client import RemoteFileSystemClient
from nxdrive.client import LocalClient
from nxdrive.client import RestAPIClient
from nxdrive.manager import Manager
from nxdrive.logging_config import configure
from nxdrive.logging_config import get_logger
from nxdrive.tests.common import TEST_WORKSPACE_PATH
from nxdrive.tests.common import TEST_DEFAULT_DELAY
from nxdrive.tests.common import clean_dir
from nxdrive.wui.translator import Translator
from nxdrive import __version__
from PyQt4 import QtCore
from threading import Thread
from time import sleep

if 'DRIVE_YAPPI' in os.environ:
    import yappi

DEFAULT_WAIT_SYNC_TIMEOUT = 20
DEFAULT_WAIT_REMOTE_SCAN_TIMEOUT = 10

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


def configure_logger():
    configure(
        console_level='DEBUG',
        command_name='test',
        force_configure=True,
    )

# Configure test logger
configure_logger()
log = get_logger(__name__)


class TestThread(QtCore.QThread):
    def __init__(self, method, method_arg):
        super(TestThread, self).__init__()
        self._method = method
        self._method_arg = method_arg

    def run(self):
        self._method(self._method_arg)


class TestQApplication(QtCore.QCoreApplication):

    def __init__(self, argv, test_case):
        super(TestQApplication, self).__init__(argv)
        self._test = test_case

    @QtCore.pyqtSlot()
    def sync_completed(self):
        if hasattr(self.sender(), 'get_uid'):
            uid = self.sender().get_uid()
            log.debug("Sync Completed slot for: %s", uid)
        else:
            uid = None
        if not uid:
            for uid in self._test._wait_sync.iterkeys():
                self._test._wait_sync[uid] = False
        else:
            self._test._wait_sync[uid] = False

    @QtCore.pyqtSlot()
    def remote_scan_completed(self):
        uid = self.sender().get_engine().get_uid()
        log.debug('Remote scan completed for engine %s', uid)
        self._test._wait_remote_scan[uid] = False

    @QtCore.pyqtSlot(int)
    def remote_changes_found(self, change_count):
        uid = self.sender().get_engine().get_uid()
        log.debug("Remote changes slot for: %s", uid)
        change_count = int(change_count)
        self._test._remote_changes_count[uid] = change_count

    @QtCore.pyqtSlot()
    def no_remote_changes_found(self,):
        uid = self.sender().get_engine().get_uid()
        log.trace("No remote changes slot for: %s", uid)
        self._test._no_remote_changes[uid] = True


class UnitTestCase(unittest.TestCase):

    def setUpServer(self, server_profile=None):
        # Long timeout for the root client that is responsible for the test
        # environment set: this client is doing the first query on the Nuxeo
        # server and might need to wait for a long time without failing for
        # Nuxeo to finish initialize the repo on the first request after
        # startup
        self.root_remote_client = RemoteDocumentClient(
            self.nuxeo_url, self.admin_user,
            u'nxdrive-test-administrator-device', self.version,
            password=self.password, base_folder=u'/', timeout=60)

        # Activate given profile if needed, eg. permission hierarchy
        if server_profile is not None:
            self.root_remote_client.activate_profile(server_profile)

        # Call the Nuxeo operation to setup the integration test environment
        credentials = self.root_remote_client.execute(
            "NuxeoDrive.SetupIntegrationTests",
            userNames="user_1, user_2", permission='ReadWrite')

        credentials = [c.strip().split(u":") for c in credentials.split(u",")]
        self.user_1, self.password_1 = credentials[0]
        self.user_2, self.password_2 = credentials[1]
        ws_info = self.root_remote_client.fetch(TEST_WORKSPACE_PATH)
        self.workspace = ws_info[u'uid']
        self.workspace_title = ws_info[u'title']
        self.workspace_1 = self.workspace
        self.workspace_2 = self.workspace
        self.workspace_title_1 = self.workspace_title
        self.workspace_title_2 = self.workspace_title

    def tearDownServer(self, server_profile=None):
        # Don't need to revoke tokens for the file system remote clients
        # since they use the same users as the remote document clients
        self.root_remote_client.execute("NuxeoDrive.TearDownIntegrationTests")

        # Deactivate given profile if needed, eg. permission hierarchy
        if server_profile is not None:
            self.root_remote_client.deactivate_profile(server_profile)

    def setUpApp(self, server_profile=None):
        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD')
        self.build_workspace = os.environ.get('WORKSPACE')
        self.result = None
        self.tearedDown = False

        # Take default parameter if none has been set
        if self.nuxeo_url is None:
            self.nuxeo_url = "http://localhost:8080/nuxeo"
        if self.admin_user is None:
            self.admin_user = "Administrator"
        if self.password is None:
            self.password = "Administrator"
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)
        self.upload_tmp_dir = tempfile.mkdtemp(u'-nxdrive-uploads', dir=self.tmpdir)

        if None in (self.nuxeo_url, self.admin_user, self.password):
            raise unittest.SkipTest(
                "No integration server configuration found in environment.")

        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp(u'-nxdrive-tests-user-1', dir=self.tmpdir)
        self.local_test_folder_2 = tempfile.mkdtemp(u'-nxdrive-tests-user-2', dir=self.tmpdir)

        self.local_nxdrive_folder_1 = os.path.join(
            self.local_test_folder_1, u'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_1)
        self.local_nxdrive_folder_2 = os.path.join(
            self.local_test_folder_2, u'Nuxeo Drive')
        os.mkdir(self.local_nxdrive_folder_2)

        self.nxdrive_conf_folder_1 = os.path.join(
            self.local_test_folder_1, u'nuxeo-drive-conf')
        os.mkdir(self.nxdrive_conf_folder_1)
        self.nxdrive_conf_folder_2 = os.path.join(
            self.local_test_folder_2, u'nuxeo-drive-conf')
        os.mkdir(self.nxdrive_conf_folder_2)

        from mock import Mock
        options = Mock()
        options.debug = False
        options.delay = TEST_DEFAULT_DELAY
        options.force_locale = None
        options.proxy_server = None
        options.log_level_file = None
        options.update_site_url = None
        options.beta_update_site_url = None
        options.autolock_interval = 30
        options.nxdrive_home = self.nxdrive_conf_folder_1
        self.manager_1 = Manager(options)
        self.connected = False
        import nxdrive
        nxdrive_path = os.path.dirname(nxdrive.__file__)
        i18n_path = os.path.join(nxdrive_path, 'tests', 'resources', "i18n.js")
        Translator(self.manager_1, i18n_path)
        options.nxdrive_home = self.nxdrive_conf_folder_2
        Manager._singleton = None
        self.manager_2 = Manager(options)
        self.version = __version__
        url = self.nuxeo_url
        log.debug("Will use %s as url", url)
        if '#' in url:
            # Remove the engine type for the rest of the test
            self.nuxeo_url = url.split('#')[0]
        self.setUpServer(server_profile)

        self.engine_1 = self.manager_1.bind_server(self.local_nxdrive_folder_1, url, self.user_1,
                                                   self.password_1, start_engine=False)
        self.engine_2 = self.manager_2.bind_server(self.local_nxdrive_folder_2, url, self.user_2,
                                                   self.password_2, start_engine=False)
        self.engine_1.syncCompleted.connect(self.app.sync_completed)
        self.engine_1.get_remote_watcher().remoteScanFinished.connect(self.app.remote_scan_completed)
        self.engine_1.get_remote_watcher().changesFound.connect(self.app.remote_changes_found)
        self.engine_1.get_remote_watcher().noChangesFound.connect(self.app.no_remote_changes_found)
        self.engine_2.syncCompleted.connect(self.app.sync_completed)
        self.engine_2.get_remote_watcher().remoteScanFinished.connect(self.app.remote_scan_completed)
        self.engine_2.get_remote_watcher().changesFound.connect(self.app.remote_changes_found)
        self.engine_2.get_remote_watcher().noChangesFound.connect(self.app.no_remote_changes_found)
        self.queue_manager_1 = self.engine_1.get_queue_manager()
        self.queue_manager_2 = self.engine_2.get_queue_manager()

        self.sync_root_folder_1 = os.path.join(self.local_nxdrive_folder_1, self.workspace_title_1)
        self.sync_root_folder_2 = os.path.join(self.local_nxdrive_folder_2, self.workspace_title_2)

        self.local_root_client_1 = self.engine_1.get_local_client()
        self.local_root_client_2 = self.engine_2.get_local_client()
        self.local_client_1 = LocalClient(os.path.join(self.local_nxdrive_folder_1, self.workspace_title_1))
        self.local_client_2 = LocalClient(os.path.join(self.local_nxdrive_folder_2, self.workspace_title_2))

        # Document client to be used to create remote test documents
        # and folders
        remote_document_client_1 = RemoteDocumentClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, base_folder=self.workspace_1,
            upload_tmp_dir=self.upload_tmp_dir)

        remote_document_client_2 = RemoteDocumentClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2, base_folder=self.workspace_2,
            upload_tmp_dir=self.upload_tmp_dir)
        # File system client to be used to create remote test documents
        # and folders
        remote_file_system_client_1 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1, upload_tmp_dir=self.upload_tmp_dir)

        remote_file_system_client_2 = RemoteFileSystemClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2, upload_tmp_dir=self.upload_tmp_dir)

        self.remote_restapi_client_1 = RestAPIClient(
            self.nuxeo_url, self.user_1, u'nxdrive-test-device-1',
            self.version,
            password=self.password_1
        )
        self.remote_restapi_client_2 = RestAPIClient(
            self.nuxeo_url, self.user_2, u'nxdrive-test-device-2',
            self.version,
            password=self.password_2
        )

        # Register root
        remote_document_client_1.register_as_root(self.workspace_1)
        remote_document_client_2.register_as_root(self.workspace_2)

        self.remote_document_client_1 = remote_document_client_1
        self.remote_document_client_2 = remote_document_client_2
        self.remote_file_system_client_1 = remote_file_system_client_1
        self.remote_file_system_client_2 = remote_file_system_client_2

        self._wait_sync = {self.engine_1.get_uid(): True, self.engine_2.get_uid(): True}
        self._wait_remote_scan = {self.engine_1.get_uid(): True, self.engine_2.get_uid(): True}
        self._remote_changes_count = {self.engine_1.get_uid(): 0, self.engine_2.get_uid(): 0}
        self._no_remote_changes = {self.engine_1.get_uid(): False, self.engine_2.get_uid(): False}

    def wait_sync(self, wait_for_async=False, timeout=DEFAULT_WAIT_SYNC_TIMEOUT, fail_if_timeout=True,
                  wait_for_engine_1=True, wait_for_engine_2=False, wait_win=False, enforce_errors=True):
        log.debug("Wait for sync")
        # First wait for server if needed
        if wait_for_async:
            self.wait()
        if sys.platform == "win32" and wait_win:
            from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
            log.trace("Need to wait for Windows delete resolution")
            sleep(WIN_MOVE_RESOLUTION_PERIOD/1000)
        self._wait_sync = {
            self.engine_1.get_uid(): wait_for_engine_1,
            self.engine_2.get_uid(): wait_for_engine_2
        }
        self._no_remote_changes = {self.engine_1.get_uid(): not wait_for_engine_1,
                                   self.engine_2.get_uid(): not wait_for_engine_2}
        if enforce_errors:
            if not self.connected:
                self.engine_1.syncPartialCompleted.connect(self.engine_1.get_queue_manager().requeue_errors)
                self.engine_2.syncPartialCompleted.connect(self.engine_1.get_queue_manager().requeue_errors)
                self.connected = True
        elif self.connected:
            self.engine_1.syncPartialCompleted.disconnect(self.engine_1.get_queue_manager().requeue_errors)
            self.engine_2.syncPartialCompleted.disconnect(self.engine_1.get_queue_manager().requeue_errors)
            self.connected = False
        while timeout > 0:
            sleep(1)
            timeout = timeout - 1
            if sum(self._wait_sync.values()) == 0:
                if wait_for_async:
                    log.debug('Sync completed, _wait_remote_scan = %r, remote changes count = %r,'
                              ' no remote changes = %r',
                              self._wait_remote_scan, self._remote_changes_count, self._no_remote_changes)
                    wait_remote_scan = False
                    if wait_for_engine_1:
                        wait_remote_scan = self._wait_remote_scan[self.engine_1.get_uid()]
                    if wait_for_engine_2:
                        wait_remote_scan = wait_remote_scan or self._wait_remote_scan[self.engine_2.get_uid()]
                    is_remote_changes = True
                    is_change_summary_over = True
                    if wait_for_engine_1:
                        is_remote_changes = self._remote_changes_count[self.engine_1.get_uid()] > 0
                        is_change_summary_over = self._no_remote_changes[self.engine_1.get_uid()]
                    if wait_for_engine_2:
                        is_remote_changes = (is_remote_changes
                                             and self._remote_changes_count[self.engine_2.get_uid()] > 0)
                        is_change_summary_over = (is_change_summary_over
                                                  and self._no_remote_changes[self.engine_2.get_uid()])
                    if (not wait_remote_scan or is_remote_changes and is_change_summary_over):
                        self._wait_remote_scan = {self.engine_1.get_uid(): wait_for_engine_1,
                                                  self.engine_2.get_uid(): wait_for_engine_2}
                        self._remote_changes_count = {self.engine_1.get_uid(): 0, self.engine_2.get_uid(): 0}
                        self._no_remote_changes = {self.engine_1.get_uid(): False, self.engine_2.get_uid(): False}
                        log.debug('Ended wait for sync, setting _wait_remote_scan values to True,'
                                  ' _remote_changes_count values to 0 and _no_remote_changes values to False')
                        return
                else:
                    log.debug("Sync completed, ended wait for sync")
                    return
        if fail_if_timeout:
            log.warn("Wait for sync timeout has expired")
            if wait_for_engine_1 and self.engine_1.get_dao().get_syncing_count() != 0:
                self.fail("Wait for sync timeout expired")
            if wait_for_engine_2 and self.engine_2.get_dao().get_syncing_count() != 0:
                self.fail("Wait for sync timeout expired")
        else:
            log.debug("Wait for sync timeout")

    def wait_remote_scan(self, timeout=DEFAULT_WAIT_REMOTE_SCAN_TIMEOUT, wait_for_engine_1=True,
                         wait_for_engine_2=False):
        log.debug("Wait for remote scan")
        self._wait_remote_scan = {self.engine_1.get_uid(): wait_for_engine_1,
                                  self.engine_2.get_uid(): wait_for_engine_2}
        while timeout > 0:
            sleep(1)
            if sum(self._wait_remote_scan.values()) == 0:
                log.debug("Ended wait for remote scan")
                return
            timeout = timeout - 1
        self.fail("Wait for remote scan timeout expired")

    def is_profiling(self):
        return 'DRIVE_YAPPI' in os.environ and yappi is not None

    def setup_profiler(self):
        if not self.is_profiling():
            return
        yappi.start()

    def teardown_profiler(self):
        if not self.is_profiling():
            return
        path = os.environ["DRIVE_YAPPI"]
        if not os.path.exists(path):
            os.mkdir(path)
        report_path = os.path.join(path, self.id() + '-yappi-threads')
        with open(report_path, 'w') as fd:
            columns = {0: ("name", 80), 1: ("tid", 15), 2: ("ttot", 8), 3: ("scnt", 10)}
            yappi.get_thread_stats().print_all(out=fd, columns=columns)
        report_path = os.path.join(path, self.id() + '-yappi-fcts')
        with open(report_path, 'w') as fd:
            columns = {0: ("name", 80), 1: ("ncall", 5), 2: ("tsub", 8), 3: ("ttot", 8), 4: ("tavg", 8)}
            stats = yappi.get_func_stats()
            stats.strip_dirs()
            stats.print_all(out=fd, columns=columns)
        log.debug("Profiler Report generated in '%s'", report_path)

    def run(self, result=None):
        self.app = TestQApplication([], self)
        self.setUpApp()
        self.result = result

        # TODO Should use a specific application
        def launch_test():
            log.debug("UnitTest thread started")
            sleep(1)
            self.setup_profiler()
            super(UnitTestCase, self).run(result)
            self.teardown_profiler()
            self.app.quit()
            log.debug("UnitTest thread finished")

        sync_thread = Thread(target=launch_test)
        sync_thread.start()
        self.app.exec_()
        sync_thread.join(30)
        self.tearDownApp()
        del self.app
        log.debug("UnitTest run finished")

    def tearDown(self):
        unittest.TestCase.tearDown(self)
        if not self.tearedDown:
            self.tearDownApp()

    def tearDownApp(self, server_profile=None):
        if self.tearedDown:
            return
        if sys.exc_info() != (None, None, None):
            self.generate_report()
        elif self.result is not None:
            if hasattr(self.result, "wasSuccessful") and not self.result.wasSuccessful():
                self.generate_report()
        log.debug("TearDown unit test")
        # Unbind all
        self.manager_1.unbind_all()
        self.manager_1.dispose_db()
        self.manager_2.unbind_all()
        self.manager_2.dispose_db()
        Manager._singleton = None
        self.tearDownServer(server_profile)

        clean_dir(self.upload_tmp_dir)
        clean_dir(self.local_test_folder_1)
        clean_dir(self.local_test_folder_2)

        del self.engine_1
        self.engine_1 = None
        del self.engine_2
        self.engine_2 = None
        del self.local_client_1
        self.local_client_1 = None
        del self.local_client_2
        self.local_client_2 = None
        del self.remote_document_client_1
        self.remote_document_client_1 = None
        del self.remote_document_client_2
        self.remote_document_client_2 = None
        del self.remote_file_system_client_1
        self.remote_file_system_client_1 = None
        del self.remote_file_system_client_2
        self.remote_file_system_client_2 = None
        self.tearedDown = True

    def _interact(self, pause=0):
        self.app.processEvents()
        if pause > 0:
            sleep(pause)
        while (self.app.hasPendingEvents()):
            self.app.processEvents()

    def make_local_tree(self, root=None, local_client=None):
        if local_client is None:
            local_client = self.local_root_client_1
        if root is None:
            root = u"/" + self.workspace_title
            if not local_client.exists(root):
                local_client.make_folder(u"/", self.workspace_title)
        # create some folders
        folder_1 = local_client.make_folder(root, u'Folder 1')
        folder_1_1 = local_client.make_folder(folder_1, u'Folder 1.1')
        folder_1_2 = local_client.make_folder(folder_1, u'Folder 1.2')
        folder_2 = local_client.make_folder(root, u'Folder 2')

        # create some files
        local_client.make_file(folder_2, u'Duplicated File.txt', content=b"Some content.")

        local_client.make_file(folder_1, u'File 1.txt', content=b"aaa")
        local_client.make_file(folder_1_1, u'File 2.txt', content=b"bbb")
        local_client.make_file(folder_1_2, u'File 3.txt', content=b"ccc")
        local_client.make_file(folder_2, u'File 4.txt', content=b"ddd")
        local_client.make_file(root, u'File 5.txt', content=b"eee")
        return (6, 5)

    def make_server_tree(self, deep=True):
        remote_client = self.remote_document_client_1
        # create some folders on the server
        folder_1 = remote_client.make_folder(self.workspace, u'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, u'Folder 2')
        if deep:
            folder_1_1 = remote_client.make_folder(folder_1, u'Folder 1.1')
            folder_1_2 = remote_client.make_folder(folder_1, u'Folder 1.2')

        # create some files on the server
        if deep:
            self._duplicate_file_1 = remote_client.make_file(folder_2, u'Duplicated File.txt',
                                                             content=b"Some content.")
            self._duplicate_file_2 = remote_client.make_file(folder_2, u'Duplicated File.txt',
                                                             content=b"Other content.")

        if deep:
            remote_client.make_file(folder_1, u'File 1.txt', content=b"aaa")
            remote_client.make_file(folder_1_1, u'File 2.txt', content=b"bbb")
            remote_client.make_file(folder_1_2, u'File 3.txt', content=b"ccc")
            remote_client.make_file(folder_2, u'File 4.txt', content=b"ddd")
        remote_client.make_file(self.workspace, u'File 5.txt', content=b"eee")
        return (7, 4) if deep else (1, 2)

    def get_local_child_count(self, path):
        dir_count = 0
        file_count = 0
        for _, dirnames, filenames in os.walk(path):
            dir_count += len(dirnames)
            file_count += len(filenames)
        if os.path.exists(os.path.join(path, '.partials')):
            dir_count -= 1
        return (dir_count, file_count)

    def get_full_queue(self, queue, dao=None):
        if dao is None:
            dao = self.engine_1.get_dao()
        result = []
        while (len(queue) > 0):
            result.append(dao.get_state_from_id(queue.pop().id))
        return result

    def generate_report(self):
        if "REPORT_PATH" not in os.environ:
            return
        report_path = os.path.join(os.environ["REPORT_PATH"], self.id())
        self.manager_1.generate_report(report_path)
        log.debug("Report generated in '%s'", report_path)

    def wait(self, retry=3):
        try:
            self.root_remote_client.wait()
        except Exception as e:
            log.debug("Exception while waiting for server : %r", e)
            # Not the nicest
            if retry > 0:
                log.debug("Retry to wait")
                self.wait(retry - 1)

    def generate_random_jpg(self, filename, size):
        try:
            import numpy
            from PIL import Image
        except:
            # Create random file
            with open(filename, 'wb') as f:
                f.write(os.urandom(1024 * size))
            return
        a = numpy.random.rand(size, size, 3) * 255
        im_out = Image.fromarray(a.astype('uint8')).convert('RGBA')
        im_out.save(filename)

    def assertNxPart(self, path, name=None, present=True):
        os_path = self.local_client_1._abspath(path)
        children = os.listdir(os_path)
        for child in children:
            if len(child) < 8:
                continue
            if name is not None and len(child) < len(name) + 8:
                continue
            if child[0] == "." and child[-7:] == ".nxpart":
                if name is None or child[1:len(name)+1] == name:
                    if present:
                        return
                    else:
                        self.fail("nxpart found in : '%s'" % (path))
        if present:
            self.fail("nxpart not found in : '%s'" % (path))
