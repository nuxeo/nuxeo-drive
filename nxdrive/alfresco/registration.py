"""Alfresco server-type registration."""

try:
    import alfresco

    # Alfresco Python Client version
    _client_version = alfresco.__version__
except ImportError:
    _client_version = ""

from nxdrive.drive.server_type import ServerTypeConfig, register


def _alfresco_auth_factory(host, token, **kwargs):
    """Create the appropriate auth object for Alfresco."""
    if isinstance(token, dict):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        return AlfrescoOAuthentication(host, token=token, **kwargs)
    from nxdrive.drive.auth.token import TokenAuthentication

    return TokenAuthentication(host, token=token, **kwargs)


def _alfresco_relogin_handler(engine, password):
    """Re-authenticate an Alfresco engine using TicketAuth."""
    from alfresco.auth import TicketAuth

    auth = TicketAuth(engine.remote_user, password, engine.server_url)
    ticket = auth.authenticate(engine.server_url)
    if not ticket:
        raise RuntimeError("No ticket returned")

    engine._alfresco_ticket = ticket
    engine._remote_password = ""
    engine._save_ticket(ticket)
    engine.set_invalid_credentials(value=False)
    engine.stop()
    engine.remote = engine.init_remote()
    engine.start()
    engine.queue_manager.resume()
    engine.dao.update_config("remote_need_full_scan", "1")


def _alfresco_password_auth_handler(
    api, local_folder: str, server_url: str, username: str, password: str
) -> None:
    from nxdrive.alfresco.gui.auth import basic_auth

    basic_auth(api, local_folder, server_url, username, password)


def _alfresco_debug_auth_handler(url, manager, api):
    """Non-frozen debug auth dialog for Alfresco servers.

    Presents a simple username/password dialog and binds the account
    directly (Alfresco tickets are obtained transparently by
    ``TicketAuth`` on the first request). Used only when
    ``Options.is_frozen`` is False, i.e. during local development.
    """
    import os

    from nxdrive.drive.qt import constants as qt
    from nxdrive.drive.qt.imports import (
        QDialog,
        QDialogButtonBox,
        QLineEdit,
        QVBoxLayout,
    )

    dialog = QDialog()
    dialog.setWindowTitle("Authentication")
    dialog.resize(250, 100)

    layout = QVBoxLayout()

    default_user = os.getenv("NXDRIVE_TEST_USERNAME", "admin")
    default_pwd = os.getenv("NXDRIVE_TEST_PASSWORD", "admin")
    username = QLineEdit(default_user, parent=dialog)
    password = QLineEdit(default_pwd, parent=dialog)
    password.setEchoMode(qt.Password)
    layout.addWidget(username)
    layout.addWidget(password)

    def auth():
        user = str(username.text())
        pwd = str(password.text())
        params = api.callback_params or {}
        if not params:
            params = api._load_pending_auth_callback_params()
        local_folder = params.get("local_folder", "")
        server_url = params.get("server_url", url)
        try:
            api.bind_server(local_folder, server_url, user, password=pwd)
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error(f"Alfresco debug auth failed: {exc}")
            api.setMessage.emit("CONNECTION_REFUSED", "error")
        api._clear_pending_auth_callback_params()
        dialog.close()

    buttons = QDialogButtonBox()
    buttons.setStandardButtons(qt.Cancel | qt.Ok)
    buttons.accepted.connect(auth)
    buttons.rejected.connect(dialog.close)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    dialog.exec()


def _alfresco_save_auth_callback_params(api, params) -> None:
    from nxdrive.alfresco.gui.auth_callback_store import save_auth_callback_params

    save_auth_callback_params(api, params)


def _alfresco_load_auth_callback_params(api):
    from nxdrive.alfresco.gui.auth_callback_store import load_auth_callback_params

    return load_auth_callback_params(api)


def _alfresco_clear_auth_callback_params(api) -> None:
    from nxdrive.alfresco.gui.auth_callback_store import clear_auth_callback_params

    clear_auth_callback_params(api)


register(
    ServerTypeConfig(
        key="ALFRESCO",
        home_dir=".alfresco-drive",
        log_file="aldrive.log",
        db_prefix="adrive_",
        engine_type="ALFRESCO",
        engine_class_path="nxdrive.alfresco.engine.engine.AlfrescoEngine",
        direct_edit_class_path="",  # not yet implemented
        direct_download_class_path="",  # not yet implemented
        workflow_class_path="",  # not yet implemented
        oauth2_class_path="nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication",
        folders_only_class_path="",  # not yet implemented
        new_account_popup_qml_path="alfresco/gui/qml/NewAccountPopup.qml",
        relogin_popup_qml_path="drive/data/qml/ReLoginPopup.qml",
        disabled_features=[
            "direct_edit",
            "direct_transfer",
            "document_type_selection",
            "tasks_management",
            "s3",
        ],
        auth_factory=_alfresco_auth_factory,
        app_name="Alfresco Drive",
        company="Hyland",
        bundle_identifier="com.alfresco.drive",
        url_scheme="nxdrive",
        config_registry_key="Software\\Alfresco\\Drive",
        emblem_name="emblem-alfresco",
        local_folder_name="Alfresco",
        download_exe="alfresco-drive.exe",
        download_dmg="alfresco-drive.dmg",
        download_appimage="alfresco-drive-x86_64.AppImage",
        sync_root="",
        url_patterns=[],
        ssl_login_page="api/discovery",
        startup_page="",
        browser_startup_page="",
        supports_browser_token_update=False,
        is_url_fallback=True,
        findersync_agent_template='<?xml version="1.0" encoding="UTF-8"?>'
        '<!DOCTYPE plist PUBLIC "-//Apple Computer//DTD PLIST 1.0//EN"'
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">'
        '<plist version="1.0">'
        "<dict>"
        "<key>Label</key>"
        "<string>org.alfresco.drive.agentlauncher</string>"
        "<key>RunAtLoad</key>"
        "<true/>"
        "<key>Program</key>"
        "<string>%s</string>"
        "</dict>"
        "</plist>",
        findersync_bundle_id_suffix="AlfrescoFinderSync",
        findersync_appex_name="AlfrescoFinderSync.appex",
        addon_installer_name="alfresco-drive-addons.exe",
        update_site_url="https://community.nuxeo.com/static/drive-updates",
        client_version=_client_version,
        relogin_handler=_alfresco_relogin_handler,
        password_auth_handler=_alfresco_password_auth_handler,
        debug_auth_handler=_alfresco_debug_auth_handler,
        save_auth_callback_params_hook=_alfresco_save_auth_callback_params,
        load_auth_callback_params_hook=_alfresco_load_auth_callback_params,
        clear_auth_callback_params_hook=_alfresco_clear_auth_callback_params,
    ),
)
