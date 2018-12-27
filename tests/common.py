# coding: utf-8
""" Common test utilities. """
import itertools
import os
import random
import shutil
import struct
import sys
import tempfile
import zlib
from logging import getLogger
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Tuple, Union
from unittest import TestCase

import pytest
from PyQt5.QtCore import QCoreApplication, pyqtSignal, pyqtSlot
from nuxeo.exceptions import HTTPError
from requests import ConnectionError

from nxdrive.constants import LINUX, MAC, WINDOWS
from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.translator import Translator
from nxdrive.utils import normalized_path, unset_path_readonly
from . import DocRemote, LocalTest, RemoteBase

# Default remote watcher delay used for tests
TEST_DEFAULT_DELAY = 3

TEST_WORKSPACE_PATH = "/default-domain/workspaces/nuxeo-drive-test-workspace"
FS_ITEM_ID_PREFIX = "defaultFileSystemItemFactory#default#"

# 1s time resolution as we truncate remote last modification time to the
# seconds in RemoteFileInfo.from_dict() because of the datetime
# resolution of some databases (MySQL...)
REMOTE_MODIFICATION_TIME_RESOLUTION = 1.0

# 1s resolution on HFS+ on OSX
# ~0.01s resolution for NTFS
# 0.001s for EXT4FS
OS_STAT_MTIME_RESOLUTION = 1.0

log = getLogger(__name__)

DEFAULT_WAIT_SYNC_TIMEOUT: int = 10
FILE_CONTENT: bytes = b"Lorem ipsum dolor sit amet ..."


class StubQApplication(QCoreApplication):
    bindEngine = pyqtSignal(int, bool)
    unbindEngine = pyqtSignal(int)

    def __init__(self, argv, test_case):
        super().__init__(argv)
        self._test = test_case
        self.bindEngine.connect(self.bind_engine)
        self.unbindEngine.connect(self.unbind_engine)

    @pyqtSlot()
    def sync_completed(self):
        uid = getattr(self.sender(), "uid", None)
        log.debug("Sync Completed slot for: %s", uid)
        if uid:
            self._test._wait_sync[uid] = False
        else:
            for uid in self._test._wait_sync.keys():
                self._test._wait_sync[uid] = False

    @pyqtSlot()
    def remote_scan_completed(self):
        uid = self.sender().engine.uid
        log.debug("Remote scan completed for engine %s", uid)
        self._test._wait_remote_scan[uid] = False
        self._test._wait_sync[uid] = False

    @pyqtSlot(int)
    def remote_changes_found(self, change_count):
        uid = self.sender().engine.uid
        log.debug("Remote changes slot for: %s", uid)
        self._test._remote_changes_count[uid] = change_count

    @pyqtSlot()
    def no_remote_changes_found(self):
        uid = self.sender().engine.uid
        log.trace("No remote changes slot for %s", uid)
        self._test._no_remote_changes[uid] = True

    @pyqtSlot(int, bool)
    def bind_engine(self, number, start_engine):
        self._test.bind_engine(number, start_engine=start_engine)

    @pyqtSlot(int)
    def unbind_engine(self, number):
        self._test.unbind_engine(number)


class UnitTestCase(TestCase):
    # Save the current path for test files
    location = normalized_path(__file__).parent

    def setUpServer(self, server_profile=None):
        # Long timeout for the root client that is responsible for the test
        # environment set: this client is doing the first query on the Nuxeo
        # server and might need to wait for a long time without failing for
        # Nuxeo to finish initialize the repo on the first request after
        # startup

        # Activate given profile if needed, eg. permission hierarchy
        if server_profile is not None:
            pytest.root_remote.activate_profile(server_profile)

        # Call the Nuxeo operation to setup the integration test environment
        credentials = pytest.root_remote.operations.execute(
            command="NuxeoDrive.SetupIntegrationTests",
            userNames="user_1, user_2",
            permission="ReadWrite",
        )

        credentials = [
            c.strip().split(":") for c in credentials.decode("utf-8").split(",")
        ]
        self.user_1, self.password_1 = credentials[0]
        self.user_2, self.password_2 = credentials[1]
        ws_info = pytest.root_remote.fetch("/default-domain/workspaces/")
        children = pytest.root_remote.get_children(ws_info["uid"])
        log.debug("SuperWorkspace info: %r", ws_info)
        log.debug("SuperWorkspace children: %r", children)
        ws_info = pytest.root_remote.fetch(TEST_WORKSPACE_PATH)
        log.debug("Workspace info: %r", ws_info)
        self.workspace = ws_info["uid"]
        self.workspace_title = ws_info["title"]
        self.workspace_1 = self.workspace
        self.workspace_2 = self.workspace
        self.workspace_title_1 = self.workspace_title
        self.workspace_title_2 = self.workspace_title

    def tearDownServer(self, server_profile=None):
        # Don't need to revoke tokens for the file system remote clients
        # since they use the same users as the remote document clients
        pytest.root_remote.operations.execute(
            command="NuxeoDrive.TearDownIntegrationTests"
        )

        # Deactivate given profile if needed, eg. permission hierarchy
        if server_profile is not None:
            pytest.root_remote.deactivate_profile(server_profile)

    def setUpApp(self, server_profile=None, register_roots=True):
        if Manager._singleton:
            Manager._singleton = None

        # Install callback early to be called the last
        self.addCleanup(self._check_cleanup)

        self.report_path = None
        if "REPORT_PATH" in os.environ:
            self.report_path = normalized_path(os.environ["REPORT_PATH"])

        self.tmpdir = normalized_path(os.environ.get("WORKSPACE", "")) / "tmp"
        self.addCleanup(clean_dir, self.tmpdir)
        self.tmpdir.mkdir(parents=True, exist_ok=True)

        self.upload_tmp_dir = normalized_path(
            tempfile.mkdtemp("-nxdrive-uploads", dir=self.tmpdir)
        )

        # Check the local filesystem test environment
        self.local_test_folder_1 = normalized_path(
            tempfile.mkdtemp("drive-1", dir=self.tmpdir)
        )
        self.local_test_folder_2 = normalized_path(
            tempfile.mkdtemp("drive-2", dir=self.tmpdir)
        )

        self.local_nxdrive_folder_1 = self.local_test_folder_1 / "Nuxeo Drive"
        self.local_nxdrive_folder_1.mkdir()
        self.local_nxdrive_folder_2 = self.local_test_folder_2 / "Nuxeo Drive"
        self.local_nxdrive_folder_2.mkdir()

        self.nxdrive_conf_folder_1 = self.local_test_folder_1 / "nuxeo-drive-conf"
        self.nxdrive_conf_folder_1.mkdir()
        self.nxdrive_conf_folder_2 = self.local_test_folder_2 / "nuxeo-drive-conf"
        self.nxdrive_conf_folder_2.mkdir()

        Options.delay = TEST_DEFAULT_DELAY
        Options.nxdrive_home = self.nxdrive_conf_folder_1
        self.manager_1 = Manager()
        self.connected = False
        i18n_path = self.location / "resources/i18n"
        Translator(self.manager_1, i18n_path)
        Options.nxdrive_home = self.nxdrive_conf_folder_2
        Manager._singleton = None
        self.manager_2 = Manager()

        self.setUpServer(server_profile)
        self.addCleanup(self.tearDownServer, server_profile)
        self.addCleanup(self._stop_managers)
        self.addCleanup(self.generate_report)

        self._wait_sync = {}
        self._wait_remote_scan = {}
        self._remote_changes_count = {}
        self._no_remote_changes = {}

        # Set engine_1 and engine_2 attributes
        self.bind_engine(1, start_engine=False)
        self.queue_manager_1 = self.engine_1.get_queue_manager()
        self.bind_engine(2, start_engine=False)

        self.sync_root_folder_1 = self.local_nxdrive_folder_1 / self.workspace_title_1
        self.sync_root_folder_2 = self.local_nxdrive_folder_2 / self.workspace_title_2

        self.local_root_client_1 = self.get_local_client(
            self.engine_1.local.base_folder
        )

        self.local_1 = self.get_local_client(self.sync_root_folder_1)
        self.local_2 = self.get_local_client(self.sync_root_folder_2)

        # Document client to be used to create remote test documents
        # and folders
        self.remote_document_client_1 = DocRemote(
            pytest.nuxeo_url,
            self.user_1,
            "nxdrive-test-device-1",
            pytest.version,
            password=self.password_1,
            base_folder=self.workspace_1,
            upload_tmp_dir=self.upload_tmp_dir,
        )

        self.remote_document_client_2 = DocRemote(
            pytest.nuxeo_url,
            self.user_2,
            "nxdrive-test-device-2",
            pytest.version,
            password=self.password_2,
            base_folder=self.workspace_2,
            upload_tmp_dir=self.upload_tmp_dir,
        )

        # File system client to be used to create remote test documents
        # and folders
        self.remote_1 = RemoteBase(
            pytest.nuxeo_url,
            self.user_1,
            "nxdrive-test-device-1",
            pytest.version,
            password=self.password_1,
            base_folder=self.workspace_1,
            upload_tmp_dir=self.upload_tmp_dir,
            dao=self.engine_1._dao,
        )

        self.remote_2 = RemoteBase(
            pytest.nuxeo_url,
            self.user_2,
            "nxdrive-test-device-2",
            pytest.version,
            password=self.password_2,
            base_folder=self.workspace_2,
            upload_tmp_dir=self.upload_tmp_dir,
            dao=self.engine_2._dao,
        )

        # Register sync roots
        if register_roots:
            self.remote_1.register_as_root(self.workspace_1)
            self.addCleanup(self._unregister, self.workspace_1)
            self.remote_2.register_as_root(self.workspace_2)
            self.addCleanup(self._unregister, self.workspace_2)

    def tearDownApp(self):
        try:
            self.engine_1.remote.client._session.close()
        except AttributeError:
            pass

        try:
            self.engine_2.remote.client._session.close()
        except AttributeError:
            pass

        attrs = (
            "engine_1",
            "engine_2",
            "local_client_1",
            "local_client_2",
            "remote_1",
            "remote_2",
            "remote_document_client_1",
            "remote_document_client_2",
            "remote_file_system_client_1",
            "remote_file_system_client_2",
        )
        for attr in attrs:
            try:
                delattr(self, attr)
            except AttributeError:
                pass

    def get_local_client(self, path: Path):
        """
        Return an OS specific LocalClient class by default to simulate user actions on:
            - Explorer (Windows)
            - File Manager (macOS)
        On GNU/Linux, there is not specific behavior so the original LocalClient will be used.
        """

        if LINUX:
            client = LocalTest
        elif MAC:
            from .mac_local_client import MacLocalClient as client
        elif WINDOWS:
            from .win_local_client import WindowsLocalClient as client

        return client(path)

    def _unregister(self, workspace):
        """ Skip HTTP errors when cleaning up the test. """
        try:
            pytest.root_remote.unregister_as_root(workspace)
        except (HTTPError, ConnectionError):
            pass

    def bind_engine(self, number: int, start_engine: bool = True) -> None:
        number_str = str(number)
        manager = getattr(self, "manager_" + number_str)
        local_folder = getattr(self, "local_nxdrive_folder_" + number_str)
        user = getattr(self, "user_" + number_str)
        password = getattr(self, "password_" + number_str)
        engine = manager.bind_server(
            local_folder, pytest.nuxeo_url, user, password, start_engine=start_engine
        )

        engine.syncCompleted.connect(self.app.sync_completed)
        engine._remote_watcher.remoteScanFinished.connect(
            self.app.remote_scan_completed
        )
        engine._remote_watcher.changesFound.connect(self.app.remote_changes_found)
        engine._remote_watcher.noChangesFound.connect(self.app.no_remote_changes_found)

        engine_uid = engine.uid
        self._wait_sync[engine_uid] = True
        self._wait_remote_scan[engine_uid] = True
        self._remote_changes_count[engine_uid] = 0
        self._no_remote_changes[engine_uid] = False

        setattr(self, "engine_" + number_str, engine)

    def unbind_engine(self, number: int) -> None:
        number_str = str(number)
        engine = getattr(self, "engine_" + number_str)
        manager = getattr(self, "manager_" + number_str)
        manager.unbind_engine(engine.uid)
        delattr(self, "engine_" + number_str)

    def send_bind_engine(self, number: int, start_engine: bool = True) -> None:
        self.app.bindEngine.emit(number, start_engine)

    def send_unbind_engine(self, number: int) -> None:
        self.app.unbindEngine.emit(number)

    def wait_bind_engine(
        self, number: int, timeout: int = DEFAULT_WAIT_SYNC_TIMEOUT
    ) -> None:
        engine = "engine_" + str(number)
        while timeout > 0:
            sleep(1)
            timeout -= 1
            if getattr(self, engine, False):
                return
        self.fail("Wait for bind engine expired")

    def wait_unbind_engine(
        self, number: int, timeout: int = DEFAULT_WAIT_SYNC_TIMEOUT
    ) -> None:
        engine = "engine_" + str(number)
        while timeout > 0:
            sleep(1)
            timeout -= 1
            if not getattr(self, engine, False):
                return
        self.fail("Wait for unbind engine expired")

    def wait_sync(
        self,
        wait_for_async=False,
        timeout=DEFAULT_WAIT_SYNC_TIMEOUT,
        fail_if_timeout=True,
        wait_for_engine_1=True,
        wait_for_engine_2=False,
        wait_win=False,
        enforce_errors=True,
    ):
        log.debug("Wait for sync")

        # First wait for server if needed
        if wait_for_async:
            self.wait()

        if wait_win:
            log.trace("Need to wait for Windows delete resolution")
            sleep(WIN_MOVE_RESOLUTION_PERIOD / 1000)

        self._wait_sync = {
            self.engine_1.uid: wait_for_engine_1,
            self.engine_2.uid: wait_for_engine_2,
        }
        self._no_remote_changes = {
            self.engine_1.uid: not wait_for_engine_1,
            self.engine_2.uid: not wait_for_engine_2,
        }

        if enforce_errors:
            if not self.connected:
                self.engine_1.syncPartialCompleted.connect(
                    self.engine_1.get_queue_manager().requeue_errors
                )
                self.engine_2.syncPartialCompleted.connect(
                    self.engine_1.get_queue_manager().requeue_errors
                )
                self.connected = True
        elif self.connected:
            self.engine_1.syncPartialCompleted.disconnect(
                self.engine_1.get_queue_manager().requeue_errors
            )
            self.engine_2.syncPartialCompleted.disconnect(
                self.engine_1.get_queue_manager().requeue_errors
            )
            self.connected = False

        while timeout > 0:
            sleep(1)
            timeout -= 1
            if sum(self._wait_sync.values()) == 0:
                if wait_for_async:
                    log.debug(
                        "Sync completed, "
                        "wait_remote_scan=%r, "
                        "remote_changes_count=%r, "
                        "no_remote_changes=%r",
                        self._wait_remote_scan,
                        self._remote_changes_count,
                        self._no_remote_changes,
                    )

                    wait_remote_scan = False
                    if wait_for_engine_1:
                        wait_remote_scan |= self._wait_remote_scan[self.engine_1.uid]
                    if wait_for_engine_2:
                        wait_remote_scan |= self._wait_remote_scan[self.engine_2.uid]

                    is_remote_changes = True
                    is_change_summary_over = True
                    if wait_for_engine_1:
                        is_remote_changes &= (
                            self._remote_changes_count[self.engine_1.uid] > 0
                        )
                        is_change_summary_over &= self._no_remote_changes[
                            self.engine_1.uid
                        ]
                    if wait_for_engine_2:
                        is_remote_changes &= (
                            self._remote_changes_count[self.engine_2.uid] > 0
                        )
                        is_change_summary_over &= self._no_remote_changes[
                            self.engine_2.uid
                        ]

                    if all(
                        {
                            not wait_remote_scan,
                            not is_remote_changes,
                            is_change_summary_over,
                        }
                    ):
                        self._wait_remote_scan = {
                            self.engine_1.uid: wait_for_engine_1,
                            self.engine_2.uid: wait_for_engine_2,
                        }
                        self._remote_changes_count = {
                            self.engine_1.uid: 0,
                            self.engine_2.uid: 0,
                        }
                        self._no_remote_changes = {
                            self.engine_1.uid: False,
                            self.engine_2.uid: False,
                        }
                        log.debug(
                            "Ended wait for sync, setting "
                            "wait_remote_scan values to True, "
                            "remote_changes_count values to 0 and "
                            "no_remote_changes values to False"
                        )
                        return
                else:
                    log.debug("Sync completed, ended wait for sync")
                    return

        if fail_if_timeout:
            count1 = self.engine_1.get_dao().get_syncing_count()
            count2 = self.engine_2.get_dao().get_syncing_count()
            if wait_for_engine_1 and count1:
                err = "Wait for sync timeout expired for engine 1 (%d)" % count1
            elif wait_for_engine_2 and count2:
                err = "Wait for sync timeout expired for engine 2 (%d)" % count2
            else:
                err = "Wait for sync timeout has expired"
            log.warning(err)
        else:
            log.debug("Wait for sync timeout")

    def run(self, result=None):
        self.app = StubQApplication([], self)
        self.setUpApp()

        def launch_test():
            log.debug("UnitTest thread started")
            pytest.root_remote.log_on_server(">>> testing: " + self.id())
            # Note: we cannot use super().run(result) here
            super(UnitTestCase, self).run(result)
            self.app.quit()
            log.debug("UnitTest thread finished")

        sync_thread = Thread(target=launch_test)
        sync_thread.start()
        self.app.exec_()
        sync_thread.join(30)
        self.tearDownApp()
        del self.app
        log.debug("UnitTest run finished")

    def _stop_managers(self):
        """ Called by self.addCleanup() to stop all managers. """

        try:
            methods = itertools.product(
                ((self.manager_1, 1), (self.manager_2, 2)),
                ("unbind_all", "dispose_all"),
            )
            for (manager, idx), method in methods:
                func = getattr(manager, method, None)
                if func:
                    log.debug("Calling self.manager_%d.%s()", idx, method)
                    try:
                        func()
                    except:
                        pass
        finally:
            Manager._singleton = None

    def _check_cleanup(self):
        """ Called by self.addCleanup() to ensure folders are deleted. """
        try:
            for root, _, files in os.walk(self.tmpdir):
                if files:
                    log.error("tempdir not cleaned-up: %r", root)
        except OSError:
            pass

    def _interact(self, pause=0):
        self.app.processEvents()
        if pause > 0:
            sleep(pause)
        while self.app.hasPendingEvents():
            self.app.processEvents()

    def make_local_tree(self, root=None, local_client=None):
        nb_files, nb_folders = 6, 4
        if not local_client:
            local_client = LocalTest(self.engine_1.local_folder)
        if not root:
            root = Path(self.workspace_title)
            if not local_client.exists(root):
                local_client.make_folder(Path(), self.workspace_title)
                nb_folders += 1
        # create some folders
        folder_1 = local_client.make_folder(root, "Folder 1")
        folder_1_1 = local_client.make_folder(folder_1, "Folder 1.1")
        folder_1_2 = local_client.make_folder(folder_1, "Folder 1.2")
        folder_2 = local_client.make_folder(root, "Folder 2")

        # create some files
        local_client.make_file(
            folder_2, "Duplicated File.txt", content=b"Some content."
        )

        local_client.make_file(folder_1, "File 1.txt", content=b"aaa")
        local_client.make_file(folder_1_1, "File 2.txt", content=b"bbb")
        local_client.make_file(folder_1_2, "File 3.txt", content=b"ccc")
        local_client.make_file(folder_2, "File 4.txt", content=b"ddd")
        local_client.make_file(root, "File 5.txt", content=b"eee")
        return nb_files, nb_folders

    def make_server_tree(self, deep: bool = True) -> Tuple[int, int]:
        """
        Create some folders on the server.
        Returns a tuple (files_count, folders_count).
        """

        remote = self.remote_document_client_1
        folder_1 = remote.make_folder(self.workspace, "Folder 1")
        folder_2 = remote.make_folder(self.workspace, "Folder 2")

        if deep:
            folder_1_1 = remote.make_folder(folder_1, "Folder 1.1")
            folder_1_2 = remote.make_folder(folder_1, "Folder 1.2")

            # Those 2 attrs are used in test_synchronization.py
            self._duplicate_file_1 = remote.make_file(
                folder_2, "Duplicated File.txt", content=b"Some content."
            )
            self._duplicate_file_2 = remote.make_file(
                folder_2, "Duplicated File.txt", content=b"Other content."
            )

            remote.make_file(folder_1, "File 1.txt", content=b"aaa")
            remote.make_file(folder_1_1, "File 2.txt", content=b"bbb")
            remote.make_file(folder_1_2, "File 3.txt", content=b"ccc")
            remote.make_file(folder_2, "File 4.txt", content=b"ddd")

        remote.make_file(self.workspace, "File 5.txt", content=b"eee")
        return (7, 4) if deep else (1, 2)

    def get_local_child_count(self, path: Path) -> Tuple[int, int]:
        """
        Create some folders on the server.
        Returns a tuple (files_count, folders_count).
        """
        dir_count = file_count = 0
        for _, dirnames, filenames in os.walk(path):
            dir_count += len(dirnames)
            file_count += len(filenames)
        if (path / ".partials").exists():
            dir_count -= 1
        return file_count, dir_count

    def get_full_queue(self, queue, dao=None):
        if dao is None:
            dao = self.engine_1.get_dao()
        result = []
        while queue:
            result.append(dao.get_state_from_id(queue.pop().id))
        return result

    def wait(self, retry=3):
        try:
            pytest.root_remote.wait()
        except Exception as e:
            log.debug("Exception while waiting for server : %r", e)
            # Not the nicest
            if retry > 0:
                log.debug("Retry to wait")
                self.wait(retry - 1)

    def generate_report(self):
        """ Generate a report on failure. """

        if not self.report_path:
            return

        # Track any exception that could happen, specially those we would not
        # see if the test succeed.
        for _, error in vars(self._outcome).get("errors"):
            exception = str(error[1]).lower()
            message = str(error[2]).lower()
            if "mock" not in exception and "mock" not in message:
                break
        else:
            # No break => no unexpected exceptions
            return

        path = self.report_path / f"{self.id()}-{sys.platform}"
        self.manager_1.generate_report(path)

    def _set_read_permission(self, user, doc_path, grant):
        input_obj = "doc:" + doc_path
        remote = pytest.root_remote
        if grant:
            remote.operations.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
                grant=True,
            )
        else:
            remote.block_inheritance(doc_path)

    @staticmethod
    def generate_random_png(filename: Path = None, size: int = 0) -> Union[None, bytes]:
        """ Generate a random PNG file.

        :param filename: The output file name. If None, returns
               the picture content.
        :param size: The number of black pixels of the picture.
        :return: None if given filename else bytes
        """

        if not size:
            size = random.randint(1, 42)
        else:
            size = max(1, size)

        pack = struct.pack

        def chunk(header, data):
            return (
                pack(">I", len(data))
                + header
                + data
                + pack(">I", zlib.crc32(header + data) & 0xFFFFFFFF)
            )

        magic = pack(">8B", 137, 80, 78, 71, 13, 10, 26, 10)
        png_filter = pack(">B", 0)
        scanline = pack(">{}B".format(size * 3), *[0] * (size * 3))
        content = [png_filter + scanline for _ in range(size)]
        png = (
            magic
            + chunk(b"IHDR", pack(">2I5B", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(content)))
            + chunk(b"IEND", b"")
        )

        if not filename:
            return png

        filename.write_bytes(png)

    def assertNxPart(self, path: str, name: str):
        for child in self.local_1.abspath(path).iterdir():
            child_name = child.name
            if len(child_name) < 8:
                continue
            if name is not None and len(child_name) < len(name) + 8:
                continue
            if (
                child_name[0] == "."
                and child_name.endswith(".nxpart")
                and (name is None or child_name[1 : len(name) + 1] == name)
            ):
                self.fail(f"nxpart found in {path!r}")

    def get_dao_state_from_engine_1(self, path: str):
        """
        Returns the pair from dao of engine 1 according to the path.

        :param path: The path to document (from workspace,
               ex: /Folder is converted to /{{workspace_title_1}}/Folder).
        :return: The pair from dao of engine 1 according to the path.
        """
        abs_path = "/" + self.workspace_title_1 + path
        return self.engine_1.get_dao().get_state_from_local(abs_path)

    def set_readonly(self, user: str, doc_path: str, grant: bool = True):
        """
        Mark a document as RO or RW.

        :param user: Affected username.
        :param doc_path: The document, either a folder or a file.
        :param grant: Set RO if True else RW.
        """
        remote = pytest.root_remote
        input_obj = "doc:" + doc_path
        if grant:
            remote.operations.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
            )
            remote.block_inheritance(doc_path, overwrite=False)
        else:
            remote.operations.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="ReadWrite",
                grant=True,
            )


def clean_dir(_dir: Path, retry: int = 1, max_retries: int = 5) -> None:
    if not _dir.exists():
        return

    test_data = os.environ.get("TEST_SAVE_DATA")
    if test_data:
        shutil.move(str(_dir), test_data)
        return

    try:
        for path, folders, filenames in os.walk(_dir):
            dirpath = normalized_path(path)
            for folder in folders:
                unset_path_readonly(dirpath / folder)
            for filename in filenames:
                unset_path_readonly(dirpath / filename)
        shutil.rmtree(_dir)
    except:
        if retry < max_retries:
            sleep(2)
            clean_dir(_dir, retry=retry + 1)
