"""
This module contains the implementation of the MultiFolderDialog class.
This is a dialog for selecting multiple folders in the NxDrive application.
"""

import string
import subprocess
from logging import getLogger
from pathlib import Path

from nxdrive.qt.imports import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDir,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
)

from ..constants import LINUX, MAC, WINDOWS

if WINDOWS:
    import winreg
    from ctypes import windll

log = getLogger(__name__)


class MultiFolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files/Folders")

        # Set minimum size
        self.setMinimumSize(700, 450)

        layout = QVBoxLayout(self)
        path_layout = QHBoxLayout()
        bottom_layout = QHBoxLayout()

        # Show hidden files checkbox
        self.showHidden = QCheckBox()
        self.showHidden.setText("Show Hidden")
        self.showHidden.checkStateChanged.connect(self.show_hidden_files)
        # Home button
        self.btnHome = QPushButton()
        self.btnHome.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnHome.setText("Home")
        self.btnHome.clicked.connect(self.go_home)
        # Up button
        self.btnUp = QPushButton()
        self.btnUp.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btnUp.setText("Go Up")
        self.btnUp.clicked.connect(self.go_up)
        # Path bar
        self.path_bar = QLineEdit()
        self.path_bar.setText(QDir.homePath())
        self.path_bar.textChanged.connect(self.path_changed)

        # Path bar layout
        path_layout.addWidget(self.path_bar)
        path_layout.addWidget(self.showHidden)
        path_layout.addWidget(self.btnHome)
        path_layout.addWidget(self.btnUp)
        layout.addLayout(path_layout)

        # Add label
        self.label = QLabel("Select files/folders:")
        layout.addWidget(self.label)

        # File System Model
        self.model = QFileSystemModel()
        self.model.setRootPath(QDir.homePath())

        # Allow files and directories except '.' and '..'
        self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)
        self.model.directoryLoaded.connect(
            lambda _: self.tree.resizeColumnToContents(0)
        )

        view_layout = QHBoxLayout()
        panel_layout = QVBoxLayout()

        panel_layout.addWidget(self.panel_locations())
        view_layout.addLayout(panel_layout)

        # Create a tree view and set the model
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setRootIndex(self.model.index(QDir.homePath()))
        # Allow Shift+Click and Ctrl+Click for multiple selection
        self.tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        # Show headers to display file attributes
        self.tree.setHeaderHidden(False)
        # Handle double-click to navigate into directories
        self.tree.doubleClicked.connect(self.load_directory)

        # Resize the width when the directory is collapsed/expanded
        self.tree.expanded.connect(lambda _: self.tree.resizeColumnToContents(0))
        self.tree.collapsed.connect(lambda _: self.tree.resizeColumnToContents(0))

        # Add the tree view to the layout
        view_layout.addWidget(self.tree)

        layout.addLayout(view_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        if ok_button:
            ok_button.setText("Add")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_button:
            cancel_button.setText("Cancel")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        # Adding Add/Cancel buttons to the layout
        bottom_layout.addWidget(buttons)
        layout.addLayout(bottom_layout)

    def selected_paths(self) -> list[str]:
        selection_model = self.tree.selectionModel()
        if selection_model:
            indexes = selection_model.selectedIndexes()
        else:
            return []
        paths = []
        for index in indexes:
            if index.column() == 0:
                path = self.model.filePath(index)
                # Check for read access
                # if not os.access(path, os.R_OK):
                #     msg = QMessageBox()
                #     msg.setIcon(QMessageBox.Icon.Warning)
                #     msg.setWindowTitle(self.tr("Permission Denied"))
                #     msg.setText(self.tr(f"You don't have read access to {path}."))
                #     msg.exec()
                #     return []
                paths.append(path)
        return list(set(paths))  # remove duplicates

    def path_changed(self) -> None:
        path = Path(self.path_bar.text())
        if path.exists():
            self.tree.setRootIndex(self.model.index(str(path)))
            self.tree.resizeColumnToContents(0)
            self.path_bar.setStyleSheet("")
        else:
            self.path_bar.setStyleSheet("background-color: #ffcccc")

    def show_hidden_files(self) -> None:
        if self.showHidden.isChecked():
            self.model.setFilter(
                QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot | QDir.Filter.Hidden
            )
        else:
            self.model.setFilter(QDir.Filter.AllEntries | QDir.Filter.NoDotAndDotDot)

    def load_directory(self, index):
        if index.column() == 0:
            folder_path = Path(self.model.filePath(index))
            if folder_path.is_dir():
                # Update the path bar to reflect the new directory
                # This automatically triggers the path_changed method to update the tree view
                self.path_bar.setText(str(folder_path))

    def go_home(self) -> None:
        self.path_bar.setText(QDir.homePath())

    def go_up(self) -> None:
        current_path = Path(self.path_bar.text())
        if current_path.exists():
            parent_path = current_path.parent
        else:
            parent_path = None

        # Prevent going above the root directory
        if not parent_path or not parent_path.exists():
            return

        self.path_bar.setText(str(parent_path))

    def navigate_to_location(self, item) -> None:
        location = item.text()
        # MacOS paths
        if MAC:
            match location:
                case "Home":
                    self.path_bar.setText(QDir.homePath())
                case "Applications":
                    self.path_bar.setText("/Applications")
                case "Desktop":
                    self.path_bar.setText(QDir.homePath() + "/Desktop")
                case "Documents":
                    self.path_bar.setText(QDir.homePath() + "/Documents")
                case "Downloads":
                    self.path_bar.setText(QDir.homePath() + "/Downloads")
                case "Pictures":
                    self.path_bar.setText(QDir.homePath() + "/Pictures")
                case "Music":
                    self.path_bar.setText(QDir.homePath() + "/Music")
                case "Movies":
                    self.path_bar.setText(QDir.homePath() + "/Movies")
                case loc if loc.startswith("Mount/"):
                    log.debug("Detecting mount points for MacOS")
                    mount_path = self.macos_mount_points().get(location)
                    if mount_path:
                        self.path_bar.setText(mount_path)
        # Windows paths
        elif WINDOWS:
            match location:
                case "Home":
                    self.path_bar.setText(QDir.homePath())
                case "Desktop":
                    self.path_bar.setText(QDir.homePath() + "/Desktop")
                case "Downloads":
                    self.path_bar.setText(QDir.homePath() + "/Downloads")
                case "Documents":
                    self.path_bar.setText(QDir.homePath() + "/Documents")
                case "Pictures":
                    self.path_bar.setText(QDir.homePath() + "/Pictures")
                case "Music":
                    self.path_bar.setText(QDir.homePath() + "/Music")
                case "Videos":
                    self.path_bar.setText(QDir.homePath() + "/Videos")
                case loc if loc in self.get_windows_fixed_drives():
                    self.path_bar.setText(loc)
                case loc if loc in self.get_windows_onedrive_paths():
                    self.path_bar.setText(self.get_windows_onedrive_paths()[loc])
        # Linux paths

    def macos_mount_points(self) -> dict[str, str]:
        output = subprocess.check_output(["mount"]).decode("utf-8")
        mounts = {}
        for line in output.splitlines():
            line = line.split(" on ")[1]
            if line.startswith("/Volumes/"):
                name = "Mount/" + (line.split(" (")[0].split("/Volumes/")[1])
                path = line.split(" (")[0]
                mounts.update({name: path})
        return mounts

    def get_windows_onedrive_paths(self) -> dict[str, str]:
        """Gets all OneDrive folder paths from the Windows registry."""
        onedrive_paths: dict[str, str] = {}
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\OneDrive\Accounts",
            )
            i = 0
            while True:
                try:
                    account_name = winreg.EnumKey(reg_key, i)
                    account_key = winreg.OpenKey(reg_key, account_name)
                    try:
                        user_folder, _ = winreg.QueryValueEx(account_key, "UserFolder")
                        if Path(user_folder).exists():
                            folder_name = Path(user_folder).name
                            onedrive_paths[folder_name] = user_folder
                    except OSError:
                        pass
                    finally:
                        winreg.CloseKey(account_key)
                    i += 1
                except OSError:
                    break
            winreg.CloseKey(reg_key)
        except OSError:
            pass
        return onedrive_paths

    def get_windows_fixed_drives(self) -> list[str]:
        """Gets all available fixed disk drive letters on Windows."""
        DRIVE_FIXED = 3
        drives = []
        bitmask = windll.kernel32.GetLogicalDrives()
        for letter in string.ascii_uppercase:
            if bitmask & 1:
                root = f"{letter}:\\"
                if windll.kernel32.GetDriveTypeW(root) == DRIVE_FIXED:
                    drives.append(root)
            bitmask >>= 1
        return drives

    def panel_locations(self) -> QListWidget:
        locations = QListWidget()
        if MAC:
            locations.addItems(
                [
                    "Home",
                    "Applications",
                    "Desktop",
                    "Documents",
                    "Downloads",
                    "Pictures",
                    "Music",
                    "Movies",
                    *self.macos_mount_points().keys(),
                ]
            )
        elif WINDOWS:
            locations.addItems(
                [
                    "Home",
                    "Desktop",
                    "Downloads",
                    "Documents",
                    "Pictures",
                    "Music",
                    "Videos",
                    *self.get_windows_fixed_drives(),
                    *self.get_windows_onedrive_paths().keys(),
                ]
            )
        elif LINUX:
            locations.addItems(["Home", "Desktop", "Documents", "Downloads"])

        locations.setFixedWidth(80)
        locations.setSpacing(3)
        # Handle clicks on the locations list to navigate to the selected location
        locations.itemClicked.connect(self.navigate_to_location)
        return locations
