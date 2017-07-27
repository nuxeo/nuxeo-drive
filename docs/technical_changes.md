# dev

# 2.4.9
- Removed `start_engine`, `check_fs` and `token` arguments from `_bind_server()` method in `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `local_folder`, `url`, `username`, `password`, `name`, `check_fs` and `token` arguments from `bind_server_async()` method in `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `check_fs` and `token` from `bind_server` method of `WebSettingsApi` class. Use `kwargs.get(arg, default)` instead.
- Removed `local_folder`, `server_url` and `engine_name` arguments from `web_authentication` method in `WebSettingsApi` class. Use `args` instead.
- Removed `config`, `server`, `authenticated`, username, password and pac_url from `set_proxy_settings_async` method in `WebSettingsApi` class. Use `args` instead.
- Changed `update_token` method to `static` in `WebSettingsApi` class
- Changed `is_office_temp_file()` function to `is_generated_tmp_file()` in utils.py. It now returns `tuple(bool, bool)`.

# 2.4.8
- Removed `size`, `digest_func`, `check_suspended` and `remote_ref` arguments from `FileInfo` class. Use `kwargs.get(arg, default)` instead.
- Removed `digest_func`, `ignored_prefixe`, `ignored_suffixes`, `check_suspended`, `case_sensitive` and `disable_duplication` arguments from `LocalClient` class. Use `kwargs.get(arg, default)` instead.

# 2.4.7
- Changed `get_zoom_factor()` method to `static` in `AbstractOSIntegration` class
- Changed `is_partition_supported()` method to `static` in `AbstractOSIntegration` class
- Changed `is_same_partition()` method to `static` in `AbstractOSIntegration` class
- Changed `_find_item_in_list()` method to `static` in `DarwinIntegration` class
- Changed `_get_favorite_list()` method to `static` in `DarwinIntegration` class
- Changed `_get_desktop_folder()` method to `static` in `WindowsIntegration` class

# 2.4.6
- Removed `mark_unknown` keyword from `RemoteWatcher._do_scan_remote()` method
- Removed `get_user_agent()` method from `Tracker` class. Use `user_agent` property instead.
