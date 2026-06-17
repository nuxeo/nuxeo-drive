"""Alfresco server-type registration."""

try:
    import alfresco

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
    auth._obtain_ticket(engine.server_url)
    ticket = auth.ticket
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
        supports_browser_token_update=False,
        is_url_fallback=True,
        client_version=_client_version,
        relogin_handler=_alfresco_relogin_handler,
    ),
)
