# dev
- Renamed `is_office_temp_file()` function to `is_generated_tmp_file()` in utils.py

# 2.4.8
- Removed `size`, `digest_func`, `check_suspended` and `remote_ref` arguments from `FileInfo` class. Use `kwargs.get(arg, default)` instead.
- Removed `digest_func`, `ignored_prefixe`, `ignored_suffixes`, `check_suspended`, `case_sensitive` and `disable_duplication` arguments from `LocalClient` class. Use `kwargs.get(arg, default)` instead.
- Added `_remove_remote_id_windows()` method to `LocalClient` class
- Added `_remove_remote_id_unix()` method to `LocalClient` class

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
- Added `make_tree()` method to `LocalClient` class.
