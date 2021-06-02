# Code to ignore for Vulture.

AbstractOSIntegration.cb_get  # OSI
ActiveSessionModel.count_no_shadow  # Used in QML
ActiveSessionModel.is_full  # Used in QML
Application.about_to_quit  # Used in QML
Application.close_direct_transfer_window  # Used in QML
Application.confirm_cancel_transfer  # Used in QML
Application._nxdrive_url_env  # Used in QML
Application.action_progressing  # Used by FileAction.processing signal
batch.upload_idx  # BaseUploader.upload_chunks()
BlocklistQueue.repush  # Used in tests
blob.batchId  # BaseUploader.upload_chunks()
blob.fileIdx  # BaseUploader.upload_chunks()
CallableFeatureHandler.__call__  # Obviously ...
CliHandler.bind_root  # Used by the arguments parser
CliHandler.clean_folder  # Used by the arguments parser
CliHandler.console  # Used by the arguments parser
CliHandler.ctx_direct_transfer  # Used by the arguments parser
CliHandler.download_edit  # Used by the arguments parser
CliHandler.unbind_root  # Used by the arguments parser
CliHandler.unbind_server  # Used by the arguments parser
_.close_settings_too  # Used by Appiclation.show_filters()
DirectTransferModel.destination_link  # Used in QML
DocPair.last_sync_error_date  # Check NXDRIVE-1804
Download.transfer_type  # Used in QML
Engine.folder  # Used in QML
EngineDAO.get_downloads_with_status()  # Used dynamically in Engine
EngineDAO.get_uploads_with_status()  # Used dynamically in Engine
engine_migrations  # Used in tests
exc.trash_issue  # LocalClient.delete()
FileInfo.is_hidden  # Used in QML
FolderTreeview.resizeEvent  # Internal use of PyQt
logging_config.debuglevel  # Only used when LOG_EVERYTHING envar is set
Manager.get_feature_state  # Used in QML
Manager.set_direct_edit_auto_lock  # Used in QML
Manager.set_auto_update  # Used in QML
Manager.set_auto_start  # Used in QML
Manager.set_feature_state  # Used in QML
Manager.set_log_level  # Used in QML
Manager.set_light_icons  # Used in QML
manager_migrations  # Used in tests
MetaOptions.mock  # Used in tests
MigrationInitial.downgrade  # Used in tests
MigrationInitial.upgrade  # Used in tests
NotificationDelegator.userNotificationCenter_didActivateNotification_
NotificationDelegator.userNotificationCenter_shouldPresentNotification_
nuxeo.constants.CHECK_PARAMS  # CliHandler.parse_cli()
ob.read_directory_changes.WATCHDOG_TRAVERSE_MOVED_DIR_DELAY  # Used by Watchdog
ob.winapi.BUFFER_SIZE  # Used by Watchdog
Options.__getattr__  # Used by MetaOptions
Options.__repr__  # Used for logging
Options.__setattr__  # Used by MetaOptions
Options.__str__  # Used for logging
Options.deletion_behavior  # Used in Manager
_.row_factory  # Internal use of SQLite
PatternMatchingEventHandler.on_any_event  # Used by Watchdog
Processor._synchronize_conflicted  # Used by Processor._execute()
Processor._synchronize_direct_transfer  # Used by Processor._execute()
Processor._synchronize_direct_transfer_replace_blob  # Used by Processor._execute()
Processor._synchronize_deleted_unknown  # Used by Processor._execute()
Processor._synchronize_locally_deleted  # Used by Processor._execute()
Processor._synchronize_locally_resolved  # Used by Processor._execute()
Processor._synchronize_locally_moved_created  # Used by Processor._execute()
Processor._synchronize_locally_moved_remotely_modified  # Used by Processor._execute()
Processor._synchronize_remotely_created  # Used by Processor._execute()
Processor._synchronize_unknown_deleted  # Used by Processor._execute()
QAbstractListModel.getTag  # Used in QML
QAbstractListModel.getName  # Internal use of QML
QAbstractListModel.nameRoles  # Internal use of QML
QMLDriveApi.confirm_cancel_session  # Used in QML
QMLDriveApi.default_local_folder  # Used in QML
QMLDriveApi.default_server_url_value  # Used in QML
QMLDriveApi.get_active_sessions_count  # Used in QML
QMLDriveApi.get_completed_sessions_count  # Used in QML
QMLDriveApi.get_disk_space_info_to_width  # Used in QML
QMLDriveApi.get_drive_disk_space  # Used in QML
QMLDriveApi.get_features_list  # Used in QML
QMLDriveApi.get_free_disk_space  # Used in QML
QMLDriveApi.get_hostname_from_url  # Used in QML
QMLDriveApi.get_remote_document_url  # Used in QML
QMLDriveApi.get_used_space_without_synced  # Used in QML
QMLDriveApi.get_proxy_settings  # Used in QML
QMLDriveApi.get_update_status  # Used in QML
QMLDriveApi.get_update_url  # Used in QML
QMLDriveApi.get_update_version  # Used in QML
QMLDriveApi.open_direct_transfer  # Used in QML
QMLDriveApi.open_document  # Used in QML
QMLDriveApi.open_in_explorer  # Used in QML
QMLDriveApi.open_local  # Used in QML
QMLDriveApi.open_remote_server  # Used in QML
QMLDriveApi.open_remote_document  # Used in QML
QMLDriveApi.open_server_folders  # Used in QML
QMLDriveApi.set_proxy_settings  # Used in QML
QMLDriveApi.set_server_ui  # Used in QML
QMLDriveApi.to_local_file  # Used in QML
QMLDriveApi.web_update_token  # Used in QML
ROOT_REGISTERED  # Used in tests
registry.create  # Used in test_windows_registry.py
shortcut.Targetpath  # WindowsIntegration._create_shortcut()
shortcut.WorkingDirectory  # WindowsIntegration._create_shortcut()
shortcut.IconLocation  # WindowsIntegration._create_shortcut()
Upload.transfer_type  # Used in QML
WindowsIntegration.install_addons  # Used in QML
