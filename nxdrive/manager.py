# coding: utf-8
import os
import platform
import subprocess
import unicodedata
import uuid
from logging import getLogger
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from PyQt5.QtCore import QObject, QT_VERSION_STR, pyqtSignal, pyqtSlot
from sip import SIP_VERSION_STR

from . import __version__
from .client.local_client import LocalClient
from .client.proxy import get_proxy, load_proxy, save_proxy, validate_proxy
from .constants import APP_NAME, MAC, WINDOWS
from .exceptions import EngineTypeMissing, FolderAlreadyUsed
from .logging_config import FILE_HANDLER
from .notification import DefaultNotificationService
from .objects import Binder, Metrics
from .options import Options, server_updater
from .osi import AbstractOSIntegration
from .updater import updater
from .utils import copy_to_clipboard, force_decode, normalized_path

if WINDOWS:
    import win32api

__all__ = ("Manager",)

log = getLogger(__name__)


class Manager(QObject):
    newEngine = pyqtSignal(object)
    dropEngine = pyqtSignal(object)
    initEngine = pyqtSignal(object)
    started = pyqtSignal()
    stopped = pyqtSignal()
    suspended = pyqtSignal()
    resumed = pyqtSignal()

    app_name = APP_NAME

    _singleton = None
    __device_id = None

    @staticmethod
    def get() -> "Manager":
        return Manager._singleton

    def __init__(self) -> None:
        if Manager._singleton:
            raise RuntimeError("Only one instance of Manager can be created.")

        super().__init__()
        Manager._singleton = self

        # Primary attributes to allow initializing the notification center early
        self.nxdrive_home = os.path.realpath(os.path.expanduser(Options.nxdrive_home))
        if not os.path.exists(self.nxdrive_home):
            os.mkdir(self.nxdrive_home)

        self._create_dao()

        self.notification_service = DefaultNotificationService(self)
        self.osi = AbstractOSIntegration.get(self)

        if not Options.consider_ssl_errors:
            self._bypass_https_verification()

        self.direct_edit_folder = os.path.join(
            normalized_path(self.nxdrive_home), "edit"
        )

        self._engine_definitions = None

        from .engine.engine import Engine
        from .engine.next.engine_next import EngineNext

        self._engine_types = {"NXDRIVE": Engine, "NXDRIVENEXT": EngineNext}
        self._engines = {}
        self.updater = None
        self.server_config_updater = None

        if Options.proxy_server is not None:
            self.proxy = get_proxy(category="Manual", url=Options.proxy_server)
            save_proxy(self.proxy, self._dao, token=self.device_id)
        else:
            self.proxy = load_proxy(self._dao)
        log.info("Proxy configuration is %r", self.proxy)

        # Set the logs levels option
        if FILE_HANDLER:
            FILE_HANDLER.setLevel(Options.log_level_file)

        # Force language
        if Options.force_locale is not None:
            self.set_config("locale", Options.force_locale)

        # Persist beta channel check
        Options.set("beta_channel", self.get_beta_channel(), setter="manual")

        # Keep a trace of installed versions
        if not self.get_config("original_version"):
            self.set_config("original_version", self.version)

        # Store the old version to be able to show release notes
        self.old_version = self.get_config("client_version")
        if self.old_version != self.version:
            self.set_config("client_version", self.version)

        # Add auto-lock on edit
        res = self._dao.get_config("direct_edit_auto_lock")
        if res is None:
            self._dao.update_config("direct_edit_auto_lock", "1")

        # Create DirectEdit
        self._create_autolock_service()
        self._create_direct_edit(Options.protocol_url)

        # Create notification service
        self._started = False

        # Pause if in debug
        self._pause = Options.debug

        # Connect all Qt signals
        self.notification_service.init_signals()
        self.load()

        # Create the server's configuration getter verification thread
        self._create_server_config_updater()

        # Create the application update verification thread
        self.updater = self._create_updater()

        # Setup analytics tracker
        self._tracker = self._create_tracker()

        # Create the FinderSync listener thread
        if MAC:
            self._create_findersync_listener()

    @staticmethod
    def _bypass_https_verification() -> None:
        """
        Let's bypass HTTPS verification since many servers
        unfortunately have invalid certificates.
        See https://www.python.org/dev/peps/pep-0476/ and NXDRIVE-506.
        """

        import ssl

        log.warning(
            "--consider-ssl-errors option is False, "
            "will not verify HTTPS certificates"
        )
        log.info(
            "Handle target environment that does not support HTTPS "
            "verification: globally disable verification by "
            "monkeypatching the ssl module though highly discouraged"
        )
        ssl._create_default_https_context = ssl._create_unverified_context

    def get_metrics(self) -> Metrics:
        return {
            "version": self.version,
            "auto_start": self.get_auto_start(),
            "auto_update": self.get_auto_update(),
            "beta_channel": self.get_beta_channel(),
            "device_id": self.device_id,
            "tracker_id": self.get_tracker_id(),
            "tracking": self.get_tracking(),
            "sip_version": SIP_VERSION_STR,
            "qt_version": QT_VERSION_STR,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "appname": self.app_name,
        }

    def open_help(self) -> None:
        self.open_local_file("https://doc.nuxeo.com/nxdoc/nuxeo-drive/")

    def _handle_os(self) -> None:
        # Be sure to register os
        self.osi.register_protocol_handlers()
        if self.get_auto_start():
            self.osi.register_startup()

    def _create_autolock_service(self) -> "ProcessAutoLockerWorker":
        from .autolocker import ProcessAutoLockerWorker

        self.autolock_service = ProcessAutoLockerWorker(
            30, self._dao, folder=self.direct_edit_folder
        )
        self.started.connect(self.autolock_service._thread.start)
        return self.autolock_service

    def _create_tracker(self) -> Optional["Tracker"]:
        if not self.get_tracking():
            return None

        from .engine.tracker import Tracker

        tracker = Tracker(self)
        # Start the tracker when we launch
        self.started.connect(tracker._thread.start)
        return tracker

    def _get_db(self) -> str:
        return os.path.join(normalized_path(self.nxdrive_home), "manager.db")

    def get_dao(self) -> "ManagerDAO":  # TODO: Remove
        return self._dao

    def _create_dao(self) -> None:
        from .engine.dao.sqlite import ManagerDAO

        self._dao = ManagerDAO(self._get_db())

    def _create_server_config_updater(self) -> None:
        if not Options.update_check_delay:
            return

        self.server_config_updater = server_updater(self)
        self.started.connect(self.server_config_updater._thread.start)

    def _create_updater(self) -> "Updater":
        updater_ = updater(self)
        self.started.connect(updater_._thread.start)
        return updater_

    def _create_findersync_listener(self) -> "FinderSyncListener":
        from .osi.darwin.darwin import FinderSyncListener

        self._findersync_listener = FinderSyncListener(self)
        self.started.connect(self._findersync_listener._thread.start)
        return self._findersync_listener

    def refresh_update_status(self) -> None:
        if self.updater:
            self.updater.refresh_status()

    def _create_direct_edit(self, url: str) -> "DirectEdit":
        from .direct_edit import DirectEdit

        self.direct_edit = DirectEdit(self, self.direct_edit_folder, url)
        self.started.connect(self.direct_edit._thread.start)
        return self.direct_edit

    def is_paused(self) -> bool:  # TODO: Remove
        return self._pause

    def resume(self, euid: str = None) -> None:
        if not self._pause:
            return
        self._pause = False
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.debug("Resume engine %s", uid)
            engine.resume()
        self.resumed.emit()

    def suspend(self, euid: str = None) -> None:
        if self._pause:
            return
        self._pause = True
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.debug("Suspend engine %s", uid)
            engine.suspend()
        self.suspended.emit()

    def stop(self, euid: str = None) -> None:
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            if engine.is_started():
                log.debug("Stop engine %s", uid)
                engine.stop()
        if MAC:
            self.osi._cleanup()
        self.stopped.emit()

    def start(self, euid: str = None) -> None:
        self._started = True
        for uid, engine in list(self._engines.items()):
            if euid is not None and euid != uid:
                continue
            if not self._pause:
                log.debug("Launch engine %s", uid)
                try:
                    engine.start()
                except:
                    log.exception("Could not start the engine %s", uid)

        # Check only if manager is started
        self._handle_os()
        self.started.emit()

    def load(self) -> None:
        if self._engine_definitions is None:
            self._engine_definitions = self._dao.get_engines()
        in_error = dict()
        self._engines = dict()
        for engine in self._engine_definitions:
            if engine.engine not in self._engine_types:
                log.warning("Cannot find engine %s anymore", engine.engine)
                if engine.engine not in in_error:
                    in_error[engine.engine] = True
            self._engines[engine.uid] = self._engine_types[engine.engine](self, engine)
            self._engines[engine.uid].online.connect(self._force_autoupdate)
            self.initEngine.emit(self._engines[engine.uid])

    def _force_autoupdate(self) -> None:
        if self.updater.get_next_poll() > 60 and self.updater.get_last_poll() > 1800:
            self.updater.force_poll()

    def get_default_nuxeo_drive_folder(self) -> str:
        """
        Find a reasonable location for the root Nuxeo Drive folder

        This folder is user specific, typically under the home folder.

        Under Windows, try to locate My Documents as a home folder, using the
        win32com shell API if allowed, else falling back on a manual detection.
        """

        folder = ""
        if WINDOWS:
            from win32com.shell import shell, shellcon

            try:
                folder = shell.SHGetFolderPath(0, shellcon.CSIDL_PERSONAL, None, 0)
            except:
                """
                In some cases (not really sure how this happens) the current user
                is not allowed to access its 'My Documents' folder path through
                the win32com shell API, which raises the following error:
                com_error: (-2147024891, 'Access is denied.', None, None)
                We noticed that in this case the 'Location' tab is missing in the
                Properties window of 'My Documents' accessed through the
                Explorer.
                So let's fall back on a manual (and poor) detection.
                WARNING: it's important to check 'Documents' first as under
                Windows 7 there also exists a 'My Documents' folder invisible in
                the Explorer and cmd / powershell but visible from Python.
                First try regular location for documents under Windows 7 and up
                """
                log.error(
                    "Access denied to the API SHGetFolderPath,"
                    " falling back on manual detection"
                )
                folder = os.path.expanduser("~\\Documents")

        if not folder:
            # Fall back on home folder otherwise
            folder = os.path.expanduser("~")

        folder = self._increment_local_folder(folder, self.app_name)
        folder = force_decode(folder)
        log.debug("Will use %r as default folder location", folder)
        return folder

    def _increment_local_folder(self, basefolder: str, name: str) -> str:
        folder = os.path.join(basefolder, name)
        num = 2
        while not self.check_local_folder_available(folder):
            folder = os.path.join(basefolder, name + " " + str(num))
            num += 1
            if num > 42:
                return ""
        return folder

    @pyqtSlot(str)
    def open_local_file(self, file_path: str, select: bool = False) -> None:
        # TODO: Move to utils.py
        """
        Launch the local OS program on the given file / folder.

        :param file_path: The file URL to open.
        :param select: Hightlight the given file_path. Useful when
                       opening a folder and to select a file.
        """
        file_path = force_decode(file_path)
        log.debug("Launching editor on %r", file_path)
        if WINDOWS:
            if select:
                win32api.ShellExecute(
                    None, "open", "explorer.exe", "/select," + file_path, None, 1
                )
            else:
                os.startfile(file_path)
        elif MAC:
            args = ["open"]
            if select:
                args += ["-R"]
            args += [file_path]
            subprocess.Popen(args)
        else:
            # TODO NXDRIVE-848: Select feature not yet implemented
            # TODO See https://bugs.freedesktop.org/show_bug.cgi?id=49552
            try:
                subprocess.Popen(["xdg-open", file_path])
            except OSError:
                # xdg-open should be supported by recent Gnome, KDE, Xfce
                log.error("Failed to find and editor for: %r", file_path)

    @property
    def device_id(self) -> str:
        if not self.__device_id:
            self.__device_id = self._dao.get_config("device_id")
            if not self.__device_id:
                self.__device_id = uuid.uuid1().hex
                self._dao.update_config("device_id", self.__device_id)
        return self.__device_id

    def get_config(self, value: str, default: Any = None) -> Any:
        return self._dao.get_config(value, default)

    def set_config(self, key: str, value: Any) -> None:
        Options.set(key, value, setter="manual", fail_on_error=False)
        self._dao.update_config(key, value)

    @pyqtSlot(result=bool)
    def get_direct_edit_auto_lock(self) -> bool:
        # Enabled by default, if app is frozen
        return (
            self._dao.get_config("direct_edit_auto_lock", str(int(Options.is_frozen)))
            == "1"
        )

    @pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value: bool) -> None:
        self._dao.update_config("direct_edit_auto_lock", value)

    @pyqtSlot(result=bool)
    def get_auto_update(self) -> bool:
        # Enabled by default, if app is frozen
        return self._dao.get_config("auto_update", str(int(Options.is_frozen))) == "1"

    @pyqtSlot(bool)
    def set_auto_update(self, value: bool) -> None:
        self._dao.update_config("auto_update", value)

    @pyqtSlot(result=bool)
    def get_auto_start(self) -> bool:
        # Enabled by default, if app is frozen
        return self._dao.get_config("auto_start", str(int(Options.is_frozen))) == "1"

    def generate_report(self, path: str = None) -> str:
        from .report import Report

        report = Report(self, path)
        report.generate()
        return report.get_path()

    @pyqtSlot(bool)
    def set_auto_start(self, value: bool) -> None:
        self._dao.update_config("auto_start", value)
        if value:
            self.osi.register_startup()
        else:
            self.osi.unregister_startup()

    @pyqtSlot(result=bool)
    def get_beta_channel(self) -> bool:
        return self._dao.get_config("beta_channel", "0") == "1"

    @pyqtSlot(bool)
    def set_beta_channel(self, value: bool) -> None:
        self.set_config("beta_channel", value)
        # Trigger update status refresh
        self.refresh_update_status()

    @pyqtSlot(result=bool)
    def get_tracking(self) -> bool:
        """
        Avoid sending statistics when testing or if the user does not allow it.
        """
        return all({Options.is_frozen, self._dao.get_config("tracking", "1") == "1"})

    @pyqtSlot(bool)
    def set_tracking(self, value: bool) -> None:
        self._dao.update_config("tracking", value)
        if value:
            self._create_tracker()
        elif self._tracker:
            self._tracker._thread.quit()
            self._tracker = None

    def get_tracker_id(self) -> str:
        return self._tracker.uid if self._tracker else ""

    def set_proxy(self, proxy: "Proxy") -> str:
        for engine in self._engines.values():
            url = engine._server_url
            if not validate_proxy(proxy, url):
                return "PROXY_INVALID"
            engine.remote.set_proxy(proxy)

        save_proxy(proxy, self._dao)
        self.proxy = proxy
        log.trace("Effective proxy: %r", proxy)
        return ""

    def _get_default_server_type(self) -> str:  # TODO: Move to constants.py
        return "NXDRIVE"

    def bind_server(
        self,
        local_folder: str,
        url: str,
        username: str,
        password: str,
        token: str = None,
        name: str = None,
        start_engine: bool = True,
        check_credentials: bool = True,
    ) -> "Engine":
        name = name or self._get_engine_name(url)
        binder = Binder(
            username=username,
            password=password,
            token=token,
            no_check=not check_credentials,
            no_fscheck=False,
            url=url,
        )
        return self.bind_engine(
            self._get_default_server_type(),
            local_folder,
            name,
            binder,
            starts=start_engine,
        )

    def _get_engine_name(self, server_url: str) -> str:
        urlp = urlparse(server_url)
        return urlp.hostname

    def check_local_folder_available(self, local_folder: str) -> bool:
        if self._engine_definitions is None:
            return True
        if not local_folder.endswith("/"):
            local_folder += "/"
        for engine in self._engine_definitions:
            other = engine.local_folder
            if not other.endswith("/"):
                other += "/"
            if other.startswith(local_folder) or local_folder.startswith(other):
                return False
        return True

    def update_engine_path(self, uid: str, local_folder: str) -> None:
        # Dont update the engine by itself,
        # should be only used by engine.update_engine_path
        if uid in self._engine_definitions:
            # Unwatch old folder
            self.osi.unwatch_folder(self._engine_definitions[uid].local_folder)
            self._engine_definitions[uid].local_folder = local_folder
        # Watch new folder
        self.osi.watch_folder(local_folder)
        self._dao.update_engine_path(uid, local_folder)

    def bind_engine(
        self,
        engine_type: str,
        local_folder: str,
        name: str,
        binder: Binder,
        starts: bool = True,
    ) -> "Engine":
        """Bind a local folder to a remote nuxeo server"""
        if name is None and hasattr(binder, "url"):
            name = self._get_engine_name(binder.url)
        if hasattr(binder, "url"):
            url = binder.url
            if "#" in url:
                # Last part of the URL is the engine type
                engine_type = url.split("#")[1]
                binder = binder._replace(url=url.split("#")[0])
                log.debug(
                    "Engine type has been specified in the URL: %s will be used",
                    engine_type,
                )

        if not self.check_local_folder_available(local_folder):
            raise FolderAlreadyUsed()

        if engine_type not in self._engine_types:
            raise EngineTypeMissing()

        if not self._engines:
            self.load()

        if not local_folder:
            local_folder = self.get_default_nuxeo_drive_folder()
        local_folder = normalized_path(local_folder)
        if local_folder == self.nxdrive_home:
            # Prevent from binding in the configuration folder
            raise FolderAlreadyUsed()

        uid = uuid.uuid1().hex

        # Watch folder in the file explorer
        self.osi.watch_folder(local_folder)
        # TODO Check that engine is not inside another or same position
        engine_def = self._dao.add_engine(engine_type, local_folder, uid, name)
        try:
            self._engines[uid] = self._engine_types[engine_type](
                self, engine_def, binder=binder
            )
        except Exception as exc:
            log.exception("Engine error")
            self._engines.pop(uid, None)
            self._dao.delete_engine(uid)
            # TODO Remove the DB?
            raise exc

        self._engine_definitions.append(engine_def)
        # As new engine was just bound, refresh application update status
        self.refresh_update_status()
        if starts:
            self._engines[uid].start()
        self.newEngine.emit(self._engines[uid])

        # NXDRIVE-978: Update the current state to reflect the change in
        # the systray menu
        self._pause = False

        return self._engines[uid]

    def unbind_engine(self, uid: str) -> None:
        if not self._engines:
            self.load()
        # Unwatch folder
        self.osi.unwatch_folder(self._engines[uid].local_folder)
        self._engines[uid].suspend()
        self._engines[uid].unbind()
        self._dao.delete_engine(uid)
        # Refresh the engines definition
        del self._engines[uid]
        self.dropEngine.emit(uid)
        self._engine_definitions = self._dao.get_engines()

    def unbind_all(self) -> None:
        if not self._engines:
            self.load()
        for engine in self._engine_definitions:
            self.unbind_engine(engine.uid)

    def dispose_db(self) -> None:
        if self._dao is not None:
            self._dao.dispose()

    def dispose_all(self) -> None:
        for engine in self.get_engines().values():
            engine.dispose_db()
        self.dispose_db()

    def get_engines(self) -> Dict[str, "Engine"]:  # TODO: Remove
        return self._engines

    @property
    def version(self) -> str:
        return __version__

    def is_started(self) -> bool:  # TODO: Remove
        return self._started

    def is_syncing(self) -> bool:
        syncing_engines = []
        for uid, engine in self._engines.items():
            if engine.is_syncing():
                syncing_engines.append(uid)
        if syncing_engines:
            log.debug("Some engines are currently synchronizing: %s", syncing_engines)
            return True
        log.debug("No engine currently synchronizing")
        return False

    def get_root_id(self, file_path: str) -> Optional[str]:
        ref = LocalClient.get_path_remote_id(file_path, "ndriveroot")
        if ref is None:
            parent = os.path.dirname(file_path)
            # We can't find in any parent
            if parent == file_path or parent is None:
                return None
            return self.get_root_id(parent)
        return ref

    def ctx_access_online(self, file_path: str) -> None:
        """ Open the user's browser to a remote document. """

        log.debug("Opening metadata window for %r", file_path)
        try:
            url = self.get_metadata_infos(file_path)
        except ValueError:
            log.warning(
                "The document %r is not handled by the Nuxeo server"
                " or is not synchronized yet.",
                file_path,
            )
        else:
            self.open_local_file(url)

    def ctx_copy_share_link(self, file_path: str) -> None:
        """ Copy the document's share-link to the clipboard. """

        url = self.get_metadata_infos(file_path)
        copy_to_clipboard(url)
        log.info("Copied %r", url)

    def ctx_edit_metadata(self, file_path: str) -> None:
        """ Open the user's browser to a remote document's metadata. """

        log.debug("Opening metadata window for %r", file_path)
        try:
            url = self.get_metadata_infos(file_path, edit=True)
        except ValueError:
            log.warning(
                "The document %r is not handled by the Nuxeo server"
                " or is not synchronized yet.",
                file_path,
            )
        else:
            self.open_local_file(url)

    def get_metadata_infos(self, file_path: str, edit: bool = False) -> str:
        remote_ref = LocalClient.get_path_remote_id(file_path)
        if remote_ref is None:
            raise ValueError(
                "Could not find file %r as Nuxeo Drive managed" % file_path
            )

        root_id = self.get_root_id(file_path)
        root_values = root_id.split("|")
        try:
            engine = self.get_engines()[root_values[3]]
        except:
            raise ValueError("Unknown engine %s for %r" % (root_values[3], file_path))

        return engine.get_metadata_url(remote_ref, edit=edit)

    def send_sync_status(self, path: str) -> None:
        for engine in self._engines.values():
            # Only send status if we picked the right
            # engine and if we're not targeting the root
            path = unicodedata.normalize("NFC", force_decode(path))
            if path.startswith(engine.local_folder_bs) and not os.path.samefile(
                path, engine.local_folder
            ):
                r_path = path.replace(engine.local_folder, "")
                dao = engine._dao
                state = dao.get_state_from_local(r_path)
                self.osi.send_sync_status(state, path)
                return
