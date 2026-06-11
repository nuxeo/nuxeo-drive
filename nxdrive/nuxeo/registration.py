"""Nuxeo server-type registration."""

from nxdrive.drive.server_type import ServerTypeConfig, register


def _nuxeo_auth_factory(host, token, **kwargs):
    """Create the appropriate auth object for Nuxeo."""
    if isinstance(token, dict):
        from nxdrive.nuxeo.auth.oauth2 import OAuthentication

        return OAuthentication(host, token=token, **kwargs)
    from nxdrive.drive.auth.token import TokenAuthentication

    return TokenAuthentication(host, token=token, **kwargs)


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
    ),
    default=True,
)
