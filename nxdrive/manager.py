import os
import platform
import shutil
import sqlite3
import uuid
from logging import getLogger
from pathlib import Path
from platform import machine
from time import sleep
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type
from urllib.parse import urlparse, urlsplit, urlunsplit
from weakref import CallableProxyType, proxy

import nuxeo
import requests
from nuxeo.utils import version_le

from . import __version__
from .auth import Token
from .autolocker import ProcessAutoLockerWorker
from .client.local import LocalClient
from .client.proxy import get_proxy, load_proxy, save_proxy, validate_proxy
from .constants import (
    APP_NAME,
    DEFAULT_CHANNEL,
    DEFAULT_SERVER_TYPE,
    NO_SPACE_ERRORS,
    STARTUP_PAGE_CONNECTION_TIMEOUT,
    WINDOWS,
    DelAction,
)
from .dao.manager import ManagerDAO
from .direct_edit import DirectEdit
from .engine.engine import Engine
from .engine.tracker import Tracker
from .engine.workers import Runner
from .exceptions import (
    AddonForbiddenError,
    AddonNotInstalledError,
    EngineInitError,
    EngineTypeMissing,
    FolderAlreadyUsed,
    MissingXattrSupport,
    NoAssociatedSoftware,
    RootAlreadyBindWithDifferentAccount,
    StartupPageConnectionError,
)
from .feature import Feature
from .metrics.utils import current_os, user_agent
from .notification import DefaultNotificationService
from .objects import Binder, EngineDef, Metrics, Session
from .options import DEFAULT_LOG_LEVEL_FILE, Options
from .osi import AbstractOSIntegration
from .poll_workers import DatabaseBackupWorker, ServerOptionsUpdater, SyncAndQuitWorker
from .qt.imports import QT_VERSION_STR, QObject, pyqtSignal, pyqtSlot
from .updater import updater
from .updater.constants import Login
from .utils import (
    client_certificate,
    force_decode,
    get_default_local_folder,
    if_frozen,
    normalized_path,
    save_config,
)

if TYPE_CHECKING:
    from .client.proxy import Proxy  # noqa
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
    directEdit = pyqtSignal(str, str, str, str)
    restartNeeded = pyqtSignal()
    featureUpdate = pyqtSignal(str, bool)

    # Direct Transfer statistics
    # args: folderish document, document size
    directTransferStats = pyqtSignal(bool, int)

    _instances: Dict[Path, CallableProxyType] = {}
    __device_id = None
    autolock_service: ProcessAutoLockerWorker

    def __init__(self, home: Path, /) -> None:
        super().__init__()

        # Primary attributes to allow initializing the notification center early
        self.home: Path = normalized_path(home)
        self.home.mkdir(exist_ok=True)

        if self.home not in Manager._instances:
            Manager._instances[self.home] = proxy(self)

        # Used to tell other components they cannot do their work
        # if this attribute is set to True (like Direct Edit or resuming engines)
        self.restart_needed = False
        self.restartNeeded.connect(self.suspend)
        self.restartNeeded.connect(self._restart_needed)

        self._create_dao()

        self.notification_service = DefaultNotificationService(self)
        self.osi = AbstractOSIntegration.get(self)
        log.info(f"OS integration type: {self.osi.nature}")

        self.direct_edit_folder = self.home / "edit"

        self._engine_definitions: List[EngineDef] = []

        self._engine_types: Dict[str, Type[Engine]] = {"NXDRIVE": Engine}
        self.engines: Dict[str, Engine] = {}
        self.db_backup_worker: Optional[DatabaseBackupWorker] = None

        if Options.proxy_server is not None:
            self.proxy = get_proxy("Manual", url=Options.proxy_server)
            save_proxy(self.proxy, self.dao, token=self.device_id)
        else:
            self.proxy = load_proxy(self.dao)
        log.info(f"Proxy configuration is {self.proxy!r}")

        # Set the logs levels option
        Options.log_level_file = self.get_log_level()

        # Force language
        if Options.force_locale is not None:
            self.set_config("locale", Options.force_locale)
        else:
            user_locale = self.get_config("locale")
            if user_locale is not None:
                Options.locale = user_locale

        # Backward-compatibility: handle synchronization state early
        if version_le(__version__, "5.2.0"):
            sync_enabled = self.dao.get_config("synchronization_enabled")
            if sync_enabled is not None:
                # Note: no need to handle the case where the sync is disabled because it is the default behavior
                if sync_enabled != "0":
                    self.set_feature_state("synchronization", True)
                self.dao.delete_config("synchronization_enabled")

        self.old_version = None

        if Options.is_frozen:
            # Persist the channel update
            # Retro-compatibility for versions < 4.0.2
            beta = self.get_config("beta_channel")
            if beta is not None:
                if beta:
                    Options.set("channel", "beta", setter="local")
                else:
                    Options.set("channel", DEFAULT_CHANNEL, setter="local")
                self.dao.delete_config("beta_channel")

            Options.set("channel", self.get_update_channel(), setter="local")
            if self.get_config("channel") != Options.channel:
                self.set_config("channel", Options.channel)

            # Keep a trace of installed versions
            if not self.get_config("original_version"):
                self.set_config("original_version", self.version)

            # Store the old version to be able to show release notes
            self.old_version = self.get_config("client_version")
            if self.old_version != self.version:
                self.dao.update_config("client_version", self.version)
            self._write_version_file()

            # Add auto-lock on edit
            if self.dao.get_config("direct_edit_auto_lock") is None:
                self.dao.store_bool("direct_edit_auto_lock", True)

        # Set default deletion behavior
        del_action = self.get_config("deletion_behavior")
        if del_action:
            Options.deletion_behavior = del_action
        else:
            self.set_config("deletion_behavior", "unsync")

        # Check for metrics approval
        self.preferences_metrics_chosen = False
        self.check_metrics_preferences()

        self._started = False

        # Pause if in debug
        self.is_paused = Options.debug

        # Create the server's configuration getter verification thread
        self._create_db_backup_worker()

        # Setup analytics tracker
        self.tracker = self.create_tracker()

        # Create the FinderSync/Explorer listener thread
        self._create_extension_listener()

        # Create the sync and quit worker
        self.sync_and_quit_worker = SyncAndQuitWorker(self)
        self.started.connect(self.sync_and_quit_worker.thread.start)

        # Create notification service
        self.notification_service.init_signals()

        # Connect all Qt signals
        self.load()

        # [this worker will control next workers, so keep it first]
        # Create the server's configuration getter verification thread
        self.server_config_updater: ServerOptionsUpdater = (
            self._create_server_config_updater()
        )

        # Create Direct Edit
        self.autolock_service = self._create_autolock_service()
        self.direct_edit = self._create_direct_edit()

        # Create the application update verification thread
        self.updater: "Updater" = self._create_updater()

    def __enter__(self) -> "Manager":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} home={self.home!r}>"

    def close(self) -> None:
        try:
            self.stop()
        except RuntimeError:
            # wrapped C/C++ object of type Manager has been deleted
            # Happens on Windows when running functional tests
            pass
        finally:
            Manager._instances.pop(self.home, None)

    def get_metrics(self) -> Metrics:
        return {
            "version": self.version,
            "auto_start": self.get_auto_start(),
            "auto_update": Feature.auto_update and self.get_auto_update(),
            "channel": self.get_update_channel(),
            "device_id": self.device_id,
            "tracker_id": self.tracker.uid,
            "tracking": Options.use_analytics,
            "sentry": Options.use_sentry,
            "qt_version": QT_VERSION_STR,
            "python_version": platform.python_version(),
            "python_client_version": nuxeo.__version__,
            "os": current_os(full=True),
            "machine": machine(),
            "appname": APP_NAME,
        }

    def _restart_needed(self) -> None:
        """Simple helper to set the attribute's value.
        That value will be used in other components.
        """
        self.restart_needed = True

    def open_help(self) -> None:
        self.open_local_file("https://doc.nuxeo.com/nxdoc/nuxeo-drive/")

    def check_metrics_preferences(self) -> None:
        """Should we setup and use Sentry and/or Google Analytics?"""
        state_file = Options.nxdrive_home / "metrics.state"
        if state_file.is_file():
            lines = state_file.read_text(encoding="utf-8").splitlines()
            Options.use_sentry = "sentry" in lines
            Options.use_analytics = "analytics" in lines
            self.preferences_metrics_chosen = True

    @if_frozen
    def _handle_os(self) -> None:
        """
        Handle primary OS features.

        Note: Before Nuxeo Drive 4.5.0, the auto start option was set here by default.
              This is no more the case because we changed how such feature is handled
              and we would enabled it every time the app is started on macOS. So we let
              the feature as-is and if one wants to enable it, just click the switch
              button in the settings window.
              Windows is another beast, the feature is enabled by default from the
              installer at the first installation on the machine.
        """
        self.osi.register_protocol_handlers()

    def _get_db(self) -> Path:
        return self.home / "manager.db"

    def _create_dao(self) -> None:
        self.dao = ManagerDAO(self._get_db())

    def create_tracker(self) -> Tracker:
        """Create the Google Analytics tracker."""

        tracker = Tracker(self)

        # Start the tracker when we launch
        self.started.connect(tracker.thread.start)

        # Connect Direct Transfer metrics
        self.directTransferStats.connect(tracker.send_direct_transfer)

        return tracker

    def _create_server_config_updater(self) -> ServerOptionsUpdater:
        worker = ServerOptionsUpdater(self)

        # Start when the manager starts
        self.started.connect(worker.thread.start)

        # Start engines when the configuration has been retrieved
        worker.firstRunCompleted.connect(self.start_engines)

        return worker

    def _create_autolock_service(self) -> ProcessAutoLockerWorker:
        worker = ProcessAutoLockerWorker(30, self, self.direct_edit_folder)

        # Start only when the configuration has been retrieved
        self.server_config_updater.firstRunCompleted.connect(worker.thread.start)

        return worker

    def _create_direct_edit(self) -> "DirectEdit":
        worker = DirectEdit(self, self.direct_edit_folder)
        self.autolock_service.direct_edit = worker

        # Start only when the configuration has been retrieved
        self.server_config_updater.firstRunCompleted.connect(worker.thread.start)

        # Connect to the Tracker metrics
        worker.openDocument.connect(self.tracker.send_directedit_open)
        worker.editDocument.connect(self.tracker.send_directedit_edit)

        return worker

    def _create_updater(self) -> "Updater":
        worker = updater(self)
        self.prompted_wrong_channel = False

        if os.getenv("FORCE_USE_LATEST_VERSION", "0") == "1":
            # Special case to test the auto-updater without the need for an account
            # (else the auto-update would never happen as there is no account and so no server config)
            self.started.connect(worker.thread.start)
        else:
            # Start only when the server config has been fetched
            self.server_config_updater.firstRunCompleted.connect(worker.thread.start)

        # Trigger a new auto-update check when the server config has been fetched
        self.server_config_updater.firstRunCompleted.connect(worker.refresh_status)

        return worker

    def _create_db_backup_worker(self) -> None:
        self.db_backup_worker = DatabaseBackupWorker(self)
        if self.db_backup_worker:
            self.started.connect(self.db_backup_worker.thread.start)

    @if_frozen
    def _create_extension_listener(self) -> None:
        self._extension_listener = self.osi.get_extension_listener()
        if not self._extension_listener:
            return
        self._extension_listener.listening.connect(self.osi.init)
        self.started.connect(self._extension_listener.start_listening)
        self.stopped.connect(self._extension_listener.close)

    def resume(self) -> None:
        if not self.is_paused:
            return
        self.is_paused = False
        for engine in self.engines.copy().values():
            engine.resume()
        self.resumed.emit()

    def suspend(self) -> None:
        if self.is_paused:
            return
        self.is_paused = True
        for engine in self.engines.copy().values():
            engine.suspend()
        self.suspended.emit()

    def stop(self) -> None:
        # Make a backup in case something happens
        self.dao.save_backup()

        for engine in self.engines.copy().values():
            if engine.is_started():
                engine.stop()
        self.osi.cleanup()
        self.dispose_db()
        self.stopped.emit()

    def start_engines(self) -> None:
        """Start all engines."""
        for engine in self.engines.copy().values():
            if self.is_paused:
                continue

            try:
                engine.start()
            except MissingXattrSupport as exc:
                log.warning(f"Could not start {engine}: {exc}")
            except Exception:
                log.exception(f"Could not start {engine}")

    def start(self) -> None:
        self._started = True

        if not self.server_config_updater.first_run:
            self.start_engines()

        # Check only if manager is started
        self._handle_os()
        self.started.emit()

    def load(self) -> None:
        self._engine_definitions = self._engine_definitions or self.dao.get_engines()
        self.engines = {}

        for engine in self._engine_definitions.copy():
            if engine.engine not in self._engine_types:
                log.error(f"Cannot find {engine.engine} engine type anymore")
                self._engine_definitions.remove(engine)
                continue
            elif not self._get_engine_db_file(engine.uid).is_file():
                log.warning(f"Cannot find {engine.uid} engine database file anymore")
                self._engine_definitions.remove(engine)
                continue

            try:
                self.engines[engine.uid] = self._engine_types[engine.engine](
                    self, engine
                )
            except EngineInitError as exc:
                log.error(
                    f"Cannot initialize the engine {exc.engine}, it is missing crucial info"
                    f" (like server URL or token). Engine definition is {engine!r}."
                )
                self._engine_definitions.remove(engine)
                continue
            else:
                self.engines[engine.uid].online.connect(self._force_autoupdate)
                self.initEngine.emit(self.engines[engine.uid])

        if self.engines:
            self.tracker.send_metric("account", "count", str(len(self.engines)))

    def _get_engine_db_file(self, uid: str, /) -> Path:
        return self.home / f"ndrive_{uid}.db"

    def _force_autoupdate(self) -> None:
        if self.updater.get_next_poll() > 60 and self.updater.get_last_poll() > 1800:
            self.updater.force_poll()

    @pyqtSlot(str)  # from IconLink.qml
    def open_local_file(self, file_path: str, /, *, select: bool = False) -> None:
        """Launch the local OS program on the given file / folder."""
        file_path = force_decode(file_path)
        log.info(f"Launching editor on {file_path!r}")
        try:
            self.osi.open_local_file(file_path, select=select)
        except OSError as exc:
            if exc.errno in NO_SPACE_ERRORS:
                log.warning("Cannot open local file, disk space needed", exc_info=True)
                raise
            if WINDOWS and exc.winerror == 1155:
                error = NoAssociatedSoftware(Path(file_path))
                log.warning(str(error))
                raise error
            log.exception(f"[OS] Failed to find an editor for {file_path!r}")
        except Exception:
            # Log the exception now, will see later if we need to adapt
            log.exception(f"Failed to find an editor for {file_path!r}")

    @property
    def device_id(self) -> str:
        if not self.__device_id:
            self.__device_id = self.dao.get_config("device_id")
        if not self.__device_id:
            self.__device_id = uuid.uuid1().hex
            self.dao.update_config("device_id", self.__device_id)
        return str(self.__device_id)

    def get_config(self, value: str, /, *, default: Any = None) -> Any:
        return self.dao.get_config(value, default=default)

    def set_config(self, key: str, value: Any, /) -> None:
        """Update a configuration setting.
        The modification may be disallowed so we ensure the correctness before saving change.
        """
        old_value = getattr(Options, key)
        Options.set(key, value, setter="manual", fail_on_error=False)
        new_value = getattr(Options, key)
        if old_value != new_value:
            self.dao.update_config(key, value)

    @pyqtSlot(result=bool)  # from GeneralTab.qml
    def get_direct_edit_auto_lock(self) -> bool:
        # Enabled by default, if app is frozen
        return self.dao.get_bool("direct_edit_auto_lock", default=Options.is_frozen)

    @pyqtSlot(bool)  # from GeneralTab.qml
    def set_direct_edit_auto_lock(self, value: bool, /) -> None:
        log.debug(f"Changed parameter 'direct_edit_auto_lock' to {value}")
        self.dao.store_bool("direct_edit_auto_lock", value)

    @pyqtSlot(str, result=bool)  # from FeaturesTab.qml
    def get_feature_state(self, name: str, /) -> bool:
        """Get the value of the Feature attribute."""
        return bool(getattr(Feature, name))

    @pyqtSlot(str, bool)  # from FeaturesTab.qml
    def set_feature_state(
        self, name: str, value: bool, /, *, setter: str = "manual"
    ) -> None:
        """Set the value of the feature in Options and save changes in config file."""
        Options.set(f"feature_{name}", value, setter=setter)
        new_config = {
            f"feature_{key}": value for key, value in Feature.__dict__.items()
        }
        save_config(new_config)
        self.featureUpdate.emit(name, value)

    @pyqtSlot(result=bool)  # from GeneralTab.qml
    def get_auto_update(self) -> bool:
        # Enabled by default, if app is frozen
        value: bool = Options.update_check_delay > 0
        value &= self.dao.get_bool("auto_update", default=Options.is_frozen)
        return value

    @pyqtSlot(bool)  # from GeneralTab.qml
    def set_auto_update(self, value: bool, /) -> None:
        log.debug(f"Changed parameter 'auto_update' to {value}")
        self.dao.store_bool("auto_update", value)

    def generate_report(self, *, path: Path = None) -> Path:
        from .report import Report

        log.info(f"Features: {Feature}")
        log.info(f"Options: {Options}")
        log.info(f"Manager metrics: {self.get_metrics()!r}")
        for engine in self.engines.copy().values():
            log.info(f"Engine metrics: {engine.get_metrics()!r}")

        report = Report(self, report_path=path)
        report.generate()
        return report.get_path()

    def generate_csv(self, session_id: int, engine: Engine) -> bool:
        """
        Generate a CSV file based on the *session_id* in an async Runner.
        """
        session = engine.dao.get_session(session_id)
        if not session:
            return False

        runner = Runner(self._generate_csv_async, engine, session)
        engine._threadpool.start(runner)
        return True

    def _generate_csv_async(self, engine: Engine, session: Session) -> None:
        from .session_csv import SessionCsv  # Circular import with Manager otherwise

        try:
            session_items = engine.dao.get_session_items(session.uid)
            session_csv = SessionCsv(self, session)
            session_csv.create_tmp()
            engine.dao.sessionUpdated.emit(False)
            log.info(
                f"Generating CSV file from Direct Transfer session {session_csv.output_file}."
            )
            session_csv.store_data(session_items)
        except Exception:
            log.exception("Asynchronous CSV generation error")
            session_csv.output_tmp.unlink(missing_ok=True)
        finally:
            engine.dao.sessionUpdated.emit(True)

    @pyqtSlot(result=bool)  # from GeneralTab.qml
    def get_auto_start(self) -> bool:
        try:
            return self.osi.startup_enabled()
        except OSError:
            log.warning("Cannot get auto-start state", exc_info=True)
            return False

    @pyqtSlot(bool)  # from GeneralTab.qml
    def set_auto_start(self, value: bool, /) -> None:
        """Change the auto start state."""
        log.debug(f"Changed auto start state to {value}")
        try:
            if value:
                self.osi.register_startup()
            else:
                self.osi.unregister_startup()
        except OSError:
            log.warning("Cannot set auto-start state", exc_info=True)

    @pyqtSlot(result=bool)  # from GeneralTab.qml
    def use_light_icons(self) -> bool:
        """Return True is the current icons set is the light one."""
        return self.dao.get_bool("light_icons")

    @pyqtSlot(bool)  # from GeneralTab.qml
    def set_light_icons(self, value: bool, /) -> None:
        self.set_config("light_icons", value)
        self.reloadIconsSet.emit(value)

    @pyqtSlot(result=str)  # from ChannelPopup.qml and Systray.qml
    def get_update_channel(self) -> str:
        return (
            self.dao.get_config("channel", default=Options.channel) or DEFAULT_CHANNEL
        )

    @pyqtSlot(str)  # from ChannelPopup.qml and Systray.qml
    def set_update_channel(self, value: str, /) -> None:
        self.set_config("channel", value)
        self.prompted_wrong_channel = False
        self.updater.refresh_status()

    @pyqtSlot(result=str)  # from LogLevelPopup.qml
    def get_log_level(self) -> str:
        if not Options.is_frozen or Options.is_alpha:
            return DEFAULT_LOG_LEVEL_FILE
        return (
            self.dao.get_config("log_level_file", default=Options.log_level_file)
            or DEFAULT_LOG_LEVEL_FILE
        )

    @pyqtSlot(str)  # from LogLevelPopup.qml
    def set_log_level(self, value: str, /) -> None:
        self.set_config("log_level_file", value)

    def set_proxy(self, proxy: "Proxy") -> str:
        log.debug(f"Trying to change proxy to {proxy}")
        for engine in self.engines.copy().values():
            if not validate_proxy(proxy, engine.server_url):
                return "PROXY_INVALID"
            engine.remote.set_proxy(proxy)

        save_proxy(proxy, self.dao)
        self.proxy = proxy
        log.debug(f"Effective proxy: {proxy!r}")
        return ""

    def get_deletion_behavior(self) -> DelAction:
        return DelAction(Options.deletion_behavior)

    def set_deletion_behavior(self, behavior: DelAction, /) -> None:
        self.set_config("deletion_behavior", behavior.value)

    def get_server_login_type(
        self, server_url: str, /, *, _raise: bool = True
    ) -> Login:
        # Take into account URL parameters
        parts = urlsplit(server_url)
        url = urlunsplit(
            (
                parts.scheme,
                parts.netloc,
                f"{parts.path.rstrip('/')}/{Options.browser_startup_page}",
                parts.query,
                parts.fragment,
            )
        )
        headers = {
            "X-Application-Name": APP_NAME,
            "X-Device-Id": self.device_id,
            "X-Client-Version": self.version,
            "User-Agent": user_agent(),
        }

        log.info(f"Proxy configuration for startup page connection: {self.proxy}")
        try:
            with requests.get(
                url,
                headers=headers,
                proxies=self.proxy.settings(url=url),
                timeout=STARTUP_PAGE_CONNECTION_TIMEOUT,
                verify=Options.ca_bundle or not Options.ssl_no_verify,
                cert=client_certificate(),
            ) as resp:
                status = resp.status_code
        except Exception as e:
            log.warning(
                f"Error while trying to connect to {APP_NAME} "
                f"startup page with URL {url}",
                exc_info=True,
            )
            if _raise:
                raise StartupPageConnectionError() from e
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
        /,
        *,
        password: str = "",
        token: Token = None,
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
            DEFAULT_SERVER_TYPE, local_folder, name, binder, starts=start_engine
        )

    def _get_engine_name(self, server_url: str, /) -> str:
        urlp = urlparse(server_url)
        return urlp.hostname or ""

    def check_local_folder_available(self, path: Path, /) -> bool:
        if not self._engine_definitions:
            return True
        for engine in self._engine_definitions:
            other = engine.local_folder
            if path == other or path in other.parents or other in path.parents:
                return False
        return True

    def update_engine_path(self, uid: str, path: Path, /) -> None:
        # Don't update the engine by itself,
        # should be only used by engine.update_engine_path
        if uid in self.engines:
            # Unwatch old folder
            self.osi.unwatch_folder(self.engines[uid].local_folder)
            self.engines[uid].local_folder = path
        # Watch new folder
        self.osi.watch_folder(path)
        self.dao.update_engine_path(uid, path)

    def bind_engine(
        self,
        engine_type: str,
        local_folder: Path,
        name: Optional[str],
        binder: Binder,
        /,
        *,
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
            local_folder = get_default_local_folder()
        elif local_folder == self.home or not self.check_local_folder_available(
            local_folder
        ):
            # Prevent from binding in the configuration folder
            raise FolderAlreadyUsed()
        if not self.engines:
            self.load()

        uid = uuid.uuid1().hex

        try:
            engine_def = self.dao.add_engine(engine_type, local_folder, uid, name)
        except sqlite3.IntegrityError:
            # UNIQUE constraint failed: Engines.local_folder
            # This happens in that scenario:
            #   - Add a new account using the local folder "/home/USER/drive".
            #   - Delete the Engine database.
            #   - Add a new account using the same local folder "/home/USER/drive".
            #
            # FolderAlreadyUsed is raised instead of deleting the old database entry because
            # it is convenient to be able to restore the DB file later for whatever reason.
            # And there is no popup to ask the user for its deletion for the same purpose.
            # Note that the use case is rare enough to be handled that way. In fact, in years,
            # that happened only while testing the application a lot.
            raise FolderAlreadyUsed()

        cls: Type[Engine] = self._engine_types[engine_type]
        try:
            self.engines[uid] = cls(self, engine_def, binder=binder)
        except Exception as exc:
            skipped_errors = (
                AddonForbiddenError,
                AddonNotInstalledError,
                MissingXattrSupport,
                RootAlreadyBindWithDifferentAccount,
            )
            if not isinstance(exc, skipped_errors):
                log.exception("Engine error")

            self.engines.pop(uid, None)
            self.dao.delete_engine(uid)
            self.remove_engine_dbs(uid)
            raise exc

        self._engine_definitions.append(engine_def)

        # As new engine was just bound, refresh application update status
        self.updater.refresh_status()

        if starts:
            self.engines[uid].start()

        # Watch folder in the file explorer
        self.osi.watch_folder(local_folder)

        self.newEngine.emit(self.engines[uid])

        # NXDRIVE-978: Update the current state to reflect the change in
        # the systray menu
        self.is_paused = False

        # Backup the database
        if self.db_backup_worker:
            self.db_backup_worker.force_poll()

        return self.engines[uid]

    def unbind_engine(self, uid: str, /, *, purge: bool = False) -> None:
        """Remove an Engine. If *purge* is True, then local files will be deleted."""

        log.debug(f"Unbinding Engine {uid}, local files purgation is {purge}")

        if not self.engines:
            self.load()

        engine = self.engines.pop(uid, None)
        if not engine:
            return

        engine.unbind()
        self.dao.delete_engine(uid)

        # On-demand local files removal
        if purge:
            engine.local.unset_readonly(engine.local_folder)
            try:
                shutil.rmtree(engine.local_folder)
            except FileNotFoundError:
                pass
            except OSError:
                log.warning("Cannot purge local files", exc_info=True)

        # Refresh the engines definition
        self.dropEngine.emit(uid)
        self._engine_definitions = self.dao.get_engines()

        # Backup the database
        if self.db_backup_worker:
            self.db_backup_worker.force_poll()

    def get_engine_db(self, uid: str) -> Path:
        """Return the full path to the Engine database file.
        Note: It is defined here to be able to delete databases on failed account addition.
        """
        return self.home / f"ndrive_{uid}.db"

    def remove_engine_dbs(self, uid: str) -> None:
        """Remove all databases files related to the Engine *uid*."""
        main_db = self.get_engine_db(uid)
        for file in (
            main_db,
            main_db.with_suffix(".db-shm"),
            main_db.with_suffix(".db-wal"),
        ):
            try:
                file.unlink(missing_ok=True)
            except OSError:
                log.warning("Database removal error", exc_info=True)

    def dispose_db(self) -> None:
        if self.dao:
            self.dao.dispose()

    @property
    def version(self) -> str:
        return __version__

    def is_started(self) -> bool:  # TODO: Remove
        return self._started

    def is_syncing(self) -> bool:
        """Return True if any engine is still syncing stuff."""
        return any(engine.is_syncing() for engine in self.engines.values())

    def get_root_id(self, path: Path, /) -> str:
        ref = LocalClient.get_path_remote_id(path, name="ndriveroot")
        if not ref:
            parent = path.parent
            # We can't find in any parent
            if parent == path or parent is None:
                return ""
            return self.get_root_id(parent)
        return ref

    def ctx_access_online(self, path: Path, /) -> None:
        """Open the user's browser to a remote document."""

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

    def ctx_copy_share_link(self, path: Path, /) -> str:
        """Copy the document's share-link to the clipboard."""

        url = self.get_metadata_infos(path)
        self.osi.cb_set(url)
        log.info(f"Copied {url!r}")
        return url

    def ctx_edit_metadata(self, path: Path, /) -> None:
        """Open the user's browser to a remote document's metadata."""

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

    def get_metadata_infos(self, path: Path, /, *, edit: bool = False) -> str:
        remote_ref = LocalClient.get_path_remote_id(path)
        if not remote_ref:
            raise ValueError(f"Could not find file {path!r} as {APP_NAME} managed")

        root_id = self.get_root_id(path)
        root_values = root_id.split("|") if root_id else []

        try:
            engine = self.engines[root_values[3]]
        except (KeyError, IndexError):
            raise ValueError(f"Unknown engine for {path!r} ({root_values=})")

        return engine.get_metadata_url(remote_ref, edit=edit)

    def send_sync_status(self, path: Path, /) -> None:
        for engine in self.engines.copy().values():
            # Only send status if we picked the right
            # engine and if we're not targeting the root
            if engine.local_folder not in path.parents:
                continue

            r_path = path.relative_to(engine.local_folder)
            dao = engine.dao
            states = dao.get_local_children(r_path)
            self.osi.send_content_sync_status(states, path)
            return

    def wait_for_server_config(self, *, timeout: int = 10) -> bool:
        """Wait for the server's config to be fetched (*timeout* seconds maximum).
        Return True if the server's config has been fetched with success.

        Note: calling that method will temporary block the UI for *timeout* second at worst.
        """

        if not self.server_config_updater.first_run:
            return True

        # Trigger a poll in case the app is already running and the next poll is not planned for long
        self.server_config_updater.force_poll()

        # Wait for *timeout* seconds for a positive response
        for _ in range(timeout):
            if not self.server_config_updater.first_run:
                return True
            sleep(1)

        return False

    @if_frozen
    def _write_version_file(self) -> None:
        """Save the current version in a VERSION file inside the home directory.
        This is for information purpose and used by the auto-update checker script."""
        file = Options.nxdrive_home / "VERSION"
        try:
            file.write_text(f"{self.version}\n")
        except FileNotFoundError:
            # Likely testing a feature and the parent folder does not exist
            log.warning(
                f"Cannot save the current version ({self.version}) to {file!r}",
                exc_info=True,
            )
        else:
            log.debug(f"Saved the current version ({self.version}) into {file!r}")
