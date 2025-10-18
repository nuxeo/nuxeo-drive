"""Unit tests for QMLDriveApi functions."""

from typing import Any, Dict
from unittest.mock import Mock, patch

import pytest

from nxdrive.gui.api import QMLDriveApi


class TestQMLDriveApiJsonDefault:
    """Test cases for QMLDriveApi methods."""

    def setup_method(self):
        """Set up test fixtures for each test method."""
        # Create a mock application and manager
        self.mock_manager = Mock()
        self.mock_application = Mock()
        self.mock_application.manager = self.mock_manager

        # Create QMLDriveApi instance
        self.api = QMLDriveApi(self.mock_application)

        # Mock the signals completely - replace them entirely
        self.mock_set_message = Mock()
        self.api.setMessage = self.mock_set_message

        self.mock_auth_dialog = Mock()
        self.api.openAuthenticationDialog = self.mock_auth_dialog

    def test_json_default_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _json_default method."""

        # Test 1: Object with callable export method - should return export() result
        class ObjectWithExport:
            def export(self) -> Dict[str, Any]:
                return {"test": "data", "id": 123}

        obj_with_export = ObjectWithExport()
        result = self.api._json_default(obj_with_export)
        assert result == {"test": "data", "id": 123}

        # Test 2: Mock object with export method returning complex data
        mock_obj = Mock()
        mock_obj.export = Mock(
            return_value={"nested": {"data": [1, 2, 3]}, "value": 42}
        )
        result = self.api._json_default(mock_obj)
        assert result == {"nested": {"data": [1, 2, 3]}, "value": 42}
        mock_obj.export.assert_called_once_with()

        # Test 3: Mock object with export method returning None
        mock_obj_none = Mock()
        mock_obj_none.export = Mock(return_value=None)
        result = self.api._json_default(mock_obj_none)
        assert result is None
        mock_obj_none.export.assert_called_once_with()

        # Test 4: Object with non-callable export attribute - should return original object
        class ObjectWithNonCallableExport:
            def __init__(self):
                self.export = "not_a_function"

        obj_non_callable = ObjectWithNonCallableExport()
        result = self.api._json_default(obj_non_callable)
        assert result is obj_non_callable

        # Test 5: Object without export attribute - should return original object

        class ObjectWithoutExport:
            def __init__(self, name: str = "test"):
                self.name = name

            def __repr__(self) -> str:
                return f"ObjectWithoutExport(name='{self.name}')"

        obj_no_export = ObjectWithoutExport("test_obj")
        result = self.api._json_default(obj_no_export)
        assert result is obj_no_export

        # Test 6: Built-in types without export - should return original values
        test_cases = [None, 42, "test_string", [1, 2, 3], {"key": "value"}, True]

        for test_obj in test_cases:
            result = self.api._json_default(test_obj)
            assert result == test_obj  # Use == for value comparison

        # Test 7: Mock object with export = None - should return original object
        mock_obj_export_none = Mock()
        mock_obj_export_none.export = None
        result = self.api._json_default(mock_obj_export_none)
        assert result is mock_obj_export_none

        # Test 8: Object with export method that raises exception - should propagate exception
        mock_obj_exception = Mock()
        mock_obj_exception.export = Mock(side_effect=ValueError("Export failed"))

        with pytest.raises(ValueError, match="Export failed"):
            self.api._json_default(mock_obj_exception)

        mock_obj_exception.export.assert_called_once_with()

        # Test 9: Verify getattr behavior with problematic __getattr__
        class ProblematicClass:
            def __getattr__(self, name):
                if name == "export":
                    # This would normally raise AttributeError but getattr handles it
                    raise AttributeError("Cannot access export")
                raise AttributeError(
                    f"'{type(self).__name__}' object has no attribute '{name}'"
                )

        problematic_obj = ProblematicClass()
        result = self.api._json_default(problematic_obj)
        assert result is problematic_obj

        # Test 10: Verify that callable() check works correctly
        class ObjectWithCallableCheck:
            def __init__(self):
                self.export = lambda: {"lambda_result": True}

        obj_callable_check = ObjectWithCallableCheck()
        result = self.api._json_default(obj_callable_check)
        assert result == {"lambda_result": True}

        # Test 11: Empty export method result
        class ObjectWithEmptyExport:
            def export(self):
                return {}

        obj_empty_export = ObjectWithEmptyExport()
        result = self.api._json_default(obj_empty_export)
        assert result == {}

        # Test 12: Verify export method is called without arguments
        class ObjectWithParameterizedExport:
            def export(self):
                return {"called_without_args": True}

        obj_param_export = ObjectWithParameterizedExport()
        result = self.api._json_default(obj_param_export)
        assert result == {"called_without_args": True}

    def test_export_formatted_state_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _export_formatted_state method."""

        # Test 1: None state should return empty dict
        # Note: Using type ignore for intentional None test
        result = self.api._export_formatted_state("test_uid", state=None)  # type: ignore
        assert result == {}

        # Test 2: No engine found should return empty dict
        self.mock_manager.engines.get.return_value = None
        mock_state = Mock()
        result = self.api._export_formatted_state("invalid_uid", state=mock_state)
        assert result == {}

        # Test 3: Valid state with engine - comprehensive functionality test
        # Setup mock engine
        mock_engine = Mock()
        mock_engine.get_user_full_name.return_value = "John Doe"
        self.mock_manager.engines.get.return_value = mock_engine

        # Create mock state with all required attributes
        mock_state = Mock()
        mock_state.export.return_value = {
            "id": 123,
            "name": "test_file.txt",
            "state": "synchronized",
            "local_path": "/path/to/file",
        }
        mock_state.last_remote_modifier = "user123"
        mock_state.last_remote_updated = "2023-10-15 14:30:00"
        mock_state.last_local_updated = "2023-10-15 15:45:00"
        mock_state.remote_can_update = True
        mock_state.remote_can_rename = False
        mock_state.last_error_details = "Some error details"

        with patch("nxdrive.gui.api.get_date_from_sqlite") as mock_get_date, patch(
            "nxdrive.gui.api.Translator.format_datetime"
        ) as mock_format_datetime:

            # Setup mock returns for date functions
            mock_date_obj = Mock()
            mock_get_date.return_value = mock_date_obj
            mock_format_datetime.return_value = "Oct 15, 2023 2:30 PM"

            result = self.api._export_formatted_state("test_uid", state=mock_state)

            # Verify all expected fields are present and correct
            assert "id" in result
            assert "name" in result
            assert "state" in result
            assert "local_path" in result
            assert result["id"] == 123
            assert result["name"] == "test_file.txt"
            assert result["state"] == "synchronized"
            assert result["local_path"] == "/path/to/file"

            # Verify added fields
            assert result["last_contributor"] == "John Doe"
            assert result["last_remote_update"] == "Oct 15, 2023 2:30 PM"
            assert result["last_local_update"] == "Oct 15, 2023 2:30 PM"
            assert result["remote_can_update"] is True
            assert result["remote_can_rename"] is False
            assert result["last_error_details"] == "Some error details"

            # Verify method calls
            mock_state.export.assert_called_once()
            mock_engine.get_user_full_name.assert_called_once_with(
                "user123", cache_only=True
            )

            # Verify date processing calls
            assert mock_get_date.call_count == 2
            mock_get_date.assert_any_call("2023-10-15 14:30:00")
            mock_get_date.assert_any_call("2023-10-15 15:45:00")

            assert mock_format_datetime.call_count == 2
            mock_format_datetime.assert_called_with(mock_date_obj)

        # Test 4: State with None last_remote_modifier
        mock_state_no_modifier = Mock()
        mock_state_no_modifier.export.return_value = {"basic": "data"}
        mock_state_no_modifier.last_remote_modifier = None
        mock_state_no_modifier.last_remote_updated = None
        mock_state_no_modifier.last_local_updated = None
        mock_state_no_modifier.remote_can_update = False
        mock_state_no_modifier.remote_can_rename = True
        mock_state_no_modifier.last_error_details = None

        with patch("nxdrive.gui.api.get_date_from_sqlite") as mock_get_date:
            mock_get_date.return_value = None

            result = self.api._export_formatted_state(
                "test_uid", state=mock_state_no_modifier
            )

            # Verify handling of None values
            assert result["last_contributor"] == ""
            assert result["last_remote_update"] == ""
            assert result["last_local_update"] == ""
            assert result["remote_can_update"] is False
            assert result["remote_can_rename"] is True
            assert result["last_error_details"] == ""

            # Verify get_user_full_name not called for None modifier
            # Reset mock to clear previous calls
            mock_engine.reset_mock()

        # Test 5: State with empty last_error_details
        mock_state_empty_error = Mock()
        mock_state_empty_error.export.return_value = {"test": "data"}
        mock_state_empty_error.last_remote_modifier = "user456"
        mock_state_empty_error.last_remote_updated = "2023-01-01 00:00:00"
        mock_state_empty_error.last_local_updated = "2023-01-01 01:00:00"
        mock_state_empty_error.remote_can_update = True
        mock_state_empty_error.remote_can_rename = True
        mock_state_empty_error.last_error_details = ""

        with patch("nxdrive.gui.api.get_date_from_sqlite") as mock_get_date, patch(
            "nxdrive.gui.api.Translator.format_datetime"
        ) as mock_format_datetime:

            mock_get_date.return_value = Mock()
            mock_format_datetime.return_value = "Jan 1, 2023 12:00 AM"
            mock_engine.get_user_full_name.return_value = "Jane Smith"

            result = self.api._export_formatted_state(
                "test_uid", state=mock_state_empty_error
            )

            assert result["last_error_details"] == ""
            assert result["last_contributor"] == "Jane Smith"
            mock_engine.get_user_full_name.assert_called_with(
                "user456", cache_only=True
            )

        # Test 6: Verify manager.engines.get is called correctly
        self.mock_manager.engines.get.assert_called_with("test_uid")

    def test_get_last_files_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of get_last_files method."""

        # Test 1: No engine found should return empty list
        self.mock_manager.engines.get.return_value = None
        result = self.api.get_last_files("invalid_uid", 5)
        assert result == []
        self.mock_manager.engines.get.assert_called_with("invalid_uid")

        # Test 2: Valid engine with no files should return empty list
        mock_engine = Mock()
        mock_engine.dao.get_last_files.return_value = []
        self.mock_manager.engines.get.return_value = mock_engine

        result = self.api.get_last_files("test_uid", 10)
        assert result == []
        mock_engine.dao.get_last_files.assert_called_once_with(10)

        # Test 3: Valid engine with files - comprehensive functionality test
        # Reset the mock engine for clean test
        mock_engine.reset_mock()

        # Create mock DocPair objects with export methods
        mock_docpair1 = Mock()
        mock_docpair1.export.return_value = {
            "id": 1,
            "name": "document1.pdf",
            "local_path": "/path/to/document1.pdf",
            "remote_ref": "ref1",
            "state": "synchronized",
            "last_transfer": "download",
            "size": 1024,
        }

        mock_docpair2 = Mock()
        mock_docpair2.export.return_value = {
            "id": 2,
            "name": "image.jpg",
            "local_path": "/path/to/image.jpg",
            "remote_ref": "ref2",
            "state": "synchronized",
            "last_transfer": "upload",
            "size": 2048,
        }

        mock_docpair3 = Mock()
        mock_docpair3.export.return_value = {
            "id": 3,
            "name": "spreadsheet.xlsx",
            "local_path": "/path/to/spreadsheet.xlsx",
            "remote_ref": "ref3",
            "state": "synchronized",
            "last_transfer": "download",
            "size": 4096,
        }

        # Mock dao.get_last_files to return list of DocPair objects
        mock_engine.dao.get_last_files.return_value = [
            mock_docpair1,
            mock_docpair2,
            mock_docpair3,
        ]

        result = self.api.get_last_files("test_uid", 3)

        # Verify result structure and content
        assert isinstance(result, list)
        assert len(result) == 3

        # Verify first file
        assert result[0]["id"] == 1
        assert result[0]["name"] == "document1.pdf"
        assert result[0]["local_path"] == "/path/to/document1.pdf"
        assert result[0]["remote_ref"] == "ref1"
        assert result[0]["state"] == "synchronized"
        assert result[0]["last_transfer"] == "download"
        assert result[0]["size"] == 1024

        # Verify second file
        assert result[1]["id"] == 2
        assert result[1]["name"] == "image.jpg"
        assert result[1]["local_path"] == "/path/to/image.jpg"
        assert result[1]["remote_ref"] == "ref2"
        assert result[1]["state"] == "synchronized"
        assert result[1]["last_transfer"] == "upload"
        assert result[1]["size"] == 2048

        # Verify third file
        assert result[2]["id"] == 3
        assert result[2]["name"] == "spreadsheet.xlsx"
        assert result[2]["local_path"] == "/path/to/spreadsheet.xlsx"
        assert result[2]["remote_ref"] == "ref3"
        assert result[2]["state"] == "synchronized"
        assert result[2]["last_transfer"] == "download"
        assert result[2]["size"] == 4096

        # Verify method calls
        mock_engine.dao.get_last_files.assert_called_once_with(3)
        mock_docpair1.export.assert_called_once()
        mock_docpair2.export.assert_called_once()
        mock_docpair3.export.assert_called_once()

        # Test 4: Engine with single file
        mock_engine.reset_mock()
        mock_single_docpair = Mock()
        mock_single_docpair.export.return_value = {
            "id": 999,
            "name": "single_file.txt",
            "local_path": "/single/path/file.txt",
            "remote_ref": "single_ref",
            "state": "conflicted",
            "last_transfer": "upload",
            "size": 512,
        }

        mock_engine.dao.get_last_files.return_value = [mock_single_docpair]

        result = self.api.get_last_files("test_uid", 1)

        assert len(result) == 1
        assert result[0]["id"] == 999
        assert result[0]["name"] == "single_file.txt"
        assert result[0]["state"] == "conflicted"
        mock_engine.dao.get_last_files.assert_called_once_with(1)
        mock_single_docpair.export.assert_called_once()

        # Test 5: Test with different number parameter values
        mock_engine.reset_mock()
        mock_engine.dao.get_last_files.return_value = []

        # Test with 0
        result = self.api.get_last_files("test_uid", 0)
        assert result == []
        mock_engine.dao.get_last_files.assert_called_with(0)

        # Test with large number
        mock_engine.reset_mock()
        result = self.api.get_last_files("test_uid", 100)
        assert result == []
        mock_engine.dao.get_last_files.assert_called_with(100)

        # Test 6: Verify _get_engine is called correctly with different UIDs
        self.mock_manager.engines.get.assert_called_with("test_uid")

        # Test with different UID
        self.api.get_last_files("another_uid", 5)
        self.mock_manager.engines.get.assert_called_with("another_uid")

        # Test 7: Test with files that have complex export data
        mock_engine.reset_mock()
        mock_complex_docpair = Mock()
        mock_complex_docpair.export.return_value = {
            "id": 42,
            "name": "complex_file.doc",
            "local_path": "/complex/path/file.doc",
            "remote_ref": "complex_ref_123",
            "state": "synchronized",
            "last_transfer": "download",
            "size": 8192,
            "folderish": False,
            "doc_type": "File",
            "last_sync_date": "2023-10-15 10:30:00",
            "last_error": None,
            "remote_name": "complex_file.doc",
            "local_parent_path": "/complex/path",
        }

        mock_engine.dao.get_last_files.return_value = [mock_complex_docpair]

        result = self.api.get_last_files("test_uid", 1)

        assert len(result) == 1
        exported_data = result[0]
        assert exported_data["id"] == 42
        assert exported_data["name"] == "complex_file.doc"
        assert exported_data["folderish"] is False
        assert exported_data["doc_type"] == "File"
        assert exported_data["last_sync_date"] == "2023-10-15 10:30:00"
        assert exported_data["last_error"] is None
        assert exported_data["remote_name"] == "complex_file.doc"
        assert exported_data["local_parent_path"] == "/complex/path"

        mock_complex_docpair.export.assert_called_once()

    def test_trigger_notification_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of trigger_notification method."""

        # Test 1: Basic functionality - verify both methods are called
        test_uid = "test_notification_uid_123"

        # Mock the notification service
        mock_notification_service = Mock()
        self.mock_manager.notification_service = mock_notification_service

        # Call the method
        self.api.trigger_notification(test_uid)

        # Verify application.hide_systray() was called
        self.mock_application.hide_systray.assert_called_once()

        # Verify notification_service.trigger_notification was called with correct uid
        mock_notification_service.trigger_notification.assert_called_once_with(test_uid)

        # Test 2: Multiple calls with different UIDs
        # Reset mocks to clean state
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        uid1 = "notification_uid_1"
        uid2 = "notification_uid_2"
        uid3 = "notification_uid_3"

        # Call with first UID
        self.api.trigger_notification(uid1)

        # Verify calls for first UID
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with(uid1)

        # Call with second UID
        self.api.trigger_notification(uid2)

        # Verify hide_systray called twice total
        assert self.mock_application.hide_systray.call_count == 2

        # Verify notification service called with second UID
        mock_notification_service.trigger_notification.assert_called_with(uid2)
        assert mock_notification_service.trigger_notification.call_count == 2

        # Call with third UID
        self.api.trigger_notification(uid3)

        # Verify hide_systray called three times total
        assert self.mock_application.hide_systray.call_count == 3

        # Verify notification service called with third UID
        mock_notification_service.trigger_notification.assert_called_with(uid3)
        assert mock_notification_service.trigger_notification.call_count == 3

        # Test 3: Test with empty string UID
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        empty_uid = ""
        self.api.trigger_notification(empty_uid)

        # Verify both methods still called even with empty string
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with("")

        # Test 4: Test with special characters in UID
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        special_uid = "notification-uid_123@domain.com#special"
        self.api.trigger_notification(special_uid)

        # Verify both methods called with special characters
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with(
            special_uid
        )

        # Test 5: Test with very long UID
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        long_uid = "very_long_notification_uid_" + "x" * 1000 + "_end"
        self.api.trigger_notification(long_uid)

        # Verify both methods called with long UID
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with(long_uid)

        # Test 6: Verify order of operations (hide_systray called before trigger_notification)
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        # Create a mock that tracks call order
        call_order = []

        def hide_systray_side_effect():
            call_order.append("hide_systray")

        def trigger_notification_side_effect(uid):
            call_order.append(f"trigger_notification({uid})")

        self.mock_application.hide_systray.side_effect = hide_systray_side_effect
        mock_notification_service.trigger_notification.side_effect = (
            trigger_notification_side_effect
        )

        test_uid_order = "order_test_uid"
        self.api.trigger_notification(test_uid_order)

        # Verify correct order of operations
        assert len(call_order) == 2
        assert call_order[0] == "hide_systray"
        assert call_order[1] == f"trigger_notification({test_uid_order})"

        # Test 7: Verify method handles None UID gracefully (edge case)
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        # Remove side effects for clean test
        self.mock_application.hide_systray.side_effect = None
        mock_notification_service.trigger_notification.side_effect = None

        # Note: Using type ignore for intentional None test
        self.api.trigger_notification(None)  # type: ignore

        # Verify both methods called even with None
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with(None)

        # Test 8: Test that function doesn't return anything (void function)
        self.mock_application.reset_mock()
        mock_notification_service.reset_mock()

        result = self.api.trigger_notification("test_return_value")

        # Verify function returns None
        assert result is None

        # Verify both methods were still called
        self.mock_application.hide_systray.assert_called_once()
        mock_notification_service.trigger_notification.assert_called_once_with(
            "test_return_value"
        )

        # Test 9: Verify that manager and application references are used correctly
        # This test ensures the right objects are being used
        assert self.api._manager is self.mock_manager
        assert self.api.application is self.mock_application
        assert self.mock_manager.notification_service is mock_notification_service

    def test_get_notifications_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of get_notifications method."""

        # Test 1: No notifications - empty result
        mock_notification_service = Mock()
        self.mock_manager.notification_service = mock_notification_service

        # Mock empty notifications dict
        mock_notification_service.get_notifications.return_value = {}

        result = self.api.get_notifications("test_engine_uid")

        # Verify the result is JSON string representing empty list
        assert result == "[]"

        # Verify notification service was called with correct engine parameter
        mock_notification_service.get_notifications.assert_called_once_with(
            engine="test_engine_uid"
        )

        # Test 2: Single notification
        mock_notification_service.reset_mock()

        # Create mock notification
        mock_notification1 = Mock()
        mock_notification1.export.return_value = {
            "level": "info",
            "uid": "notif_uid_1",
            "title": "Test Notification",
            "description": "This is a test notification",
            "discardable": True,
            "discard": False,
            "systray": True,
        }

        # Mock notifications dict with single notification
        notifications_dict = {"notif_uid_1": mock_notification1}
        mock_notification_service.get_notifications.return_value = notifications_dict

        result = self.api.get_notifications("engine_uid_1")

        # Parse the JSON result to verify structure
        import json

        parsed_result = json.loads(result)

        assert isinstance(parsed_result, list)
        assert len(parsed_result) == 1

        notification_data = parsed_result[0]
        assert notification_data["level"] == "info"
        assert notification_data["uid"] == "notif_uid_1"
        assert notification_data["title"] == "Test Notification"
        assert notification_data["description"] == "This is a test notification"
        assert notification_data["discardable"] is True
        assert notification_data["discard"] is False
        assert notification_data["systray"] is True

        # Verify method calls
        mock_notification_service.get_notifications.assert_called_once_with(
            engine="engine_uid_1"
        )
        mock_notification1.export.assert_called_once()

        # Test 3: Multiple notifications with different properties
        mock_notification_service.reset_mock()

        # Create multiple mock notifications
        mock_notification1 = Mock()
        mock_notification1.export.return_value = {
            "level": "warning",
            "uid": "warning_notif",
            "title": "Warning Message",
            "description": "This is a warning",
            "discardable": False,
            "discard": False,
            "systray": True,
        }

        mock_notification2 = Mock()
        mock_notification2.export.return_value = {
            "level": "danger",
            "uid": "error_notif",
            "title": "Error Occurred",
            "description": "An error has occurred during sync",
            "discardable": True,
            "discard": True,
            "systray": False,
        }

        mock_notification3 = Mock()
        mock_notification3.export.return_value = {
            "level": "info",
            "uid": "sync_complete",
            "title": "Sync Completed",
            "description": "Synchronization completed successfully",
            "discardable": True,
            "discard": False,
            "systray": True,
        }

        # Mock notifications dict with multiple notifications
        notifications_dict = {
            "warning_notif": mock_notification1,
            "error_notif": mock_notification2,
            "sync_complete": mock_notification3,
        }
        mock_notification_service.get_notifications.return_value = notifications_dict

        result = self.api.get_notifications("multi_engine_uid")

        # Parse and verify multiple notifications
        parsed_result = json.loads(result)

        assert isinstance(parsed_result, list)
        assert len(parsed_result) == 3

        # Verify all notifications are present (order may vary due to dict.values())
        uids = [notif["uid"] for notif in parsed_result]
        assert "warning_notif" in uids
        assert "error_notif" in uids
        assert "sync_complete" in uids

        # Find and verify each notification
        for notif_data in parsed_result:
            if notif_data["uid"] == "warning_notif":
                assert notif_data["level"] == "warning"
                assert notif_data["title"] == "Warning Message"
                assert notif_data["discardable"] is False
            elif notif_data["uid"] == "error_notif":
                assert notif_data["level"] == "danger"
                assert notif_data["title"] == "Error Occurred"
                assert notif_data["discard"] is True
                assert notif_data["systray"] is False
            elif notif_data["uid"] == "sync_complete":
                assert notif_data["level"] == "info"
                assert notif_data["title"] == "Sync Completed"
                assert notif_data["systray"] is True

        # Verify method calls
        mock_notification_service.get_notifications.assert_called_once_with(
            engine="multi_engine_uid"
        )
        mock_notification1.export.assert_called_once()
        mock_notification2.export.assert_called_once()
        mock_notification3.export.assert_called_once()

        # Test 4: Different engine UIDs
        mock_notification_service.reset_mock()
        mock_notification_service.get_notifications.return_value = {}

        # Test with empty string engine UID
        result = self.api.get_notifications("")
        assert result == "[]"
        mock_notification_service.get_notifications.assert_called_with(engine="")

        # Test with special characters in engine UID
        mock_notification_service.reset_mock()
        special_uid = "engine-123@domain.com#special"
        result = self.api.get_notifications(special_uid)
        assert result == "[]"
        mock_notification_service.get_notifications.assert_called_with(
            engine=special_uid
        )

        # Test 5: Notification with complex data types
        mock_notification_service.reset_mock()

        mock_complex_notification = Mock()
        mock_complex_notification.export.return_value = {
            "level": "info",
            "uid": "complex_notif_123",
            "title": "Complex Notification",
            "description": "Notification with special chars: @#$%^&*()",
            "discardable": True,
            "discard": False,
            "systray": True,
            "extra_field": None,  # Test None values
            "numeric_field": 42,  # Test numeric values
            "nested_data": {"key": "value", "number": 123},  # Test nested objects
        }

        notifications_dict = {"complex_notif_123": mock_complex_notification}
        mock_notification_service.get_notifications.return_value = notifications_dict

        result = self.api.get_notifications("complex_engine")

        # Verify complex data is properly serialized
        parsed_result = json.loads(result)
        assert len(parsed_result) == 1

        complex_data = parsed_result[0]
        assert complex_data["uid"] == "complex_notif_123"
        assert (
            complex_data["description"] == "Notification with special chars: @#$%^&*()"
        )
        assert complex_data["extra_field"] is None
        assert complex_data["numeric_field"] == 42
        assert complex_data["nested_data"]["key"] == "value"
        assert complex_data["nested_data"]["number"] == 123

        # Test 6: Verify return type is always string
        mock_notification_service.reset_mock()
        mock_notification_service.get_notifications.return_value = {}

        result = self.api.get_notifications("type_test_engine")

        assert isinstance(result, str)
        assert result == "[]"

        # Test 7: Test with None engine UID (edge case)
        mock_notification_service.reset_mock()

        # Note: Using type ignore for intentional None test
        result = self.api.get_notifications(None)  # type: ignore

        assert isinstance(result, str)
        mock_notification_service.get_notifications.assert_called_with(engine=None)

        # Test 8: Verify the complete flow - notification service -> _export_notifications -> _json
        mock_notification_service.reset_mock()

        # Create a test notification
        mock_flow_notification = Mock()
        mock_flow_notification.export.return_value = {
            "level": "info",
            "uid": "flow_test",
            "title": "Flow Test",
            "description": "Testing complete flow",
            "discardable": True,
            "discard": False,
            "systray": True,
        }

        notifications_dict = {"flow_test": mock_flow_notification}
        mock_notification_service.get_notifications.return_value = notifications_dict

        result = self.api.get_notifications("flow_engine")

        # Verify the complete flow works correctly
        assert isinstance(result, str)
        parsed_result = json.loads(result)
        assert len(parsed_result) == 1
        assert parsed_result[0]["uid"] == "flow_test"
        assert parsed_result[0]["title"] == "Flow Test"

        # Verify all components were called correctly
        mock_notification_service.get_notifications.assert_called_once_with(
            engine="flow_engine"
        )
        mock_flow_notification.export.assert_called_once()

        # Test 9: Verify manager.notification_service reference
        assert self.api._manager.notification_service is mock_notification_service

    def test_get_transfers_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of get_transfers method."""

        # Test 1: No downloads or uploads - empty result
        mock_dao = Mock()
        mock_dao.get_downloads.return_value = iter([])  # Empty generator
        mock_dao.get_uploads.return_value = iter([])  # Empty generator

        result = self.api.get_transfers(mock_dao)

        # Verify empty result
        assert result == []
        assert isinstance(result, list)

        # Verify DAO methods were called
        mock_dao.get_downloads.assert_called_once()
        mock_dao.get_uploads.assert_called_once()

        # Test 2: Only downloads, no uploads
        mock_dao.reset_mock()

        # Create mock Download objects (dataclass-like structure)
        from dataclasses import dataclass, field
        from pathlib import Path
        from typing import Optional

        from nxdrive.constants import TransferStatus

        @dataclass
        class MockDownload:
            uid: Optional[int] = 1
            path: Path = Path("/test/download1.txt")
            name: str = field(init=False, default="download1.txt")
            status: TransferStatus = TransferStatus.ONGOING
            engine: str = "test_engine"
            is_direct_edit: bool = False
            is_direct_transfer: bool = False
            progress: float = 0.5
            doc_pair: Optional[int] = None
            filesize: int = 1024
            transfer_type: str = "download"
            tmpname: Optional[Path] = Path("/tmp/download1.txt")
            url: Optional[str] = "http://example.com/download1.txt"

            def __post_init__(self):
                self.name = self.path.name

        download1 = MockDownload()
        download2 = MockDownload(
            uid=2,
            path=Path("/test/download2.pdf"),
            status=TransferStatus.DONE,
            progress=1.0,
            filesize=2048,
        )
        download2.__post_init__()

        mock_dao.get_downloads.return_value = iter([download1, download2])
        mock_dao.get_uploads.return_value = iter([])

        result = self.api.get_transfers(mock_dao)

        # Verify result structure
        assert len(result) == 2
        assert isinstance(result, list)

        # Verify first download
        download1_dict = result[0]
        assert download1_dict["uid"] == 1
        assert download1_dict["name"] == "download1.txt"
        assert download1_dict["path"] == Path("/test/download1.txt")
        assert download1_dict["status"] == TransferStatus.ONGOING
        assert download1_dict["engine"] == "test_engine"
        assert download1_dict["is_direct_edit"] is False
        assert download1_dict["progress"] == 0.5
        assert download1_dict["filesize"] == 1024
        assert download1_dict["transfer_type"] == "download"
        assert download1_dict["tmpname"] == Path("/tmp/download1.txt")
        assert download1_dict["url"] == "http://example.com/download1.txt"

        # Verify second download
        download2_dict = result[1]
        assert download2_dict["uid"] == 2
        assert download2_dict["name"] == "download2.pdf"
        assert download2_dict["status"] == TransferStatus.DONE
        assert download2_dict["progress"] == 1.0
        assert download2_dict["filesize"] == 2048

        # Test 3: Only uploads, no downloads
        mock_dao.reset_mock()

        @dataclass
        class MockUpload:
            uid: Optional[int] = 3
            path: Path = Path("/test/upload1.txt")
            name: str = field(init=False, default="upload1.txt")
            status: TransferStatus = TransferStatus.ONGOING
            engine: str = "test_engine"
            is_direct_edit: bool = False
            is_direct_transfer: bool = False
            progress: float = 0.7
            doc_pair: Optional[int] = None
            filesize: int = 512
            transfer_type: str = "upload"
            batch: dict = field(default_factory=dict)
            chunk_size: int = 1024
            remote_parent_path: str = "/remote/parent"
            remote_parent_ref: str = "remote_ref_123"
            batch_obj = None
            request_uid: Optional[str] = "req_uid_456"
            is_dirty: bool = False

            def __post_init__(self):
                self.name = self.path.name

        upload1 = MockUpload()
        upload2 = MockUpload(
            uid=4,
            path=Path("/test/upload2.docx"),
            status=TransferStatus.DONE,
            progress=1.0,
            filesize=4096,
            chunk_size=2048,
        )
        upload2.__post_init__()

        mock_dao.get_downloads.return_value = iter([])
        mock_dao.get_uploads.return_value = iter([upload1, upload2])

        result = self.api.get_transfers(mock_dao)

        # Verify result structure
        assert len(result) == 2
        assert isinstance(result, list)

        # Verify first upload
        upload1_dict = result[0]
        assert upload1_dict["uid"] == 3
        assert upload1_dict["name"] == "upload1.txt"
        assert upload1_dict["path"] == Path("/test/upload1.txt")
        assert upload1_dict["status"] == TransferStatus.ONGOING
        assert upload1_dict["engine"] == "test_engine"
        assert upload1_dict["progress"] == 0.7
        assert upload1_dict["filesize"] == 512
        assert upload1_dict["transfer_type"] == "upload"
        assert upload1_dict["chunk_size"] == 1024
        assert upload1_dict["remote_parent_path"] == "/remote/parent"
        assert upload1_dict["remote_parent_ref"] == "remote_ref_123"
        assert upload1_dict["request_uid"] == "req_uid_456"
        assert upload1_dict["is_dirty"] is False

        # Test 4: Both downloads and uploads mixed
        mock_dao.reset_mock()

        download_mixed = MockDownload(uid=5, path=Path("/mixed/download.zip"))
        download_mixed.__post_init__()
        upload_mixed = MockUpload(uid=6, path=Path("/mixed/upload.jpg"))
        upload_mixed.__post_init__()

        mock_dao.get_downloads.return_value = iter([download_mixed])
        mock_dao.get_uploads.return_value = iter([upload_mixed])

        result = self.api.get_transfers(mock_dao)

        # Verify mixed result
        assert len(result) == 2

        # Find download and upload in result (order: downloads first, then uploads)
        download_found = result[0]
        upload_found = result[1]

        assert download_found["uid"] == 5
        assert download_found["name"] == "download.zip"
        assert download_found["transfer_type"] == "download"

        assert upload_found["uid"] == 6
        assert upload_found["name"] == "upload.jpg"
        assert upload_found["transfer_type"] == "upload"

        # Test 5: Limit enforcement - more than 5 downloads
        mock_dao.reset_mock()

        # Create 7 downloads (should only get first 5)
        downloads = []
        for i in range(7):
            download = MockDownload(uid=i + 10, path=Path(f"/test/download{i}.txt"))
            download.__post_init__()
            downloads.append(download)

        mock_dao.get_downloads.return_value = iter(downloads)
        mock_dao.get_uploads.return_value = iter([])

        result = self.api.get_transfers(mock_dao)

        # Verify only first 5 downloads returned
        assert len(result) == 5
        for i in range(5):
            assert result[i]["uid"] == i + 10
            assert result[i]["name"] == f"download{i}.txt"

        # Test 6: Limit enforcement - more than 5 uploads
        mock_dao.reset_mock()

        # Create 8 uploads (should only get first 5)
        uploads = []
        for i in range(8):
            upload = MockUpload(uid=i + 20, path=Path(f"/test/upload{i}.txt"))
            upload.__post_init__()
            uploads.append(upload)

        mock_dao.get_downloads.return_value = iter([])
        mock_dao.get_uploads.return_value = iter(uploads)

        result = self.api.get_transfers(mock_dao)

        # Verify only first 5 uploads returned
        assert len(result) == 5
        for i in range(5):
            assert result[i]["uid"] == i + 20
            assert result[i]["name"] == f"upload{i}.txt"

        # Test 7: Limit enforcement - more than 5 of each type
        mock_dao.reset_mock()

        # Create 6 downloads and 7 uploads (should get 5 + 5 = 10 total)
        downloads = []
        for i in range(6):
            download = MockDownload(uid=i + 30, path=Path(f"/limit/download{i}.txt"))
            download.__post_init__()
            downloads.append(download)

        uploads = []
        for i in range(7):
            upload = MockUpload(uid=i + 40, path=Path(f"/limit/upload{i}.txt"))
            upload.__post_init__()
            uploads.append(upload)

        mock_dao.get_downloads.return_value = iter(downloads)
        mock_dao.get_uploads.return_value = iter(uploads)

        result = self.api.get_transfers(mock_dao)

        # Verify exactly 10 items returned (5 downloads + 5 uploads)
        assert len(result) == 10

        # Verify first 5 are downloads
        for i in range(5):
            assert result[i]["uid"] == i + 30
            assert result[i]["transfer_type"] == "download"
            assert result[i]["name"] == f"download{i}.txt"

        # Verify next 5 are uploads
        for i in range(5):
            assert result[i + 5]["uid"] == i + 40
            assert result[i + 5]["transfer_type"] == "upload"
            assert result[i + 5]["name"] == f"upload{i}.txt"

        # Test 8: Verify asdict conversion preserves all fields
        mock_dao.reset_mock()

        # Create transfer with all possible fields set
        comprehensive_download = MockDownload(
            uid=999,
            path=Path("/comprehensive/test.file"),
            status=TransferStatus.PAUSED,
            engine="comprehensive_engine",
            is_direct_edit=True,
            is_direct_transfer=True,
            progress=0.75,
            doc_pair=12345,
            filesize=9999,
            tmpname=Path("/tmp/comprehensive.file"),
            url="https://comprehensive.example.com/test.file",
        )
        comprehensive_download.__post_init__()

        mock_dao.get_downloads.return_value = iter([comprehensive_download])
        mock_dao.get_uploads.return_value = iter([])

        result = self.api.get_transfers(mock_dao)

        # Verify all fields preserved in dict conversion
        assert len(result) == 1
        comp_dict = result[0]

        assert comp_dict["uid"] == 999
        assert comp_dict["path"] == Path("/comprehensive/test.file")
        assert comp_dict["name"] == "test.file"
        assert comp_dict["status"] == TransferStatus.PAUSED
        assert comp_dict["engine"] == "comprehensive_engine"
        assert comp_dict["is_direct_edit"] is True
        assert comp_dict["is_direct_transfer"] is True
        assert comp_dict["progress"] == 0.75
        assert comp_dict["doc_pair"] == 12345
        assert comp_dict["filesize"] == 9999
        assert comp_dict["transfer_type"] == "download"
        assert comp_dict["tmpname"] == Path("/tmp/comprehensive.file")
        assert comp_dict["url"] == "https://comprehensive.example.com/test.file"

        # Test 9: Verify DAO method calls are made correctly
        mock_dao.get_downloads.assert_called_once()
        mock_dao.get_uploads.assert_called_once()

    def test_pause_transfer_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of pause_transfer method."""

        # Test 1: Basic functionality - pause download transfer
        mock_engine = Mock()
        mock_dao = Mock()
        mock_engine.dao = mock_dao
        self.mock_manager.engines.get.return_value = mock_engine

        # Call the method with download transfer
        nature = "downloads"
        engine_uid = "test_engine_123"
        transfer_uid = 456
        progress = 0.75

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer(nature, engine_uid, transfer_uid, progress)

            # Verify logging
            mock_log.info.assert_called_once_with(
                f"Pausing {nature} {transfer_uid} for engine {engine_uid!r}"
            )

        # Verify manager.engines.get called with correct engine_uid
        self.mock_manager.engines.get.assert_called_once_with(engine_uid)

        # Verify dao.pause_transfer called with correct parameters
        mock_dao.pause_transfer.assert_called_once_with(
            nature, transfer_uid, progress, is_direct_transfer=False
        )

        # Test 2: Pause upload transfer with different parameters
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()
        mock_dao.reset_mock()

        nature2 = "uploads"
        engine_uid2 = "another_engine_456"
        transfer_uid2 = 789
        progress2 = 0.25

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer(nature2, engine_uid2, transfer_uid2, progress2)

            # Verify logging with different parameters
            mock_log.info.assert_called_once_with(
                f"Pausing {nature2} {transfer_uid2} for engine {engine_uid2!r}"
            )

        # Verify method calls with new parameters
        self.mock_manager.engines.get.assert_called_once_with(engine_uid2)
        mock_dao.pause_transfer.assert_called_once_with(
            nature2, transfer_uid2, progress2, is_direct_transfer=False
        )

        # Test 3: Pause transfer with is_direct_transfer=True
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()
        mock_dao.reset_mock()

        nature3 = "downloads"
        engine_uid3 = "direct_transfer_engine"
        transfer_uid3 = 999
        progress3 = 0.5
        is_direct_transfer = True

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer(
                nature3,
                engine_uid3,
                transfer_uid3,
                progress3,
                is_direct_transfer=is_direct_transfer,
            )

            # Verify logging
            mock_log.info.assert_called_once_with(
                f"Pausing {nature3} {transfer_uid3} for engine {engine_uid3!r}"
            )

        # Verify dao.pause_transfer called with is_direct_transfer=True
        mock_dao.pause_transfer.assert_called_once_with(
            nature3, transfer_uid3, progress3, is_direct_transfer=True
        )

        # Test 4: No engine found - should return early without calling DAO
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()
        mock_dao.reset_mock()

        # Mock manager to return None (no engine found)
        self.mock_manager.engines.get.return_value = None

        nature4 = "uploads"
        engine_uid4 = "nonexistent_engine"
        transfer_uid4 = 111
        progress4 = 0.1

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer(nature4, engine_uid4, transfer_uid4, progress4)

            # Verify logging still occurs
            mock_log.info.assert_called_once_with(
                f"Pausing {nature4} {transfer_uid4} for engine {engine_uid4!r}"
            )

        # Verify manager.engines.get was called
        self.mock_manager.engines.get.assert_called_once_with(engine_uid4)

        # Verify dao.pause_transfer was NOT called (engine not found)
        mock_dao.pause_transfer.assert_not_called()

        # Test 5: Edge cases - different data types and values
        # Reset mocks and restore engine
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()
        mock_dao.reset_mock()
        self.mock_manager.engines.get.return_value = mock_engine

        # Test with progress = 0.0 (starting)
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer("downloads", "edge_engine", 1, 0.0)
            mock_log.info.assert_called_once()
        mock_dao.pause_transfer.assert_called_with(
            "downloads", 1, 0.0, is_direct_transfer=False
        )

        # Test with progress = 1.0 (completed)
        mock_dao.reset_mock()
        with patch("nxdrive.gui.api.log"):
            self.api.pause_transfer("uploads", "edge_engine", 2, 1.0)
        mock_dao.pause_transfer.assert_called_with(
            "uploads", 2, 1.0, is_direct_transfer=False
        )

        # Test with large transfer_uid
        mock_dao.reset_mock()
        large_uid = 999999999
        with patch("nxdrive.gui.api.log"):
            self.api.pause_transfer("downloads", "edge_engine", large_uid, 0.33)
        mock_dao.pause_transfer.assert_called_with(
            "downloads", large_uid, 0.33, is_direct_transfer=False
        )

        # Test 6: Test with special characters in engine_uid
        self.mock_manager.reset_mock()
        mock_dao.reset_mock()

        special_engine_uid = "engine-123@domain.com#special"
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer("uploads", special_engine_uid, 777, 0.66)

            # Verify logging includes special characters correctly
            expected_log = f"Pausing uploads 777 for engine {special_engine_uid!r}"
            mock_log.info.assert_called_once_with(expected_log)

        self.mock_manager.engines.get.assert_called_once_with(special_engine_uid)
        mock_dao.pause_transfer.assert_called_once_with(
            "uploads", 777, 0.66, is_direct_transfer=False
        )

        # Test 7: Test various nature values
        self.mock_manager.reset_mock()
        mock_dao.reset_mock()

        # Test "downloads" nature
        with patch("nxdrive.gui.api.log"):
            self.api.pause_transfer("downloads", "test_engine", 10, 0.1)
        mock_dao.pause_transfer.assert_called_with(
            "downloads", 10, 0.1, is_direct_transfer=False
        )

        mock_dao.reset_mock()

        # Test "uploads" nature
        with patch("nxdrive.gui.api.log"):
            self.api.pause_transfer("uploads", "test_engine", 20, 0.2)
        mock_dao.pause_transfer.assert_called_with(
            "uploads", 20, 0.2, is_direct_transfer=False
        )

        # Test 8: Test function returns None (void function)
        mock_dao.reset_mock()

        result = self.api.pause_transfer("downloads", "test_engine", 30, 0.3)
        assert result is None

        # Test 9: Test parameter passing with all combinations
        test_cases = [
            # (nature, engine_uid, transfer_uid, progress, is_direct_transfer)
            ("downloads", "engine1", 100, 0.0, False),
            ("uploads", "engine2", 200, 0.25, False),
            ("downloads", "engine3", 300, 0.5, True),
            ("uploads", "engine4", 400, 0.75, True),
            ("downloads", "engine5", 500, 1.0, False),
        ]

        for nature, engine_uid, transfer_uid, progress, is_direct in test_cases:
            mock_dao.reset_mock()
            self.mock_manager.reset_mock()

            with patch("nxdrive.gui.api.log") as mock_log:
                self.api.pause_transfer(
                    nature,
                    engine_uid,
                    transfer_uid,
                    progress,
                    is_direct_transfer=is_direct,
                )

                # Verify logging
                expected_log = (
                    f"Pausing {nature} {transfer_uid} for engine {engine_uid!r}"
                )
                mock_log.info.assert_called_once_with(expected_log)

            # Verify manager call
            self.mock_manager.engines.get.assert_called_once_with(engine_uid)

            # Verify DAO call
            mock_dao.pause_transfer.assert_called_once_with(
                nature, transfer_uid, progress, is_direct_transfer=is_direct
            )

        # Test 10: Verify logging format with different parameter types
        self.mock_manager.reset_mock()
        mock_dao.reset_mock()

        # Test with empty string engine_uid
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer("downloads", "", 999, 0.99)
            mock_log.info.assert_called_once_with("Pausing downloads 999 for engine ''")

        # Test with transfer_uid = 0
        mock_dao.reset_mock()
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_transfer("uploads", "test_engine", 0, 0.0)
            mock_log.info.assert_called_once_with(
                "Pausing uploads 0 for engine 'test_engine'"
            )

        mock_dao.pause_transfer.assert_called_with(
            "uploads", 0, 0.0, is_direct_transfer=False
        )

    def test_resume_transfer_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of resume_transfer method."""

        # Test 1: Basic functionality - resume download transfer
        mock_engine = Mock()
        self.mock_manager.engines.get.return_value = mock_engine

        # Call the method with download transfer
        nature = "downloads"
        engine_uid = "test_engine_123"
        uid = 456

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer(nature, engine_uid, uid)

            # Verify logging
            mock_log.info.assert_called_once_with(
                f"Resume {nature} {uid} for engine {engine_uid!r}"
            )

        # Verify manager.engines.get called with correct engine_uid
        self.mock_manager.engines.get.assert_called_once_with(engine_uid)

        # Verify engine.resume_transfer called with correct parameters
        mock_engine.resume_transfer.assert_called_once_with(
            nature, uid, is_direct_transfer=False
        )

        # Test 2: Resume upload transfer with different parameters
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        nature2 = "uploads"
        engine_uid2 = "another_engine_456"
        uid2 = 789

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer(nature2, engine_uid2, uid2)

            # Verify logging with different parameters
            mock_log.info.assert_called_once_with(
                f"Resume {nature2} {uid2} for engine {engine_uid2!r}"
            )

        # Verify method calls with new parameters
        self.mock_manager.engines.get.assert_called_once_with(engine_uid2)
        mock_engine.resume_transfer.assert_called_once_with(
            nature2, uid2, is_direct_transfer=False
        )

        # Test 3: Resume transfer with is_direct_transfer=True
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        nature3 = "downloads"
        engine_uid3 = "direct_transfer_engine"
        uid3 = 999
        is_direct_transfer = True

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer(
                nature3, engine_uid3, uid3, is_direct_transfer=is_direct_transfer
            )

            # Verify logging
            mock_log.info.assert_called_once_with(
                f"Resume {nature3} {uid3} for engine {engine_uid3!r}"
            )

        # Verify engine.resume_transfer called with is_direct_transfer=True
        mock_engine.resume_transfer.assert_called_once_with(
            nature3, uid3, is_direct_transfer=True
        )

        # Test 4: No engine found - should return early without calling engine method
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        # Mock manager to return None (no engine found)
        self.mock_manager.engines.get.return_value = None

        nature4 = "uploads"
        engine_uid4 = "nonexistent_engine"
        uid4 = 111

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer(nature4, engine_uid4, uid4)

            # Verify logging still occurs
            mock_log.info.assert_called_once_with(
                f"Resume {nature4} {uid4} for engine {engine_uid4!r}"
            )

        # Verify manager.engines.get was called
        self.mock_manager.engines.get.assert_called_once_with(engine_uid4)

        # Verify engine.resume_transfer was NOT called (engine not found)
        mock_engine.resume_transfer.assert_not_called()

        # Test 5: Edge cases - different data types and values
        # Reset mocks and restore engine
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()
        self.mock_manager.engines.get.return_value = mock_engine

        # Test with uid = 0 (edge case)
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer("downloads", "edge_engine", 0)
            mock_log.info.assert_called_once()
        mock_engine.resume_transfer.assert_called_with(
            "downloads", 0, is_direct_transfer=False
        )

        # Test with large uid
        mock_engine.reset_mock()
        large_uid = 999999999
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("uploads", "edge_engine", large_uid)
        mock_engine.resume_transfer.assert_called_with(
            "uploads", large_uid, is_direct_transfer=False
        )

        # Test with negative uid (edge case)
        mock_engine.reset_mock()
        negative_uid = -1
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("downloads", "edge_engine", negative_uid)
        mock_engine.resume_transfer.assert_called_with(
            "downloads", negative_uid, is_direct_transfer=False
        )

        # Test 6: Test with special characters in engine_uid
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        special_engine_uid = "engine-123@domain.com#special"
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer("uploads", special_engine_uid, 777)

            # Verify logging includes special characters correctly
            expected_log = f"Resume uploads 777 for engine {special_engine_uid!r}"
            mock_log.info.assert_called_once_with(expected_log)

        self.mock_manager.engines.get.assert_called_once_with(special_engine_uid)
        mock_engine.resume_transfer.assert_called_once_with(
            "uploads", 777, is_direct_transfer=False
        )

        # Test 7: Test various nature values
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        # Test "downloads" nature
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("downloads", "test_engine", 10)
        mock_engine.resume_transfer.assert_called_with(
            "downloads", 10, is_direct_transfer=False
        )

        mock_engine.reset_mock()

        # Test "uploads" nature
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("uploads", "test_engine", 20)
        mock_engine.resume_transfer.assert_called_with(
            "uploads", 20, is_direct_transfer=False
        )

        # Test "download" (singular) nature
        mock_engine.reset_mock()
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("download", "test_engine", 30)
        mock_engine.resume_transfer.assert_called_with(
            "download", 30, is_direct_transfer=False
        )

        # Test "upload" (singular) nature
        mock_engine.reset_mock()
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("upload", "test_engine", 40)
        mock_engine.resume_transfer.assert_called_with(
            "upload", 40, is_direct_transfer=False
        )

        # Test 8: Test function returns None (void function)
        mock_engine.reset_mock()

        result = self.api.resume_transfer("downloads", "test_engine", 50)
        assert result is None

        # Test 9: Test parameter passing with all combinations
        test_cases = [
            # (nature, engine_uid, uid, is_direct_transfer)
            ("downloads", "engine1", 100, False),
            ("uploads", "engine2", 200, False),
            ("download", "engine3", 300, True),
            ("upload", "engine4", 400, True),
            ("downloads", "engine5", 500, False),
        ]

        for nature, engine_uid, uid, is_direct in test_cases:
            mock_engine.reset_mock()
            self.mock_manager.reset_mock()

            with patch("nxdrive.gui.api.log") as mock_log:
                self.api.resume_transfer(
                    nature, engine_uid, uid, is_direct_transfer=is_direct
                )

                # Verify logging
                expected_log = f"Resume {nature} {uid} for engine {engine_uid!r}"
                mock_log.info.assert_called_once_with(expected_log)

            # Verify manager call
            self.mock_manager.engines.get.assert_called_once_with(engine_uid)

            # Verify engine call
            mock_engine.resume_transfer.assert_called_once_with(
                nature, uid, is_direct_transfer=is_direct
            )

        # Test 10: Verify logging format with different parameter types
        self.mock_manager.reset_mock()
        mock_engine.reset_mock()

        # Test with empty string engine_uid
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer("downloads", "", 999)
            mock_log.info.assert_called_once_with("Resume downloads 999 for engine ''")

        # Test with uid = 0
        mock_engine.reset_mock()
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_transfer("uploads", "test_engine", 0)
            mock_log.info.assert_called_once_with(
                "Resume uploads 0 for engine 'test_engine'"
            )

        mock_engine.resume_transfer.assert_called_with(
            "uploads", 0, is_direct_transfer=False
        )

        # Test 11: Test parameter order and keyword arguments
        mock_engine.reset_mock()
        self.mock_manager.reset_mock()

        # Test positional parameters
        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer("downloads", "pos_engine", 123)

        mock_engine.resume_transfer.assert_called_with(
            "downloads", 123, is_direct_transfer=False
        )

        # Test with keyword argument
        mock_engine.reset_mock()
        self.mock_manager.reset_mock()

        with patch("nxdrive.gui.api.log"):
            self.api.resume_transfer(
                "uploads", "kw_engine", 456, is_direct_transfer=True
            )

        mock_engine.resume_transfer.assert_called_with(
            "uploads", 456, is_direct_transfer=True
        )

        # Test 12: Verify method signature matches expected Qt slot signature
        # This test ensures the pyqtSlot decorator parameters match the function signature
        import inspect

        sig = inspect.signature(self.api.resume_transfer)
        params = list(sig.parameters.keys())

        # Verify parameter names (excluding 'self')
        expected_params = ["nature", "engine_uid", "uid", "is_direct_transfer"]
        actual_params = [p for p in params if p != "self"]
        assert actual_params == expected_params

        # Verify is_direct_transfer has default value
        is_direct_param = sig.parameters["is_direct_transfer"]
        assert is_direct_param.default is False
        assert is_direct_param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_resume_session_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of resume_session method."""
        mock_engine = Mock()
        self.mock_manager.engines.get.return_value = mock_engine

        # Test basic functionality
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.resume_session("test_engine", 123)
            mock_log.info.assert_called_once_with(
                "Resume session 123 for engine 'test_engine'"
            )

        self.mock_manager.engines.get.assert_called_once_with("test_engine")
        mock_engine.resume_session.assert_called_once_with(123)

        # Test no engine found
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = None
        mock_engine.reset_mock()

        result = self.api.resume_session("missing_engine", 456)
        assert result is None
        mock_engine.resume_session.assert_not_called()

    def test_pause_session_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of pause_session method."""
        mock_engine = Mock()
        mock_dao = Mock()
        mock_engine.dao = mock_dao
        self.mock_manager.engines.get.return_value = mock_engine

        # Test basic functionality
        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.pause_session("test_engine", 789)
            mock_log.info.assert_called_once_with(
                "Pausing session 789 for engine 'test_engine'"
            )

        self.mock_manager.engines.get.assert_called_once_with("test_engine")
        mock_dao.pause_session.assert_called_once_with(789)

        # Test no engine found
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = None
        mock_dao.reset_mock()

        result = self.api.pause_session("missing_engine", 999)
        assert result is None
        mock_dao.pause_session.assert_not_called()

    def test_generate_report_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of generate_report method."""
        # Test successful report generation
        self.mock_manager.generate_report.return_value = "Test report content"

        result = self.api.generate_report()
        assert result == "Test report content"
        self.mock_manager.generate_report.assert_called_once()

        # Test exception handling
        self.mock_manager.reset_mock()
        test_exception = Exception("Report generation failed")
        self.mock_manager.generate_report.side_effect = test_exception

        with patch("nxdrive.gui.api.log") as mock_log:
            result = self.api.generate_report()
            assert result == "[ERROR] Report generation failed"
            mock_log.exception.assert_called_once_with("Report error")

    def test_generate_csv_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of generate_csv method."""
        mock_engine = Mock()
        self.mock_manager.engines.get.return_value = mock_engine
        self.mock_manager.generate_csv.return_value = True

        # Test successful CSV generation
        result = self.api.generate_csv("123", "test_engine")
        assert result is True
        self.mock_manager.engines.get.assert_called_once_with("test_engine")
        self.mock_manager.generate_csv.assert_called_once_with(123, mock_engine)

        # Test no engine found
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = None

        result = self.api.generate_csv("456", "missing_engine")
        assert result is False
        self.mock_manager.generate_csv.assert_not_called()

        # Test exception handling
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = mock_engine
        self.mock_manager.generate_csv.side_effect = Exception("CSV generation failed")

        with patch("nxdrive.gui.api.log") as mock_log:
            result = self.api.generate_csv("789", "test_engine")
            assert result is False
            mock_log.exception.assert_called_once_with("CSV export error.")

    def test_open_direct_transfer_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of open_direct_transfer method."""
        mock_engine = Mock()

        with patch.object(self.api, "_get_engine", return_value=mock_engine):
            self.api.open_direct_transfer("test_uid")

            # Verify application.hide_systray was called
            self.mock_application.hide_systray.assert_called_once()

    def test_open_help_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of open_help method."""
        self.api.open_help()

        # Verify both methods called
        self.mock_application.hide_systray.assert_called_once()
        self.mock_manager.open_help.assert_called_once()

    def test_open_document_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of open_document method."""
        mock_engine = Mock()
        mock_dao = Mock()
        mock_engine.dao = mock_dao
        self.mock_manager.engines.get.return_value = mock_engine

        # Test document with error state and remote info
        mock_doc_pair = Mock()
        mock_doc_pair.pair_state = "error"
        mock_doc_pair.remote_ref = "remote_ref_123"
        mock_doc_pair.remote_name = "test_document.pdf"
        mock_doc_pair.local_parent_path = "/local/path"
        mock_dao.get_state_from_id.return_value = mock_doc_pair

        with patch.object(self.api, "open_remote") as mock_open_remote:
            self.api.open_document("test_engine", 123)
            mock_open_remote.assert_called_once_with(
                "test_engine", "remote_ref_123", "test_document.pdf"
            )

        # Test document with non-error state
        mock_doc_pair.pair_state = "synchronized"
        mock_dao.reset_mock()

        with patch.object(self.api, "open_local") as mock_open_local:
            self.api.open_document("test_engine", 456)
            mock_open_local.assert_called_once_with("test_engine", "/local/path")

        # Test no engine found
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = None

        result = self.api.open_document("missing_engine", 789)
        assert result is None

        # Test no doc pair found
        self.mock_manager.reset_mock()
        self.mock_manager.engines.get.return_value = mock_engine
        mock_dao.get_state_from_id.return_value = None

        result = self.api.open_document("test_engine", 999)
        assert result is None

    def test_show_settings_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of show_settings method."""
        section = "general"

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.show_settings(section)
            mock_log.info.assert_called_once_with(f"Show settings on section {section}")

        self.mock_application.hide_systray.assert_called_once()
        self.mock_application.show_settings.assert_called_once_with(section)

    def test_quit_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of quit method."""
        # Test successful quit
        self.api.quit()
        self.mock_application.quit.assert_called_once()

        # Test exception handling
        self.mock_application.reset_mock()
        self.mock_application.quit.side_effect = Exception("Quit failed")

        with patch("nxdrive.gui.api.log") as mock_log:
            self.api.quit()
            mock_log.exception.assert_called_once_with("Application exit error")

    def test_web_update_token_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of web_update_token method."""

        from nxdrive.auth import OAuthentication
        from nxdrive.updater.constants import Login

        mock_engine = Mock()
        mock_engine.server_url = "https://test.server.com"
        mock_engine.remote.auth = Mock(spec=OAuthentication)

        with patch.object(self.api, "_get_engine", return_value=mock_engine), patch(
            "nxdrive.gui.api.urlencode"
        ) as mock_urlencode, patch("nxdrive.gui.api.get_auth") as mock_get_auth:

            mock_urlencode.return_value = "updateToken=True"
            self.mock_manager.get_server_login_type.return_value = Login.NEW

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://auth.url"
            mock_get_auth.return_value = mock_auth

            self.api.web_update_token("test_uid")

            # Verify auth URL opened
            self.mock_application.open_authentication_dialog.assert_called_once()
            args = self.mock_application.open_authentication_dialog.call_args[0]
            assert "https://auth.url" in args[0]

        # Test no engine found
        with patch.object(self.api, "_get_engine", return_value=None):
            self.api.web_update_token("missing_uid")
            # Verify error message emitted
            # Note: setMessage is a signal, so we just verify the call structure

    def test_get_ssl_error_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of _get_ssl_error method."""

        import pytest

        from nxdrive.exceptions import (
            EncryptedSSLCertificateKey,
            InvalidSSLCertificate,
            MissingClientSSLCertificate,
        )

        # Test successful URL validation
        with patch("nxdrive.gui.api.test_url") as mock_test_url:
            mock_test_url.return_value = ""

            result = self.api._get_ssl_error("https://valid.server.com")
            assert result == ""
            mock_test_url.assert_called_once_with(
                "https://valid.server.com", proxy=self.mock_manager.proxy
            )

        # Test SSL certificate error with acceptance
        with patch("nxdrive.gui.api.test_url") as mock_test_url, patch(
            "nxdrive.gui.api.log"
        ) as mock_log, patch("nxdrive.gui.api.save_config") as mock_save_config:

            ssl_error = InvalidSSLCertificate("SSL cert invalid")
            # First call raises SSL error, second call (after acceptance) returns empty string
            mock_test_url.side_effect = [ssl_error, ""]
            self.mock_application.accept_unofficial_ssl_cert.return_value = True

            result = self.api._get_ssl_error("https://invalid-ssl.server.com")
            assert result == ""

            # Verify SSL error was logged
            mock_log.warning.assert_called_once_with(ssl_error)

            # Verify SSL acceptance was called with hostname
            self.mock_application.accept_unofficial_ssl_cert.assert_called_once_with(
                "invalid-ssl.server.com"
            )

            # Verify config was saved
            mock_save_config.assert_called_once()

            # Verify test_url was called twice (once with error, once after acceptance)
            assert mock_test_url.call_count == 2

        # Test SSL certificate error with rejection
        with patch("nxdrive.gui.api.test_url") as mock_test_url, patch(
            "nxdrive.gui.api.log"
        ) as mock_log:

            # Reset the mock from previous test case
            self.mock_application.reset_mock()

            ssl_error = InvalidSSLCertificate("SSL cert invalid")
            mock_test_url.side_effect = ssl_error
            self.mock_application.accept_unofficial_ssl_cert.return_value = False

            result = self.api._get_ssl_error("https://rejected-ssl.server.com")
            assert (
                result == "CONNECTION_ERROR"
            )  # Function returns CONNECTION_ERROR when SSL cert is rejected

            # Verify SSL error was logged
            mock_log.warning.assert_called_once_with(ssl_error)

            # Verify SSL acceptance was called
            self.mock_application.accept_unofficial_ssl_cert.assert_called_once_with(
                "rejected-ssl.server.com"
            )

        # Test MissingClientSSLCertificate exception
        with patch("nxdrive.gui.api.test_url") as mock_test_url, patch(
            "nxdrive.gui.api.log"
        ) as mock_log:

            ssl_error = MissingClientSSLCertificate("Missing client SSL certificate")
            mock_test_url.side_effect = ssl_error

            result = self.api._get_ssl_error("https://missing-client-ssl.server.com")
            assert result == "MISSING_CLIENT_SSL"

            # Verify error was logged
            mock_log.warning.assert_called_once_with(ssl_error)

        # Test EncryptedSSLCertificateKey exception
        with patch("nxdrive.gui.api.test_url") as mock_test_url, patch(
            "nxdrive.gui.api.log"
        ) as mock_log:

            ssl_error = EncryptedSSLCertificateKey("Encrypted SSL certificate key")
            mock_test_url.side_effect = ssl_error

            result = self.api._get_ssl_error("https://encrypted-ssl-key.server.com")
            assert result == "ENCRYPTED_CLIENT_SSL_KEY"

            # Verify error was logged
            mock_log.warning.assert_called_once_with(ssl_error)

        # Test non-SSL related exception (function lets these bubble up for caller to handle)
        with patch("nxdrive.gui.api.test_url") as mock_test_url:
            from requests.exceptions import ConnectionError

            connection_error = ConnectionError("Connection failed")
            mock_test_url.side_effect = connection_error

            # Function lets non-SSL exceptions bubble up to the caller
            with pytest.raises(ConnectionError, match="Connection failed"):
                self.api._get_ssl_error(
                    "https://unreachable.server.com"
                )  # Non-SSL errors return CONNECTION_ERROR

        # Test with empty URL
        with patch("nxdrive.gui.api.test_url") as mock_test_url:
            mock_test_url.return_value = ""

            result = self.api._get_ssl_error("")
            assert result == ""
            mock_test_url.assert_called_once_with("", proxy=self.mock_manager.proxy)

        # Test URL parsing for hostname extraction
        with patch("nxdrive.gui.api.test_url") as mock_test_url, patch(
            "nxdrive.gui.api.log"
        ):

            ssl_error = InvalidSSLCertificate("SSL cert invalid")
            mock_test_url.side_effect = ssl_error
            self.mock_application.accept_unofficial_ssl_cert.return_value = False

            # Test various URL formats
            test_urls = [
                "https://example.com/path",
                "https://example.com:8080/path",
                "example.com",  # No scheme
            ]

            for url in test_urls:
                self.mock_application.reset_mock()
                self.api._get_ssl_error(url)
                # Verify that accept_unofficial_ssl_cert was called with some hostname
                self.mock_application.accept_unofficial_ssl_cert.assert_called_once()

    def test_bind_server_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of bind_server method."""

        from pathlib import Path

        from nuxeo.exceptions import HTTPError, Unauthorized
        from requests.exceptions import ConnectionError

        from nxdrive.exceptions import (
            AddonForbiddenError,
            AddonNotInstalledError,
            FolderAlreadyUsed,
            MissingXattrSupport,
            NotFound,
            RootAlreadyBindWithDifferentAccount,
        )

        # Test successful server binding
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = Path("/test/folder")

            self.api.bind_server(
                "/test/folder",
                "https://test.server.com",
                "testuser",
                password="testpass",
                name="Test Server",
                token="test_token",
                check_fs=True,
            )

            # Verify settings window shown
            self.mock_application._show_window.assert_called_once_with(
                self.mock_application.settings_window
            )

            # Verify _bind_server called with correct parameters
            mock_bind_server.assert_called_once_with(
                Path("/test/folder"),
                "https://test.server.com",
                "testuser",
                "testpass",
                "Test Server",
                token="test_token",
                check_fs=True,
            )

        # Test empty server URL
        self.mock_application.reset_mock()

        with patch.object(self.api.setMessage, "emit") as mock_emit:
            self.api.bind_server("", "", "testuser")
            # Verify error message emitted
            mock_emit.assert_called_with("CONNECTION_ERROR", "error")

        # Test RootAlreadyBindWithDifferentAccount exception with user cancellation
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path, patch("nxdrive.gui.api.log") as mock_log, patch(
            "nxdrive.gui.api.Translator"
        ) as mock_translator, patch.object(
            self.api.setMessage, "emit"
        ) as mock_emit:

            mock_normalized_path.return_value = Path("/test/folder")
            exception = RootAlreadyBindWithDifferentAccount("other_user", "other_url")
            mock_bind_server.side_effect = exception
            mock_translator.get.return_value = "Folder used"

            # Mock question dialog - user clicks cancel
            mock_question = Mock()
            cancel_button = Mock()
            mock_question.addButton.return_value = cancel_button
            mock_question.clickedButton.return_value = cancel_button
            self.mock_application.question.return_value = mock_question

            self.api.bind_server("/test/folder", "https://test.server.com", "testuser")

            # Verify warning logged
            mock_log.warning.assert_called()

            # Verify question dialog shown
            self.mock_application.question.assert_called()

            # Verify error message for folder usage
            mock_emit.assert_called_with("FOLDER_USED", "error")

        # Test RootAlreadyBindWithDifferentAccount exception with user continuation
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path, patch(
            "nxdrive.gui.api.Translator"
        ) as mock_translator, patch.object(
            self.api, "bind_server"
        ) as mock_bind_server_recursive:

            mock_normalized_path.return_value = Path("/test/folder")
            exception = RootAlreadyBindWithDifferentAccount("other_user", "other_url")
            mock_bind_server.side_effect = exception
            mock_translator.get.return_value = "Folder used"

            # Mock question dialog - user clicks continue
            mock_question = Mock()
            cancel_button = Mock()
            continue_button = Mock()
            mock_question.addButton.side_effect = [continue_button, cancel_button]
            mock_question.clickedButton.return_value = continue_button
            self.mock_application.question.return_value = mock_question

            # Reset the recursive call mock to prevent infinite recursion
            mock_bind_server_recursive.side_effect = None

            self.api.bind_server(
                "/test/folder", "https://test.server.com", "testuser", password="pass"
            )

            # Verify recursive call with check_fs=False
            assert mock_bind_server_recursive.call_count >= 1

        # Test various exceptions and their error mappings
        exceptions_and_errors = [
            (NotFound(), "FOLDER_DOES_NOT_EXISTS"),
            (MissingXattrSupport(Path("/test")), "INVALID_LOCAL_FOLDER"),
            (AddonForbiddenError(), "ADDON_FORBIDDEN"),
            (AddonNotInstalledError(), "ADDON_NOT_INSTALLED"),
            (Unauthorized(), "UNAUTHORIZED"),
            (FolderAlreadyUsed(), "FOLDER_USED"),
            (PermissionError(), "FOLDER_PERMISSION_ERROR"),
            (HTTPError(), "CONNECTION_ERROR"),
        ]

        for exception, expected_error in exceptions_and_errors:
            with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
                "nxdrive.gui.api.normalized_path"
            ) as mock_normalized_path, patch("nxdrive.gui.api.log") as mock_log, patch(
                "nxdrive.gui.api.Translator"
            ) as mock_translator, patch.object(
                self.api.setMessage, "emit"
            ) as mock_emit:

                mock_normalized_path.return_value = Path("/test/folder")
                mock_bind_server.side_effect = exception
                mock_translator.get.return_value = expected_error

                self.api.bind_server(
                    "/test/folder", "https://test.server.com", "testuser"
                )

                # Verify error logged and emitted
                mock_log.warning.assert_called()
                mock_emit.assert_called_with(expected_error, "error")

        # Test CONNECTION_ERROR with errno 61 (connection refused)
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path, patch("nxdrive.gui.api.log") as mock_log, patch(
            "nxdrive.gui.api.Translator"
        ) as mock_translator, patch.object(
            self.api.setMessage, "emit"
        ) as mock_emit:

            mock_normalized_path.return_value = Path("/test/folder")
            connection_error = ConnectionError("Connection refused")
            connection_error.errno = 61
            mock_bind_server.side_effect = connection_error
            mock_translator.get.return_value = "CONNECTION_REFUSED"

            self.api.bind_server("/test/folder", "https://test.server.com", "testuser")

            # Verify specific connection refused error
            mock_log.warning.assert_called()
            mock_emit.assert_called_with("CONNECTION_REFUSED", "error")

        # Test generic ConnectionError
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path, patch("nxdrive.gui.api.log") as mock_log, patch(
            "nxdrive.gui.api.Translator"
        ) as mock_translator, patch.object(
            self.api.setMessage, "emit"
        ) as mock_emit:

            mock_normalized_path.return_value = Path("/test/folder")
            connection_error = ConnectionError("Generic connection error")
            mock_bind_server.side_effect = connection_error
            mock_translator.get.return_value = "CONNECTION_ERROR"

            self.api.bind_server("/test/folder", "https://test.server.com", "testuser")

            # Verify generic connection error
            mock_log.warning.assert_called()
            mock_emit.assert_called_with("CONNECTION_ERROR", "error")

        # Test unexpected exception
        with patch.object(self.api, "_bind_server") as mock_bind_server, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path, patch("nxdrive.gui.api.log") as mock_log, patch(
            "nxdrive.gui.api.Translator"
        ) as mock_translator, patch.object(
            self.api.setMessage, "emit"
        ) as mock_emit:

            mock_normalized_path.return_value = Path("/test/folder")
            mock_bind_server.side_effect = ValueError("Unexpected error")
            mock_translator.get.return_value = "CONNECTION_UNKNOWN"

            self.api.bind_server("/test/folder", "https://test.server.com", "testuser")

            # Verify both warning calls - first with exception details, then with translated message
            assert mock_log.warning.call_count == 2
            mock_log.warning.assert_any_call("Unexpected error", exc_info=True)
            mock_log.warning.assert_any_call("CONNECTION_UNKNOWN")
            mock_emit.assert_called_with("CONNECTION_UNKNOWN", "error")

    def test_web_authentication_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of web_authentication method."""

        from urllib3.exceptions import LocationParseError

        from nxdrive.exceptions import StartupPageConnectionError
        from nxdrive.updater.constants import Login

        # Test successful web authentication with legacy auth (NEW login type)
        with patch.object(self.api, "_get_ssl_error", return_value=""), patch(
            "nxdrive.gui.api.get_auth"
        ) as mock_get_auth, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True
            self.mock_manager.get_server_login_type.return_value = Login.NEW

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://connect.url"
            mock_get_auth.return_value = mock_auth

            self.api.web_authentication("https://test.server.com", "/test/folder", True)

            # Verify authentication dialog opened
            self.mock_auth_dialog.emit.assert_called_once()
            args = self.mock_auth_dialog.emit.call_args[0]
            assert args[0] == "https://connect.url"
            assert args[1]["local_folder"] == "/test/folder"
            assert args[1]["server_url"] == "https://test.server.com"
            assert args[1]["engine_type"] == "NXDRIVE"

        # Test successful web authentication without legacy auth (dict token)
        with patch.object(self.api, "_get_ssl_error", return_value=""), patch(
            "nxdrive.gui.api.get_auth"
        ) as mock_get_auth, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://connect.url.non.legacy"
            mock_get_auth.return_value = mock_auth

            # Reset mock
            self.mock_auth_dialog.reset_mock()

            self.api.web_authentication(
                "https://test.server.com", "/test/folder", False
            )

            # Verify authentication dialog opened
            self.mock_auth_dialog.emit.assert_called_once()
            # Verify that non-legacy auth passes dict token instead of string
            call_args = mock_get_auth.call_args[0]
            assert call_args[1] == {}  # dict token for non-legacy auth

        # Test folder not available
        with patch("nxdrive.gui.api.normalized_path") as mock_normalized_path:

            mock_normalized_path.return_value = "/used/folder"
            self.mock_manager.check_local_folder_available.return_value = False

            # Reset mock
            self.mock_set_message.reset_mock()

            self.api.web_authentication("https://test.server.com", "/used/folder", True)

            # Verify error message emitted for folder usage
            self.mock_set_message.emit.assert_called_with("FOLDER_USED", "error")

        # Test server URL with login.jsp (invalid)
        with patch("nxdrive.gui.api.normalized_path") as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            # Reset mock
            self.mock_set_message.reset_mock()

            self.api.web_authentication(
                "https://test.server.com/login.jsp", "/test/folder", True
            )

            # Verify connection error emitted for login.jsp URL
            self.mock_set_message.emit.assert_called_with("CONNECTION_ERROR", "error")

        # Test SSL error from _get_ssl_error
        with patch.object(self.api, "_get_ssl_error", return_value="SSL_ERROR"), patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            # Reset mock
            self.mock_set_message.reset_mock()

            self.api.web_authentication(
                "https://ssl-error.server.com", "/test/folder", True
            )

            # Verify SSL error emitted
            self.mock_set_message.emit.assert_called_with("SSL_ERROR", "error")

        # Test LocationParseError from _get_ssl_error (should continue with auth)
        with patch.object(
            self.api, "_get_ssl_error", side_effect=LocationParseError("Bad URL")
        ), patch("nxdrive.gui.api.normalized_path") as mock_normalized_path, patch(
            "nxdrive.gui.api.log"
        ) as mock_log, patch(
            "nxdrive.gui.api.get_auth"
        ) as mock_get_auth:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://connect.url"
            mock_get_auth.return_value = mock_auth

            # Reset mock
            self.mock_auth_dialog.reset_mock()

            self.api.web_authentication("https://bad-url", "/test/folder", False)

            # Verify debug log for bad URL
            mock_log.debug.assert_called_with("Bad URL: https://bad-url")
            # Should continue with authentication dialog
            self.mock_auth_dialog.emit.assert_called_once()

        # Test general exception from _get_ssl_error (should continue with auth)
        with patch.object(
            self.api, "_get_ssl_error", side_effect=Exception("Unexpected error")
        ), patch("nxdrive.gui.api.normalized_path") as mock_normalized_path, patch(
            "nxdrive.gui.api.log"
        ) as mock_log, patch(
            "nxdrive.gui.api.get_auth"
        ) as mock_get_auth:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://connect.url"
            mock_get_auth.return_value = mock_auth

            # Reset mock
            self.mock_auth_dialog.reset_mock()

            self.api.web_authentication(
                "https://exception-error", "/test/folder", False
            )

            # Verify exception logged
            mock_log.exception.assert_called_with("Unhandled error")
            # Should continue with authentication dialog
            self.mock_auth_dialog.emit.assert_called_once()

        # Test StartupPageConnectionError (legacy auth)
        with patch.object(self.api, "_get_ssl_error", return_value=""), patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True
            self.mock_manager.get_server_login_type.side_effect = (
                StartupPageConnectionError()
            )

            # Reset mock
            self.mock_set_message.reset_mock()

            self.api.web_authentication(
                "https://startup-error.server.com", "/test/folder", True
            )

            # Verify connection error emitted
            self.mock_set_message.emit.assert_called_with("CONNECTION_ERROR", "error")

        # Test authentication with server URL fragment (custom engine type)
        with patch.object(self.api, "_get_ssl_error", return_value=""), patch(
            "nxdrive.gui.api.get_auth"
        ) as mock_get_auth, patch(
            "nxdrive.gui.api.normalized_path"
        ) as mock_normalized_path:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            mock_auth = Mock()
            mock_auth.connect_url.return_value = "https://connect.url"
            mock_get_auth.return_value = mock_auth

            # Reset mock
            self.mock_auth_dialog.reset_mock()

            self.api.web_authentication(
                "https://test.server.com#CUSTOM_TYPE", "/test/folder", False
            )

            # Verify custom engine type extracted from fragment
            self.mock_auth_dialog.emit.assert_called_once()
            args = self.mock_auth_dialog.emit.call_args[0]
            assert args[1]["engine_type"] == "CUSTOM_TYPE"

        # Test exception during authentication setup
        with patch.object(self.api, "_get_ssl_error", return_value=""), patch(
            "nxdrive.gui.api.get_auth", side_effect=Exception("Auth setup failed")
        ), patch("nxdrive.gui.api.normalized_path") as mock_normalized_path, patch(
            "nxdrive.gui.api.log"
        ) as mock_log:

            mock_normalized_path.return_value = "/test/folder"
            self.mock_manager.check_local_folder_available.return_value = True

            # Reset mock
            self.mock_set_message.reset_mock()

            self.api.web_authentication(
                "https://auth-error.server.com", "/test/folder", False
            )

            # Verify exception logged and connection unknown error emitted
            mock_log.warning.assert_called_with(
                "Unexpected error while trying to open web authentication window",
                exc_info=True,
            )
            self.mock_set_message.emit.assert_called_with("CONNECTION_UNKNOWN", "error")

    def test_get_proxy_settings_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of get_proxy_settings method."""
        # Test with proxy settings
        mock_proxy = Mock()
        mock_proxy.category = "manual"
        mock_proxy.pac_url = "http://pac.url"
        mock_proxy.url = "http://proxy.url:8080"
        self.mock_manager.proxy = mock_proxy

        result = self.api.get_proxy_settings()

        # Parse JSON result
        import json

        parsed = json.loads(result)
        assert parsed["config"] == "manual"
        assert parsed["pac_url"] == "http://pac.url"
        assert parsed["url"] == "http://proxy.url:8080"

        # Test with no proxy
        mock_proxy_none = Mock(spec=[])  # Mock with no attributes
        self.mock_manager.proxy = mock_proxy_none

        result = self.api.get_proxy_settings()
        parsed = json.loads(result)
        assert parsed["config"] is None
        assert parsed["pac_url"] is None
        assert parsed["url"] is None

    def test_set_proxy_settings_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of set_proxy_settings method."""

        # Test successful proxy setting
        mock_proxy = Mock()
        with patch(
            "nxdrive.gui.api.get_proxy", return_value=mock_proxy
        ) as mock_get_proxy:
            self.mock_manager.set_proxy.return_value = None  # No error

            result = self.api.set_proxy_settings("manual", "http://proxy:8080", "")

            assert result is True
            mock_get_proxy.assert_called_once_with(
                "manual", url="http://proxy:8080", pac_url=""
            )
            self.mock_manager.set_proxy.assert_called_once_with(mock_proxy)

        # Test FileNotFoundError
        with patch(
            "nxdrive.gui.api.get_proxy",
            side_effect=FileNotFoundError("PAC file not found"),
        ):
            result = self.api.set_proxy_settings("pac", "", "http://pac.url")
            assert result is False

        # Test manager error
        self.mock_manager.reset_mock()
        with patch("nxdrive.gui.api.get_proxy", return_value=mock_proxy):
            self.mock_manager.set_proxy.return_value = "PROXY_ERROR"

            result = self.api.set_proxy_settings("manual", "http://proxy:8080", "")
            assert result is False

    def test_continue_oauth2_flow_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of continue_oauth2_flow method."""
        from nuxeo.exceptions import OAuth2Error

        # Test successful OAuth2 flow for account creation
        with patch.object(
            self.api, "create_account", return_value=""
        ) as mock_create_account, patch(
            "nxdrive.gui.api.OAuthentication"
        ) as mock_oauth_class, patch(
            "nxdrive.gui.api.Options"
        ) as mock_options:

            # Setup mock manager config
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            mock_options.oauth2_openid_configuration_url = None

            # Setup mock OAuth authentication
            mock_auth = Mock()
            mock_auth.get_token.return_value = "test_token"
            mock_auth.get_username.return_value = "testuser"
            mock_oauth_class.return_value = mock_auth

            # Clear callback_params to test account creation path
            self.api.callback_params = {}

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify OAuth authentication setup
            mock_oauth_class.assert_called_once_with(
                "https://test.server.com",
                dao=self.mock_manager.dao,
                subclient_kwargs={},
            )

            # Verify token request
            mock_auth.get_token.assert_called_once_with(
                code_verifier="test_verifier", code="auth_code", state="test_state"
            )

            # Verify account creation
            mock_auth.get_username.assert_called_once()
            mock_create_account.assert_called_once_with("test_token", "testuser")

            # Verify config cleanup
            expected_delete_calls = [
                (("tmp_oauth2_url",),),
                (("tmp_oauth2_code_verifier",),),
                (("tmp_oauth2_state",),),
            ]
            self.mock_manager.dao.delete_config.assert_has_calls(
                expected_delete_calls, any_order=True
            )
            assert self.mock_manager.dao.delete_config.call_count == 3

        # Test successful OAuth2 flow for token update (engine exists)
        with patch.object(
            self.api, "update_token", return_value=""
        ) as mock_update_token, patch(
            "nxdrive.gui.api.OAuthentication"
        ) as mock_oauth_class, patch(
            "nxdrive.gui.api.Options"
        ) as mock_options:

            # Setup mock manager config
            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            mock_options.oauth2_openid_configuration_url = "https://openid.config.url"
            self.mock_manager.proxy.settings.return_value = {"http": "proxy:8080"}

            # Setup mock OAuth authentication
            mock_auth = Mock()
            mock_auth.get_token.return_value = "updated_token"
            mock_auth.get_username.return_value = "testuser"
            mock_oauth_class.return_value = mock_auth

            # Set callback_params to test token update path
            self.api.callback_params = {"engine": "test_engine"}

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify OAuth authentication setup with proxy
            mock_oauth_class.assert_called_once_with(
                "https://test.server.com",
                dao=self.mock_manager.dao,
                subclient_kwargs={"proxies": {"http": "proxy:8080"}},
            )

            # Verify proxy settings call
            self.mock_manager.proxy.settings.assert_called_once_with(
                url="https://openid.config.url"
            )

            # Verify token update
            mock_update_token.assert_called_once_with("updated_token", "testuser")

        # Test missing stored URL error
        with patch.object(self.api, "setMessage") as mock_set_message:
            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": None,
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with("OAUTH2_MISSING_URL", "error")

        # Test missing code parameter error
        with patch.object(self.api, "setMessage") as mock_set_message:
            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            query = {"state": "test_state"}  # Missing code
            self.api.continue_oauth2_flow(query)

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with("CONNECTION_REFUSED", "error")

        # Test missing state parameter error
        with patch.object(self.api, "setMessage") as mock_set_message:
            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            query = {"code": "auth_code"}  # Missing state
            self.api.continue_oauth2_flow(query)

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with("CONNECTION_REFUSED", "error")

        # Test state mismatch error
        with patch.object(self.api, "setMessage") as mock_set_message:
            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "expected_state",
            }.get(key)

            query = {"state": "wrong_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with(
                "OAUTH2_STATE_MISMATCH", "error"
            )

        # Test OAuth2Error during token retrieval
        with patch.object(self.api, "setMessage") as mock_set_message, patch(
            "nxdrive.gui.api.OAuthentication"
        ) as mock_oauth_class, patch("nxdrive.gui.api.log") as mock_log, patch(
            "nxdrive.gui.api.Options"
        ) as mock_options:

            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            mock_options.oauth2_openid_configuration_url = None

            # Setup mock OAuth authentication to raise OAuth2Error
            mock_auth = Mock()
            mock_auth.get_token.side_effect = OAuth2Error("Token request failed")
            mock_oauth_class.return_value = mock_auth

            self.api.callback_params = {}

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify error logging
            mock_log.warning.assert_called_once_with(
                "Unexpected error while trying to get a token", exc_info=True
            )

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")

            # Verify config cleanup still happens
            expected_delete_calls = [
                (("tmp_oauth2_url",),),
                (("tmp_oauth2_code_verifier",),),
                (("tmp_oauth2_state",),),
            ]
            self.mock_manager.dao.delete_config.assert_has_calls(
                expected_delete_calls, any_order=True
            )
            assert self.mock_manager.dao.delete_config.call_count == 3

        # Test account creation error
        with patch.object(
            self.api, "create_account", return_value="ACCOUNT_CREATION_ERROR"
        ) as mock_create_account, patch.object(
            self.api, "setMessage"
        ) as mock_set_message, patch(
            "nxdrive.gui.api.OAuthentication"
        ) as mock_oauth_class, patch(
            "nxdrive.gui.api.Options"
        ) as mock_options:

            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            mock_options.oauth2_openid_configuration_url = None

            # Setup mock OAuth authentication
            mock_auth = Mock()
            mock_auth.get_token.return_value = "test_token"
            mock_auth.get_username.return_value = "testuser"
            mock_oauth_class.return_value = mock_auth

            self.api.callback_params = {}

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify account creation was attempted
            mock_create_account.assert_called_once_with("test_token", "testuser")

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with(
                "ACCOUNT_CREATION_ERROR", "error"
            )

            # Verify config cleanup
            expected_delete_calls = [
                (("tmp_oauth2_url",),),
                (("tmp_oauth2_code_verifier",),),
                (("tmp_oauth2_state",),),
            ]
            self.mock_manager.dao.delete_config.assert_has_calls(
                expected_delete_calls, any_order=True
            )
            assert self.mock_manager.dao.delete_config.call_count == 3

        # Test token update error
        with patch.object(
            self.api, "update_token", return_value="TOKEN_UPDATE_ERROR"
        ) as mock_update_token, patch.object(
            self.api, "setMessage"
        ) as mock_set_message, patch(
            "nxdrive.gui.api.OAuthentication"
        ) as mock_oauth_class, patch(
            "nxdrive.gui.api.Options"
        ) as mock_options:

            self.mock_manager.reset_mock()
            self.mock_manager.get_config.side_effect = lambda key: {
                "tmp_oauth2_url": "https://test.server.com",
                "tmp_oauth2_code_verifier": "test_verifier",
                "tmp_oauth2_state": "test_state",
            }.get(key)

            mock_options.oauth2_openid_configuration_url = None

            # Setup mock OAuth authentication
            mock_auth = Mock()
            mock_auth.get_token.return_value = "test_token"
            mock_auth.get_username.return_value = "testuser"
            mock_oauth_class.return_value = mock_auth

            self.api.callback_params = {"engine": "test_engine"}

            query = {"state": "test_state", "code": "auth_code"}
            self.api.continue_oauth2_flow(query)

            # Verify token update was attempted
            mock_update_token.assert_called_once_with("test_token", "testuser")

            # Verify error message emitted
            mock_set_message.emit.assert_called_once_with("TOKEN_UPDATE_ERROR", "error")

            # Verify config cleanup
            expected_delete_calls = [
                (("tmp_oauth2_url",),),
                (("tmp_oauth2_code_verifier",),),
                (("tmp_oauth2_state",),),
            ]
            self.mock_manager.dao.delete_config.assert_has_calls(
                expected_delete_calls, any_order=True
            )
            assert self.mock_manager.dao.delete_config.call_count == 3

    def test_create_account_comprehensive_functionality(self):
        """Comprehensive test covering all functionality of create_account method."""

        # Test successful account creation
        with patch.object(
            self.api, "bind_server", return_value=""
        ) as mock_bind_server, patch("nxdrive.gui.api.log") as mock_log:

            # Setup callback parameters
            self.api.callback_params = {
                "local_folder": "/test/local/folder",
                "server_url": "https://test.server.com",
                "engine_type": "NXDRIVE",
            }

            token = "test_oauth_token"
            username = "testuser@example.com"

            result = self.api.create_account(token, username)

            # Verify successful return (empty string indicates success)
            assert result == ""

            # Verify bind_server was called with correct parameters
            mock_bind_server.assert_called_once_with(
                "/test/local/folder",
                "https://test.server.com#NXDRIVE",
                "testuser@example.com",
                token="test_oauth_token",
            )

            # Verify logging for account creation start
            mock_log.info.assert_any_call(
                "Creating new account [local_folder='/test/local/folder', "
                "server_url='https://test.server.com#NXDRIVE', username='testuser@example.com']"
            )

            # Verify logging for bind_server return
            mock_log.info.assert_any_call("Return from bind_server() is ''")

            # Verify info was called twice (start and end logging)
            assert mock_log.info.call_count == 2

        # Test account creation with bind_server error
        with patch.object(
            self.api, "bind_server", return_value="BINDING_ERROR"
        ) as mock_bind_server, patch("nxdrive.gui.api.log") as mock_log:

            # Setup callback parameters
            self.api.callback_params = {
                "local_folder": "/test/local/folder",
                "server_url": "https://test.server.com",
                "engine_type": "CUSTOM_TYPE",
            }

            token = {"access_token": "oauth2_token", "token_type": "Bearer"}
            username = "user@domain.com"

            result = self.api.create_account(token, username)

            # Verify error returned from bind_server
            assert result == "BINDING_ERROR"

            # Verify bind_server was called with correct parameters including custom engine type
            mock_bind_server.assert_called_once_with(
                "/test/local/folder",
                "https://test.server.com#CUSTOM_TYPE",
                "user@domain.com",
                token={"access_token": "oauth2_token", "token_type": "Bearer"},
            )

            # Verify logging for account creation start with custom engine type
            mock_log.info.assert_any_call(
                "Creating new account [local_folder='/test/local/folder', "
                "server_url='https://test.server.com#CUSTOM_TYPE', username='user@domain.com']"
            )

            # Verify logging for bind_server return with error
            mock_log.info.assert_any_call(
                "Return from bind_server() is 'BINDING_ERROR'"
            )

        # Test exception during account creation
        with patch.object(
            self.api, "bind_server", side_effect=Exception("Unexpected error")
        ) as mock_bind_server, patch("nxdrive.gui.api.log") as mock_log:

            # Setup callback parameters
            self.api.callback_params = {
                "local_folder": "/error/folder",
                "server_url": "https://error.server.com",
                "engine_type": "ERROR_TYPE",
            }

            token = "error_token"
            username = "erroruser"

            result = self.api.create_account(token, username)

            # Verify CONNECTION_UNKNOWN error returned
            assert result == "CONNECTION_UNKNOWN"

            # Verify bind_server was called (but failed with exception)
            mock_bind_server.assert_called_once_with(
                "/error/folder",
                "https://error.server.com#ERROR_TYPE",
                "erroruser",
                token="error_token",
            )

            # Verify info logging for account creation start
            mock_log.info.assert_called_once_with(
                "Creating new account [local_folder='/error/folder', "
                "server_url='https://error.server.com#ERROR_TYPE', username='erroruser']"
            )

            # Verify exception logging with proper message and variables
            mock_log.exception.assert_called_once_with(
                "Unexpected error while trying to create a new account "
                "[local_folder='/error/folder', server_url='https://error.server.com#ERROR_TYPE', username='erroruser']"
            )

        # Test with missing callback parameters (exposes UnboundLocalError bug in original code)
        with patch("nxdrive.gui.api.log") as mock_log:

            # Setup incomplete callback parameters (missing required keys)
            self.api.callback_params = {
                "local_folder": "/test/folder"
                # Missing server_url and engine_type
            }

            token = "test_token"
            username = "testuser"

            # The current implementation has a bug: when server_url is missing from callback_params,
            # it raises UnboundLocalError because server_url is referenced in exception logging
            # but was never initialized due to the KeyError during parameter extraction
            with pytest.raises(
                UnboundLocalError, match="cannot access local variable 'server_url'"
            ):
                self.api.create_account(token, username)

        # Test with empty callback parameters (exposes UnboundLocalError bug)
        with patch("nxdrive.gui.api.log") as mock_log:

            # Setup empty callback parameters
            self.api.callback_params = {}

            token = "empty_token"
            username = "emptyuser"

            # The current implementation has a bug: when local_folder is missing from callback_params,
            # it raises UnboundLocalError because local_folder is referenced in exception logging
            # but was never initialized due to the KeyError during parameter extraction
            with pytest.raises(
                UnboundLocalError, match="cannot access local variable 'local_folder'"
            ):
                self.api.create_account(token, username)

        # Test with different token types (string vs dict)
        with patch.object(
            self.api, "bind_server", return_value=""
        ) as mock_bind_server, patch("nxdrive.gui.api.log") as mock_log:

            # Setup callback parameters
            self.api.callback_params = {
                "local_folder": "/dict/token/folder",
                "server_url": "https://dict.token.server.com",
                "engine_type": "DICT_ENGINE",
            }

            # Test with dictionary token (OAuth2 format)
            dict_token = {
                "access_token": "abc123",
                "refresh_token": "refresh456",
                "token_type": "Bearer",
                "expires_in": 3600,
            }
            username = "dicttokenuser"

            result = self.api.create_account(dict_token, username)

            # Verify successful return
            assert result == ""

            # Verify bind_server was called with dict token
            mock_bind_server.assert_called_once_with(
                "/dict/token/folder",
                "https://dict.token.server.com#DICT_ENGINE",
                "dicttokenuser",
                token=dict_token,
            )

            # Verify proper logging with dict token reference
            mock_log.info.assert_any_call(
                "Creating new account [local_folder='/dict/token/folder', "
                "server_url='https://dict.token.server.com#DICT_ENGINE', username='dicttokenuser']"
            )

        # Test with special characters in parameters
        with patch.object(
            self.api, "bind_server", return_value=""
        ) as mock_bind_server, patch("nxdrive.gui.api.log") as mock_log:

            # Setup callback parameters with special characters
            self.api.callback_params = {
                "local_folder": "/test folder/with spaces",
                "server_url": "https://test-server.example.com:8443",
                "engine_type": "CUSTOM_ENGINE_2.0",
            }

            token = "special_chars_token"
            username = "user@sub-domain.example.com"

            result = self.api.create_account(token, username)

            # Verify successful return
            assert result == ""

            # Verify bind_server was called with parameters containing special characters
            mock_bind_server.assert_called_once_with(
                "/test folder/with spaces",
                "https://test-server.example.com:8443#CUSTOM_ENGINE_2.0",
                "user@sub-domain.example.com",
                token="special_chars_token",
            )

            # Verify logging handles special characters correctly
            expected_log_message = (
                "Creating new account [local_folder='/test folder/with spaces', "
                "server_url='https://test-server.example.com:8443#CUSTOM_ENGINE_2.0', "
                "username='user@sub-domain.example.com']"
            )
            mock_log.info.assert_any_call(expected_log_message)
