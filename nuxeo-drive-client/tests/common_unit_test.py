"""Common test utilities"""
import os
import struct
import sys
import tempfile
import traceback
import unittest
import zlib
from functools import wraps
from os.path import dirname
from threading import Thread
from time import sleep

from PyQt4 import QtCore
from mock import Mock

from nxdrive import __version__
from nxdrive.client import LocalClient, RemoteDocumentClient, RemoteFileSystemClient, RestAPIClient
from nxdrive.logging_config import get_logger
from nxdrive.manager import Manager
from nxdrive.osi import AbstractOSIntegration
from nxdrive.wui.translator import Translator
from tests.common import TEST_DEFAULT_DELAY, TEST_WORKSPACE_PATH, clean_dir

if 'DRIVE_YAPPI' in os.environ:
    import yappi

log = get_logger(__name__)
DEFAULT_WAIT_SYNC_TIMEOUT = 30
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


class RandomBugError(Exception):

    def __init__(self, message, cause=None):
        msg = message if cause is None else message + u'\nCaused by ' + repr(cause) + u'\n' + traceback.format_exc()
        super(RandomBugError, self).__init__(msg)
        self.cause = cause


class RandomBug(object):
    """
    Use this annotation if a bug is a RandomBug, you need to track it with a ticket before.
    """
    MODES = ('RELAX', 'STRICT', 'BYPASS')
    OS = ('windows', 'mac', 'linux')

    def __init__(self, ticket, target=None, repeat=10, mode='RELAX'):
        """
        :param ticket: Nuxeo ticket that tracks the random
        :param target: Restrict the annotation only for a specific OS target
        :param repeat: Number of times to repeat the test
        :param mode: Mode of the bug

        RELAX: will retry as repeat times until it succeeds
        STRICT: will repeat it until it fails or hits the repeat limit
        BYPASS: skip the test
        """
        if target not in self.OS:
            raise ValueError('Random bug, invalid OS: {} not in ({})'.format(target, ', '.join(self.OS)))
        if mode not in self.MODES:
            raise ValueError('Random bug, invalid mode: {} not in ({})'.format(mode, ', '.join(self.MODES)))

        self._repeat = max(1, repeat)
        # Enforce a ticket reference
        self._ticket = ticket
        self._iteration = 0
        self._mode = mode.upper()
        self._os = target.lower()

        if os.environ.get('RANDOM_BUG_MODE', '') in self.MODES:
            self._mode = os.environ['RANDOM_BUG_MODE']

    def __call__(self, func):
        @wraps(func)
        def _callable(*args, **kwargs):
            # Handle specific OS
            if self._os == 'linux' and not AbstractOSIntegration.is_linux():
                return func(*args, **kwargs)
            elif self._os == 'windows' and not AbstractOSIntegration.is_windows():
                return func(*args, **kwargs)
            elif self._os == 'mac' and not AbstractOSIntegration.is_mac():
                return func(*args, **kwargs)

            # Skip if BYPASS mode
            if self._mode == 'BYPASS':
                raise unittest.SkipTest('RandomTest is in ' + self._mode)

            res = None
            for i in range(self._repeat):
                log.debug('Repeating test %s %d/%d', func.func_name, i + 1, self._repeat)
                success = False
                try:
                    res = func(*args, **kwargs)
                    success = True
                except Exception as e:
                    # In strict mode we propagate Exception
                    if self._mode == 'STRICT':
                        raise e
                finally:
                    # In RELAX mode, if the test succeeds once we don't fail
                    if self._mode == 'RELAX' and success:
                        return res
                if SimpleUnitTestCase.getSingleton() is not None and i < self._repeat - 1:
                    SimpleUnitTestCase.getSingleton().reinit()
            # In RELAX mode, if the test never succeeds we fail because it means that
            # this is probably not a random bug but a systematic one
            if self._mode == 'RELAX':
                raise RandomBugError("No success after %d tries in %s mode."
                                     " Either the %s issue is not random or you should increase the 'repeat' value." %
                                     (self._repeat, self._mode, self._ticket), cause=e)
            # In STRICT mode, if the test never fails we fail because it means that
            # this is probably not a random bug anymore
            if self._mode == 'STRICT':
                raise RandomBugError("No failure after %d tries in %s mode."
                                     " Either the %s issue is fixed or you should increase the 'repeat' value." %
                                     (self._repeat, self._mode, self._ticket))
            return res

        _callable._repeat = self._repeat
        return _callable


class StubQApplication(QtCore.QCoreApplication):

    def __init__(self, argv, test_case):
        super(StubQApplication, self).__init__(argv)
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


class SimpleUnitTestCase(unittest.TestCase):
    """
    Simple unit test to handle reinit on RandomBug
    """
    _singleton = None

    @staticmethod
    def getSingleton():
        return SimpleUnitTestCase._singleton

    def reinit(self):
        """
        Launch the tearDown and setUp of the test
        :return:
        """
        self.tearDown()
        self.setUp()

    def run(self, *args, **kwargs):
        SimpleUnitTestCase._singleton = self
        super(SimpleUnitTestCase, self).run(*args, **kwargs)
        SimpleUnitTestCase._singleton = None


class UnitTestCase(SimpleUnitTestCase):

    def setUpServer(self, server_profile=None):
        # Save the current path for test files
        self.location = dirname(__file__)

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
        ws_info = self.root_remote_client.fetch(u'/default-domain/workspaces/')
        children = self.root_remote_client.get_children(ws_info['uid'])
        log.debug("SuperWorkspace info: %r", ws_info)
        log.debug("SuperWorkspace children: %r", children)
        ws_info = self.root_remote_client.fetch(TEST_WORKSPACE_PATH)
        log.debug("Workspace info: %r", ws_info)
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

    def get_local_client(self, path):
        if AbstractOSIntegration.is_windows():
            from tests.win_local_client import WindowsLocalClient
            return WindowsLocalClient(path)
        if AbstractOSIntegration.is_mac():
            from tests.mac_local_client import MacLocalClient
            return MacLocalClient(path)
        return LocalClient(path)

    def setUpApp(self, server_profile=None):
        # Save the current path for test files
        self.location = dirname(__file__)

        # Check the Nuxeo server test environment
        self.nuxeo_url = os.environ.get('NXDRIVE_TEST_NUXEO_URL', 'http://localhost:8080/nuxeo')
        self.admin_user = os.environ.get('NXDRIVE_TEST_USER', 'Administrator')
        self.password = os.environ.get('NXDRIVE_TEST_PASSWORD', 'Administrator')
        self.build_workspace = os.environ.get('WORKSPACE')
        self.tearedDown = False

        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)
        self.upload_tmp_dir = tempfile.mkdtemp(u'-nxdrive-uploads', dir=self.tmpdir)

        # Check the local filesystem test environment
        self.local_test_folder_1 = tempfile.mkdtemp(u'drive-1', dir=self.tmpdir)
        self.local_test_folder_2 = tempfile.mkdtemp(u'drive-2', dir=self.tmpdir)

        # Correct the casing of the temp folders for windows
        if sys.platform == 'win32':
            import win32api
            self.local_test_folder_1 = win32api.GetLongPathName(self.local_test_folder_1)
            self.local_test_folder_2 = win32api.GetLongPathName(self.local_test_folder_2)

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
        i18n_path = self.location + '/resources/i18n.js'
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

        self.local_client_1 = self.get_local_client(os.path.join(self.local_nxdrive_folder_1, self.workspace_title))
        self.local_client_2 = self.get_local_client(os.path.join(self.local_nxdrive_folder_2, self.workspace_title))

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
        self.remote_restapi_client_admin = RestAPIClient(
            self.nuxeo_url, self.admin_user, u'nxdrive-test-device-2',
            self.version,
            password=self.password
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
            timeout -= 1
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

    def reinit(self):
        self.tearDown()
        self.tearDownApp()
        self.setUpApp()
        try:
            self.setUp()
        except:
            # We can end on a wait timeout. Just ignore it, the test should
            # fail and will be launched again.
            pass

    def run(self, result=None):
        self.app = StubQApplication([], self)
        self.setUpApp()
        self.result = result

        # TODO Should use a specific application
        def launch_test():
            self.remote_restapi_client_admin.log_on_server(
                '----- Testing ' + self.id())
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
        while self.app.hasPendingEvents():
            self.app.processEvents()

    def make_local_tree(self, root=None, local_client=None):
        nb_files, nb_folders = 6, 4
        if not local_client:
            local_client = self.local_root_client_1
        if not root:
            root = u"/" + self.workspace_title
            if not local_client.exists(root):
                local_client.make_folder(u"/", self.workspace_title)
                nb_folders += 1
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
        return nb_files, nb_folders

    def make_server_tree(self, deep=True):
        remote_client = self.remote_document_client_1
        # create some folders on the server
        folder_1 = remote_client.make_folder(self.workspace, u'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, u'Folder 2')
        if deep:
            folder_1_1 = remote_client.make_folder(folder_1, u'Folder 1.1')
            folder_1_2 = remote_client.make_folder(folder_1, u'Folder 1.2')

            # create some files on the server
            self._duplicate_file_1 = remote_client.make_file(folder_2, u'Duplicated File.txt',
                                                             content=b"Some content.")
            self._duplicate_file_2 = remote_client.make_file(folder_2, u'Duplicated File.txt',
                                                             content=b"Other content.")

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
        while len(queue) > 0:
            result.append(dao.get_state_from_id(queue.pop().id))
        return result

    def wait(self, retry=3):
        try:
            self.root_remote_client.wait()
        except Exception as e:
            log.debug("Exception while waiting for server : %r", e)
            # Not the nicest
            if retry > 0:
                log.debug("Retry to wait")
                self.wait(retry - 1)

    def generate_report(self):
        if "REPORT_PATH" not in os.environ:
            return

        report_path = os.path.join(os.environ["REPORT_PATH"],
                                   self.id() + '-' + sys.platform)
        self.manager_1.generate_report(report_path)
        log.debug("Report generated in '%s'", report_path)

    def _set_read_permission(self, user, doc_path, grant):
        op_input = "doc:" + doc_path
        if grant:
            self.root_remote_client.execute("Document.SetACE",
                                            op_input=op_input,
                                            user=user,
                                            permission="Read",
                                            grant="true")
        else:
            self.root_remote_client.block_inheritance(doc_path)

    @staticmethod
    def generate_random_png(filename=None, size=1):
        """ Generate a random PNG file.

        :param filename: The output file name. If None, returns picture content.
        :param size: The number of black pixels of the picture.
        :return mixed: None if given filename else bytes
        """

        pack = struct.pack

        def chunk(header, data):
            return (pack('>I', len(data)) + header + data
                    + pack('>I', zlib.crc32(header + data) & 0xffffffff))

        data = pack('>{}B'.format(size), *[0] * size)
        png = (b'\x89PNG\r\n\x1A\n'
               + chunk(b'IHDR', pack('>2I5B', size, size, 1, 0, 0, 0, 0))
               + chunk(b'IDAT', zlib.compress(data))
               + chunk(b'IEND', b''))

        if not filename:
            return png

        with open(filename, 'wb') as f:
            f.write(png)

    def assertNxPart(self, path, name=None, present=True):
        os_path = self.local_client_1.abspath(path)
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

    def get_dao_state_from_engine_1(self, path):
        """
        Returns the pair from dao of engine 1 according to the path.

        :param path: The path to document (from workspace, ex: /Folder is converted to /{{workspace_title_1}}/Folder).
        :return: The pair from dao of engine 1 according to the path.
        """
        abs_path = '/' + self.workspace_title_1 + path
        return self.engine_1.get_dao().get_state_from_local(abs_path)
