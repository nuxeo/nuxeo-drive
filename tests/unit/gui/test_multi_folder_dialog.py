"""Unit tests for nxdrive.gui.multi_folder_dialog module."""

import struct
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QDir, QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent, QStandardItemModel
from PyQt6.QtWidgets import QApplication, QListWidget, QListWidgetItem

from nxdrive.gui.multi_folder_dialog import (
    CenteredHeaderFileSystemModel,
    FDAAlert,
    MultiFolderDialog,
)

from ...markers import not_linux

pytestmark = not_linux(
    reason="Qt GUI tests don't work reliably on Linux",
)


@pytest.fixture(scope="module")
def qapp():
    """Ensure a QApplication instance exists."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    yield app


@pytest.fixture
def mfd_setup(qapp, tmp_path):
    """Setup a MultiFolderDialog with a temporary filesystem."""
    from nxdrive.options import Options

    original_res_dir = Options.res_dir
    Options.set("res_dir", tmp_path)

    # Create test structure
    (tmp_path / "folder1").mkdir()
    (tmp_path / "folder2").mkdir()
    (tmp_path / "file1.txt").touch()
    (tmp_path / "file2.txt").touch()
    (tmp_path / ".hidden_file").touch()
    (tmp_path / ".hidden_folder").mkdir()

    with patch(
        "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
    ), patch(
        "nxdrive.gui.multi_folder_dialog.find_icon",
        return_value=Path("/tmp/fake_icon.svg"),
    ):

        # Mock stylesheet paths
        (tmp_path / "styles").mkdir(exist_ok=True)
        (tmp_path / "styles" / "multi_folder_dialog_light.qss").touch()
        (tmp_path / "styles" / "multi_folder_dialog_dark.qss").touch()

        dialog = MultiFolderDialog()
        dialog.path_bar.setText(str(tmp_path))
        # Point the model to our tmp_path
        dialog.model.setRootPath(str(tmp_path))
        dialog.tree.setRootIndex(dialog.model.index(str(tmp_path)))
        yield dialog, tmp_path

    Options.set("res_dir", original_res_dir)


class TestCenteredHeaderFileSystemModel:
    """Test cases for CenteredHeaderFileSystemModel."""

    def test_header_data_text_alignment(self, qapp):
        model = CenteredHeaderFileSystemModel()
        alignment = model.headerData(
            0, Qt.Orientation.Horizontal, Qt.ItemDataRole.TextAlignmentRole
        )
        assert alignment == Qt.AlignmentFlag.AlignCenter

        # Default role should call super
        data = model.headerData(
            0, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
        )
        assert data is not None


class TestFDAAlert:
    """Test cases for FDAAlert."""

    def test_fda_alert_initialization(self, qapp):
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            alert = FDAAlert()
            assert alert.objectName() == "fdaAlertDialog"
            assert alert.ok_button.text() == "FDA_POPUP_SYSTEM_SETTINGS"
            assert alert.not_now_button.text() == "FDA_POPUP_NOT_NOW"

    def test_fda_alert_accept_reject(self, qapp):
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            alert = FDAAlert()
            alert.close_alert()
            assert not FDAAlert.visible

            alert.reject()
            assert not FDAAlert.visible

    def test_fda_alert_key_press(self, qapp):
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            alert = FDAAlert()

            # Escape key
            event_esc = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
            )
            with patch.object(alert, "reject") as mock_reject:
                alert.keyPressEvent(event_esc)
                mock_reject.assert_called_once()

            # Enter key on checkbox
            event_enter = QKeyEvent(
                QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
            )
            alert.dont_show_checkbox.setFocus()
            with patch.object(alert, "accept") as mock_accept:
                alert.keyPressEvent(event_enter)
                mock_accept.assert_called_once()

            # None event
            alert.keyPressEvent(None)

    def test_fda_alert_remember_close_choice(self, qapp, tmp_path):
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ), patch("nxdrive.gui.multi_folder_dialog.Path.home", return_value=tmp_path):
            alert = FDAAlert()
            dont_show_file = tmp_path / ".nuxeo-drive" / "dont_show_fda_alert"

            # Check choice
            alert.remember_close_choice(Qt.CheckState.Checked)  # type: ignore[arg-type]
            assert dont_show_file.exists()

            # Uncheck choice
            alert.remember_close_choice(Qt.CheckState.Unchecked)  # type: ignore[arg-type]
            assert not dont_show_file.exists()

    def test_fda_alert_accept_focus_behavior(self, qapp):
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            alert = FDAAlert()
            with patch.object(
                alert.dont_show_checkbox, "hasFocus", return_value=False
            ), patch.object(alert.dont_show_checkbox, "toggle") as mock_toggle:
                alert.accept()
                mock_toggle.assert_not_called()

            with patch.object(
                alert.dont_show_checkbox, "hasFocus", return_value=True
            ), patch.object(alert.dont_show_checkbox, "toggle") as mock_toggle:
                alert.accept()
                mock_toggle.assert_called_once()


class TestMultiFolderDialog:
    """Test cases for MultiFolderDialog."""

    def test_mfd_initialization(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        assert mfd.windowTitle() == "SELECT_FILES_FOLDERS"
        assert mfd.path_bar.text() == str(tmp_path)

    def test_mfd_dark_mode_changed(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        with patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            mfd._on_dark_mode_changed(True)
            assert mfd._dark_mode is True

    def test_mfd_dark_mode_changed_reloads_panel_and_icons(self, mfd_setup):
        mfd, _ = mfd_setup
        fake_item = MagicMock()
        fake_widget = MagicMock()
        fake_item.widget.return_value = fake_widget

        with patch.object(
            mfd.panel_layout, "takeAt", return_value=fake_item
        ), patch.object(mfd.panel_layout, "addWidget") as mock_add_widget, patch.object(
            mfd, "panel_locations", return_value=MagicMock()
        ), patch.object(
            mfd, "fetch_icon", return_value=mfd.btnHome.icon()
        ):
            mfd._on_dark_mode_changed(False)

        assert mfd._dark_mode is False
        fake_widget.deleteLater.assert_called_once()
        mock_add_widget.assert_called_once()

    def test_mfd_selected_paths(self, mfd_setup):
        mfd, tmp_path = mfd_setup

        # Select files
        file1 = str(tmp_path / "file1.txt")
        file2 = str(tmp_path / "file2.txt")
        index1 = mfd.model.index(file1)
        index2 = mfd.model.index(file2)

        selection_model = mfd.tree.selectionModel()
        selection_model.select(
            index1,
            selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
        )
        selection_model.select(
            index2,
            selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
        )

        selected = [str(Path(p)) for p in mfd.selected_paths()]
        assert file1 in selected
        assert file2 in selected
        assert len(selected) == 2

        # Select folders
        folder1 = str(tmp_path / "folder1")
        index_f1 = mfd.model.index(folder1)
        selection_model.clearSelection()
        selection_model.select(
            index_f1,
            selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
        )

        selected = [str(Path(p)) for p in mfd.selected_paths()]
        assert folder1 in selected
        assert len(selected) == 1

        # Mixed selection
        selection_model.select(
            index1,
            selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
        )
        selected = [str(Path(p)) for p in mfd.selected_paths()]
        assert folder1 in selected
        assert file1 in selected
        assert len(selected) == 2

        # Tag mode
        mfd._using_custom_model = True
        mock_tag_model = QStandardItemModel()
        mfd.tree.setModel(mock_tag_model)
        with patch.object(mfd.tree, "selectionModel") as mock_sel_model:
            mock_index = MagicMock()
            mock_index.column.return_value = 0
            mock_index.data.return_value = "/tag/path"
            mock_sel_model.return_value.selectedIndexes.return_value = [mock_index]
            assert mfd.selected_paths() == ["/tag/path"]

        # Restore for other tests
        mfd._restore_filesystem_model()

    def test_mfd_selected_paths_handles_missing_selection_model(self, mfd_setup):
        mfd, _ = mfd_setup

        with patch.object(mfd.tree, "selectionModel", return_value=None):
            assert mfd.selected_paths() == []

        mfd._using_custom_model = True
        with patch.object(mfd.tree, "selectionModel", return_value=None):
            assert mfd.selected_paths() == []
        mfd._using_custom_model = False

    def test_mfd_path_changed_and_navigate(self, mfd_setup):
        mfd, tmp_path = mfd_setup

        # Path changed to existing path
        mfd.path_bar.setText(str(tmp_path / "folder1"))
        assert Path(mfd.model.rootPath()) == tmp_path / "folder1"

        # Path changed to non-existing path
        mfd.path_bar.setText(str(tmp_path / "non_existent"))
        assert "background-color: #ffcccc" in mfd.path_bar.styleSheet()

    def test_mfd_show_hidden_files(self, mfd_setup):
        mfd, tmp_path = mfd_setup

        mfd.showHidden.setChecked(True)
        assert mfd.model.filter() & QDir.Filter.Hidden

        mfd.showHidden.setChecked(False)
        assert not (mfd.model.filter() & QDir.Filter.Hidden)

    def test_mfd_load_directory(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        folder1 = str(tmp_path / "folder1")
        index = mfd.model.index(folder1)
        mfd.load_directory(index)
        assert mfd.path_bar.text() == folder1

    def test_mfd_go_home_up(self, mfd_setup):
        mfd, tmp_path = mfd_setup

        # Go Home
        with patch("PyQt6.QtCore.QDir.homePath", return_value="/home/user"):
            mfd.go_home()
            assert mfd.path_bar.text() == "/home/user"

        # Go Up
        mfd.path_bar.setText(str(tmp_path / "folder1"))
        mfd.go_up()
        assert mfd.path_bar.text() == str(tmp_path)

        # Go up from root (or non-existent)
        mfd.path_bar.setText("/")
        mfd.go_up()  # Should stay at / or do nothing if not exists

    def test_mfd_go_up_nonexistent_path(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        missing = tmp_path / "does_not_exist" / "child"
        mfd.path_bar.setText(str(missing))
        mfd.go_up()
        assert mfd.path_bar.text() == str(missing)

    def test_mfd_resize_column_to_contents(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch.object(mfd.tree, "resizeColumnToContents") as mock_resize:
            mfd._resize_column_to_contents()
            mock_resize.assert_called_once_with(0)

    def test_mfd_navigate_to_location_macos(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        mock_item = MagicMock()
        mock_item.data.return_value = "Home"

        with patch("nxdrive.gui.multi_folder_dialog.MAC", True), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch(
            "PyQt6.QtCore.QDir.homePath", return_value=str(tmp_path)
        ):

            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == str(tmp_path)

            mock_item.data.return_value = "Applications"
            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == "/Applications"

            # Tag location
            mfd._finder_tags = ["Tag1"]
            mock_item.data.return_value = "Tag1"
            with patch.object(mfd, "_show_tagged_files") as mock_show_tags:
                mfd.navigate_to_location(mock_item)
                mock_show_tags.assert_called_once_with("Tag1")

    def test_mfd_navigate_to_location_windows(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        mock_item = MagicMock()

        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", True
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch(
            "PyQt6.QtCore.QDir.homePath", return_value=str(tmp_path)
        ):

            mock_item.data.return_value = "Desktop"
            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == str(tmp_path) + "/Desktop"

    def test_mfd_navigate_to_location_windows_drive_cases(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        mock_item = MagicMock()
        drive_with_content = tmp_path / "drive_c"
        drive_with_content.mkdir()
        (drive_with_content / "x.txt").touch()

        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", True
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch(
            "PyQt6.QtCore.QDir.homePath", return_value=str(tmp_path)
        ), patch.object(
            mfd, "_show_empty_drive"
        ) as mock_empty:
            mfd._windows_onedrive_paths = {}
            mfd._windows_pinned_items = {}
            mfd._windows_network_locations = {}
            mfd._windows_drives = {
                "ContentDrive": ["Win_fixed", str(drive_with_content)],
                "EmptyDrive": ["Win_fixed", str(tmp_path / "drive_empty")],
            }

            mock_item.data.return_value = "ContentDrive"
            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == str(drive_with_content)

            mock_item.data.return_value = "EmptyDrive"
            mfd.navigate_to_location(mock_item)
            mock_empty.assert_called_once_with(str(tmp_path / "drive_empty"))

    def test_mfd_navigate_to_location_linux(self, mfd_setup):
        mfd, tmp_path = mfd_setup
        mock_item = MagicMock()

        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", True), patch.object(
            mfd, "linux_standard_locations", return_value={"Home": "/home/user"}
        ):

            mock_item.data.return_value = "Home"
            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == "/home/user"

    def test_mfd_navigate_to_location_linux_mount(self, mfd_setup):
        mfd, _ = mfd_setup
        mock_item = MagicMock()

        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", True), patch.object(
            mfd, "linux_standard_locations", return_value={"Home": "/home/user"}
        ):
            mfd._linux_mount_points = {"usb": "/mnt/usb"}
            mock_item.data.return_value = "usb"
            mfd.navigate_to_location(mock_item)
            assert mfd.path_bar.text() == "/mnt/usb"

    def test_mfd_linux_standard_locations(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("PyQt6.QtCore.QDir.homePath", return_value="/home/user"):
            locs = mfd.linux_standard_locations()
            assert locs["Home"] == "/home/user"
            assert locs["Root"] == "/"

    def test_mfd_linux_mount_points(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        (tmp_path / "media").mkdir()
        (tmp_path / "media" / "user").mkdir()
        (tmp_path / "media" / "user" / "usb").mkdir()

        with patch("nxdrive.gui.multi_folder_dialog.Path") as mock_path:
            mock_media = MagicMock()
            mock_media.is_dir.return_value = True
            mock_usb = MagicMock(name="usb")
            mock_usb.is_dir.return_value = True
            mock_usb.name = "usb"
            mock_user = MagicMock(name="user")
            mock_user.is_dir.return_value = True
            mock_user.iterdir.return_value = [mock_usb]

            mock_media.iterdir.return_value = [mock_user]

            def path_side_effect(x):
                if x == "/media":
                    return mock_media
                return MagicMock()

            mock_path.side_effect = path_side_effect
            assert "usb" in mfd.linux_mount_points()

    def test_mfd_macos_mount_points(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch(
            "subprocess.check_output",
            return_value=b"/dev/disk3s1 on /Volumes/USB (msdos, local, nodev, nosuid, noowners)\n",
        ):
            mounts = mfd.macos_mount_points()
            assert "Mount/USB" in mounts
            assert mounts["Mount/USB"] == "/Volumes/USB"

    def test_mfd_macos_finder_tags(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch(
            "subprocess.check_output", return_value=b'(\n  Tag1,\n  "Tag 2"\n)\n'
        ):
            tags = mfd.macos_finder_tags()
            assert "Tag1" in tags
            assert "Tag 2" in tags

    def test_mfd_macos_finder_tags_skips_empty_quoted_entries(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("subprocess.check_output", return_value=b'(\n  ""\n  Tag1,\n)\n'):
            tags = mfd.macos_finder_tags()
            assert tags == ["Tag1"]

    def test_mfd_show_tagged_files(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        file1 = tmp_path / "file1.txt"
        with patch("subprocess.check_output", return_value=str(file1).encode()):
            mfd._show_tagged_files("Tag1")
            assert mfd._using_custom_model
            assert mfd.path_bar.text() == "Tag: Tag1"

    def test_mfd_show_tagged_files_subprocess_failure(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("subprocess.check_output", side_effect=RuntimeError("boom")):
            mfd._show_tagged_files("Tag1")
            assert mfd._using_custom_model
            assert mfd.path_bar.text() == "Tag: Tag1"

    def test_mfd_load_fda_alert(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        with patch(
            "nxdrive.gui.multi_folder_dialog.Path.home", return_value=tmp_path
        ), patch("nxdrive.gui.multi_folder_dialog.FDAAlert.open") as mock_open, patch(
            "nxdrive.gui.multi_folder_dialog.Translator.get", side_effect=lambda x: x
        ):
            mfd._load_fda_alert()
            mock_open.assert_called_once()

    def test_mfd_navigate_to_system_settings(self):
        with patch("subprocess.run") as mock_run:
            MultiFolderDialog.navigate_to_system_settings()
            mock_run.assert_called_once()

    def test_mfd_parse_sfl_file(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        sfl_path = tmp_path / "favorites.sfl2"
        with patch(
            "plistlib.load",
            return_value={"items": [{"Bookmark": b"bookdata", "Name": "Fav1"}]},
        ), patch.object(
            mfd, "_path_from_bookmark", return_value=str(tmp_path / "folder1")
        ), patch(
            "builtins.open", MagicMock()
        ):
            favs = mfd._parse_sfl_file(sfl_path)
            assert "Fav1" in favs

    def test_mfd_parse_sfl_file_objects_format(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        sfl_path = tmp_path / "favorites.sfl4"
        with patch(
            "plistlib.load", return_value={"$objects": [b"book" + b"x" * 64]}
        ), patch.object(
            mfd, "_path_from_bookmark", return_value=str(tmp_path / "folder1")
        ), patch(
            "builtins.open", MagicMock()
        ):
            favs = mfd._parse_sfl_file(sfl_path)
            assert "folder1" in favs

    def test_mfd_parse_sfl_file_permission_denied_shows_alert(
        self, mfd_setup, tmp_path
    ):
        mfd, _ = mfd_setup
        sfl_path = tmp_path / "favorites.sfl4"
        with patch("builtins.open", side_effect=PermissionError), patch.object(
            mfd, "_read_plist_via_plutil", return_value=None
        ), patch.object(mfd, "_load_fda_alert") as mock_load_alert:
            favs = mfd._parse_sfl_file(sfl_path)
            assert favs == {}
            assert not mfd.fda_alert_widget.isHidden()
            mock_load_alert.assert_called_once()

    def test_mfd_read_plist_via_plutil(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        with patch("subprocess.check_output", return_value=b"<plist></plist>"), patch(
            "plistlib.loads", return_value={}
        ):
            res = mfd._read_plist_via_plutil(tmp_path / "test.plist")
            assert res == {}

    def test_mfd_read_plist_via_plutil_failure(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        with patch(
            "subprocess.check_output",
            side_effect=subprocess.CalledProcessError(returncode=1, cmd=["plutil"]),
        ):
            res = mfd._read_plist_via_plutil(tmp_path / "test.plist")
            assert res is None

    def test_mfd_path_from_bookmark(self, mfd_setup):
        mfd, _ = mfd_setup
        # Test with invalid data
        assert mfd._path_from_bookmark(b"short") is None
        # Test with non-bookmark magic
        assert mfd._path_from_bookmark(b"notbook" + b"0" * 40) is None

    def test_mfd_path_from_bookmark_valid(self, mfd_setup):
        mfd, _ = mfd_setup
        data = bytearray(b"\x00" * 256)
        data[0:4] = b"book"

        data_start = 32
        struct.pack_into("<I", data, 12, data_start)

        toc_offset = 132
        struct.pack_into("<I", data, data_start, toc_offset - data_start)

        struct.pack_into("<I", data, toc_offset + 16, 3)
        entry_pos = toc_offset + 20
        struct.pack_into("<IIi", data, entry_pos, 0x2002, 8, 0)
        struct.pack_into("<IIi", data, entry_pos + 12, 0x1004, 32, 0)
        struct.pack_into("<IIi", data, entry_pos + 24, 0x7777, 56, 0)

        volume = b"/Volumes/Data"
        struct.pack_into("<II", data, data_start + 8, len(volume), 0x101)
        data[data_start + 16 : data_start + 16 + len(volume)] = volume

        comp_array = struct.pack("<I", 56)
        struct.pack_into("<II", data, data_start + 32, len(comp_array), 0x601)
        data[data_start + 40 : data_start + 40 + len(comp_array)] = comp_array

        component = b"Users"
        struct.pack_into("<II", data, data_start + 56, len(component), 0x101)
        data[data_start + 64 : data_start + 64 + len(component)] = component

        assert mfd._path_from_bookmark(bytes(data)) == "/Volumes/Data/Users"

    def test_mfd_macos_finder_favorites(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        shared_dir = tmp_path / "Library/Application Support/com.apple.sharedfilelist"
        shared_dir.mkdir(parents=True)
        sfl3 = shared_dir / "com.apple.LSSharedFileList.FavoriteItems.sfl3"
        sfl3.touch()

        with patch(
            "nxdrive.gui.multi_folder_dialog.Path.home", return_value=tmp_path
        ), patch.object(
            mfd, "_parse_sfl_file", return_value={"Fav": "/x"}
        ) as mock_parse:
            assert mfd.macos_finder_favorites() == {"Fav": "/x"}
            mock_parse.assert_called_once_with(sfl3)

    def test_mfd_macos_finder_favorites_parse_error(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        shared_dir = tmp_path / "Library/Application Support/com.apple.sharedfilelist"
        shared_dir.mkdir(parents=True)
        sfl4 = shared_dir / "com.apple.LSSharedFileList.FavoriteItems.sfl4"
        sfl4.touch()

        with patch(
            "nxdrive.gui.multi_folder_dialog.Path.home", return_value=tmp_path
        ), patch.object(mfd, "_parse_sfl_file", side_effect=RuntimeError("boom")):
            assert mfd.macos_finder_favorites() == {}

    def test_mfd_get_windows_onedrive_paths(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        user_folder = tmp_path / "OneDrive"
        user_folder.mkdir()

        with patch(
            "nxdrive.gui.multi_folder_dialog.winreg", create=True
        ) as mock_winreg:
            mock_winreg.HKEY_CURRENT_USER = object()
            reg_key = object()
            account_key = object()
            mock_winreg.OpenKey.side_effect = [reg_key, account_key]
            mock_winreg.EnumKey.side_effect = ["Business1", OSError()]
            mock_winreg.QueryValueEx.return_value = (str(user_folder), None)

            paths = mfd.get_windows_onedrive_paths()
            assert paths == {"OneDrive": str(user_folder)}

    def test_mfd_get_windows_drives_types(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch(
            "nxdrive.gui.multi_folder_dialog.ctypes", create=True
        ) as mock_ctypes:
            windll = MagicMock()
            windll.kernel32.GetLogicalDrives.return_value = 0b111
            windll.kernel32.GetDriveTypeW.side_effect = [2, 3, 5]
            windll.kernel32.GetVolumeInformationW.return_value = True
            mock_ctypes.windll = windll
            mock_ctypes.create_unicode_buffer.return_value = MagicMock(value="Label")

            drives = mfd.get_windows_drives()
            assert drives["Label (A:)"][0] == "Win_removable"
            assert drives["Label (B:)"][0] == "Win_fixed"
            assert drives["Label (C:)"][0] == "Win_cdrom"

    def test_mfd_get_windows_pinned_items(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        valid_dir = tmp_path / "Pinned"
        valid_dir.mkdir()
        invalid_path = tmp_path / "missing"

        with patch(
            "subprocess.check_output",
            return_value=f"{valid_dir}\n{invalid_path}\n".encode(),
        ), patch(
            "nxdrive.gui.multi_folder_dialog.subprocess.STARTUPINFO",
            create=True,
            return_value=MagicMock(dwFlags=0, wShowWindow=0),
        ), patch(
            "nxdrive.gui.multi_folder_dialog.subprocess.STARTF_USESHOWWINDOW",
            create=True,
            new=1,
        ), patch(
            "nxdrive.gui.multi_folder_dialog.subprocess.SW_HIDE",
            create=True,
            new=0,
        ), patch(
            "nxdrive.gui.multi_folder_dialog.subprocess.CREATE_NO_WINDOW",
            create=True,
            new=0,
        ):
            pinned = mfd.get_windows_pinned_items()
            assert pinned == {"Pinned": str(valid_dir)}

    def test_mfd_get_windows_network_locations(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch(
            "nxdrive.gui.multi_folder_dialog.ctypes", create=True
        ) as mock_ctypes, patch(
            "nxdrive.gui.multi_folder_dialog.winreg", create=True
        ) as mock_winreg:
            mock_ctypes.windll.kernel32.GetLogicalDrives.return_value = 1
            mock_ctypes.windll.kernel32.GetDriveTypeW.return_value = 4

            mock_winreg.HKEY_CURRENT_USER = object()
            reg_key = object()
            drive_key = object()
            mock_winreg.OpenKey.side_effect = [reg_key, drive_key]
            mock_winreg.EnumKey.side_effect = ["Z", OSError()]
            mock_winreg.QueryValueEx.return_value = (r"\\server\share", None)

            locations = mfd.get_windows_network_locations()
            assert "A:\\" in locations
            assert "Z: (\\\\server\\share)" in locations

    def test_mfd_fetch_icon_all_branches(self, mfd_setup):
        mfd, _ = mfd_setup
        names = [
            "Home",
            "Up Arrow",
            "Applications",
            "Desktop",
            "Documents",
            "Downloads",
            "Pictures",
            "Music",
            "Movies",
            "Videos",
            "Mount/USB",
            "tag",
            "Win_removable\\A",
            "Win_fixed\\B",
            "Win_cdrom\\C",
            "Win_onedrive\\OneDrive",
            "Win_network\\Share",
            "Other",
        ]
        with patch(
            "nxdrive.gui.multi_folder_dialog.find_icon",
            return_value=Path("/tmp/icon.svg"),
        ):
            for name in names:
                assert mfd.fetch_icon(name) is not None

    def test_mfd_fetch_icon_linux_color_detection(self, mfd_setup):
        mfd, _ = mfd_setup
        palette = MagicMock()
        palette.color.return_value.red.return_value = 10
        palette.color.return_value.green.return_value = 10
        palette.color.return_value.blue.return_value = 10
        with patch("nxdrive.gui.multi_folder_dialog.LINUX", True), patch.object(
            mfd, "palette", return_value=palette
        ), patch(
            "nxdrive.gui.multi_folder_dialog.find_icon",
            return_value=Path("/tmp/icon.svg"),
        ):
            assert mfd.fetch_icon("Home") is not None

    def test_mfd_panel_locations_mac_and_fallback(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("nxdrive.gui.multi_folder_dialog.MAC", True), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch.object(
            mfd, "macos_finder_favorites", return_value={"Fav1": "/path/to/fav"}
        ), patch.object(
            mfd, "macos_mount_points", return_value={"Mount/X": "/Volumes/X"}
        ), patch.object(
            mfd, "macos_finder_tags", return_value=["Tag1"]
        ):
            panel = mfd.panel_locations()
            assert panel.count() > 0

        with patch("nxdrive.gui.multi_folder_dialog.MAC", True), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch.object(
            mfd, "macos_finder_favorites", return_value={}
        ), patch.object(
            mfd, "macos_mount_points", return_value={}
        ), patch.object(
            mfd, "macos_finder_tags", return_value=[]
        ):
            panel = mfd.panel_locations()
            assert panel.count() > 0

    def test_mfd_panel_locations_windows_and_linux(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", True
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", False), patch.object(
            mfd, "get_windows_onedrive_paths", return_value={"OD": "C:/OD"}
        ), patch.object(
            mfd, "get_windows_drives", return_value={"D": ["Win_fixed", "D:\\"]}
        ), patch.object(
            mfd, "get_windows_pinned_items", return_value={"Pin": "C:/Pin"}
        ), patch.object(
            mfd, "get_windows_network_locations", return_value={"Net": "Z:\\"}
        ):
            panel = mfd.panel_locations()
            assert panel.count() > 0

        with patch("nxdrive.gui.multi_folder_dialog.MAC", False), patch(
            "nxdrive.gui.multi_folder_dialog.WINDOWS", False
        ), patch("nxdrive.gui.multi_folder_dialog.LINUX", True), patch.object(
            mfd, "linux_standard_locations", return_value={"Home": "/", "Root": "/"}
        ), patch.object(
            mfd, "linux_mount_points", return_value={"USB": "/mnt/usb"}
        ), patch(
            "nxdrive.gui.multi_folder_dialog.Path.exists", return_value=True
        ):
            panel = mfd.panel_locations()
            assert panel.count() > 0

    def test_mfd_add_separator_and_font_helpers(self, mfd_setup):
        mfd, _ = mfd_setup
        locations = QListWidget()
        item = QListWidgetItem("X")
        locations.addItem(item)

        mfd._set_item_bold(item, True)
        assert item.font().bold()

        mfd._add_separator(locations)
        assert locations.count() == 2

    def test_mfd_hover_and_selection_helpers(self, mfd_setup):
        mfd, _ = mfd_setup
        locations = QListWidget()
        item1 = QListWidgetItem("Item1")
        item2 = QListWidgetItem("Item2")
        locations.addItem(item1)
        locations.addItem(item2)

        mfd._hovered_item = item1
        item2.setSelected(True)
        mfd._on_item_hover(item2)
        assert item2.font().bold()

        mfd._on_selection_changed(locations)
        assert item1.font().bold() is item1.isSelected()
        assert item2.font().bold() is item2.isSelected()

    def test_mfd_get_windows_drives(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("nxdrive.gui.multi_folder_dialog.WINDOWS", True), patch(
            "nxdrive.gui.multi_folder_dialog.ctypes", create=True
        ) as mock_ctypes:
            mock_ctypes.windll.kernel32.GetLogicalDrives.return_value = 1
            mock_ctypes.windll.kernel32.GetDriveTypeW.return_value = 3
            mock_ctypes.create_unicode_buffer.return_value = MagicMock(value="Label")
            drives = mfd.get_windows_drives()
            assert "Label (A:)" in drives

    def test_mfd_fetch_icon(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch(
            "nxdrive.gui.multi_folder_dialog.find_icon",
            return_value=Path("/tmp/icon.svg"),
        ):
            icon = mfd.fetch_icon("Home")
            assert icon is not None

    def test_mfd_panel_locations(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("nxdrive.gui.multi_folder_dialog.MAC", True), patch.object(
            mfd, "macos_finder_favorites", return_value={"Fav1": "/path/to/fav"}
        ), patch.object(mfd, "macos_mount_points", return_value={}), patch.object(
            mfd, "macos_finder_tags", return_value=[]
        ):
            panel = mfd.panel_locations()
            assert panel.count() > 0

    def test_mfd_event_filter(self, mfd_setup):
        mfd, _ = mfd_setup
        mock_obj = QObject()
        mock_event = QEvent(QEvent.Type.Leave)
        mfd._locations_widget = MagicMock()
        mfd._locations_widget.viewport.return_value = mock_obj

        mfd.eventFilter(mock_obj, mock_event)

    def test_mfd_event_filter_runtime_error_branch(self, mfd_setup):
        mfd, _ = mfd_setup
        mfd._locations_widget = MagicMock()
        mfd._locations_widget.viewport.side_effect = RuntimeError("deleted")
        result = mfd.eventFilter(QObject(), QEvent(QEvent.Type.Leave))
        assert result in (True, False)

    def test_mfd_show_empty_drive(self, mfd_setup):
        mfd, _ = mfd_setup
        mfd._show_empty_drive("E:\\")
        assert mfd._using_custom_model
        assert mfd.path_bar.text() == "E:\\"
