"""Nuxeo server-type registration."""

import nuxeo

from nxdrive.drive.server_type import ServerTypeConfig, register


def _nuxeo_auth_factory(host, token, **kwargs):
    """Create the appropriate auth object for Nuxeo."""
    if isinstance(token, dict):
        from nxdrive.nuxeo.auth.oauth2 import OAuthentication

        return OAuthentication(host, token=token, **kwargs)
    from nxdrive.nuxeo.auth.token import TokenAuthentication

    return TokenAuthentication(host, token=token, **kwargs)


def _nuxeo_debug_init():
    """Enable parameter checking in the nuxeo-python-client."""
    import nuxeo.constants

    nuxeo.constants.CHECK_PARAMS = True


def _nuxeo_debug_auth_handler(url, manager, api):
    """Non-frozen debug auth dialog for Nuxeo servers."""
    import os

    from nuxeo.client import Nuxeo

    from nxdrive.drive.constants import APP_NAME, TOKEN_PERMISSION
    from nxdrive.drive.metrics.utils import current_os
    from nxdrive.drive.qt import constants as qt
    from nxdrive.drive.qt.imports import (
        QDialog,
        QDialogButtonBox,
        QLineEdit,
        QVBoxLayout,
    )
    from nxdrive.drive.utils import client_certificate, get_verify

    dialog = QDialog()
    dialog.setWindowTitle("Authentication")
    dialog.resize(250, 100)

    layout = QVBoxLayout()

    default_user = os.getenv("NXDRIVE_TEST_USERNAME", "Administrator")
    default_pwd = os.getenv("NXDRIVE_TEST_PASSWORD", "Administrator")
    username = QLineEdit(default_user, parent=dialog)
    password = QLineEdit(default_pwd, parent=dialog)
    password.setEchoMode(qt.Password)
    layout.addWidget(username)
    layout.addWidget(password)

    def auth():
        user = str(username.text())
        pwd = str(password.text())
        verification_needed = get_verify()
        nuxeo_client = Nuxeo(
            host=url,
            auth=(user, pwd),
            proxies=manager.proxy.settings(url=url),
            verify=verification_needed,
            cert=client_certificate(),
        )
        try:
            token = nuxeo_client.client.request_auth_token(
                manager.device_id,
                TOKEN_PERMISSION,
                app_name=APP_NAME,
                device=current_os(full=True),
            )
        except Exception as exc:
            import logging

            logging.getLogger(__name__).error(f"Connection error: {exc}")
            token = ""
        finally:
            del nuxeo_client
        api.handle_token(token, user)
        dialog.close()

    buttons = QDialogButtonBox()
    buttons.setStandardButtons(qt.Cancel | qt.Ok)
    buttons.accepted.connect(auth)
    buttons.rejected.connect(dialog.close)
    layout.addWidget(buttons)
    dialog.setLayout(layout)
    dialog.exec()


def _nuxeo_parse_direct_transfer_remote_path(value: str) -> str:
    from nxdrive.nuxeo.protocol import parse_direct_transfer_remote_path

    return parse_direct_transfer_remote_path(value)


def _nuxeo_normalize_download_server_path(server_part: str) -> str:
    from nxdrive.nuxeo.protocol import normalize_download_server_path

    return normalize_download_server_path(server_part)


register(
    ServerTypeConfig(
        key="NUXEO",
        home_dir=".nuxeo-drive",
        log_file="nxdrive.log",
        db_prefix="ndrive_",
        engine_type="NXDRIVE",
        engine_class_path="nxdrive.nuxeo.engine.engine.Engine",
        direct_edit_class_path="nxdrive.nuxeo.direct_edit.DirectEdit",
        direct_download_class_path="nxdrive.nuxeo.direct_download.DirectDownload",
        workflow_class_path="nxdrive.nuxeo.client.workflow.Workflow",
        oauth2_class_path="nxdrive.nuxeo.auth.oauth2.OAuthentication",
        folders_only_class_path="nxdrive.nuxeo.gui.folders_model.FoldersOnly",
        disabled_features=[],
        auth_factory=_nuxeo_auth_factory,
        app_name="Nuxeo Drive",
        company="Hyland",
        bundle_identifier="org.nuxeo.drive",
        url_scheme="nxdrive",
        config_registry_key="Software\\Nuxeo\\Drive",
        emblem_name="emblem-nuxeo",
        local_folder_name="Nuxeo Drive",
        download_exe="nuxeo-drive.exe",
        download_dmg="nuxeo-drive.dmg",
        download_appimage="nuxeo-drive-x86_64.AppImage",
        sync_root="/org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#",
        url_patterns=["nuxeo"],
        startup_page="drive_login.jsp",
        browser_startup_page="drive_browser_login.jsp",
        client_version=nuxeo.__version__,
        debug_init_hook=_nuxeo_debug_init,
        debug_auth_handler=_nuxeo_debug_auth_handler,
        parse_direct_transfer_remote_path=_nuxeo_parse_direct_transfer_remote_path,
        normalize_download_server_path=_nuxeo_normalize_download_server_path,
    ),
    default=True,
)
