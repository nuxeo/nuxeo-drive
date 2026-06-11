"""Alfresco server-type registration."""

from nxdrive.drive.server_type import ServerTypeConfig, register


def _alfresco_auth_factory(host, token, **kwargs):
    """Create the appropriate auth object for Alfresco."""
    if isinstance(token, dict):
        from nxdrive.alfresco.auth.oauth2 import AlfrescoOAuthentication

        return AlfrescoOAuthentication(host, token=token, **kwargs)
    from nxdrive.drive.auth.token import TokenAuthentication

    return TokenAuthentication(host, token=token, **kwargs)


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
    ),
)
