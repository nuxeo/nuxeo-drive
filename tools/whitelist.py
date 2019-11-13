# Whitelist file for Vulture.

Application._nxdrive_url_env  # Used in QML
Application.action_progressing  # Used by FileAction.processing signal
BlacklistQueue.repush  # Used in tests
blob.batch_id  # Remote.upload_chunks()
blob.fileIdx  # Remote.upload_chunks()
blob.mimetype  # Remote.upload_chunks()
cb_get  # OSI
CliHandler.bind_root  # Used by the arguments parser
CliHandler.clean_folder  # Used by the arguments parser
CliHandler.ctx_direct_transfer  # Used by the arguments parser
CliHandler.download_edit  # Used by the arguments parser
CliHandler.unbind_root  # Used by the arguments parser
CliHandler.unbind_server  # Used by the arguments parser
_.close_settings_too  # Used by Appiclation.show_filters()
DocPair.last_sync_error_date  # Check NXDRIVE-1804
Download.transfer_type  # Used in QML
Engine.account  # Used in QML
Engine.folder  # Used in QML
EngineDAO.get_downloads_with_status()  # Used dynamically in Engine
EngineDAO.get_uploads_with_status()  # Used dynamically in Engine
exc.trash_issue  # LocalClient.delete()
FolderTreeview.resizeEvent  # Internal use of PyQt
install_addons  # Used in QML
getTag  # Used in QML
getName  # Internal use of QML
Manager.set_light_icons  # Used in QML
MetaOptions.mock  # Used in tests
nameRoles  # Internal use of QML
nuxeo.constants.CHECK_PARAMS  # CliHandler.parse_cli()
ob.read_directory_changes.WATCHDOG_TRAVERSE_MOVED_DIR_DELAY  # Used by Watchdog
ob.winapi.BUFFER_SIZE  # Used by Watchdog
on_any_event  # Used by Watchdog
_.row_factory  # Internal use of SQLite
Processor._synchronize_conflicted  # Used by Processor._execute()
Processor._synchronize_direct_transfer  # Used by Processor._execute()
Procesor._synchronize_direct_transfer_replace_blob  # Used by Processor._execute()
Processor._synchronize_deleted_unknown  # Used by Processor._execute()
Processor._synchronize_locally_deleted  # Used by Processor._execute()
Processor._synchronize_locally_resolved  # Used by Processor._execute()
Processor._synchronize_locally_moved_created  # Used by Processor._execute()
Processor._synchronize_locally_moved_remotely_modified  # Used by Processor._execute()
Processor._synchronize_remotely_created  # Used by Processor._execute()
Processor._synchronize_unknown_deleted  # Used by Processor._execute()
QMLDriveApi.default_local_folder  # Used in QML
QMLDriveApi.default_server_url_value  # Used in QML
QMLDriveApi.get_proxy_settings  # Used in QML
QMLDriveApi.get_update_url  # Used in QML
QMLDriveApi.get_update_version  # Used in QML
QMLDriveApi.open_local  # Used in QML
QMLDriveApi.open_remote_server  # Used in QML
QMLDriveApi.open_report  # Used in QML
QMLDriveApi.set_proxy_settings  # Used in QML
QMLDriveApi.set_server_ui  # Used in QML
QMLDriveApi.to_local_file  # Used in QML
QMLDriveApi.web_update_token  # Used in QML
shortcut.Targetpath  # WindowsIntegration._create_shortcut()
shortcut.WorkingDirectory  # WindowsIntegration._create_shortcut()
shortcut.IconLocation  # WindowsIntegration._create_shortcut()
Upload.transfer_type  # Used in QML
userNotificationCenter_didActivateNotification_  # From NotificationDelegator
userNotificationCenter_shouldPresentNotification_  # From NotificationDelegator
