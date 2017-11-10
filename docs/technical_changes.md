[//]: # (Note 1: class.method ordered)
[//]: # (Note 2: single files last)
[//]: # (Note 3: keywords ordered [Added, Changed, Moved, Removed])

# dev
- Removed `options` keyword from `Application.__init__()`. Use `Options` instead.
- Removed `ignored_prefixes` keyword from `BaseAutomationClient.__init__()`. Use `Options.ignored_prefixes` instead.
- Removed `ignored_suffixes` keyword from `BaseAutomationClient.__init__()`. Use `Options.ignored_suffixes` instead.
- Removed `options` keyword from `CliHandler.get_manager()`. Use `Options` instead.
- Removed `options` keyword from `CliHandler.uninstall()`. Use `Options` instead.
- Added `Engine.add_to_favorites()`
- Removed `Engine.get_update_url()`. Use `Options.update_site_url` instead.
- Removed `Engine.get_beta_update_url()`. Use `Options.beta_update_site_url` instead.
- Removed `ignored_prefixes` keyword from `LocalClient.__init__()`. Use `Options.ignored_prefixes` instead.
- Removed `ignored_suffixes` keyword from `LocalClient.__init__()`. Use `Options.ignored_suffixes` instead.
- Removed `options` keyword from `Manager.__init__()`. Use `Options` instead.
- Removed `refresh_engines` keyword from `Manager.get_version_finder()`
- Removed `Manager.is_beta_channel_available()`. Always True.
- Removed `options` keyword from `SimpleApplication.__init__()`. Use `Options` instead.
- Removed `WebDriveApi.is_beta_channel_available()`. Always True.
- Added options.py
- Removed client/common.py::`DEFAULT_BETA_SITE_URL`. Use `Options.beta_update_site_url` instead.
- Removed client/common.py::`DEFAULT_IGNORED_PREFIXES`. Use `Options.ignored_prefixes` instead.
- Removed client/common.py::`DEFAULT_IGNORED_SUFFIXES`. Use `Options.ignored_suffixes` instead.
- Removed client/common.py::`DEFAULT_REPOSITORY_NAME`. Use `Options.repository` instead.
- Removed client/common.py::`DEFAULT_UPDATE_SITE_URL`. Use `Options.update_site_url` instead.
- Removed client/common.py::`DRIVE_STARTUP_PAGE`. Use `Options.startup_page` instead.
- Removed commandline.py::`DEFAULT_HANDSHAKE_TIMEOUT`. Use `Options.handshake_timeout` instead.
- Removed commandline.py::`DEFAULT_MAX_ERRORS`. Use `Options.max_errors` instead.
- Removed commandline.py::`DEFAULT_MAX_SYNC_STEP`. Use `Options.max_sync_step` instead.
- Removed commandline.py::`DEFAULT_QUIT_TIMEOUT`. Use `Options.quit_timeout` instead.
- Removed commandline.py::`DEFAULT_REMOTE_WATCHER_DELAY`. Use `Options.delay` instead.
- Removed commandline.py::`DEFAULT_TIMEOUT`. Use `Options.timeout` instead.
- Removed commandline.py::`DEFAULT_UPDATE_CHECK_DELAY`. Use `Options.update_check_delay` instead.
- Removed commandline.py::`DEFAULT_UPDATE_SITE_URL`. Use `Options.update_site_url` instead.

# 2.5.7
- Removed `BaseAutomationClient.get_download_buffer()`. Use `FILE_BUFFER_SIZE` attribute instead.

# 2.5.6
- Added `BaseAutomationClient.check_access()`
- Added `BaseAutomationClient.server_reachable()`
- Removed `LocalWatcher.get_windows_queue_threshold()`
- Removed `LocalWatcher.set_windows_queue_threshold()`
- Added `Manager.open_metadata_window()`
- Removed `WindowsIntegration.register_desktop_link()`
- Removed `WindowsIntegration.unregister_desktop_link()`
- Added utils.py::`get_device()`
- Removed utils.py::`DEFAULT_ENCODING`
- Removed utils.py::`WIN32_SUFFIX`
- Removed wui/metadata.py

# 2.5.5
- Removed `LocalClient.is_osxbundle()`
- Removed `Manager.is_updated()`. Use `updated` attribute instead.
- Changed `WebSettingsApi.update_token()`. No more static.
- Moved engine/watcher/local_watcher.py::`normalize_event_filename()` to utils.py

# 2.5.4
- Moved `RemoteDocumentClient.activate_profile()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.add_to_locally_edited_collection()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.deactivate_profile()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.get_collection_members()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.get_repository_names()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.make_file_in_user_workspace()` `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.mass_import()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.result_set_query()` to `RemoteDocumentClientForTests`
- Moved `RemoteDocumentClient.wait_for_async_and_es_indexing()` to `RemoteDocumentClientForTests`

# 2.5.2
- Added `enrichers` keyword to `BaseAutomationClient.execute()`
- Added `force` keyword to `Engine.local_rollback()`
- Added `dynamic_states` keyword to `EngineDAO.synchronize_state()`
- Added `**kwargs` keyword to `RemoteDocumentClient.fetch()`
- Removed `RestAPIClient.fetch()`
- Removed `RestAPIClient.is_locked()`
- Removed `RestAPIClient.log_on_server()`
- Added `RemoteDocumentClient.create_user()`
- Added `RemoteDocumentClient.log_on_server()`
- Added `RemoteDocumentClient.is_locked()`
- Removed `RootAlreadyBindWithDifferentAccount.get_username()`. Use `username` attribute instead.
- Removed `RootAlreadyBindWithDifferentAccount.get_url()`. Use `url` attribute instead.
- Added utils.py::`guess_server_url()`
- Moved wui/settings.py::`DRIVE_STARTUP_PAGE` to client/common.py
- Removed local_watcher.py::`is_office_file()`
- Removed utils.py::`deprecated()`

# 2.5.1
- Removed `Application._get_debug_dialog()`
- Removed `Application.update_tooltip()`

# 2.5.0
- Removed `AbstractOSIntegration.get_zoom_factor()`. Use `zoom_factor` attribute instead. It is a property on Windows.
- Changed `Application.get_mac_app()` to static
- Changed `Application._message_clicked()` to `message_clicked()`
- Removed `Application.get_default_tooltip()` . Use `default_tooltip` attribute instead.
- Removed `Application.get_icon_state()`. Use `icon_state` attribute instead.
- Removed `Application.get_systray_menu()`
- Removed `Application.show_message()`
- Removed `DriveScript.set_engine_uid()`. Use `engine_uid` attribute instead.
- Removed `DriveSystrayIcon._show_popup()`
- Removed `DriveSystrayIcon.showMessage()`
- Removed `Engine.get_local_folder()`. Use `local_folder` attribute instead.
- Removed `Engine.get_remote_user()`. Use `remote_user` property instead.
- Removed `Engine.get_server_url()`. Use `server_url` property instead.
- Removed `Engine.get_uid()`. Use `uid` attribute instead.
- Changed `FolderTreeview.loadChildren()` to `load_children()`
- Changed `FolderTreeview.loadChildrenThread()` to `load_children_thread()`
- Changed `FolderTreeview.resolveItemDownChanged()` to `resolve_item_down_changed()`
- Changed `FolderTreeview.resolveItemUpChanged()` to `resolve_item_up_changed()`
- Changed `FolderTreeview.setClient()` method to `set_client()`
- Changed `FolderTreeview.sortChildren()` to `sort_children()`
- Changed `FolderTreeview.updateItemChanged()` to `update_item_changed()`
- Removed `FolderTreeview.get_dirty_items()`. Use `dirty_items` attribute instead.
- Removed `FolderTreeview.getLoadingOverlay()`
- Removed `FolderTreeview.loadFinished()`
- Removed `Manager._create_notification_service()`
- Removed `Manager.get_appname()`. Use `app_name` attribute instead.
- Removed `Manager.get_direct_edit()`. Use `direct_edit` attribute instead.
- Removed `Manager.get_notification_service()`. Use `notification_service` property instead.
- Removed `Manager.get_osi()`. Use `osi` attribute instead.
- Removed `Manager.is_debug()`. Use `debug` attribute instead.
- Removed `Notification.get_action()`. Use `action` attribute instead.
- Removed `Notification.get_engine_uid()`. Use `engine_uid` attribute instead.
- Removed `Notification.get_description()`. Use `description` attribute instead.
- Removed `Notification.get_flags()`. Use `flags` attribute instead.
- Removed `Notification.get_level()`. Use `level` attribute instead.
- Removed `Notification.get_title()`. Use `title` attribute instead.
- Removed `Notification.get_uid()`. Use `uid` attribute instead.
- Removed `Overlay.paintEvent()`
- Removed `SimpleApplication._get_skin()`. Use `skin` attribute instead.
- Changed `StatusTreeview.loadChildren()` to `load_children()`
- Removed `StatusTreeview.getLoadingOverlay()`
- Removed `StatusTreeview.loadFinished()`
- Changed `WebDialog._attachJsApi()` to `attachJsApi()`
- Changed `WebDialog._set_proxy()` to static
- Changed `WebDialog._sslErrorHandler()` to static `_ssl_error_handler()`
- Removed `WebDialog.__del__()`
- Removed `WebDialog.get_frame()`. Use `frame` attribute instead.
- Removed `WebDialog.get_view()`. Use `view` attribute instead.
- Removed `WebDialog.set_token()`. Use `token` attribute instead.
- Removed `WebDialog.show()`
- Removed `WebDriveApi.get_dialog()`. Use `dialog` attribute instead.
- Removed `WebDriveApi.set_dialog()`. Use `dialog` attribute instead.
- Removed `WebDriveApi.set_last_url()`. Use `last_url` attribute instead.
- Removed `WebMetadataApi.set_last_error()`. Use `error` attribute instead.
- Changed `WebSettingsApi.update_token` method to static
- Removed `start_engine`, `check_fs` and `token` keywords from `WebSettingsApi._bind_server()`. Use `kwargs.get(arg, default)` instead.
- Removed `check_fs` and `token` keywords from `WebSettingsApi.bind_server()`. Use `kwargs.get(arg, default)` instead.
- Removed `local_folder`, `url`, `username`, `password`, `name`, `check_fs` and `token` keywords from `WebSettingsApi.bind_server_async()`. Use `kwargs.get(arg, default)` instead.
- Removed `config`, `server`, `authenticated`, `username`, `password` and `pac_url` keywords from `WebSettingsApi.set_proxy_settings_async()`. Use `args` instead.
- Removed `local_folder`, `server_url` and `engine_name` keywords from `WebSettingsApi.web_authentication()`. Use `args` instead.
- Removed `WebSystray.close()`
- Removed `WebSystray.dialogDeleted()`
- Removed `WebSystray.focusOutEvent()`
- Removed `WebSystray.resizeEvent()`
- Removed `WebSystray.shouldHide()`
- Removed `WebSystray.show()`
- Removed `WebSystray.underMouse()`
- Removed `WebSystrayApi._create_advanced_menu()`
- Removed `WebSystrayApi.open_about()`
- Changed `WebSystrayView.replace()` to `resize_and_move()`
- Removed `Worker.get_action()`. Use `action` property instead.
- Changed utils.py::`is_office_temp_file()` to `is_generated_tmp_file()`. It now returns `tuple(bool, bool)`.

# 2.4.8
- Removed `size`, `digest_func`, `check_suspended` and `remote_ref` keywords from `FileInfo.__init__()`. Use `kwargs.get(arg, default)` instead.
- Removed `digest_func`, `ignored_prefixe`, `ignored_suffixes`, `check_suspended`, `case_sensitive` and `disable_duplication` keywords from `LocalClient.__init__()`. Use `kwargs.get(arg, default)` instead.

# 2.4.7
- Changed `AbstractOSIntegration.get_zoom_factor()` to static
- Changed `AbstractOSIntegration.is_partition_supported()` to static
- Changed `AbstractOSIntegration.is_same_partition()` to static
- Changed `DarwinIntegration._find_item_in_list()` to static
- Changed `DarwinIntegration._get_favorite_list()` to static
- Changed `WindowsIntegration._get_desktop_folder()` to static

# 2.4.6
- Removed `mark_unknown` keyword from `RemoteWatcher._do_scan_remote()`
- Removed `Tracker.get_user_agent()`. Use `user_agent` property instead.
