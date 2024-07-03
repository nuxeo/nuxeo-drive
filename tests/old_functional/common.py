""" Common test utilities. """
import os
import sys
import tempfile
from contextlib import suppress
from logging import getLogger
from pathlib import Path
from threading import Thread
from time import sleep
from typing import Dict, List, Tuple
from unittest import TestCase
from uuid import uuid4

import pytest
from faker import Faker
from nuxeo.exceptions import BadQuery
from nuxeo.models import Document, User
from sentry_sdk import configure_scope

from nxdrive import __version__
from nxdrive.constants import LINUX, MAC, WINDOWS
from nxdrive.engine.watcher.local_watcher import WIN_MOVE_RESOLUTION_PERIOD
from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.qt.imports import QCoreApplication, QTimer, pyqtSignal, pyqtSlot
from nxdrive.translator import Translator
from nxdrive.utils import normalized_path

from .. import env
from ..utils import clean_dir, salt
from . import DocRemote, LocalTest, RemoteBase, RemoteTest

# Default remote watcher delay used for tests
TEST_DEFAULT_DELAY = 3

FS_ITEM_ID_PREFIX = "defaultFileSystemItemFactory#default#"
SYNC_ROOT_FAC_ID = "defaultSyncRootFolderItemFactory#default#"

# 1s time resolution as we truncate remote last modification time to the
# seconds in RemoteFileInfo.from_dict() because of the datetime
# resolution of some databases (MySQL...)
REMOTE_MODIFICATION_TIME_RESOLUTION = 1.0

# 1s resolution on HFS+ on OSX
# ~0.01  sec for NTFS
#  0.001 sec for EXT4FS
OS_STAT_MTIME_RESOLUTION = 1.0

log = getLogger(__name__)

DEFAULT_WAIT_SYNC_TIMEOUT = 10
FILE_CONTENT = b"Lorem ipsum dolor sit amet ..."
FAKER = Faker("en_US")
LOCATION = normalized_path(__file__).parent.parent


Translator(LOCATION / "resources" / "i18n")


def nuxeo_url() -> str:
    """Retrieve the Nuxeo URL."""
    return env.NXDRIVE_TEST_NUXEO_URL.split("#")[0]


def root_remote(base_folder: str = "/") -> DocRemote:
    return DocRemote(
        nuxeo_url(),
        env.NXDRIVE_TEST_USERNAME,
        "nxdrive-test-administrator-device",
        __version__,
        password=env.NXDRIVE_TEST_PASSWORD,
        base_folder=base_folder,
        timeout=60,
    )


class StubQApplication(QCoreApplication):
    bindEngine = pyqtSignal(int, bool)
    unbindEngine = pyqtSignal(int)

    def __init__(self, argv, test_case):
        super().__init__(argv)

        # Little trick here! See Application.__init__() for details.
        self.timer = QTimer()
        self.timer.timeout.connect(lambda: None)
        self.timer.start(100)

        self._test = test_case
        self.bindEngine.connect(self.bind_engine)
        self.unbindEngine.connect(self.unbind_engine)

        # Used by test_local_move_folders.py
        self.local_scan_count = 0

    @pyqtSlot()
    def local_scan_finished(self) -> None:
        """Count the number of local scan done."""
        self.local_scan_count += 1

    @pyqtSlot()
    def sync_completed(self):
        uid = getattr(self.sender(), "uid", None)
        log.info("Sync Completed slot for: %s", uid)
        if uid:
            self._test._wait_sync[uid] = False
        else:
            for uid in self._test._wait_sync.keys():
                self._test._wait_sync[uid] = False

    @pyqtSlot()
    def remote_scan_completed(self):
        uid = self.sender().engine.uid
        log.info("Remote scan completed for engine %s", uid)
        self._test._wait_remote_scan[uid] = False
        self._test._wait_sync[uid] = False

    @pyqtSlot(int)
    def remote_changes_found(self, change_count):
        uid = self.sender().engine.uid
        log.info("Remote changes slot for: %s", uid)
        self._test._remote_changes_count[uid] = change_count

    @pyqtSlot()
    def no_remote_changes_found(self):
        uid = self.sender().engine.uid
        log.debug("No remote changes slot for %s", uid)
        self._test._no_remote_changes[uid] = True

    @pyqtSlot(int, bool)
    def bind_engine(self, number, start_engine):
        self._test.bind_engine(number, start_engine=start_engine)

    @pyqtSlot(int)
    def unbind_engine(self, number):
        self._test.unbind_engine(number, purge=False)


class TwoUsersTest(TestCase):
    @pytest.fixture(autouse=True)
    def inject_fixtures(self, caplog):
        self._caplog = caplog

    def setup_method(
        self,
        test_method,
        register_roots=True,
        user_2=True,
        server_profile=None,
        sync_enabled=True,
    ):
        """Setup method that will be invoked for every test method of a class."""

        log.info("TEST master setup start")
        Options.feature_synchronization = sync_enabled

        # To be replaced with fixtures when migrating to 100% pytest
        self.nuxeo_url = nuxeo_url()  # fixture name: nuxeo_url
        self.version = __version__  # fixture name: version
        self.root_remote = root_remote()
        self.fake = FAKER
        self.location = LOCATION

        self.server_profile = server_profile
        if server_profile:
            self.root_remote.activate_profile(server_profile)

        self.users = [self._create_user(1)]
        if user_2:
            self.users.append(self._create_user(2))
        self._create_workspace(f"{self._testMethodName}-{sys.platform.lower()}")

        # Add proper rights for all users on the root workspace
        users = [user.uid for user in self.users]
        try:
            self.ws.add_permission({"permission": "ReadWrite", "users": users})
        except BadQuery:
            # *users* is a valid parameter starting with Nuxeo 10.3.
            # Keep that compatibility code for test_volume.py to work on old customers server.
            for user in self.users:
                self.ws.add_permission(
                    {"permission": "ReadWrite", "username": user.uid}
                )

        Options.delay = TEST_DEFAULT_DELAY
        self.connected = False

        self.app = StubQApplication([], self)

        self._wait_sync = {}
        self._wait_remote_scan = {}
        self._remote_changes_count = {}
        self._no_remote_changes = {}

        self.tmpdir = (
            normalized_path(tempfile.gettempdir()) / str(uuid4()).split("-")[0]
        )
        self.upload_tmp_dir = self.tmpdir / "uploads"
        self.upload_tmp_dir.mkdir(parents=True)

        self._append_user_attrs(1, register_roots)
        if user_2:
            self._append_user_attrs(2, register_roots)

    def teardown_method(self, test_method):
        """Clean-up method."""

        log.info("TEST master teardown start")

        if self.server_profile:
            self.root_remote.deactivate_profile(self.server_profile)

        for user in list(self.users):
            self.root_remote.users.delete(user.uid)
            self.users.remove(user)

        self.ws.delete()

        self.manager_1.close()
        clean_dir(self.local_test_folder_1)
        clean_dir(self.upload_tmp_dir)

        if hasattr(self, "manager_2"):
            self.manager_2.close()
            clean_dir(self.local_test_folder_2)

        clean_dir(self.tmpdir)

        log.info("TEST master teardown end")

    def run(self, result=None):
        """
        I could not (yet?) migrate this method to pytest because I did not
        find a way to make tests pass.
        We need to start each test in a thread and call self.app.exec_() to
        let signals transit in the QApplication.
        """

        log.info("TEST run start")

        def launch_test():
            # Cleanup potential old report
            self._get_report_file().unlink(missing_ok=True)

            # Note: we cannot use super().run(result) here
            super(TwoUsersTest, self).run(result)

            # Generate a report if there are exceptions (failures or unexpected errors)
            if result._excinfo:
                try:
                    self.generate_report(result._excinfo)
                except Exception:
                    log.warning("Report generation failed", exc_info=True)

            with suppress(Exception):
                self.app.quit()

        # Ensure to kill the app if it is taking too long.
        # We need to do that because sometimes a thread get blocked and so the test suite.
        # Here, we set the default timeout to 2 minutes but use higher values for long-running tests.
        default_timeout = 60 * 2
        timeouts = {
            "test_nxdrive_903": 60 * 4,  # 4 minutes
            "test_nxdrive_947": 60 * 20,  # 20 minutes
            "test_nxdrive_1033": 60 * 6,  # 6 minutes
            "test_volume": 60 * 60 * 4,  # 4 hours
        }
        test_file = self.id().replace("tests.old_functional.", "").split(".")[0]
        timeout = timeouts.get(test_file, default_timeout)

        def kill_test():
            log.error(f"Killing {self.id()} after {timeout} seconds")
            self.app.exit(1)

        QTimer.singleShot(timeout * 1000, kill_test)

        # Start the app and let signals transit between threads!
        sync_thread = Thread(target=launch_test)

        with configure_scope() as scope:
            scope.set_tag("test", self._testMethodName)
            scope.set_tag("branch", os.getenv("BRANCH_NAME"))
            sync_thread.start()
            assert self.app.exec_() == 0
            sync_thread.join(30)

        log.info("TEST run end")

    def _get_report_file(self) -> Path:
        path = Path(os.getenv("REPORT_PATH", "."))
        file = f"{self._testMethodName}-{sys.platform.lower()}.zip"
        return path / file

    def _create_user(self, number: int) -> User:
        def _company_domain(company_: str) -> str:
            company_domain = company_.lower()
            company_domain = company_domain.replace(",", "_")
            company_domain = company_domain.replace(" ", "_")
            company_domain = company_domain.replace("-", "_")
            company_domain = company_domain.replace("__", "_")

        company = self.fake.company()
        company_domain = _company_domain(company)
        first_name, last_name = self.fake.name().split(" ", 1)
        username = salt(first_name.lower())
        properties = {
            "lastName": last_name,
            "firstName": first_name,
            "email": f"{username}@{company_domain}.org",
            "password": username,
            "username": username,
        }

        user = self.root_remote.users.create(User(properties=properties))
        log.warning(f"Created user {user}")

        setattr(self, f"user_{number}", username)
        setattr(self, f"password_{number}", username)

        return user

    def _create_workspace(self, title: str) -> Document:
        title = salt(title, prefix="")
        new_ws = Document(
            name=title, type=env.DOCTYPE_FOLDERISH, properties={"dc:title": title}
        )
        self.ws = self.root_remote.documents.create(new_ws, parent_path=env.WS_DIR)
        self.workspace = self.ws.uid
        self.workspace_title = self.ws.title
        log.warning(f"Created workspace {self.ws}")
        return self.ws

    def _append_user_attrs(self, number: int, register_roots: bool) -> None:
        """Create all stuff needed for one user. Ugly but useful."""

        # Create all what we need
        local_test_folder = self.tmpdir / str(number)
        local_nxdrive_folder = local_test_folder / "drive"
        local_nxdrive_folder.mkdir(parents=True)
        nxdrive_conf_folder = local_test_folder / "conf"
        nxdrive_conf_folder.mkdir()
        manager = Manager(nxdrive_conf_folder)
        user = getattr(self, f"user_{number}")
        password = getattr(self, f"password_{number}")
        engine = self.bind_engine(
            number,
            start_engine=False,
            manager=manager,
            user=user,
            password=password,
            folder=local_nxdrive_folder,
        )
        queue_manager = engine.queue_manager
        sync_root_folder = local_nxdrive_folder / self.workspace_title
        local_root_client = self.get_local_client(engine.local.base_folder)
        local = self.get_local_client(sync_root_folder)
        remote_document_client = DocRemote(
            self.nuxeo_url,
            getattr(self, f"user_{number}"),
            f"nxdrive-test-device-{number}",
            self.version,
            password=getattr(self, f"password_{number}"),
            base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir,
            dao=engine.dao,
        )
        remote = RemoteBase(
            self.nuxeo_url,
            getattr(self, f"user_{number}"),
            f"nxdrive-test-device-{number}",
            self.version,
            password=getattr(self, f"password_{number}"),
            base_folder=self.workspace,
            upload_tmp_dir=self.upload_tmp_dir,
            dao=engine.dao,
        )
        if register_roots:
            remote.register_as_root(self.workspace)

        # Force deletion behavior to real deletion for all tests
        manager.set_config("deletion_behavior", "delete_server")
        manager.dao.store_bool("show_deletion_prompt", False)

        # And now persist in attributes
        setattr(self, f"manager_{number}", manager)
        setattr(self, f"local_test_folder_{number}", local_test_folder)
        setattr(self, f"local_nxdrive_folder_{number}", local_nxdrive_folder)
        setattr(self, f"nxdrive_conf_folder_{number}", nxdrive_conf_folder)
        setattr(self, f"queue_manager_{number}", queue_manager)
        setattr(self, f"sync_root_folder_{number}", sync_root_folder)
        setattr(self, f"local_root_client_{number}", local_root_client)
        setattr(self, f"local_{number}", local)
        setattr(self, f"remote_document_client_{number}", remote_document_client)
        setattr(self, f"remote_{number}", remote)

    def get_bad_remote(self):
        """A Remote client that will raise some error."""
        return RemoteTest(
            self.nuxeo_url,
            self.user_1,
            "nxdrive-test-administrator-device",
            self.version,
            password=self.password_1,
            dao=self.engine_1.dao,
        )

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
            from .local_client_darwin import MacLocalClient as client
        elif WINDOWS:
            from .local_client_windows import WindowsLocalClient as client

        return client(path)

    def bind_engine(
        self,
        number,
        start_engine=True,
        manager=None,
        folder=None,
        user=None,
        password=None,
    ):
        number_str = str(number)
        manager = manager or getattr(self, f"manager_{number_str}")
        folder = folder or getattr(self, f"local_nxdrive_folder_{number_str}")
        user = user or getattr(self, f"user_{number_str}")
        password = password or getattr(self, f"password_{number_str}")
        engine = manager.bind_server(
            folder, self.nuxeo_url, user, password=password, start_engine=start_engine
        )

        self.app.aboutToQuit.connect(manager.stop)
        engine.syncCompleted.connect(self.app.sync_completed)
        if hasattr(engine, "_remote_watcher"):  # Sync is disabled
            engine._remote_watcher.remoteScanFinished.connect(
                self.app.remote_scan_completed
            )
            engine._remote_watcher.changesFound.connect(self.app.remote_changes_found)
            engine._remote_watcher.noChangesFound.connect(
                self.app.no_remote_changes_found
            )

        engine_uid = engine.uid
        self._wait_sync[engine_uid] = True
        self._wait_remote_scan[engine_uid] = True
        self._remote_changes_count[engine_uid] = 0
        self._no_remote_changes[engine_uid] = False

        setattr(self, f"engine_{number}", engine)

        # If there are Remotes, update their DAO as the old one is no more revelant
        for remote in (f"remote_document_client_{number}", f"remote_{number}"):
            if hasattr(self, remote):
                getattr(self, remote).dao = engine.dao

        return engine

    def unbind_engine(self, number: int, purge: bool = True) -> None:
        number_str = str(number)
        engine = getattr(self, f"engine_{number_str}")
        manager = getattr(self, f"manager_{number_str}")
        manager.unbind_engine(engine.uid, purge=purge)
        delattr(self, f"engine_{number_str}")

    def send_bind_engine(self, number: int, start_engine: bool = True) -> None:
        self.app.bindEngine.emit(number, start_engine)

    def send_unbind_engine(self, number: int) -> None:
        self.app.unbindEngine.emit(number)

    def wait_bind_engine(
        self, number: int, timeout: int = DEFAULT_WAIT_SYNC_TIMEOUT
    ) -> None:
        engine = f"engine_{number}"
        for _ in range(timeout):
            if hasattr(self, engine):
                return
            sleep(1)

        self.fail("Wait for bind engine expired")

    def wait_unbind_engine(
        self, number: int, timeout: int = DEFAULT_WAIT_SYNC_TIMEOUT
    ) -> None:
        engine = f"engine_{number}"
        for _ in range(timeout):
            if not hasattr(self, engine):
                return
            sleep(1)

        self.fail("Wait for unbind engine expired")

    def wait(self, retry=3):
        try:
            self.root_remote.wait()
        except Exception as e:
            log.warning(f"Exception while waiting for server: {e!r}")
            # Not the nicest
            if retry > 0:
                log.info("Retry to wait")
                self.wait(retry - 1)

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
        log.info("Wait for sync")

        # First wait for server if needed
        if wait_for_async:
            self.wait()

        if wait_win and WINDOWS:
            log.debug("Waiting for Windows delete resolution")
            sleep(WIN_MOVE_RESOLUTION_PERIOD / 1000)

        engine_1 = self.engine_1.uid
        engine_2 = self.engine_2.uid

        self._wait_sync = {engine_1: wait_for_engine_1, engine_2: wait_for_engine_2}
        self._no_remote_changes = {
            engine_1: not wait_for_engine_1,
            engine_2: not wait_for_engine_2,
        }

        if enforce_errors:
            if not self.connected:
                self.engine_1.syncPartialCompleted.connect(
                    self.engine_1.queue_manager.requeue_errors
                )
                self.engine_2.syncPartialCompleted.connect(
                    self.engine_2.queue_manager.requeue_errors
                )
                self.connected = True
        elif self.connected:
            self.engine_1.syncPartialCompleted.disconnect(
                self.engine_1.queue_manager.requeue_errors
            )
            self.engine_2.syncPartialCompleted.disconnect(
                self.engine_2.queue_manager.requeue_errors
            )
            self.connected = False

        for _ in range(timeout):
            sleep(1)

            if sum(self._wait_sync.values()):
                continue

            if not wait_for_async:
                return

            log.info(
                "Sync completed, "
                f"wait_remote_scan={self._wait_remote_scan}, "
                f"remote_changes_count={self._remote_changes_count}, "
                f"no_remote_changes={self._no_remote_changes}"
            )

            wait_remote_scan = False
            if wait_for_engine_1:
                wait_remote_scan |= self._wait_remote_scan[engine_1]
            if wait_for_engine_2:
                wait_remote_scan |= self._wait_remote_scan[engine_2]

            is_remote_changes = True
            is_change_summary_over = True
            if wait_for_engine_1:
                is_remote_changes &= self._remote_changes_count[engine_1] > 0
                is_change_summary_over &= self._no_remote_changes[engine_1]
            if wait_for_engine_2:
                is_remote_changes &= self._remote_changes_count[engine_2] > 0
                is_change_summary_over &= self._no_remote_changes[engine_2]

            if (
                not wait_remote_scan
                and not is_remote_changes
                and is_change_summary_over
            ):
                self._wait_remote_scan = {
                    engine_1: wait_for_engine_1,
                    engine_2: wait_for_engine_2,
                }
                self._remote_changes_count = {engine_1: 0, engine_2: 0}
                self._no_remote_changes = {engine_1: False, engine_2: False}
                log.info(
                    "Ended wait for sync, setting "
                    "wait_remote_scan values to True, "
                    "remote_changes_count values to 0 and "
                    "no_remote_changes values to False"
                )
                return

        if not fail_if_timeout:
            log.info("Wait for sync timeout")
            return

        count1 = self.engine_1.dao.get_syncing_count()
        count2 = self.engine_2.dao.get_syncing_count()
        err = "Wait for sync timeout has expired"
        if wait_for_engine_1 and count1:
            err += f" for engine 1 (syncing_count={count1})"
        if wait_for_engine_2 and count2:
            err += f" for engine 2 (syncing_count={count2})"
        log.warning(err)

    def make_server_tree(self, deep: bool = True) -> Dict[str, str]:
        """
        Create some folders on the server.
        Returns a dict of document UIDs.
        """

        make_folder = self.remote_document_client_1.make_folder
        make_file = self.remote_document_client_1.make_file

        docs = {}
        docs["Folder 1"] = folder_1 = make_folder(self.workspace, "Folder 1")
        docs["Folder 2"] = folder_2 = make_folder(self.workspace, "Folder 2")
        docs["File 5.txt"] = make_file(self.workspace, "File 5.txt", content=b"eee")

        if deep:
            docs["Folder 1.1"] = folder_1_1 = make_folder(folder_1, "Folder 1.1")
            docs["Folder 1.2"] = folder_1_2 = make_folder(folder_1, "Folder 1.2")
            docs["Dupe 1.txt"] = make_file(
                folder_2, "Duplicated File.txt", content=b"Some content."
            )
            docs["Dupe 2.txt"] = make_file(
                folder_2, "Duplicated File.txt", content=b"Other content."
            )
            docs["File 1.txt"] = make_file(folder_1, "File 1.txt", content=b"aaa")
            docs["File 2.txt"] = make_file(folder_1_1, "File 2.txt", content=b"bbb")
            docs["File 3.txt"] = make_file(folder_1_2, "File 3.txt", content=b"ccc")
            docs["File 4.txt"] = make_file(folder_2, "File 4.txt", content=b"ddd")

        return docs

    def get_local_child_count(self, path: Path) -> Tuple[int, int]:
        """
        Create some folders on the server.
        Returns a tuple (files_count, folders_count).
        """
        dir_count = file_count = 0
        for _, dirnames, filenames in os.walk(path):
            dir_count += len(dirnames)
            file_count += len(filenames)
        return file_count, dir_count

    def generate_report(self, exceptions: List[Exception]) -> None:
        """Generate a report on failure."""
        # Track any exception that could happen, specially those we would not
        # see if the test succeed.

        from _pytest.outcomes import Skipped, XFailed

        unexpected_error = False

        for n, exc in enumerate(exceptions, 1):
            if isinstance(exc.value, (Skipped, XFailed)):
                # Uninteresting exceptions
                continue

            if (
                isinstance(exc.value, AssertionError)
                or "mock" not in str(exc.exconly()).lower()
            ):
                # - If the exception is an AssertionError, then the test failed.
                # - If there is another exception, ensure it is not a crafted one.
                unexpected_error = True

                # Log the error to help understanding what happened
                error = exc.getrepr(
                    showlocals=True, style="long", funcargs=True, truncate_locals=False
                )
                log.warning(f"Error n°{n} ({type(exc.value)})\n{error}")

        if not unexpected_error:
            return

        self.manager_1.generate_report(path=self._get_report_file())

    def _set_read_permission(self, user, doc_path, grant):
        input_obj = "doc:" + doc_path
        remote = self.root_remote
        if grant:
            remote.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
                grant=True,
            )
        else:
            remote.block_inheritance(doc_path)

    def get_dao_state_from_engine_1(self, path: str):
        """
        Returns the pair from dao of engine 1 according to the path.

        :param path: The path to document (from workspace,
               ex: /Folder is converted to /{{workspace_title}}/Folder).
        :return: The pair from dao of engine 1 according to the path.
        """
        abs_path = Path(f"/{self.workspace_title}") / path
        return self.engine_1.dao.get_state_from_local(abs_path)

    def set_readonly(self, user: str, doc_path: str, grant: bool = True):
        """
        Mark a document as RO or RW.

        :param user: Affected username.
        :param doc_path: The document, either a folder or a file.
        :param grant: Set RO if True else RW.
        """
        remote = self.root_remote
        input_obj = "doc:" + doc_path
        if grant:
            remote.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="Read",
            )
            remote.block_inheritance(doc_path, overwrite=False)
        else:
            remote.execute(
                command="Document.SetACE",
                input_obj=input_obj,
                user=user,
                permission="ReadWrite",
                grant=True,
            )


class OneUserTest(TwoUsersTest):
    """Tests requiring only one user."""

    def setup_method(self, *args, **kwargs):
        kwargs["user_2"] = False
        super().setup_method(*args, **kwargs)

    def wait_sync(
        self,
        wait_for_async=False,
        timeout=DEFAULT_WAIT_SYNC_TIMEOUT,
        fail_if_timeout=True,
        wait_for_engine_1=True,
        wait_win=False,
        enforce_errors=True,
    ):
        log.info("Wait for sync")

        # First wait for server if needed
        if wait_for_async:
            self.wait()

        if wait_win and WINDOWS:
            log.debug("Waiting for Windows delete resolution")
            sleep(WIN_MOVE_RESOLUTION_PERIOD / 1000)

        engine_1 = self.engine_1.uid

        self._wait_sync = {engine_1: wait_for_engine_1}
        self._no_remote_changes = {engine_1: not wait_for_engine_1}

        if enforce_errors:
            if not self.connected:
                self.engine_1.syncPartialCompleted.connect(
                    self.engine_1.queue_manager.requeue_errors
                )
                self.connected = True
        elif self.connected:
            self.engine_1.syncPartialCompleted.disconnect(
                self.engine_1.queue_manager.requeue_errors
            )
            self.connected = False

        for _ in range(timeout):
            sleep(1)

            if sum(self._wait_sync.values()):
                continue

            if not wait_for_async:
                return

            log.info(
                "Sync completed, "
                f"wait_remote_scan={self._wait_remote_scan}, "
                f"remote_changes_count={self._remote_changes_count}, "
                f"no_remote_changes={self._no_remote_changes}"
            )

            wait_remote_scan = False
            if wait_for_engine_1:
                wait_remote_scan |= self._wait_remote_scan[engine_1]

            is_remote_changes = True
            is_change_summary_over = True
            if wait_for_engine_1:
                is_remote_changes &= self._remote_changes_count[engine_1] > 0
                is_change_summary_over &= self._no_remote_changes[engine_1]

            if (
                not wait_remote_scan
                and not is_remote_changes
                and is_change_summary_over
            ):
                self._wait_remote_scan = {engine_1: wait_for_engine_1}
                self._remote_changes_count = {engine_1: 0}
                self._no_remote_changes = {engine_1: False}
                log.info(
                    "Ended wait for sync, setting "
                    "wait_remote_scan values to True, "
                    "remote_changes_count values to 0 and "
                    "no_remote_changes values to False"
                )
                return

        if not fail_if_timeout:
            log.info("Wait for sync timeout")
            return

        count = self.engine_1.dao.get_syncing_count()
        err = "Wait for sync timeout has expired"
        if wait_for_engine_1 and count:
            err += f" for engine 1 (syncing_count={count})"
        log.warning(err)


class OneUserNoSync(OneUserTest):
    """Tests requiring only one user with synchronization features disabled."""

    def setup_method(self, *args, **kwargs):
        kwargs["sync_enabled"] = False
        super().setup_method(*args, **kwargs)
