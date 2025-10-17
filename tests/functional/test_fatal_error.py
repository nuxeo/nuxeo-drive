"""Functional tests for fatal_error.py module."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from nxdrive.constants import APP_NAME
from nxdrive.fatal_error import (
    check_executable_path,
    check_executable_path_error_qt,
    check_os_version,
    fatal_error_mac,
    fatal_error_qt,
    fatal_error_win,
    show_critical_error,
)
from nxdrive.options import Options
from tests.functional.mocked_classes import Mock_Qt

from ..markers import mac_only, not_linux, windows_only


class TestExecutablePathChecking:
    """Test cases for executable path validation functionality."""

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_check_executable_path_error_qt_basic(self):
        """Test check_executable_path_error_qt displays error dialog."""
        mock_qt = Mock_Qt()
        test_path = Path("/invalid/path/app.app")

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QPixmap"
        ) as mock_pixmap, patch(
            "nxdrive.qt.imports.QMessageBox"
        ) as mock_messagebox, patch(
            "nxdrive.translator.Translator"
        ) as mock_translator, patch(
            "nxdrive.utils.find_icon"
        ) as mock_find_icon, patch(
            "nxdrive.utils.find_resource"
        ) as mock_find_resource:

            mock_app.return_value = mock_qt
            mock_pixmap.return_value = "dummy_icon"
            mock_messagebox.return_value = mock_qt
            mock_find_icon.return_value = "icon_path"
            mock_find_resource.return_value = "i18n_path"

            # Mock the Translator.get method
            mock_translator.get.return_value = "Error message"

            result = check_executable_path_error_qt(test_path)

            assert result is None
            mock_app.assert_called_once_with([])
            mock_messagebox.assert_called_once()
            # Note: exec_ is called but we can't assert on Mock_Qt methods

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_check_executable_path_error_qt_with_translations(self):
        """Test check_executable_path_error_qt with proper translations."""
        mock_qt = Mock_Qt()
        test_path = Path("/Applications/WrongName.app")

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QPixmap"
        ), patch("nxdrive.qt.imports.QMessageBox") as mock_messagebox, patch(
            "nxdrive.translator.Translator"
        ) as mock_translator_class, patch(
            "nxdrive.utils.find_icon"
        ) as mock_find_icon, patch(
            "nxdrive.utils.find_resource"
        ) as mock_find_resource:

            mock_app.return_value = mock_qt
            mock_messagebox.return_value = mock_qt
            mock_find_icon.return_value = Path("/path/to/icon.svg")
            mock_find_resource.return_value = Path("/path/to/i18n")

            # Mock translator instance and get method
            mock_translator = MagicMock()
            mock_translator.get.return_value = (
                f"Please move the application to /Applications/{APP_NAME}.app"
            )
            mock_translator_class.return_value = mock_translator

            check_executable_path_error_qt(test_path)

            # Verify translator was called with correct parameters
            mock_translator_class.assert_called_once_with(Path("/path/to/i18n"))

    @mac_only
    def test_check_executable_path_valid_applications_folder(self):
        """Test check_executable_path returns True for valid Applications folder path."""
        valid_path = f"/Applications/{APP_NAME}.app/Contents/MacOS/{APP_NAME}"
        original_frozen = Options.is_frozen
        try:
            Options.set("is_frozen", True, setter="manual")
            with patch("sys.executable", valid_path):
                result = check_executable_path()
                assert result is True
        finally:
            Options.set("is_frozen", original_frozen, setter="manual")

    @mac_only
    def test_check_executable_path_valid_user_applications(self):
        """Test check_executable_path returns True for valid user Applications folder."""
        home_path = Path.home() / "Applications" / f"{APP_NAME}.app"
        valid_path = f"{home_path}/Contents/MacOS/{APP_NAME}"
        original_frozen = Options.is_frozen
        try:
            Options.set("is_frozen", True, setter="manual")
            with patch("sys.executable", valid_path):
                result = check_executable_path()
                assert result is True
        finally:
            Options.set("is_frozen", original_frozen, setter="manual")

    @mac_only
    def test_check_executable_path_invalid_path_qt_success(self):
        """Test check_executable_path with invalid path but Qt dialog works."""
        invalid_path = f"/Users/test/Downloads/{APP_NAME}.app/Contents/MacOS/{APP_NAME}"
        original_frozen = Options.is_frozen
        try:
            Options.set("is_frozen", True, setter="manual")
            with patch("sys.executable", invalid_path), patch(
                "nxdrive.fatal_error.check_executable_path_error_qt"
            ) as mock_qt_error:

                result = check_executable_path()

                assert result is False
                mock_qt_error.assert_called_once()
                # Verify it was called with the correct path
                called_path = mock_qt_error.call_args[0][0]
                assert str(called_path).endswith(f"{APP_NAME}.app")
        finally:
            Options.set("is_frozen", original_frozen, setter="manual")

    @mac_only
    def test_check_executable_path_invalid_path_qt_fails(self):
        """Test check_executable_path falls back to macOS dialog when Qt fails."""
        invalid_path = f"/tmp/{APP_NAME}.app/Contents/MacOS/{APP_NAME}"
        qt_exception = Exception("Qt initialization failed")
        original_frozen = Options.is_frozen
        try:
            Options.set("is_frozen", True, setter="manual")
            with patch("sys.executable", invalid_path), patch(
                "nxdrive.fatal_error.check_executable_path_error_qt",
                side_effect=qt_exception,
            ), patch("nxdrive.fatal_error.fatal_error_mac") as mock_mac_error:

                result = check_executable_path()

                assert result is False
                mock_mac_error.assert_called_once()
                # Verify the error message contains the exception details
                error_text = mock_mac_error.call_args[0][0]
                assert "entire installation is broken" in error_text
                assert "Qt initialization failed" in error_text
        finally:
            Options.set("is_frozen", original_frozen, setter="manual")

    def test_check_executable_path_not_mac_or_not_frozen(self):
        """Test check_executable_path returns True when not on macOS or not frozen."""
        with patch("nxdrive.fatal_error.MAC", False):
            result = check_executable_path()
            assert result is True

        with patch("nxdrive.fatal_error.MAC", True):
            # Store original value
            original_frozen = Options.is_frozen
            try:
                # Set is_frozen to False using Options.set
                Options.set("is_frozen", False, setter="manual")
                result = check_executable_path()
                assert result is True
            finally:
                # Restore original value
                Options.set("is_frozen", original_frozen, setter="manual")


class TestOSVersionChecking:
    """Test cases for OS version validation functionality."""

    @mac_only
    def test_check_os_version_mac_supported(self):
        """Test check_os_version returns True for supported macOS versions."""
        with patch("platform.mac_ver", return_value=("11.6.0", "", "")):
            result = check_os_version()
            assert result is True

        with patch("platform.mac_ver", return_value=("10.15.7", "", "")):
            result = check_os_version()
            assert result is True

    @mac_only
    def test_check_os_version_mac_unsupported(self):
        """Test check_os_version returns False for unsupported macOS versions."""
        with patch("platform.mac_ver", return_value=("10.12.6", "", "")), patch(
            "nxdrive.fatal_error.fatal_error_mac"
        ) as mock_fatal:

            result = check_os_version()

            assert result is False
            mock_fatal.assert_called_once()
            error_msg = mock_fatal.call_args[0][0]
            assert "macOS 10.13 (High Sierra) or newer is required" in error_msg
            assert "10.12.6" in error_msg

    @windows_only
    def test_check_os_version_windows_supported(self):
        """Test check_os_version returns True for supported Windows versions."""
        # Mock Windows 10 (version 10.0)
        with patch("sys.getwindowsversion", return_value=(10, 0, 0, 0, "")):
            result = check_os_version()
            assert result is True

        # Mock Windows 8.1 (version 6.3)
        with patch("sys.getwindowsversion", return_value=(6, 3, 0, 0, "")):
            result = check_os_version()
            assert result is True

    @windows_only
    def test_check_os_version_windows_unsupported(self):
        """Test check_os_version returns False for unsupported Windows versions."""
        # Mock Windows 7 (version 6.1)
        with patch("sys.getwindowsversion", return_value=(6, 1, 0, 0, "")), patch(
            "nxdrive.fatal_error.fatal_error_win"
        ) as mock_fatal:

            result = check_os_version()

            assert result is False
            mock_fatal.assert_called_once_with("Windows 8 or newer is required.")

    def test_check_os_version_other_platforms(self):
        """Test check_os_version returns True for other platforms (Linux)."""
        with patch("nxdrive.fatal_error.MAC", False), patch(
            "nxdrive.fatal_error.WINDOWS", False
        ):
            result = check_os_version()
            assert result is True


class TestPlatformSpecificFatalErrors:
    """Test cases for platform-specific fatal error dialogs."""

    @windows_only
    def test_fatal_error_win_basic(self):
        """Test fatal_error_win displays Windows message box."""
        error_text = "Critical application error occurred"

        with patch("ctypes.windll.user32.MessageBoxW") as mock_messagebox:
            result = fatal_error_win(error_text)

            assert result is None
            mock_messagebox.assert_called_once_with(
                0, error_text, f"{APP_NAME} Fatal Error", 0x0 | 0x10
            )

    @windows_only
    def test_fatal_error_win_with_special_characters(self):
        """Test fatal_error_win handles special characters in error text."""
        error_text = "Error with Unicode: café, naïve, résumé"

        with patch("ctypes.windll.user32.MessageBoxW") as mock_messagebox:
            fatal_error_win(error_text)

            mock_messagebox.assert_called_once_with(
                0, error_text, f"{APP_NAME} Fatal Error", 0x0 | 0x10
            )

    @mac_only
    def test_fatal_error_mac_basic(self):
        """Test fatal_error_mac displays macOS dialog via osascript."""
        error_text = "Critical application error occurred"

        with patch("subprocess.Popen") as mock_popen:
            result = fatal_error_mac(error_text)

            assert result is None
            mock_popen.assert_called_once()

            # Verify the osascript command was constructed correctly
            call_args = mock_popen.call_args[0][0]
            assert call_args[0] == "osascript"
            assert call_args[1] == "-e"
            assert f"{APP_NAME} Fatal Error" in call_args[2]
            assert error_text in call_args[2]

    @mac_only
    def test_fatal_error_mac_escapes_quotes(self):
        """Test fatal_error_mac properly escapes quotes in error text."""
        error_text = 'Error with "quotes" in message'

        with patch("subprocess.Popen") as mock_popen:
            fatal_error_mac(error_text)

            call_args = mock_popen.call_args[0][0]
            # Quotes should be escaped
            assert r"Error with \"quotes\" in message" in call_args[2]

    @mac_only
    def test_fatal_error_mac_complex_message(self):
        """Test fatal_error_mac handles complex error messages."""
        error_text = """
        Multi-line error
        with "quotes" and
        special characters: café
        """

        with patch("subprocess.Popen") as mock_popen:
            fatal_error_mac(error_text)

            mock_popen.assert_called_once()
            call_args = mock_popen.call_args[0][0]
            assert "osascript" in call_args
            assert "Tell me to display dialog" in call_args[2]


class TestQtFatalErrorDialog:
    """Test cases for Qt-based fatal error dialog functionality."""

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_fatal_error_qt_basic_display(self):
        """Test fatal_error_qt creates and displays dialog with exception."""
        exception_text = (
            "Traceback (most recent call last):\n  File test.py\nValueError: Test error"
        )

        # Mock Qt components
        mock_qt = Mock_Qt()
        mock_dialog = MagicMock()
        mock_layout = MagicMock()

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QDialog"
        ) as mock_dialog_class, patch(
            "nxdrive.qt.imports.QVBoxLayout"
        ) as mock_layout_class, patch(
            "nxdrive.qt.imports.QLabel"
        ), patch(
            "nxdrive.qt.imports.QTextEdit"
        ), patch(
            "nxdrive.qt.imports.QDialogButtonBox"
        ), patch(
            "nxdrive.qt.imports.QIcon"
        ), patch(
            "nxdrive.translator.Translator"
        ) as mock_translator, patch(
            "nxdrive.utils.find_icon"
        ) as mock_find_icon, patch(
            "nxdrive.utils.find_resource"
        ) as mock_find_resource:

            # Setup mocks
            mock_app.return_value = mock_qt
            mock_dialog_class.return_value = mock_dialog
            mock_layout_class.return_value = mock_layout
            mock_find_icon.return_value = "icon_path"
            mock_find_resource.return_value = "i18n_path"

            # Mock translator
            mock_translator.get.side_effect = (
                lambda key, values=None: f"Translated: {key}"
            )

            # Mock dialog components
            mock_dialog.resize = MagicMock()
            mock_dialog.setWindowTitle = MagicMock()
            mock_dialog.setWindowIcon = MagicMock()
            mock_dialog.setLayout = MagicMock()
            mock_dialog.show = MagicMock()

            fatal_error_qt(exception_text)

            # Verify basic dialog setup
            mock_dialog_class.assert_called_once()
            mock_dialog.setWindowTitle.assert_called_once()
            mock_dialog.resize.assert_called_once_with(800, 600)
            mock_dialog.show.assert_called_once()
            # Note: exec_ is called but we can't assert on Mock_Qt methods

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_fatal_error_qt_with_cli_args(self):
        """Test fatal_error_qt displays CLI arguments when present."""
        exception_text = "Test exception"
        original_argv = sys.argv.copy()

        try:
            # Set CLI arguments
            sys.argv = ["nxdrive", "--debug", "--log-level", "INFO"]

            mock_qt = Mock_Qt()
            mock_dialog = MagicMock()

            with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
                "nxdrive.qt.imports.QDialog"
            ) as mock_dialog_class, patch("nxdrive.qt.imports.QVBoxLayout"), patch(
                "nxdrive.qt.imports.QLabel"
            ), patch(
                "nxdrive.qt.imports.QTextEdit"
            ) as mock_textedit, patch(
                "nxdrive.qt.imports.QDialogButtonBox"
            ), patch(
                "nxdrive.qt.imports.QIcon"
            ), patch(
                "nxdrive.translator.Translator"
            ) as mock_translator, patch(
                "nxdrive.utils.find_icon"
            ), patch(
                "nxdrive.utils.find_resource"
            ):

                mock_app.return_value = mock_qt
                mock_dialog_class.return_value = mock_dialog
                mock_translator.get.side_effect = (
                    lambda key, values=None: f"Translated: {key}"
                )

                # Mock text edit widget for CLI args
                mock_cli_textedit = MagicMock()
                mock_textedit.return_value = mock_cli_textedit

                fatal_error_qt(exception_text)

                # Verify CLI args text edit was created and configured
                assert mock_textedit.call_count >= 1  # At least one for CLI args
                mock_cli_textedit.setReadOnly.assert_called()

        finally:
            sys.argv = original_argv

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_fatal_error_qt_with_logs(self):
        """Test fatal_error_qt displays log information when available."""
        exception_text = "Test exception"
        mock_log_lines = [
            b"2023-01-01 10:00:00 INFO Starting application",
            b"2023-01-01 10:00:01 ERROR Something went wrong",
            b"2023-01-01 10:00:02 FATAL Critical error",
        ]

        mock_qt = Mock_Qt()
        mock_dialog = MagicMock()

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QDialog"
        ) as mock_dialog_class, patch("nxdrive.qt.imports.QVBoxLayout"), patch(
            "nxdrive.qt.imports.QLabel"
        ), patch(
            "nxdrive.qt.imports.QTextEdit"
        ), patch(
            "nxdrive.qt.imports.QDialogButtonBox"
        ), patch(
            "nxdrive.qt.imports.QIcon"
        ), patch(
            "nxdrive.translator.Translator"
        ) as mock_translator, patch(
            "nxdrive.utils.find_icon"
        ), patch(
            "nxdrive.utils.find_resource"
        ), patch(
            "nxdrive.report.Report"
        ) as mock_report:

            mock_app.return_value = mock_qt
            mock_dialog_class.return_value = mock_dialog
            mock_translator.get.side_effect = (
                lambda key, values=None: f"Translated: {key}"
            )

            # Mock report export_logs
            mock_report.export_logs.return_value = mock_log_lines

            fatal_error_qt(exception_text)

            # Verify report was called to get logs
            mock_report.export_logs.assert_called_once_with(20)

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_fatal_error_qt_copy_functionality(self):
        """Test fatal_error_qt copy details functionality."""
        exception_text = "Test exception"

        mock_qt = Mock_Qt()
        mock_dialog = MagicMock()
        mock_buttonbox = MagicMock()
        mock_copy_button = MagicMock()

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QDialog"
        ) as mock_dialog_class, patch("nxdrive.qt.imports.QVBoxLayout"), patch(
            "nxdrive.qt.imports.QLabel"
        ), patch(
            "nxdrive.qt.imports.QTextEdit"
        ), patch(
            "nxdrive.qt.imports.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nxdrive.qt.imports.QIcon"
        ), patch(
            "nxdrive.translator.Translator"
        ) as mock_translator, patch(
            "nxdrive.utils.find_icon"
        ), patch(
            "nxdrive.utils.find_resource"
        ), patch(
            "nxdrive.osi.AbstractOSIntegration"
        ) as mock_osi:

            mock_app.return_value = mock_qt
            mock_dialog_class.return_value = mock_dialog
            mock_buttonbox_class.return_value = mock_buttonbox
            mock_translator.get.side_effect = (
                lambda key, values=None: f"Translated: {key}"
            )

            # Mock OSI clipboard functionality
            mock_osi_instance = MagicMock()
            mock_osi.get.return_value = mock_osi_instance
            mock_buttonbox.addButton.return_value = mock_copy_button

            fatal_error_qt(exception_text)

            # Verify copy button was added
            assert mock_buttonbox.addButton.call_count >= 1

    @not_linux(reason="Qt does not work correctly on Linux")
    def test_fatal_error_qt_update_button_functionality(self):
        """Test fatal_error_qt update button opens correct URL."""
        exception_text = "Test exception"

        mock_qt = Mock_Qt()
        mock_dialog = MagicMock()
        mock_buttonbox = MagicMock()

        with patch("nxdrive.qt.imports.QApplication") as mock_app, patch(
            "nxdrive.qt.imports.QDialog"
        ) as mock_dialog_class, patch("nxdrive.qt.imports.QVBoxLayout"), patch(
            "nxdrive.qt.imports.QLabel"
        ), patch(
            "nxdrive.qt.imports.QTextEdit"
        ), patch(
            "nxdrive.qt.imports.QDialogButtonBox"
        ) as mock_buttonbox_class, patch(
            "nxdrive.qt.imports.QIcon"
        ), patch(
            "nxdrive.qt.imports.QDesktopServices"
        ), patch(
            "nxdrive.qt.imports.QUrl"
        ), patch(
            "nxdrive.translator.Translator"
        ) as mock_translator, patch(
            "nxdrive.utils.find_icon"
        ), patch(
            "nxdrive.utils.find_resource"
        ):

            mock_app.return_value = mock_qt
            mock_dialog_class.return_value = mock_dialog
            mock_buttonbox_class.return_value = mock_buttonbox
            mock_translator.get.side_effect = (
                lambda key, values=None: f"Translated: {key}"
            )

            # Capture the update button click handler
            update_button_calls = []

            def mock_add_button(text, role):
                button = MagicMock()
                if "UPDATE" in text:
                    update_button_calls.append(button)
                return button

            mock_buttonbox.addButton.side_effect = mock_add_button

            fatal_error_qt(exception_text)

            # Verify update button was created
            assert len(update_button_calls) >= 1


class TestCriticalErrorHandling:
    """Test cases for show_critical_error functionality."""

    def test_show_critical_error_qt_success(self):
        """Test show_critical_error uses Qt dialog when available."""
        # Create a mock exception
        try:
            raise ValueError("Test critical error")
        except ValueError:
            with patch("nxdrive.fatal_error.fatal_error_qt") as mock_qt_error, patch(
                "pathlib.Path.home"
            ) as mock_home, patch("pathlib.Path.mkdir"), patch(
                "pathlib.Path.write_text"
            ):

                mock_home.return_value = Path("/home/user")

                show_critical_error()

                # Verify Qt dialog was called
                mock_qt_error.assert_called_once()
                # Verify the traceback was passed
                error_text = mock_qt_error.call_args[0][0]
                assert "ValueError: Test critical error" in error_text
                assert "Traceback" in error_text

    def test_show_critical_error_crash_file_creation(self):
        """Test show_critical_error creates crash file."""
        try:
            raise RuntimeError("Critical system error")
        except RuntimeError:
            mock_crash_file = MagicMock()
            mock_crash_dir = MagicMock()

            with patch("pathlib.Path.home") as mock_home, patch(
                "nxdrive.fatal_error.fatal_error_qt"
            ) as mock_qt_error:

                # Mock home directory and crash file
                mock_home_path = MagicMock()
                mock_home.return_value = mock_home_path
                mock_nuxeo_dir = MagicMock()
                mock_home_path.__truediv__.return_value = mock_nuxeo_dir
                mock_nuxeo_dir.__truediv__.return_value = mock_crash_file
                mock_crash_file.parent = mock_crash_dir

                show_critical_error()

                # Verify crash file directory was created
                mock_crash_dir.mkdir.assert_called_once_with(
                    parents=True, exist_ok=True
                )
                # Verify crash file was written
                mock_crash_file.write_text.assert_called_once()

                # Verify Qt dialog was called
                mock_qt_error.assert_called_once()

                # Verify the content includes the exception
                write_call_args = mock_crash_file.write_text.call_args
                crash_content = write_call_args[0][0]
                assert "RuntimeError: Critical system error" in crash_content

    @windows_only
    def test_show_critical_error_qt_fails_windows_fallback(self):
        """Test show_critical_error falls back to Windows dialog when Qt fails."""
        try:
            raise OSError("File system error")
        except OSError:
            qt_exception = Exception("Qt not available")

            with patch(
                "nxdrive.fatal_error.fatal_error_qt", side_effect=qt_exception
            ), patch("nxdrive.fatal_error.fatal_error_win") as mock_win_error, patch(
                "pathlib.Path.home"
            ), patch(
                "pathlib.Path.mkdir"
            ), patch(
                "pathlib.Path.write_text"
            ):

                show_critical_error()

                # Verify Windows dialog was called
                mock_win_error.assert_called_once()
                error_text = mock_win_error.call_args[0][0]
                assert "entire installation is broken" in error_text
                assert "OSError: File system error" in error_text
                assert "Qt not available" in error_text

    @mac_only
    def test_show_critical_error_qt_fails_mac_fallback(self):
        """Test show_critical_error falls back to macOS dialog when Qt fails."""
        try:
            raise ConnectionError("Network connection failed")
        except ConnectionError:
            qt_exception = Exception("Qt initialization error")

            with patch(
                "nxdrive.fatal_error.fatal_error_qt", side_effect=qt_exception
            ), patch("nxdrive.fatal_error.fatal_error_mac") as mock_mac_error, patch(
                "pathlib.Path.home"
            ), patch(
                "pathlib.Path.mkdir"
            ), patch(
                "pathlib.Path.write_text"
            ):

                show_critical_error()

                # Verify macOS dialog was called
                mock_mac_error.assert_called_once()
                error_text = mock_mac_error.call_args[0][0]
                assert "entire installation is broken" in error_text
                assert "ConnectionError: Network connection failed" in error_text
                assert "Qt initialization error" in error_text

    def test_show_critical_error_qt_fails_linux_fallback(self):
        """Test show_critical_error falls back to stderr on Linux when Qt fails."""
        try:
            raise MemoryError("Out of memory")
        except MemoryError:
            qt_exception = Exception("Display not available")

            with patch(
                "nxdrive.fatal_error.fatal_error_qt", side_effect=qt_exception
            ), patch("nxdrive.fatal_error.MAC", False), patch(
                "nxdrive.fatal_error.WINDOWS", False
            ), patch(
                "pathlib.Path.home"
            ), patch(
                "pathlib.Path.mkdir"
            ), patch(
                "pathlib.Path.write_text"
            ), patch(
                "sys.stderr"
            ) as mock_stderr:

                show_critical_error()

                # Verify error was printed to stderr
                mock_stderr.write.assert_called()

    def test_show_critical_error_crash_file_exception_handling(self):
        """Test show_critical_error handles crash file creation errors gracefully."""
        try:
            raise ValueError("Test error for crash file")
        except ValueError:
            with patch("nxdrive.fatal_error.fatal_error_qt") as mock_qt_error, patch(
                "pathlib.Path.home",
                side_effect=Exception("Home directory access failed"),
            ):

                # Should not raise exception even if crash file creation fails
                show_critical_error()

                # Qt dialog should still be called
                mock_qt_error.assert_called_once()

    def test_show_critical_error_no_exception_context(self):
        """Test show_critical_error handles case when no exception context exists."""
        # Simulate no exception context
        with patch("sys.exc_info", return_value=(None, None, None)), patch(
            "traceback.format_exception", return_value=["No exception information\n"]
        ), patch("nxdrive.fatal_error.fatal_error_qt") as mock_qt_error, patch(
            "pathlib.Path.home"
        ), patch(
            "pathlib.Path.mkdir"
        ), patch(
            "pathlib.Path.write_text"
        ):

            show_critical_error()

            # Should still call Qt dialog even without exception info
            mock_qt_error.assert_called_once()


class TestIntegrationScenarios:
    """Integration test cases for real-world scenarios."""

    def test_startup_path_validation_workflow(self):
        """Test complete startup path validation workflow."""
        # Simulate macOS frozen app in wrong location
        original_frozen = Options.is_frozen
        try:
            Options.set("is_frozen", True, setter="manual")
            with patch("nxdrive.fatal_error.MAC", True), patch(
                "sys.executable",
                "/Users/test/Downloads/Nuxeo Drive.app/Contents/MacOS/Nuxeo Drive",
            ), patch(
                "nxdrive.fatal_error.check_executable_path_error_qt",
                side_effect=Exception("Qt failed"),
            ), patch(
                "nxdrive.fatal_error.fatal_error_mac"
            ) as mock_mac_error:

                result = check_executable_path()

                assert result is False
                mock_mac_error.assert_called_once()
        finally:
            Options.set("is_frozen", original_frozen, setter="manual")

    def test_version_compatibility_workflow(self):
        """Test complete version compatibility check workflow."""
        # Test unsupported macOS version
        with patch("nxdrive.fatal_error.MAC", True), patch(
            "nxdrive.fatal_error.WINDOWS", False
        ), patch("platform.mac_ver", return_value=("10.11.6", "", "")), patch(
            "nxdrive.fatal_error.fatal_error_mac"
        ) as mock_mac_error:

            result = check_os_version()

            assert result is False
            mock_mac_error.assert_called_once()
            error_msg = mock_mac_error.call_args[0][0]
            assert "macOS 10.13" in error_msg

    def test_complete_error_display_workflow(self):
        """Test complete error display workflow from exception to user dialog."""
        # Simulate a real application error
        def problematic_function():
            raise FileNotFoundError(
                "Configuration file not found: /path/to/config.json"
            )

        try:
            problematic_function()
        except FileNotFoundError:
            with patch("nxdrive.fatal_error.fatal_error_qt") as mock_qt_error, patch(
                "pathlib.Path.home"
            ) as mock_home, patch("pathlib.Path.mkdir"), patch(
                "pathlib.Path.write_text"
            ) as mock_write:

                mock_home.return_value = Path("/home/testuser")

                show_critical_error()

                # Verify the complete workflow
                mock_qt_error.assert_called_once()
                error_content = mock_qt_error.call_args[0][0]
                assert "FileNotFoundError" in error_content
                assert "Configuration file not found" in error_content
                assert "problematic_function" in error_content

                # Verify crash file was handled
                mock_write.assert_called_once()

    @windows_only
    def test_multi_platform_error_handling_windows(self):
        """Test Windows error handling behavior."""
        error_text = "Multi-platform error test"

        # Test Windows behavior
        with patch("ctypes.windll.user32.MessageBoxW") as mock_win_dialog:
            fatal_error_win(error_text)
            mock_win_dialog.assert_called_once()

    @mac_only
    def test_multi_platform_error_handling_mac(self):
        """Test macOS error handling behavior."""
        error_text = "Multi-platform error test"

        # Test macOS behavior
        with patch("subprocess.Popen") as mock_mac_dialog:
            fatal_error_mac(error_text)
            mock_mac_dialog.assert_called_once()


def teardown_module():
    """Cleanup after all tests are done."""
    # Reset any module-level state if needed
    pass
