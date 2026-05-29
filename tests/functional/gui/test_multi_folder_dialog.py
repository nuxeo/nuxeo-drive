"""Functional tests for nxdrive.gui.multi_folder_dialog module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import QDir, QEvent, QObject, Qt
from PyQt6.QtGui import QKeyEvent, QStandardItemModel
from PyQt6.QtWidgets import QApplication

from nxdrive.gui.multi_folder_dialog import (
    CenteredHeaderFileSystemModel,
    FDAAlert,
    MultiFolderDialog,
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
            alert.remember_close_choice(Qt.CheckState.Checked)
            assert dont_show_file.exists()

            # Uncheck choice
            alert.remember_close_choice(Qt.CheckState.Unchecked)
            assert not dont_show_file.exists()


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

        selected = mfd.selected_paths()
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

        selected = mfd.selected_paths()
        assert folder1 in selected
        assert len(selected) == 1

        # Mixed selection
        selection_model.select(
            index1,
            selection_model.SelectionFlag.Select | selection_model.SelectionFlag.Rows,
        )
        selected = mfd.selected_paths()
        assert folder1 in selected
        assert file1 in selected
        assert len(selected) == 2

        # Tag mode
        mfd._in_tag_mode = True
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

    def test_mfd_path_changed_and_navigate(self, mfd_setup):
        mfd, tmp_path = mfd_setup

        # Path changed to existing path
        mfd.path_bar.setText(str(tmp_path / "folder1"))
        assert mfd.model.rootPath() == str(tmp_path / "folder1")

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

    def test_mfd_show_tagged_files(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        file1 = tmp_path / "file1.txt"
        with patch("subprocess.check_output", return_value=str(file1).encode()):
            mfd._show_tagged_files("Tag1")
            assert mfd._in_tag_mode
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

    def test_mfd_read_plist_via_plutil(self, mfd_setup, tmp_path):
        mfd, _ = mfd_setup
        with patch("subprocess.check_output", return_value=b"<plist></plist>"), patch(
            "plistlib.loads", return_value={}
        ):
            res = mfd._read_plist_via_plutil(tmp_path / "test.plist")
            assert res == {}

    def test_mfd_path_from_bookmark(self, mfd_setup):
        mfd, _ = mfd_setup
        # Test with invalid data
        assert mfd._path_from_bookmark(b"short") is None
        # Test with non-bookmark magic
        assert mfd._path_from_bookmark(b"notbook" + b"0" * 40) is None

    def test_mfd_get_windows_drives(self, mfd_setup):
        mfd, _ = mfd_setup
        with patch("nxdrive.gui.multi_folder_dialog.WINDOWS", True), patch(
            "nxdrive.gui.multi_folder_dialog.windll", create=True
        ) as mock_windll, patch(
            "nxdrive.gui.multi_folder_dialog.ctypes", create=True
        ) as mock_ctypes:
            mock_windll.kernel32.GetLogicalDrives.return_value = 1
            mock_windll.kernel32.GetDriveTypeW.return_value = 3
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

    def test_mfd_show_empty_drive(self, mfd_setup):
        mfd, _ = mfd_setup
        mfd._show_empty_drive("E:\\")
        assert mfd._in_tag_mode
        assert mfd.path_bar.text() == "E:\\"
