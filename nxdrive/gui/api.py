# coding: utf-8
import json
from logging import getLogger
from pathlib import Path
from os import getenv
from os.path import abspath
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from urllib.parse import urlencode, urlsplit, urlunsplit

from nuxeo.exceptions import HTTPError, Unauthorized
from PyQt5.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtWidgets import QMessageBox

from ..client.proxy import get_proxy
from ..constants import APP_NAME, CONNECTION_ERROR, TOKEN_PERMISSION
from ..engine.activity import Action, FileAction
from ..engine.engine import Engine
from ..exceptions import (
    FolderAlreadyUsed,
    InvalidDriveException,
    InvalidSSLCertificate,
    NotFound,
    RootAlreadyBindWithDifferentAccount,
    StartupPageConnectionError,
)
from ..notification import Notification
from ..objects import Binder, DocPair
from ..options import Options
from ..translator import Translator
from ..updater.constants import Login
from ..utils import (
    force_decode,
    get_date_from_sqlite,
    get_device,
    get_default_local_folder,
    guess_server_url,
    normalized_path,
)

if TYPE_CHECKING:
    from .application import Application  # noqa

__all__ = ("QMLDriveApi",)

log = getLogger(__name__)


class QMLDriveApi(QObject):

    openAuthenticationDialog = pyqtSignal(str, object)
    setMessage = pyqtSignal(str, str)

    def __init__(self, application: "Application") -> None:
        super().__init__()
        self._manager = application.manager
        self.application = application
        self._callback_params: Dict[str, str] = {}

        # Attributes for the web authentication feedback
        self.openAuthenticationDialog.connect(
            self.application._open_authentication_dialog
        )

    def _json_default(self, obj: Any) -> Any:
        export = getattr(obj, "export", None)
        if callable(export):
            return export()
        else:
            log.error(f"Object {obj} has no export() method.")
            return obj

    def _json(self, obj: Any) -> Any:
        # Avoid to fail on non serializable object
        return json.dumps(obj, default=self._json_default)

    def _export_formatted_state(
        self, uid: str, state: DocPair = None
    ) -> Dict[str, Any]:
        if not state:
            return {}

        engine = self._get_engine(uid)
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

    def _get_engine(self, uid: str) -> Optional[Engine]:
        engines = self._manager.get_engines()
        return engines.get(uid)

    def get_last_files(
        self, uid: str, number: int, direction: str, duration: int = None
    ) -> List[Dict[str, Any]]:
        """ Return the last files transferred (see EngineDAO). """
        engine = self._get_engine(uid)
        result = []
        if engine is not None:
            for state in engine.get_last_files(number, direction, duration):
                result.append(state.export())
        return result

    @pyqtSlot(str, result=int)
    def get_last_files_count(self, uid: str) -> int:
        """ Return the count of the last files transferred (see EngineDAO). """
        count = 0
        engine = self._get_engine(uid)
        if engine:
            count = engine.get_last_files_count(direction="", duration=60)
        return count

    @pyqtSlot(result=str)
    def get_tracker_id(self) -> str:
        return self._manager.get_tracker_id()

    @pyqtSlot(str)
    def set_language(self, locale: str) -> None:
        try:
            Translator.set(locale)
        except RuntimeError:
            log.exception("Set language error")

    @pyqtSlot(QUrl, result=str)
    def to_local_file(self, url: QUrl) -> str:
        """
        Convert the given QUrl to its local path equivalent.

            >>> to_local_file("file:///home/username/nuxeo")
            /home/username/nuxeo
            >>> to_local_file("file:///C:/Users/username/nuxeo")
            C:\\Users\\username\\nuxeo

        """
        return abspath(url.toLocalFile())

    @pyqtSlot(str)
    def trigger_notification(self, id_: str) -> None:
        self.application.hide_systray()
        self._manager.notification_service.trigger_notification(id_)

    @pyqtSlot(str)
    def discard_notification(self, id_) -> None:
        self._manager.notification_service.discard_notification(id_)

    def _export_notifications(
        self, notifs: Dict[str, Notification]
    ) -> List[Dict[str, Any]]:
        return [notif.export() for notif in notifs.values()]

    @pyqtSlot(str, result=str)
    def get_notifications(self, engine_uid: str) -> str:
        engine_uid = engine_uid
        center = self._manager.notification_service
        notif = self._export_notifications(center.get_notifications(engine_uid))
        return self._json(notif)

    @pyqtSlot(result=str)
    def get_update_channel(self) -> str:
        """ Return the channel of the update. """
        return self._manager.get_update_channel()

    @pyqtSlot(result=str)
    def get_update_status(self) -> str:
        """ Return the status of the update. """
        return self._manager.updater.status

    @pyqtSlot(result=str)
    def get_update_version(self) -> str:
        """ Return the version of the update, if one is available. """
        return self._manager.updater.version

    @pyqtSlot(result=int)
    def get_update_progress(self) -> float:
        """ Return the progress of the update, if one is ingoing. """
        return self._manager.updater.progress

    @pyqtSlot(str)
    def app_update(self, version: str) -> None:
        """ Start the udpate to the specified version. """
        self._manager.updater.update(version)

    @pyqtSlot(result=list)
    def get_actions(self) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []

        if not self._manager.get_engines():
            return result

        for action in Action.get_actions().values():
            if isinstance(action, FileAction):
                result.append(action.export())
        return result

    @pyqtSlot(str, result=str)
    def get_threads(self, uid: str) -> str:
        engine = self._get_engine(uid)
        return self._json(engine._get_threads() if engine else [])

    @pyqtSlot(str, str)
    def show_metadata(self, uid: str, ref: str) -> None:
        self.application.hide_systray()
        engine = self._get_engine(uid)
        if engine:
            path = engine.local.abspath(Path(ref))
            self.application.show_metadata(path)

    @pyqtSlot(str, result=list)
    def get_unsynchronizeds(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for conflict in engine.get_dao().get_unsynchronizeds():
                result.append(self._export_formatted_state(uid, conflict))
        return result

    @pyqtSlot(str, result=list)
    def get_conflicts(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for conflict in engine.get_conflicts():
                result.append(self._export_formatted_state(uid, conflict))
        return result

    @pyqtSlot(str, result=list)
    def get_errors(self, uid: str) -> List[Dict[str, Any]]:
        result = []
        engine = self._get_engine(uid)
        if engine:
            for error in engine.get_errors():
                result.append(self._export_formatted_state(uid, error))
        return result

    @pyqtSlot(bool)
    def set_direct_edit_auto_lock(self, value: bool) -> None:
        self._manager.set_direct_edit_auto_lock(value)

    @pyqtSlot(result=bool)
    def get_direct_edit_auto_lock(self) -> bool:
        return self._manager.get_direct_edit_auto_lock()

    @pyqtSlot(bool, result=bool)
    def set_auto_start(self, value: bool) -> bool:
        return self._manager.set_auto_start(value)

    @pyqtSlot(result=bool)
    def get_auto_start(self) -> bool:
        return self._manager.get_auto_start()

    @pyqtSlot(bool)
    def set_auto_update(self, value: bool) -> None:
        self._manager.set_auto_update(value)

    @pyqtSlot(result=bool)
    def get_auto_update(self) -> bool:
        return self._manager.get_auto_update()

    @pyqtSlot(str)
    def set_update_channel(self, value: str) -> None:
        self._manager.set_update_channel(value)

    @pyqtSlot(str)
    def set_log_level(self, value: str) -> None:
        self._manager.set_log_level(value)

    @pyqtSlot(result=str)
    def get_log_level(self) -> str:
        return self._manager.get_log_level()

    @pyqtSlot(result=str)
    def generate_report(self) -> str:
        try:
            return str(self._manager.generate_report())
        except Exception as e:
            log.exception("Report error")
            return "[ERROR] " + str(e)

    @pyqtSlot(str)
    def open_remote_server(self, uid: str) -> None:
        self.application.hide_systray()
        engine = self._get_engine(uid)
        if engine:
            engine.open_remote()

    @pyqtSlot(str)
    def open_report(self, path: str) -> None:
        self._manager.open_local_file(path, select=True)

    @pyqtSlot(str, str)
    def open_local(self, uid: str, path: str) -> None:
        self.application.hide_systray()
        log.debug(f"Opening local file {path!r}")
        filepath = Path(force_decode(path).lstrip("/"))
        if not uid:
            self._manager.open_local_file(filepath)
        else:
            engine = self._get_engine(uid)
            if engine:
                filepath = engine.local.abspath(filepath)
                self._manager.open_local_file(filepath)

    @pyqtSlot()
    def open_help(self) -> None:
        self.application.hide_systray()
        self._manager.open_help()

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid: str) -> None:
        self.application.hide_systray()
        engine = self._get_engine(uid)
        if engine:
            self.application.show_conflicts_resolution(engine)

    @pyqtSlot(str)
    def show_settings(self, page: str) -> None:
        self.application.hide_systray()
        log.info(f"Show settings on page {page}")
        self.application.show_settings(section=page or None)

    @pyqtSlot()
    def quit(self) -> None:
        try:
            self.application.quit()
        except:
            log.exception("Application exit error")

    @pyqtSlot(result=str)
    def get_version(self) -> str:
        return self._manager.version

    @pyqtSlot(result=str)
    def get_update_url(self) -> str:
        return Options.update_site_url

    @pyqtSlot(str)
    def web_update_token(self, uid: str) -> None:
        try:
            engine = self._get_engine(uid)
            if not engine:
                self.setMessage.emit("CONNECTION_UNKNOWN", "error")
                return
            params = urlencode({"updateToken": True})

            url = engine.server_url
            login_type = self._manager._get_server_login_type(url)
            if login_type is Login.OLD:
                # We might have to downgrade because the
                # browser login is not available.
                self._manager.updater._force_downgrade()
                return

            url = self._get_authentication_url(engine.server_url)
            if Options.is_frozen:
                url = f"{url}&{params}"
            callback_params = {"engine": uid}
            log.info(f"Opening login window for token update with URL {url}")
            self.application._open_authentication_dialog(url, callback_params)
        except:
            log.exception(
                "Unexpected error while trying to open web"
                " authentication window for token update"
            )
            self.setMessage.emit("CONNECTION_UNKNOWN", "error")

    def _guess_server_url(self, server_url: str) -> str:
        """Handle invalide SSL certificates when guessing the server URL."""
        try:
            return guess_server_url(server_url, proxy=self._manager.proxy)
        except InvalidSSLCertificate as exc:
            log.warning(exc)
            parts = urlsplit(server_url)
            hostname = parts.netloc or parts.path
            if self.application.accept_unofficial_ssl_cert(hostname):
                Options.ca_bundle = None
                Options.ssl_no_verify = True
                return self._guess_server_url(server_url)
        return ""

    def _get_authentication_url(self, server_url: str) -> str:
        if not server_url:
            raise ValueError("No URL found for Nuxeo server")

        if not Options.is_frozen:
            return server_url

        params = urlencode(
            {
                "deviceId": self._manager.device_id,
                "applicationName": APP_NAME,
                "permission": TOKEN_PERMISSION,
                "deviceDescription": get_device(),
                "forceAnonymousLogin": "true",
                "useProtocol": "true",
            }
        )

        # Handle URL parameters
        parts = urlsplit(server_url)
        path = f"{parts.path}/{Options.browser_startup_page}".replace("//", "/")

        params = f"{parts.query}&{params}" if parts.query else params
        return urlunsplit((parts.scheme, parts.netloc, path, params, parts.fragment))

    # Settings section

    @pyqtSlot(result=str)
    def default_local_folder(self) -> str:
        return str(get_default_local_folder())

    @pyqtSlot(result=str)
    def default_server_url_value(self) -> str:
        """Make daily job better for our developers :)"""
        return getenv("NXDRIVE_TEST_NUXEO_URL", "")

    @pyqtSlot(str)
    def unbind_server(self, uid: str) -> None:
        self._manager.unbind_engine(uid)

    @pyqtSlot(str)
    def filters_dialog(self, uid: str) -> None:
        engine = self._get_engine(uid)
        if engine:
            self.application.show_filters(engine)

    def _bind_server(
        self,
        local_folder: Path,
        url: str,
        username: str,
        password: Optional[str],
        name: Optional[str],
        **kwargs: Any,
    ) -> None:
        # Remove any parameters from the original URL
        parts = urlsplit(url)
        url = urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))

        name = name or None
        binder = Binder(
            username=username,
            password=password,
            token=kwargs.get("token"),
            no_check=False,
            no_fscheck=not kwargs.get("check_fs", True),
            url=url,
        )
        log.info(f"Binder is : {binder.url}/{binder.username}")

        engine = self._manager.bind_engine(
            self._manager._get_default_server_type(),
            local_folder,
            name,
            binder,
            starts=False,
        )

        # Flag to close the settings window when the filters dialog is closed
        self.application.close_settings_too = True

        # Display the filters window to let the user choose what to sync
        self.filters_dialog(engine.uid)
        self.setMessage.emit("CONNECTION_SUCCESS", "success")

    @pyqtSlot(str, str, str, str, str)
    def bind_server(
        self,
        local_folder: str,
        server_url: str,
        username: str,
        password: str = None,
        name: str = None,
        **kwargs: Any,
    ) -> None:
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
                **kwargs,
            )
        except RootAlreadyBindWithDifferentAccount as e:
            log.warning(Translator.get("FOLDER_USED"))

            # Ask for the user
            values = [e.username, e.url]
            msgbox = QMessageBox(
                QMessageBox.Question,
                APP_NAME,
                Translator.get("ROOT_USED_WITH_OTHER_BINDING", values),
                QMessageBox.NoButton,
            )
            msgbox.addButton(Translator.get("CONTINUE"), QMessageBox.AcceptRole)
            cancel = msgbox.addButton(Translator.get("CANCEL"), QMessageBox.RejectRole)
            msgbox.exec_()
            if msgbox.clickedButton() == cancel:
                self.setMessage.emit("FOLDER_USED", "error")
                return

            kwargs["check_fs"] = False
            return self.bind_server(
                local_folder, server_url, username, password, name, **kwargs
            )
        except NotFound:
            error = "FOLDER_DOES_NOT_EXISTS"
        except InvalidDriveException:
            error = "INVALID_PARTITION"
        except Unauthorized:
            error = "UNAUTHORIZED"
        except FolderAlreadyUsed:
            error = "FOLDER_USED"
        except HTTPError:
            error = "CONNECTION_ERROR"
        except CONNECTION_ERROR as e:
            if getattr(e, "errno") == 61:
                error = "CONNECTION_REFUSED"
            else:
                error = "CONNECTION_ERROR"
        except:
            log.exception("Unexpected error")
            # Map error here
            error = "CONNECTION_UNKNOWN"

        log.warning(Translator.get(error))
        self.setMessage.emit(error, "error")

    @pyqtSlot(str, str)
    def web_authentication(self, server_url: str, local_folder: str) -> None:
        # Handle the server URL
        server_url = self._guess_server_url(server_url)
        if not server_url:
            self.setMessage.emit("CONNECTION_ERROR", "error")
            return

        parts = urlsplit(server_url)

        # Handle the engine
        engine_type = parts.fragment or self._manager._get_default_server_type()

        try:
            # Handle local folder
            if not self._manager.check_local_folder_available(
                normalized_path(local_folder)
            ):
                raise FolderAlreadyUsed()

            # Connect to startup page
            login_type = self._manager._get_server_login_type(server_url)
            url = self._get_authentication_url(server_url)

            if login_type is not Login.OLD:
                # Page should exists, let's open authentication dialog
                log.info(f"Web authentication is available on server {server_url}")
            else:
                # Startup page is not available
                log.info(
                    f"Web authentication not available on server {server_url}, "
                    "falling back on basic authentication"
                )
                if Options.is_frozen:
                    # We might have to downgrade because the
                    # browser login is not available.
                    self._manager.updater._force_downgrade()
                    return

            callback_params = {
                "local_folder": local_folder,
                "server_url": server_url,
                "engine_type": engine_type,
            }
            self.openAuthenticationDialog.emit(url, callback_params)
            return
        except FolderAlreadyUsed:
            error = "FOLDER_USED"
        except StartupPageConnectionError:
            error = "CONNECTION_ERROR"
        except:
            log.exception(
                "Unexpected error while trying to open web authentication window"
            )
            error = "CONNECTION_UNKNOWN"
        self.setMessage.emit(error, "error")

    @pyqtSlot(str, str, result=bool)
    def set_server_ui(self, uid: str, server_ui: str) -> bool:
        log.info(f"Setting ui to {server_ui}")
        engine = self._get_engine(uid)
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
    def set_proxy_settings(self, config: str, url: str, pac_url: str) -> bool:
        proxy = get_proxy(category=config, url=url, pac_url=pac_url)
        result = self._manager.set_proxy(proxy)
        if result:
            self.setMessage.emit(result, "error")
            return False
        else:
            self.setMessage.emit("PROXY_APPLIED", "success")
            return True

    @pyqtSlot(result=str)
    def get_deletion_behavior(self) -> str:
        return self._manager.get_config("deletion_behavior")

    @pyqtSlot(str)
    def set_deletion_behavior(self, behavior: str) -> None:
        self._manager.set_config("deletion_behavior", behavior)

    @pyqtSlot(str, result=bool)
    def has_invalid_credentials(self, uid: str) -> bool:
        engine = self._get_engine(uid)
        return engine.has_invalid_credentials() if engine else False

    # Authentication section

    @pyqtSlot(str, str)
    def handle_token(self, token: str, username: str) -> None:
        if not token:
            error = "CONNECTION_REFUSED"
        elif "engine" in self._callback_params:
            error = self.update_token(token)
        else:
            error = self.create_account(token, username)
        if error:
            self.setMessage.emit(error, "error")

    def create_account(self, token: str, username: str) -> str:
        error = ""
        try:
            local_folder = self._callback_params["local_folder"]
            server_url = (
                self._callback_params["server_url"]
                + "#"
                + self._callback_params["engine_type"]
            )

            log.info(f"Creating new account [{local_folder}, {server_url}, {username}]")

            error = self.bind_server(
                local_folder,
                server_url,
                username,
                password=None,
                token=token,
                name=None,
            )

            log.info(f"RETURN FROM BIND_SERVER IS: '{error}'")
        except:
            log.exception(
                "Unexpected error while trying to create a new account "
                f"[{local_folder}, {server_url}, {username}]"
            )
            error = "CONNECTION_UNKNOWN"
        finally:
            return error

    def update_token(self, token: str) -> str:
        error = ""
        engine = self._get_engine(self._callback_params["engine"])
        if not engine:
            return ""
        try:
            log.info(
                "Updating token for account "
                f"[{engine.local_folder}, {engine.server_url}, {engine.remote_user}]"
            )

            engine.update_token(token)
            self.application.set_icon_state("idle")
            self.application.show_settings(section="Accounts")
            self.setMessage.emit("CONNECTION_SUCCESS", "success")

        except CONNECTION_ERROR as e:
            log.exception("HTTP Error")
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
    def suspend(self, start: bool) -> None:
        if start:
            self._manager.resume()
        else:
            self._manager.suspend()

    @pyqtSlot(result=bool)
    def is_paused(self) -> bool:
        return self._manager.is_paused()

    @pyqtSlot(str, result=int)
    def get_syncing_count(self, uid: str) -> int:
        count = 0
        engine = self._get_engine(uid)
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot(str, result=int)
    def get_conflicts_count(self, uid: str) -> int:
        return len(self.get_conflicts(uid))

    @pyqtSlot(str, result=int)
    def get_errors_count(self, uid: str) -> int:
        return len(self.get_errors(uid))

    # Conflicts section

    @pyqtSlot(str, int)
    def resolve_with_local(self, uid: str, state_id: int) -> None:
        engine = self._get_engine(uid)
        if engine:
            engine.resolve_with_local(state_id)

    @pyqtSlot(str, int)
    def resolve_with_remote(self, uid: str, state_id: int) -> None:
        engine = self._get_engine(uid)
        if engine:
            engine.resolve_with_remote(state_id)

    @pyqtSlot(str, int)
    def retry_pair(self, uid: str, state_id: int) -> None:
        engine = self._get_engine(uid)
        if engine:
            engine.retry_pair(state_id)

    @pyqtSlot(str, int, str)
    def ignore_pair(self, uid: str, state_id: int, reason: str = "UNKNOWN") -> None:
        engine = self._get_engine(uid)
        if engine:
            engine.ignore_pair(state_id, reason=reason)

    @pyqtSlot(str, str, str)
    def open_remote(self, uid: str, remote_ref: str, remote_name: str) -> None:
        log.info(f"Should open this : {remote_name} ({remote_ref})")
        try:
            engine = self._get_engine(uid)
            if engine:
                engine.open_edit(remote_ref, remote_name)
        except OSError:
            log.exception("Remote open error")
