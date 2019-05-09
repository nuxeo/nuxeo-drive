# coding: utf-8
import platform
import uuid
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, List, Optional, Type, TYPE_CHECKING
from urllib.parse import urlparse, urlsplit, urlunsplit
from weakref import CallableProxyType, proxy

import requests
from PyQt5.QtCore import QObject, QT_VERSION_STR, pyqtSignal, pyqtSlot
from PyQt5.sip import SIP_VERSION_STR

from . import __version__
from .autolocker import ProcessAutoLockerWorker
from .client.local_client import LocalClient
from .client.proxy import get_proxy, load_proxy, save_proxy, validate_proxy
from .constants import APP_NAME, STARTUP_PAGE_CONNECTION_TIMEOUT, DelAction
from .engine.dao.sqlite import ManagerDAO
from .engine.engine import Engine
from .exceptions import (
    EngineTypeMissing,
    FolderAlreadyUsed,
    InvalidDriveException,
    RootAlreadyBindWithDifferentAccount,
    StartupPageConnectionError,
)
from .logging_config import DEFAULT_LEVEL_FILE
from .notification import DefaultNotificationService
from .objects import Binder, EngineDef, Metrics
from .options import Options
from .osi import AbstractOSIntegration
from .poll_workers import DatabaseBackupWorker, ServerOptionsUpdater
from .updater import updater
from .updater.constants import Login
from .utils import (
    copy_to_clipboard,
    force_decode,
    get_arch,
    get_current_os_full,
    get_default_nuxeo_drive_folder,
    get_device,
    if_frozen,
    normalized_path,
)

if TYPE_CHECKING:
    from .client.proxy import Proxy  # noqa
    from .direct_edit import DirectEdit  # noqa
    from .engine.tracker import Tracker  # noqa
    from .updater import Updater  # noqa


__all__ = ("Manager",)

log = getLogger(__name__)


class Manager(QObject):
    newEngine = pyqtSignal(object)
    dropEngine = pyqtSignal(object)
    initEngine = pyqtSignal(object)
    started = pyqtSignal()
    stopped = pyqtSignal()
    suspended = pyqtSignal()
    reloadIconsSet = pyqtSignal(bool)
    resumed = pyqtSignal()

    _instances: Dict[Path, CallableProxyType] = {}
    __device_id = None
    autolock_service: ProcessAutoLockerWorker

    def __init__(self, home: Path) -> None:
        super().__init__()

        self._os = get_device()
        self._arch = get_arch()
        self._platform = get_current_os_full()

        # Primary attributes to allow initializing the notification center early
        self.home = normalized_path(home)
        self.home.mkdir(exist_ok=True)

        if self.home not in Manager._instances:
            Manager._instances[self.home] = proxy(self)

        # Used to tell other components they cannot do their work
        # if this attribute is set to True (like DirectEdit or resuming engines)
        self.restart_needed = False

        self._create_dao()

        self.notification_service = DefaultNotificationService(self)
        self.osi = AbstractOSIntegration.get(self)
        log.info(f"OS integration type: {self.osi.nature}")

        self.direct_edit_folder = self.home / "edit"

        self._engine_definitions: List[EngineDef] = []

        self._engine_types: Dict[str, Type[Engine]] = {"NXDRIVE": Engine}
        self._engines: Dict[str, Engine] = {}
        self.server_config_updater: Optional[ServerOptionsUpdater] = None
        self.db_backup_worker: Optional[DatabaseBackupWorker] = None

        if Options.proxy_server is not None:
            self.proxy = get_proxy(category="Manual", url=Options.proxy_server)
            save_proxy(self.proxy, self._dao, token=self.device_id)
        else:
            self.proxy = load_proxy(self._dao)
        log.info(f"Proxy configuration is {self.proxy!r}")

        # Set the logs levels option
        Options.log_level_file = self.get_log_level()

        # Force language
        if Options.force_locale is not None:
            self.set_config("locale", Options.force_locale)

        self.old_version = None
        if Options.is_frozen:
            # Persist the channel update
            # Retro-compatibility for versions < 4.0.2
            beta = self.get_config("beta_channel")
            if beta is not None:
                if beta:
                    Options.set("channel", "beta", setter="local")
                else:
                    Options.set("channel", "release", setter="local")
                self._dao.delete_config("beta_channel")

            Options.set("channel", self.get_update_channel(), setter="local")
            if self.get_config("channel") != Options.channel:
                self.set_config("channel", Options.channel)

            # Keep a trace of installed versions
            if not self.get_config("original_version"):
                self.set_config("original_version", self.version)

            # Store the old version to be able to show release notes
            self.old_version = self.get_config("client_version")
            if self.old_version != self.version:
                self.set_config("client_version", self.version)

            # Add auto-lock on edit
            if self._dao.get_config("direct_edit_auto_lock") is None:
                self._dao.store_bool("direct_edit_auto_lock", True)

        # Set default deletion behavior
        if not self.get_config("deletion_behavior"):
            self.set_config("deletion_behavior", "unsync")

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
        # Create the server's configuration getter verification thread
        self._create_db_backup_worker()

        # Create the application update verification thread
        self.updater: "Updater" = self._create_updater()

        # Setup analytics tracker
        self._tracker = self._create_tracker()

        # Create the FinderSync/Explorer listener thread
        self._create_extension_listener()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} home={self.home!r}>"

    def close(self):
        try:
            self.stop()
        finally:
            Manager._instances.pop(self.home, None)

    def get_metrics(self) -> Metrics:
        return {
            "version": self.version,
            "auto_start": self.get_auto_start(),
            "auto_update": self.get_auto_update(),
            "channel": self.get_update_channel(),
            "device_id": self.device_id,
            "tracker_id": self.get_tracker_id(),
            "tracking": Options.use_analytics,
            "sentry": Options.use_sentry,
            "sip_version": SIP_VERSION_STR,
            "qt_version": QT_VERSION_STR,
            "python_version": platform.python_version(),
            "os": self._os,
            "platform": self._platform,
            "arch": self._arch,
            "appname": APP_NAME,
        }

    def open_help(self) -> None:
        self.open_local_file("https://doc.nuxeo.com/nxdoc/nuxeo-drive/")

    @if_frozen
    def _handle_os(self) -> None:
        # Be sure to register os
        self.osi.register_protocol_handlers()
        if self.get_auto_start():
            self.osi.register_startup()

    def _create_autolock_service(self) -> ProcessAutoLockerWorker:

        self.autolock_service = ProcessAutoLockerWorker(
            30, self._dao, folder=self.direct_edit_folder
        )
        self.started.connect(self.autolock_service.thread.start)
        return self.autolock_service

    def _create_tracker(self) -> Optional["Tracker"]:
        if not self.get_tracking():
            return None

        from .engine.tracker import Tracker  # noqa

        tracker = Tracker(self)
        # Start the tracker when we launch
        self.started.connect(tracker.thread.start)
        return tracker

    def _get_db(self) -> Path:
        return self.home / "manager.db"

    def get_dao(self) -> ManagerDAO:  # TODO: Remove
        return self._dao

    def _create_dao(self) -> None:
        self._dao = ManagerDAO(self._get_db())

    def _create_server_config_updater(self) -> None:
        if not Options.update_check_delay:
            return

        self.server_config_updater = ServerOptionsUpdater(self)
        if self.server_config_updater:
            self.started.connect(self.server_config_updater.thread.start)

    def _create_updater(self) -> "Updater":  # type: ignore
        updater_ = updater(self)
        self.prompted_wrong_channel = False
        self.started.connect(updater_.thread.start)
        return updater_

    def _create_db_backup_worker(self) -> None:
        self.db_backup_worker = DatabaseBackupWorker(self)
        if self.db_backup_worker:
            self.started.connect(self.db_backup_worker.thread.start)

    @if_frozen
    def _create_extension_listener(self) -> None:

        self._extension_listener = self.osi.get_extension_listener()
        if not self._extension_listener:
            return
        self._extension_listener.listening.connect(self.osi._init)
        self.started.connect(self._extension_listener._listen)
        self.stopped.connect(self._extension_listener.close)

    @if_frozen
    def refresh_update_status(self) -> None:
        if self.updater:
            self.updater.refresh_status()

    def _create_direct_edit(self, url: str) -> "DirectEdit":
        from .direct_edit import DirectEdit  # noqa

        self.direct_edit = DirectEdit(self, self.direct_edit_folder, url)
        self.started.connect(self.direct_edit.thread.start)
        self.autolock_service.direct_edit = self.direct_edit
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
            log.info(f"Resume engine {uid}")
            engine.resume()
        self.resumed.emit()

    def suspend(self, euid: str = None) -> None:
        if self._pause:
            return
        self._pause = True
        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            log.info(f"Suspend engine {uid}")
            engine.suspend()
        self.suspended.emit()

    def stop(self, euid: str = None) -> None:
        # Make a backup in case something happens
        self._dao.save_backup()

        for uid, engine in self._engines.items():
            if euid is not None and euid != uid:
                continue
            if engine.is_started():
                log.info(f"Stop engine {uid}")
                engine.stop()
        self.osi._cleanup()
        self.dispose_db()
        self.stopped.emit()

    def start(self, euid: str = None) -> None:
        self._started = True
        for uid, engine in list(self._engines.items()):
            if euid is not None and euid != uid:
                continue
            if not self._pause:
                log.info(f"Launch engine {uid}")
                try:
                    engine.start()
                except:
                    log.exception(f"Could not start the engine {uid}")

        # Check only if manager is started
        self._handle_os()
        self.started.emit()

    def load(self) -> None:
        self._engine_definitions = self._engine_definitions or self._dao.get_engines()
        self._engines = {}

        for engine in self._engine_definitions.copy():
            if engine.engine not in self._engine_types:
                log.error(f"Cannot find {engine.engine} engine type anymore")
                self._engine_definitions.remove(engine)
                continue
            elif not self._get_engine_db_file(engine.uid).is_file():
                log.warning(f"Cannot find {engine.uid} engine database file anymore")
                self._engine_definitions.remove(engine)
                continue

            self._engines[engine.uid] = self._engine_types[engine.engine](self, engine)
            self._engines[engine.uid].online.connect(self._force_autoupdate)
            self.initEngine.emit(self._engines[engine.uid])

    def _get_engine_db_file(self, uid: str) -> Path:
        return self.home / f"ndrive_{uid}.db"

    def _force_autoupdate(self) -> None:
        if not self.updater:
            return
        if self.updater.get_next_poll() > 60 and self.updater.get_last_poll() > 1800:
            self.updater.force_poll()

    @pyqtSlot(str)
    def open_local_file(self, file_path: str, select: bool = False) -> None:
        """Launch the local OS program on the given file / folder."""
        file_path = force_decode(file_path)
        log.info(f"Launching editor on {file_path!r}")
        try:
            self.osi.open_local_file(file_path)
        except Exception:
            # Log the exception now, will see later if we need to adapt
            log.exception(f"Failed to find an editor for {file_path!r}")
            return

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
        return self._dao.get_bool("direct_edit_auto_lock", default=Options.is_frozen)

    @pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value: bool) -> None:
        self._dao.store_bool("direct_edit_auto_lock", value)

    @pyqtSlot(result=bool)
    def get_auto_update(self) -> bool:
        # Enabled by default, if app is frozen
        return Options.update_check_delay > 0 and self._dao.get_bool(
            "auto_update", default=Options.is_frozen
        )

    @pyqtSlot(bool)
    def set_auto_update(self, value: bool) -> None:
        self._dao.store_bool("auto_update", value)

    @pyqtSlot(result=bool)
    def get_auto_start(self) -> bool:
        # Enabled by default, if app is frozen
        return self._dao.get_bool("auto_start", default=Options.is_frozen)

    def generate_report(self, path: Path = None) -> Path:
        from .report import Report

        report = Report(self, path)
        report.generate()
        return report.get_path()

    @pyqtSlot(bool, result=bool)
    def set_auto_start(self, value: bool) -> bool:
        self._dao.store_bool("auto_start", value)

        if value:
            return self.osi.register_startup()

        return self.osi.unregister_startup()

    @pyqtSlot(result=bool)
    def use_light_icons(self) -> bool:
        """Return True is the current icons set is the light one."""
        return self._dao.get_bool("light_icons")

    @pyqtSlot(bool)
    def set_light_icons(self, value: bool) -> None:
        self.set_config("light_icons", value)
        self.reloadIconsSet.emit(value)

    @pyqtSlot(result=str)
    def get_update_channel(self) -> str:
        return self._dao.get_config("channel", default=Options.channel or "release")

    @pyqtSlot(str)
    def set_update_channel(self, value: str) -> None:
        self.set_config("channel", value)
        self.prompted_wrong_channel = False
        # Trigger update status refresh
        if self.updater.enable:
            self.refresh_update_status()

    @pyqtSlot(result=str)
    def get_log_level(self) -> str:
        level = self._dao.get_config("log_level_file")
        if not level:
            level = Options.log_level_file or DEFAULT_LEVEL_FILE
        return level

    @pyqtSlot(str)
    def set_log_level(self, value: str) -> None:
        if value == "DEBUG":
            log.warning("Setting log level to DEBUG, sensitive data may be logged.")
        self.set_config("log_level_file", value)

    def get_tracking(self) -> bool:
        """
        Avoid sending statistics when testing or if the user does not allow it.
        """
        return Options.is_frozen and Options.use_analytics

    def get_tracker_id(self) -> str:
        return self._tracker.uid if self._tracker else ""

    def set_proxy(self, proxy: "Proxy") -> str:
        for engine in self._engines.values():
            if not validate_proxy(proxy, engine.server_url):
                return "PROXY_INVALID"
            engine.remote.set_proxy(proxy)

        save_proxy(proxy, self._dao)
        self.proxy = proxy
        log.debug(f"Effective proxy: {proxy!r}")
        return ""

    def get_deletion_behavior(self) -> DelAction:
        return DelAction(self.get_config("deletion_behavior", default="unsync"))

    def set_deletion_behavior(self, behavior: DelAction) -> None:
        self.set_config("deletion_behavior", behavior.value)

    def _get_default_server_type(self) -> str:  # TODO: Move to constants.py
        return "NXDRIVE"

    def _get_server_login_type(self, server_url: str, _raise: bool = True) -> Login:
        # Take into account URL parameters
        parts = urlsplit(server_url)
        url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                f"{parts.path}/{Options.browser_startup_page}",
                parts.query,
                parts.fragment,
            )
        )
        headers = {
            "X-Application-Name": APP_NAME,
            "X-Device-Id": self.device_id,
            "X-Client-Version": self.version,
            "User-Agent": f"{APP_NAME}/{self.version}",
        }

        log.info(f"Proxy configuration for startup page connection: {self.proxy}")
        try:
            with requests.get(
                url,
                headers=headers,
                proxies=self.proxy.settings(url=url),
                timeout=STARTUP_PAGE_CONNECTION_TIMEOUT,
                verify=Options.ca_bundle or not Options.ssl_no_verify,
            ) as resp:
                status = resp.status_code
        except:
            log.exception(
                f"Error while trying to connect to {APP_NAME} "
                f"startup page with URL {url}"
            )
            if _raise:
                raise StartupPageConnectionError()
        else:
            log.info(f"Status code for {url} = {status}")
            if status == 404:
                # We know the new endpoint is unavailable,
                # so we need to use the old login.
                return Login.OLD
            if status < 400 or status in {401, 403}:
                # We can access the new login page, or we are unauthorized
                # but it exists, so we can use the new login.
                return Login.NEW
        # The server returned an unexpected status code, or it was unreachable
        # for some reason, so the login endpoint is unknown.
        return Login.UNKNOWN

    def bind_server(
        self,
        local_folder: Path,
        url: str,
        username: str,
        password: str = None,
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

    def check_local_folder_available(self, path: Path) -> bool:
        if not self._engine_definitions:
            return True
        for engine in self._engine_definitions:
            other = engine.local_folder
            if path == other or path in other.parents or other in path.parents:
                return False
        return True

    def update_engine_path(self, uid: str, path: Path) -> None:
        # Dont update the engine by itself,
        # should be only used by engine.update_engine_path
        if uid in self._engines:
            # Unwatch old folder
            self.osi.unwatch_folder(self._engines[uid].local_folder)
            self._engines[uid].local_folder = path
        # Watch new folder
        self.osi.watch_folder(path)
        self._dao.update_engine_path(uid, path)

    def bind_engine(
        self,
        engine_type: str,
        local_folder: Path,
        name: Optional[str],
        binder: Binder,
        starts: bool = True,
    ) -> "Engine":
        """Bind a local folder to a remote server."""

        if name is None:
            name = self._get_engine_name(binder.url)

        if hasattr(binder, "url"):
            url = binder.url
            if "#" in url:
                # Last part of the URL is the engine type
                engine_type = url.split("#")[1]
                binder = binder._replace(url=url.split("#")[0])
                log.info(
                    f"Engine type has been specified in the URL: {engine_type} will be used"
                )

        if engine_type not in self._engine_types:
            raise EngineTypeMissing()

        if not local_folder:
            local_folder = get_default_nuxeo_drive_folder()
        elif local_folder == self.home:
            # Prevent from binding in the configuration folder
            raise FolderAlreadyUsed()
        elif not self.check_local_folder_available(local_folder):
            raise FolderAlreadyUsed()

        if not self._engines:
            self.load()

        uid = uuid.uuid1().hex

        # TODO Check that engine is not inside another or same position
        engine_def = self._dao.add_engine(engine_type, local_folder, uid, name)
        try:
            self._engines[uid] = self._engine_types[engine_type](
                self, engine_def, binder=binder
            )
        except Exception as exc:
            if not isinstance(
                exc, (InvalidDriveException, RootAlreadyBindWithDifferentAccount)
            ):
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

        # Watch folder in the file explorer
        self.osi.watch_folder(local_folder)

        self.newEngine.emit(self._engines[uid])

        # NXDRIVE-978: Update the current state to reflect the change in
        # the systray menu
        self._pause = False

        # Backup the database
        if self.db_backup_worker:
            self.db_backup_worker.force_poll()

        return self._engines[uid]

    def unbind_engine(self, uid: str) -> None:
        if not self._engines:
            self.load()
        if uid not in self._engines:
            return
        # Unwatch folder
        self.osi.unwatch_folder(self._engines[uid].local_folder)
        self._engines[uid].suspend()
        self._engines[uid].unbind()
        self._dao.delete_engine(uid)
        # Refresh the engines definition
        del self._engines[uid]
        self.dropEngine.emit(uid)
        self._engine_definitions = self._dao.get_engines()

        # Backup the database
        if self.db_backup_worker:
            self.db_backup_worker.force_poll()

    def dispose_db(self) -> None:
        if self._dao:
            self._dao.dispose()

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
            log.info(f"Some engines are currently synchronizing: {syncing_engines}")
            return True
        log.info("No engine currently synchronizing")
        return False

    def get_root_id(self, path: Path) -> str:
        ref = LocalClient.get_path_remote_id(path, "ndriveroot")
        if not ref:
            parent = path.parent
            # We can't find in any parent
            if parent == path or parent is None:
                return ""
            return self.get_root_id(parent)
        return ref

    def ctx_access_online(self, path: Path) -> None:
        """ Open the user's browser to a remote document. """

        log.info(f"Opening metadata window for {path!r}")
        try:
            url = self.get_metadata_infos(path)
        except ValueError:
            log.warning(
                f"The document {path!r} is not handled by the Nuxeo server "
                "or is not synchronized yet."
            )
        else:
            self.open_local_file(url)

    def ctx_copy_share_link(self, path: Path) -> None:
        """ Copy the document's share-link to the clipboard. """

        url = self.get_metadata_infos(path)
        copy_to_clipboard(url)
        log.info(f"Copied {url!r}")

    def ctx_edit_metadata(self, path: Path) -> None:
        """ Open the user's browser to a remote document's metadata. """

        log.info(f"Opening metadata window for {path!r}")
        try:
            url = self.get_metadata_infos(path, edit=True)
        except ValueError:
            log.warning(
                f"The document {path!r} is not handled by the Nuxeo server "
                "or is not synchronized yet."
            )
        else:
            self.open_local_file(url)

    def get_metadata_infos(self, path: Path, edit: bool = False) -> str:
        remote_ref = LocalClient.get_path_remote_id(path)
        if not remote_ref:
            raise ValueError(f"Could not find file {path!r} as {APP_NAME} managed")

        root_id = self.get_root_id(path)
        root_values = root_id.split("|") if root_id else []
        try:
            engine = self.get_engines()[root_values[3]]
        except:
            raise ValueError(f"Unknown engine {root_values[3]} for {path!r}")

        return engine.get_metadata_url(remote_ref, edit=edit)

    def send_sync_status(self, path: Path) -> None:
        for engine in self._engines.values():
            # Only send status if we picked the right
            # engine and if we're not targeting the root
            if engine.local_folder not in path.parents:
                continue

            r_path = path.relative_to(engine.local_folder)
            dao = engine._dao
            states = dao.get_local_children(r_path)
            self.osi.send_content_sync_status(states, path)
            return
