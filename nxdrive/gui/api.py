import json
from dataclasses import asdict
from logging import getLogger
from os import getenv
from os.path import abspath
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit

import requests
from nuxeo.exceptions import HTTPError, OAuth2Error, Unauthorized
from urllib3.exceptions import LocationParseError

from ..auth import OAuthentication, Token, get_auth
from ..client.proxy import get_proxy
from ..constants import (
    APP_NAME,
    CONNECTION_ERROR,
    DEFAULT_SERVER_TYPE,
    DT_MONITORING_MAX_ITEMS,
    TransferStatus,
)
from ..dao.engine import EngineDAO
from ..exceptions import (
    AddonForbiddenError,
    AddonNotInstalledError,
    EncryptedSSLCertificateKey,
    FolderAlreadyUsed,
    InvalidSSLCertificate,
    MissingClientSSLCertificate,
    MissingXattrSupport,
    NotFound,
    RootAlreadyBindWithDifferentAccount,
    StartupPageConnectionError,
)
from ..feature import Feature
from ..notification import Notification
from ..objects import Binder, DocPair
from ..options import Options
from ..qt import constants as qt
from ..qt.imports import QObject, QUrl, pyqtSignal, pyqtSlot
from ..translator import Translator
from ..updater.constants import Login
from ..utils import (
    disk_space,
    force_decode,
    get_date_from_sqlite,
    get_default_local_folder,
    normalized_path,
    sizeof_fmt,
    test_url,
)

if TYPE_CHECKING:
    from .application import Application  # noqa

__all__ = ("QMLDriveApi",)

log = getLogger(__name__)


class QMLDriveApi(QObject):

    openAuthenticationDialog = pyqtSignal(str, object)
    setMessage = pyqtSignal(str, str)

    def __init__(self, application: "Application", /) -> None:
        super().__init__()
        self._manager = application.manager
        self.application = application
        self.callback_params: Dict[str, str] = {}

        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(
            self.application.open_authentication_dialog
        )

    def _json_default(self, obj: Any, /) -> Any:
        export = getattr(obj, "export", None)
        if callable(export):
            return export()

        log.error(f"Object {obj} has no export() method.")
        return obj

    def _json(self, obj: Any) -> Any:
        # Avoid to fail on non serializable object
        return json.dumps(obj, default=self._json_default)

    def _export_formatted_state(
        self, uid: str, /, *, state: DocPair = None
    ) -> Dict[str, Any]:
        if not state:
            return {}

        engine = self._manager.engines.get(uid)
        if not engine:
            return {}

        result = state.export()
        result["last_contributor"] = (
            ""
            if state.last_remote_modifier is None
            else engine.get_user_full_name(state.last_remote_modifier, cache_only=True)
        )
        date_time = get_date_from_sqlite(state.last_remote_updated)
        result["last_remote_update"] = (
            Translator.format_datetime(date_time) if date_time else ""
        )
        date_time = get_date_from_sqlite(state.last_local_updated)
        result["last_local_update"] = (
            Translator.format_datetime(date_time) if date_time else ""
        )
        result["remote_can_update"] = state.remote_can_update
        result["remote_can_rename"] = state.remote_can_rename
        result["last_error_details"] = state.last_error_details or ""
        return result

    @pyqtSlot(str, int, result=list)
    def get_last_files(self, uid: str, number: int, /) -> List[Dict[str, Any]]:
        """Return the last files transferred (see EngineDAO)."""
        engine = self._manager.engines.get(uid)
        if not engine:
            return []
        return [s.export() for s in engine.dao.get_last_files(number)]

    @pyqtSlot(str, result=int)
    def get_last_files_count(self, uid: str, /) -> int:
        """Return the count of the last files transferred (see EngineDAO)."""
        count = 0
        engine = self._manager.engines.get(uid)
        if engine:
            count = engine.dao.get_last_files_count(duration=60)
        return count

    @pyqtSlot(QUrl, result=str)
    def to_local_file(self, url: QUrl, /) -> str:
        """
        Convert the given QUrl to its local path equivalent.

            >>> to_local_file("file:///home/username/nuxeo")
            /home/username/nuxeo
            >>> to_local_file("file:///C:/Users/username/nuxeo")
            C:\\Users\\username\\nuxeo

        """
        return abspath(url.toLocalFile())

    @pyqtSlot(str)
    def trigger_notification(self, uid: str, /) -> None:
        self.application.hide_systray()
        self._manager.notification_service.trigger_notification(uid)

    @pyqtSlot(str)
    def discard_notification(self, uid: str, /) -> None:
        self._manager.notification_service.discard_notification(uid)

    def _export_notifications(
        self, notifs: Dict[str, Notification], /
    ) -> List[Dict[str, Any]]:
        return [notif.export() for notif in notifs.values()]

    @pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid: str, /) -> str:
        center = self._manager.notification_service
        notif = self._export_notifications(center.get_notifications(engine=engine_uid))
        return self._json(notif)

    @pyqtSlot(result=str)
    def get_update_status(self) -> str:
        """Return the status of the update."""
        return self._manager.updater.status

    @pyqtSlot(result=str)
    def get_update_version(self) -> str:
        """Return the version of the update, if one is available."""
        return self._manager.updater.version

    @pyqtSlot(str)
    def app_update(self, version: str, /) -> None:
        """Start the update to the specified version."""
        self._manager.updater.update(version)

    def get_transfers(self, dao: EngineDAO, /) -> List[Dict[str, Any]]:
        limit = 5  # 10 files are displayed in the systray, so take 5 of each kind
        result: List[Dict[str, Any]] = []

        for count, download in enumerate(dao.get_downloads()):
            if count >= limit:
                break
            result.append(asdict(download))

        for count, upload in enumerate(dao.get_uploads()):
            if count >= limit:
                break
            result.append(asdict(upload))

        return result

    def get_direct_transfer_items(self, dao: EngineDAO, /) -> List[Dict[str, Any]]:
        """Fetch at most *DT_MONITORING_MAX_ITEMS* transfers from the database."""
        return dao.get_dt_uploads_raw(limit=DT_MONITORING_MAX_ITEMS, chunked=True)

    def get_active_sessions_items(self, dao: EngineDAO, /) -> List[Dict[str, Any]]:
        """Fetch the list of active sessions from the database."""
        return dao.get_active_sessions_raw()

    def get_completed_sessions_items(self, dao: EngineDAO, /) -> List[Dict[str, Any]]:
        """Fetch the list of completed sessions from the database."""
        return dao.get_completed_sessions_raw(limit=20)

    @pyqtSlot(str, result=int)
    def get_active_sessions_count(self, uid: str, /) -> int:
        """Return the count of active sessions items."""
        engine = self._manager.engines.get(uid)
        if engine:
            return engine.dao.get_count(
                f"status IN ({TransferStatus.ONGOING.value}, {TransferStatus.PAUSED.value})",
                table="Sessions",
            )
        return 0

    @pyqtSlot(str, result=int)
    def get_completed_sessions_count(self, uid: str, /) -> int:
        """Return the count of completed sessions items."""
        engine = self._manager.engines.get(uid)
        if engine:
            return engine.dao.get_count(
                f"status IN ({TransferStatus.CANCELLED.value}, {TransferStatus.DONE.value})",
                table="Sessions",
            )
        return 0

    @pyqtSlot(str, str, int, float, bool)
    def pause_transfer(
        self,
        nature: str,
        engine_uid: str,
        transfer_uid: int,
        progress: float,
        /,
        *,
        is_direct_transfer: bool = False,
    ) -> None:
        """Pause a given transfer. *nature* is either downloads or upload."""
        log.info(f"Pausing {nature} {transfer_uid} for engine {engine_uid!r}")
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return
        engine.dao.pause_transfer(
            nature, transfer_uid, progress, is_direct_transfer=is_direct_transfer
        )

    @pyqtSlot(str, str, int, bool)
    def resume_transfer(
        self,
        nature: str,
        engine_uid: str,
        uid: int,
        /,
        *,
        is_direct_transfer: bool = False,
    ) -> None:
        """Resume a given transfer. *nature* is either downloads or upload."""
        log.info(f"Resume {nature} {uid} for engine {engine_uid!r}")
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return
        engine.resume_transfer(nature, uid, is_direct_transfer=is_direct_transfer)

    @pyqtSlot(str, int)
    def resume_session(self, engine_uid: str, uid: int, /) -> None:
        """Resume a given session and it's transfers."""
        log.info(f"Resume session {uid} for engine {engine_uid!r}")
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return
        engine.resume_session(uid)

    @pyqtSlot(str, int)
    def pause_session(self, engine_uid: str, uid: int, /) -> None:
        """Pause a given session and it's transfers."""
        log.info(f"Pausing session {uid} for engine {engine_uid!r}")
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return
        engine.dao.pause_session(uid)

    def cancel_session(self, engine_uid: str, uid: int, /) -> None:
        """Cancel a given session and it's transfers."""
        log.info(f"Cancelling session {uid} for engine {engine_uid!r}")
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return
        engine.cancel_session(uid)

    @pyqtSlot(str, str)
    def show_metadata(self, uid: str, ref: str, /) -> None:
        self.application.hide_systray()
        engine = self._manager.engines.get(uid)
        if engine:
            path = engine.local.abspath(Path(ref))
            self.application.show_metadata(path)

    @pyqtSlot(str, result=list)
    def get_unsynchronizeds(self, uid: str, /) -> List[Dict[str, Any]]:
        result = []
        engine = self._manager.engines.get(uid)
        if engine:
            for conflict in engine.dao.get_unsynchronizeds():
                result.append(self._export_formatted_state(uid, state=conflict))
        return result

    @pyqtSlot(str, result=list)
    def get_conflicts(self, uid: str, /) -> List[Dict[str, Any]]:
        result = []
        engine = self._manager.engines.get(uid)
        if engine:
            for conflict in engine.get_conflicts():
                result.append(self._export_formatted_state(uid, state=conflict))
        return result

    @pyqtSlot(str, result=list)
    def get_errors(self, uid: str, /) -> List[Dict[str, Any]]:
        result = []
        engine = self._manager.engines.get(uid)
        if engine:
            for error in engine.dao.get_errors():
                result.append(self._export_formatted_state(uid, state=error))
        return result

    @pyqtSlot(result=list)
    def get_features_list(self) -> List[List[str]]:
        """Return the list of declared features with their value, title and translation key."""
        result = []
        for feature in vars(Feature).keys():
            title = feature.replace("_", " ").title()
            translation_key = f"FEATURE_{feature.upper()}"
            result.append([title, feature, translation_key])
        return result

    @pyqtSlot(result=str)
    def generate_report(self) -> str:
        try:
            return str(self._manager.generate_report())
        except Exception as e:
            log.exception("Report error")
            return "[ERROR] " + str(e)

    @pyqtSlot(str, str, result=bool)
    def generate_csv(self, session_id: str, engine_uid: str) -> bool:
        """
        Generate a CSV file from the *session_id*.
        """
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return False
        try:
            return self._manager.generate_csv(int(session_id), engine)
        except Exception:
            log.exception("CSV export error.")
            return False

    @pyqtSlot(str)
    def open_direct_transfer(self, uid: str, /) -> None:
        self.application.hide_systray()

        engine = self._manager.engines.get(uid)
        if not engine:
            return

        self.application.refresh_direct_transfer_items(engine.dao)
        self.application.refresh_active_sessions_items(engine.dao)
        self.application.refresh_completed_sessions_items(engine.dao)
        self.application.show_direct_transfer_window(engine.uid)

    @pyqtSlot(str)
    def open_server_folders(self, uid: str, /) -> None:
        """Hide the systray and show the server folders dialog."""
        self.application.hide_systray()
        engine = self._manager.engines.get(uid)
        if not engine:
            return

        self.application.show_server_folders(engine, None)

    @pyqtSlot(str, result=str)
    def get_hostname_from_url(self, url: str, /) -> str:
        urlp = urlparse(url)
        return urlp.hostname or url

    @pyqtSlot(str)
    def open_remote_server(self, uid: str, /) -> None:
        self.application.hide_systray()
        engine = self._manager.engines.get(uid)
        if engine:
            engine.open_remote()

    @pyqtSlot(str)
    def open_in_explorer(self, path: str, /) -> None:
        """
        Open the file's folder and select it.
        """
        self._manager.open_local_file(path, select=True)

    @pyqtSlot(str, str)
    def open_local(self, uid: str, path: str, /) -> None:
        self.application.hide_systray()
        log.debug(f"Opening local file {path!r}")
        filepath = Path(force_decode(path).lstrip("/"))
        if not uid:
            self._manager.open_local_file(filepath)
        else:
            engine = self._manager.engines.get(uid)
            if engine:
                filepath = engine.local.abspath(filepath)
                self._manager.open_local_file(filepath)

    @pyqtSlot()
    def open_help(self) -> None:
        self.application.hide_systray()
        self._manager.open_help()

    @pyqtSlot(str, int)
    def open_document(self, engine_uid: str, doc_pair_id: int, /) -> None:
        """Open the local or remote document depending on the pair state"""
        engine = self._manager.engines.get(engine_uid)
        if not engine:
            return

        doc_pair = engine.dao.get_state_from_id(doc_pair_id)
        if not doc_pair:
            return
        if (
            doc_pair.pair_state == "error"
            and doc_pair.remote_ref
            and doc_pair.remote_name
        ):
            self.open_remote(engine_uid, doc_pair.remote_ref, doc_pair.remote_name)
        else:
            self.open_local(engine_uid, str(doc_pair.local_parent_path))

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid: str, /) -> None:
        self.application.hide_systray()
        engine = self._manager.engines.get(uid)
        if engine:
            self.application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def show_settings(self, section: str, /) -> None:
        self.application.hide_systray()
        log.info(f"Show settings on section {section}")
        self.application.show_settings(section)

    @pyqtSlot()
    def quit(self) -> None:
        try:
            self.application.quit()
        except Exception:
            log.exception("Application exit error")

    @pyqtSlot(result=str)
    def get_version(self) -> str:
        return self._manager.version

    @pyqtSlot(result=str)
    def get_update_url(self) -> str:
        return Options.update_site_url

    @pyqtSlot(str)
    def web_update_token(self, uid: str, /) -> None:
        try:
            engine = self._manager.engines.get(uid)
            if not engine:
                self.setMessage.emit("CONNECTION_UNKNOWN", "error")
                return
            params = urlencode({"updateToken": True})

            url = engine.server_url
            login_type = self._manager.get_server_login_type(url)
            if login_type is Login.OLD:
                # We might have to downgrade because the
                # browser login is not available.
                self._manager.updater.force_downgrade()
                return

            # The good authentication class is chosen following the type of the token
            crafted_token: Token = (
                {} if isinstance(engine.remote.auth, OAuthentication) else ""
            )
            auth = get_auth(
                url,
                crafted_token,
                dao=self._manager.dao,
                device_id=self._manager.device_id,
            )
            url = auth.connect_url()
            if Options.is_frozen and crafted_token == "":  # Only for Nuxeo token
                url = f"{url}&{params}"
            callback_params = {"engine": uid, "server_url": engine.server_url}
            log.info(f"Opening login window for token update with URL {url}")
            self.application.open_authentication_dialog(url, callback_params)
        except Exception:
            log.exception(
                "Unexpected error while trying to open web"
                " authentication window for token update"
            )
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")

    def _get_ssl_error(self, server_url: str, /) -> str:
        """Handle invalid SSL certificates for the server URL."""
        try:
            return test_url(server_url, proxy=self._manager.proxy)
        except InvalidSSLCertificate as exc:
            log.warning(exc)
            parts = urlsplit(server_url)
            hostname = parts.netloc or parts.path
            if self.application.accept_unofficial_ssl_cert(hostname):
                Options.ca_bundle = None
                Options.ssl_no_verify = True
                return self._get_ssl_error(server_url)
        except MissingClientSSLCertificate as exc:
            log.warning(exc)
            return "MISSING_CLIENT_SSL"
        except EncryptedSSLCertificateKey as exc:
            log.warning(exc)
            return "ENCRYPTED_CLIENT_SSL_KEY"
        return "CONNECTION_ERROR"

    # Settings section

    @pyqtSlot(result=str)
    def default_local_folder(self) -> str:
        return str(get_default_local_folder())

    @pyqtSlot(result=str)
    def default_server_url_value(self) -> str:
        """Make daily job better for our developers :)"""
        return getenv("NXDRIVE_TEST_NUXEO_URL", "")

    @pyqtSlot(str, str, int, result=list)
    def get_disk_space_info_to_width(
        self, uid: str, path: str, width: int, /
    ) -> List[float]:
        """Return a list:
        - Size of free space converted to percentage of the width.
        - Size of space used by other applications converted to percentage of the width.
        - Global size of synchronized files converted to percentage of the width.
        """
        engine = self._manager.engines.get(uid)

        synced = engine.dao.get_global_size() if engine else 0
        used, free = disk_space(path)
        used_without_sync = used - synced
        total = used + free
        result = self._balance_percents(
            {
                "free": free * width / total,
                "used_without_sync": used_without_sync * width / total,
                "synced": synced * width / total,
            }
        )
        return [result["free"], result["used_without_sync"], result["synced"]]

    def _balance_percents(self, result: Dict[str, float], /) -> Dict[str, float]:
        """Return an altered version of the dict in which no value is under a minimum threshold."""

        result = {k: v for k, v in sorted(result.items(), key=lambda item: item[1])}
        keys = list(result)
        min_threshold = 10
        data = 0.0

        key = keys[0]
        if result[key] < min_threshold:
            # Setting key value to min_threshold and saving difference to data
            data += min_threshold - result[key]
            result[key] = min_threshold

        key = keys[1]
        if result[key] - (data / 2) < min_threshold:
            # If we remove half of data from key value then the value will go under min_threshold
            if result[key] < min_threshold:
                # Key value is already under min_threshold so we set it to min_threshold and add difference to data
                data += min_threshold - result[key]
                result[key] = min_threshold
            else:
                # We calculate the difference between current key value and min_threshold
                # Then set key value to min_threshold and subtracts difference from data
                minus = (min_threshold - result[key]) * -1
                data -= minus
                result[key] -= minus
        else:
            # Remove half of the saved data from the key value
            data /= 2
            result[key] -= data

        key = keys[2]
        # Remove the last of data from key value
        result[key] -= data

        return result

    @pyqtSlot(str, result=str)
    def get_drive_disk_space(self, uid: str, /) -> str:
        """Fetch the global size of synchronized files and return a formatted version."""
        engine = self._manager.engines.get(uid)
        synced = engine.dao.get_global_size() if engine else 0
        return sizeof_fmt(synced, suffix=Translator.get("BYTE_ABBREV"))

    @pyqtSlot(str, result=str)
    def get_free_disk_space(self, path: str, /) -> str:
        """Fetch the size of free space and return a formatted version."""
        _, free = disk_space(path)
        return sizeof_fmt(free, suffix=Translator.get("BYTE_ABBREV"))

    @pyqtSlot(str, str, result=str)
    def get_used_space_without_synced(self, uid: str, path: str, /) -> str:
        """Fetch the size of space used by other applications and return a formatted version."""
        engine = self._manager.engines.get(uid)
        synced = engine.dao.get_global_size() if engine else 0
        used, _ = disk_space(path)
        return sizeof_fmt(used - synced, suffix=Translator.get("BYTE_ABBREV"))

    @pyqtSlot(str, bool)
    def unbind_server(self, uid: str, purge: bool, /) -> None:
        self._manager.unbind_engine(uid, purge=purge)

    @pyqtSlot(str)
    def filters_dialog(self, uid: str, /) -> None:
        engine = self._manager.engines.get(uid)
        if engine:
            self.application.show_filters(engine)

    def _bind_server(
        self,
        local_folder: Path,
        url: str,
        username: str,
        password: str,
        name: Optional[str],
        /,
        *,
        token: Token = None,
        check_fs: bool = True,
    ) -> None:
        # Remove any parameters from the original URL
        parts = urlsplit(url)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))

        name = name or None
        binder = Binder(
            username=username,
            password=password,
            token=token,
            no_check=False,
            no_fscheck=not check_fs,
            url=url,
        )
        log.info(f"Binder is {binder.url}/{binder.username}")

        # We _don't_ want the Engine to be started right now when the sync is enabled
        # to let the user choose what documents to sync (cf NXDRIVE-1069).
        # But we _do_ want to start it when the sync is disabled. Not doing that
        # leads to the impossibility to use Direct Transfer right after the account
        # addition (cf NXDRIVE-2643).
        starts = not Feature.synchronization
        engine = self._manager.bind_engine(
            DEFAULT_SERVER_TYPE, local_folder, name, binder, starts=starts
        )

        # Flag to close the settings window when the filters dialog is closed
        self.application.close_settings_too = True

        # Display the filters window to let the user choose what to sync
        if Feature.synchronization:
            self.filters_dialog(engine.uid)
        self.setMessage.emit("CONNECTION_SUCCESS", "success")

    @pyqtSlot(str, str, str, str, str)
    def bind_server(
        self,
        local_folder: str,
        server_url: str,
        username: str,
        /,
        *,
        password: str = "",
        name: str = None,
        token: Token = None,
        check_fs: bool = True,
    ) -> None:
        # Arise the settings window to let the user know the error
        self.application._show_window(self.application.settings_window)

        if not server_url:
            self.setMessage.emit("CONNECTION_ERROR", "error")
            return

        try:
            return self._bind_server(
                normalized_path(local_folder),
                server_url,
                username,
                password,
                name,
                token=token,
                check_fs=check_fs,
            )
        except RootAlreadyBindWithDifferentAccount as e:
            log.warning(Translator.get("FOLDER_USED", values=[APP_NAME]))

            # Ask for the user
            msg = self.application.question(
                Translator.get("ROOT_USED_WITH_OTHER_BINDING_HEADER"),
                Translator.get(
                    "ROOT_USED_WITH_OTHER_BINDING", values=[e.username, e.url]
                ),
            )
            msg.addButton(Translator.get("CONTINUE"), qt.AcceptRole)
            cancel = msg.addButton(Translator.get("CANCEL"), qt.RejectRole)
            msg.exec_()
            if msg.clickedButton() == cancel:
                self.setMessage.emit("FOLDER_USED", "error")
                return

            self.bind_server(
                local_folder,
                server_url,
                username,
                password=password,
                name=name,
                token=token,
                check_fs=False,
            )
            return
        except NotFound:
            error = "FOLDER_DOES_NOT_EXISTS"
        except MissingXattrSupport:
            error = "INVALID_LOCAL_FOLDER"
        except AddonForbiddenError:
            error = "ADDON_FORBIDDEN"
        except AddonNotInstalledError:
            error = "ADDON_NOT_INSTALLED"
        except Unauthorized:
            error = "UNAUTHORIZED"
        except FolderAlreadyUsed:
            error = "FOLDER_USED"
        except PermissionError:
            error = "FOLDER_PERMISSION_ERROR"
        except HTTPError:
            error = "CONNECTION_ERROR"
        except CONNECTION_ERROR as e:
            if getattr(e, "errno") == 61:
                error = "CONNECTION_REFUSED"
            else:
                error = "CONNECTION_ERROR"
        except Exception:
            log.warning("Unexpected error", exc_info=True)
            error = "CONNECTION_UNKNOWN"

        log.warning(Translator.get(error))
        self.setMessage.emit(error, "error")

    @pyqtSlot(str, str, bool)
    def web_authentication(
        self, server_url: str, local_folder: str, use_legacy_auth: bool, /
    ) -> None:
        # Handle local folder
        if not self._manager.check_local_folder_available(
            normalized_path(local_folder)
        ):
            self.setMessage.emit("FOLDER_USED", "error")
            return

        # Handle the server URL
        error = ""
        try:
            error = self._get_ssl_error(server_url)
        except (LocationParseError, ValueError, requests.RequestException):
            log.debug(f"Bad URL: {server_url}")
        except Exception:
            log.exception("Unhandled error")
        if error:
            self.setMessage.emit(error, "error")
            return

        # Detect if the server can use the appropriate login webpage
        if use_legacy_auth:
            try:
                login_type = self._manager.get_server_login_type(server_url)
            except StartupPageConnectionError:
                self.setMessage.emit("CONNECTION_ERROR", "error")
                return
            else:
                if login_type is Login.OLD:
                    # Startup page is not available
                    log.info(
                        f"Web authentication not available on server {server_url}, "
                        "falling back on basic authentication"
                    )
                    if Options.is_frozen:
                        # We might have to downgrade because the
                        # browser login is not available.
                        self._manager.updater.force_downgrade()
                        return
                else:
                    # Page should exists, let's open authentication dialog
                    log.info(f"Web authentication is available on server {server_url}")

        # Connect to the authentication page
        try:
            callback_params = {
                "local_folder": local_folder,
                "server_url": server_url,
                "engine_type": urlsplit(server_url).fragment or DEFAULT_SERVER_TYPE,
            }
            # The good authentication class is chosen based on the token type
            crafted_token: Token = "" if use_legacy_auth else {}
            auth = get_auth(
                server_url,
                crafted_token,
                dao=self._manager.dao,
                device_id=self._manager.device_id,
            )
            self.openAuthenticationDialog.emit(auth.connect_url(), callback_params)
        except Exception:
            log.exception(
                "Unexpected error while trying to open web authentication window"
            )
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")

    @pyqtSlot(str, str, result=bool)
    def set_server_ui(self, uid: str, server_ui: str, /) -> bool:
        log.info(f"Setting ui to {server_ui}")
        engine = self._manager.engines.get(uid)
        if not engine:
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")
            return False
        engine.set_ui(server_ui)
        return True

    @pyqtSlot(result=str)
    def get_proxy_settings(self) -> str:
        proxy = self._manager.proxy
        result = {
            "config": getattr(proxy, "category", None),
            "pac_url": getattr(proxy, "pac_url", None),
            "url": getattr(proxy, "url", None),
        }
        return self._json(result)

    @pyqtSlot(str, str, str, result=bool)
    def set_proxy_settings(self, config: str, url: str, pac_url: str, /) -> bool:
        try:
            proxy = get_proxy(config, url=url, pac_url=pac_url)
        except FileNotFoundError:
            self.setMessage.emit("PROXY_NO_PAC_FILE", "error")
            return False

        error = self._manager.set_proxy(proxy)
        if error:
            self.setMessage.emit(error, "error")
            return False

        self.setMessage.emit("PROXY_APPLIED", "success")
        return True

    @pyqtSlot(result=str)
    def get_deletion_behavior(self) -> str:
        return Options.deletion_behavior

    @pyqtSlot(str)
    def set_deletion_behavior(self, behavior: str, /) -> None:
        self._manager.set_config("deletion_behavior", behavior)

    @pyqtSlot(str, result=bool)
    def has_invalid_credentials(self, uid: str, /) -> bool:
        engine = self._manager.engines.get(uid)
        return engine.has_invalid_credentials() if engine else False

    # Authentication section

    @pyqtSlot(dict)
    def continue_oauth2_flow(self, query: Dict[str, str], /) -> None:
        """Handle a OAuth2 flow to create an account."""
        manager = self._manager
        stored_url = manager.get_config("tmp_oauth2_url")
        stored_code_verifier = manager.get_config("tmp_oauth2_code_verifier")
        stored_state = manager.get_config("tmp_oauth2_state")

        # Pre-checks
        error = ""
        if not stored_url:
            error = "OAUTH2_MISSING_URL"
        elif "state" not in query or "code" not in query:
            error = "CONNECTION_REFUSED"
        elif query["state"] != stored_state:
            error = "OAUTH2_STATE_MISMATCH"
        if error:
            self.setMessage.emit(error, "error")
            return

        # Get required data and add the account
        try:
            auth = OAuthentication(stored_url, dao=self._manager.dao)
            token = auth.get_token(
                code_verifier=stored_code_verifier,
                code=query["code"],
                state=query["state"],
            )
        except OAuth2Error:
            log.warning("Unexpected error while trying to get a token", exc_info=True)
            error = "CONNECTION_UNKNOWN"
        else:
            username = auth.get_username()
            if "engine" in self.callback_params:
                error = self.update_token(token, username)
            else:
                error = self.create_account(token, username)
        finally:
            # Clean-up
            manager.dao.delete_config("tmp_oauth2_url")
            manager.dao.delete_config("tmp_oauth2_code_verifier")
            manager.dao.delete_config("tmp_oauth2_state")

            if error:
                self.setMessage.emit(error, "error")

    @pyqtSlot(str, str)
    def handle_token(self, token: str, username: str, /) -> None:
        """Handle a Nuxeo token to create an account."""
        error = ""
        if not token:
            error = "CONNECTION_REFUSED"
        elif "engine" in self.callback_params:
            error = self.update_token(token, username)
        elif "local_folder" in self.callback_params:
            error = self.create_account(token, username)
        else:
            log.warning(
                f"Cannot handle connection token, invalid callback parameters {self.callback_params!r}"
            )
        if error:
            self.setMessage.emit(error, "error")

    def create_account(self, token: Token, username: str, /) -> str:
        error = ""
        try:
            local_folder = self.callback_params["local_folder"]
            server_url = (
                self.callback_params["server_url"]
                + "#"
                + self.callback_params["engine_type"]
            )
            log.info(
                f"Creating new account [{local_folder=}, {server_url=}, {username=}]"
            )

            error = self.bind_server(
                local_folder,
                server_url,
                username,
                token=token,
            )
            log.info(f"Return from bind_server() is {error!r}")
        except Exception:
            log.exception(
                "Unexpected error while trying to create a new account "
                f"[{local_folder=}, {server_url=}, {username=}]"
            )
            error = "CONNECTION_UNKNOWN"
        return error

    def update_token(self, token: Token, username: str, /) -> str:
        error = ""
        engine = self._manager.engines.get(self.callback_params["engine"])
        if not engine:
            return ""
        try:
            log.info(
                "Updating token for account "
                f"[{engine.local_folder}, {engine.server_url},"
                f" {engine.remote_user!r} -> {username!r}]"
            )

            engine.update_token(token, username)
            self.application.set_icon_state("idle")
            self.application.show_settings("Accounts")
            self.setMessage.emit("CONNECTION_SUCCESS", "success")
        except CONNECTION_ERROR as e:
            log.warning("HTTP Error", exc_info=True)
            if getattr(e, "errno") == 61:
                error = "CONNECTION_REFUSED"
            else:
                error = "CONNECTION_ERROR"
        except Exception:
            log.exception(
                "Unexpected error while trying to update token for account "
                f"[{engine.local_folder}, {engine.server_url}, {engine.remote_user}]"
            )
            error = "CONNECTION_UNKNOWN"
        finally:
            return error

    # Systray section

    @pyqtSlot(result=bool)
    def restart_needed(self) -> bool:
        return self._manager.restart_needed

    @pyqtSlot(bool)
    def suspend(self, start: bool, /) -> None:
        if start:
            self._manager.resume()
        else:
            self._manager.suspend()

    @pyqtSlot(result=bool)
    def is_paused(self) -> bool:
        return self._manager.is_paused

    @pyqtSlot(str, result=int)
    def get_syncing_count(self, uid: str, /) -> int:
        count = 0
        engine = self._manager.engines.get(uid)
        if engine:
            count = engine.dao.get_syncing_count()
        return count

    # Conflicts section

    @pyqtSlot(str, int)
    def resolve_with_local(self, uid: str, state_id: int, /) -> None:
        engine = self._manager.engines.get(uid)
        if engine:
            engine.resolve_with_local(state_id)

    @pyqtSlot(str, int)
    def resolve_with_remote(self, uid: str, state_id: int, /) -> None:
        engine = self._manager.engines.get(uid)
        if engine:
            engine.resolve_with_remote(state_id)

    @pyqtSlot(str, int)
    def retry_pair(self, uid: str, state_id: int, /) -> None:
        engine = self._manager.engines.get(uid)
        if engine:
            engine.retry_pair(state_id)

    @pyqtSlot(str, int, str)
    def ignore_pair(self, uid: str, state_id: int, reason: str, /) -> None:
        engine = self._manager.engines.get(uid)
        if engine:
            engine.ignore_pair(state_id, reason)

    @pyqtSlot(str, str, str)
    def open_remote(self, uid: str, remote_ref: str, remote_name: str, /) -> None:
        log.info(f"Should open {remote_name!r} ({remote_ref!r})")
        try:
            engine = self._manager.engines.get(uid)
            if engine:
                engine.open_edit(remote_ref, remote_name)
        except OSError:
            log.exception("Remote open error")

    @pyqtSlot(str, str, str)
    def open_remote_document(
        self, uid: str, remote_ref: str, remote_path: str, /
    ) -> None:
        log.info(f"Should open remote document {remote_path!r} ({remote_ref!r})")
        try:
            engine = self._manager.engines.get(uid)
            if engine:
                url = engine.get_metadata_url(remote_ref)
                engine.open_remote(url=url)
        except OSError:
            log.exception("Remote document cannot be opened")

    @pyqtSlot(str, str, result=str)
    def get_remote_document_url(self, uid: str, remote_ref: str, /) -> str:
        """Return the URL to a remote document based on its reference."""
        engine = self._manager.engines.get(uid)
        return engine.get_metadata_url(remote_ref) if engine else ""
