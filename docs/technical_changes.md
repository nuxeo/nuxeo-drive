# dev
- Changed `update_token` method in `WebSettingsApi` class. No more `static.`
- Removed `is_osxbundle()` method from `LocalClient` class
- Removed `is_updated()` method from `Manager` class. Use `updated` attribute instead.
- Moved `normalize_event_filename()` function from engine/watcher/local_watcher.py to utils.py

# 2.5.4
- Moved `get_repository_names()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `make_file_in_user_workspace()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `activate_profile()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `deactivate_profile()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `add_to_locally_edited_collection()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `get_collection_members()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `mass_import()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `wait_for_async_and_es_indexing()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests
- Moved `result_set_query()` method from `RemoteDocumentClient` class to `RemoteDocumentClientForTests` class, only for tests

# 2.5.2
- Removed `is_office_file()` function from local_watcher.py
- Added `dynamic_states` keyword to `synchronize_state()` method in `EngineDAO` class
- Added `force` keyword to `local_rollback()` method in `Engine` class
- Removed `get_username()` method from `RootAlreadyBindWithDifferentAccount` class. Use `username` attribute instead.
- Removed `get_url()` method from `RootAlreadyBindWithDifferentAccount` class. Use `url` attribute instead.
- Removed `deprecated()` function from utils.py
- Added `guess_server_url()` function to utils.py
- Moved `DRIVE_STARTUP_PAGE` constant from wui/settings.py to client/common.py
- Added `enrichers` keyword to `execute()` method in `BaseAutomationClient` class
- Added `**kwargs` keyword to `fetch()` method in `RemoteDocumentClient` class
- Removed `fetch()` method from `RestAPIClient` class
- Removed `is_locked()` method from `RestAPIClient` class
- Removed `log_on_server()` method from `RestAPIClient` class
- Added `log_on_server()` method to `RemoteDocumentClient` class
- Added `is_locked()` method to `RemoteDocumentClient` class
- Added `create_user()` method to `RemoteDocumentClient` class

# 2.5.1
- Removed `update_tooltip()` method from `Application` class
- Removed `_get_debug_dialog()` method from `Application` class

# 2.5.0
- Removed `start_engine`, `check_fs` and `token` keywords from `_bind_server()` method in `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `local_folder`, `url`, `username`, `password`, `name`, `check_fs` and `token` keywords from `bind_server_async()` method in `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `check_fs` and `token` keywords from `bind_server` method of `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `local_folder`, `server_url` and `engine_name` keywords from `web_authentication` method in `WebSettingsApi` class. Use `args` instead.
- Removed `config`, `server`, `authenticated`, `username`, `password` and `pac_url` keywords from `set_proxy_settings_async()` method in `WebSettingsApi` class. Use `args` instead.
- Removed `get_local_folder()` method from `Engine` class. Use `local_folder` attribute instead.
- Removed `get_uid()` method from `Engine` class. Use `uid` attribute instead.
- Removed `get_server_url()` method from `Engine` class. Use `server_url` property instead.
- Removed `get_remote_user()` method from `Engine` class. Use `remote_user` property instead.
- Removed `get_action()` method from `Worker` class. Use `action` property instead.
- Removed `paintEvent()` method from `Overlay` class
- Removed `get_appname()` method from `Manager` class. Use `app_name` attribute instead.
- Removed `get_notification_service()` method from `Manager` class. Use `notification_service` property instead.
- Removed `get_direct_edit()` method from `Manager` class. Use `direct_edit` attribute instead.
- Removed `get_osi()` method from `Manager` class. Use `osi` attribute instead.
- Removed `is_debug()` method from `Manager` class. Use `debug` attribute instead.
- Removed `_create_notification_service()` method from `Manager` class
- Removed `get_flags()` method from `Notification` class. Use `flags` attribute instead.
- Removed `get_engine_uid()` method from `Notification` class. Use `engine_uid` attribute instead.
- Removed `get_action()` method from `Notification` class. Use `action` attribute instead.
- Removed `get_uid()` method from `Notification` class. Use `uid` attribute instead.
- Removed `get_level()` method from `Notification` class. Use `level` attribute instead.
- Removed `get_title()` method from `Notification` class. Use `title` attribute instead.
- Removed `get_description()` method from `Notification` class. Use `description` attribute instead.
- Removed `get_zoom_factor()` method from `AbstractOSIntegration` class. Use `zoom_factor` attribute instead. It is a property on Windows.
- Removed `set_engine_uid()` method from `DriveScript` class. Use `engine_uid` attribute instead.
- Removed `_get_skin()` method from `SimpleApplication` class. Use `skin` attribute instead.
- Removed `get_default_tooltip()` method from `Application` class. Use `default_tooltip` attribute instead.
- Removed `get_icon_state()` method from `Application` class. Use `icon_state` attribute instead.
- Removed `show_message()` method from `Application` class
- Removed `get_systray_menu()` method from `Application` class
- Removed `get_dialog()` method from `WebDriveApi` class. Use `dialog` attribute instead.
- Removed `set_dialog()` method from `WebDriveApi` class. Use `dialog` attribute instead.
- Removed `set_last_url()` method from `WebDriveApi` class. Use `last_url` attribute instead.
- Removed `set_token()` method from `WebDialog` class. Use `token` attribute instead.
- Removed `get_frame()` method from `WebDialog` class. Use `frame` attribute instead.
- Removed `get_view()` method from `WebDialog` class. Use `view` attribute instead.
- Removed `show()` method from `WebDialog` class
- Removed `__del__()` method from `WebDialog` class
- Removed `set_last_error()` method from `WebMetadataApi` class. Use `error` attribute instead.
- Removed `getLoadingOverlay()` method from `FolderTreeview` class
- Removed `loadFinished()` method from `FolderTreeview` class
- Removed `get_dirty_items()` method from `FolderTreeview` class. Use `dirty_items` attribute instead.
- Removed `getLoadingOverlay()` method from `StatusTreeview` class
- Removed `loadFinished()` method from `StatusTreeview` class
- Removed `showMessage()` method from `DriveSystrayIcon` class
- Removed `_show_popup()` method from `DriveSystrayIcon` class
- Removed `open_about()` method from `WebSystrayApi` class
- Removed `_create_advanced_menu()` method from `WebSystrayApi` class
- Removed `show()` method from `WebSystrayView` class
- Removed `underMouse()` method from `WebSystrayView` class
- Removed `shouldHide()` method from `WebSystrayView` class
- Removed `focusOutEvent()` method from `WebSystrayView` class
- Removed `resizeEvent()` method from `WebSystrayView` class
- Removed `close()` method from `WebSystrayView` class
- Removed `dialogDeleted()` method from `WebSystray` class
- Changed `update_token` method to `static` in `WebSettingsApi` class
- Changed `is_office_temp_file()` function to `is_generated_tmp_file()` in utils.py. It now returns `tuple(bool, bool)`.
- Changed `get_mac_app()` method to `static` in `Application` class
- Changed `_message_clicked()` method to `message_clicked()` in `Application` class
- Changed `_sslErrorHandler()` method to static `_ssl_error_handler()` in `WebDialog` class
- Changed `_set_proxy()` method to `static` in `WebDialog` class
- Changed `_attachJsApi()` method to `attachJsApi()` in `WebDialog` class
- Changed `replace()` method to `resize_and_move()` in `WebSystrayView` class
- Changed `loadChildren()` method to `load_children()` in `FolderTreeview` class
- Changed `resolveItemUpChanged()` method to `resolve_item_up_changed()` in `FolderTreeview` class
- Changed `updateItemChanged()` method to `update_item_changed()` in `FolderTreeview` class
- Changed `resolveItemDownChanged()` method to `resolve_item_down_changed()` in `FolderTreeview` class
- Changed `setClient()` method to `set_client()` in `FolderTreeview` class
- Changed `sortChildren()` method to `sort_children()` in `FolderTreeview` class
- Changed `loadChildrenThread()` method to `load_children_thread()` in `FolderTreeview` class
- Changed `loadChildren()` method to `load_children()` in `StatusTreeview` class

# 2.4.8
- Removed `size`, `digest_func`, `check_suspended` and `remote_ref` keywords from `FileInfo` class. Use `kwargs.get(arg, default)` instead.
- Removed `digest_func`, `ignored_prefixe`, `ignored_suffixes`, `check_suspended`, `case_sensitive` and `disable_duplication` keywords from `LocalClient` class. Use `kwargs.get(arg, default)` instead.

# 2.4.7
- Changed `get_zoom_factor()` method to `static` in `AbstractOSIntegration` class
- Changed `is_partition_supported()` method to `static` in `AbstractOSIntegration` class
- Changed `is_same_partition()` method to `static` in `AbstractOSIntegration` class
- Changed `_find_item_in_list()` method to `static` in `DarwinIntegration` class
- Changed `_get_favorite_list()` method to `static` in `DarwinIntegration` class
- Changed `_get_desktop_folder()` method to `static` in `WindowsIntegration` class

# 2.4.6
- Removed `mark_unknown` keyword from `_do_scan_remote()` method in `RemoteWatcher` class
- Removed `get_user_agent()` method from `Tracker` class. Use `user_agent` property instead.
