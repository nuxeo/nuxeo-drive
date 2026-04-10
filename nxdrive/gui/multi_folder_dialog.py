"""
This module contains the implementation of the MultiFolderDialog class.
This is a dialog for selecting multiple folders in the NxDrive application.
"""

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
                # Show the contents of the clicked directory
                self.tree.setRootIndex(index)
                # Update the path bar to reflect the new directory
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
            if location == "Applications":
                applications_path = "/Applications"
                self.path_bar.setText(applications_path)
            elif location == "Desktop":
                desktop_path = QDir.homePath() + "/Desktop"
                self.path_bar.setText(desktop_path)
            elif location == "Documents":
                documents_path = QDir.homePath() + "/Documents"
                self.path_bar.setText(documents_path)
            elif location == "Downloads":
                downloads_path = QDir.homePath() + "/Downloads"
                self.path_bar.setText(downloads_path)
            elif location == "Pictures":
                pictures_path = QDir.homePath() + "/Pictures"
                self.path_bar.setText(pictures_path)
            elif location == "Music":
                music_path = QDir.homePath() + "/Music"
                self.path_bar.setText(music_path)
            elif location == "Movies":
                movies_path = QDir.homePath() + "/Movies"
                self.path_bar.setText(movies_path)
        # Windows paths
        elif WINDOWS:
            if location == "Desktop":
                desktop_path = QDir.homePath() + "/Desktop"
                self.path_bar.setText(desktop_path)
            elif location == "Downloads":
                downloads_path = QDir.homePath() + "/Downloads"
                self.path_bar.setText(downloads_path)
            elif location == "Documents":
                documents_path = QDir.homePath() + "/Documents"
                self.path_bar.setText(documents_path)
            elif location == "Pictures":
                pictures_path = QDir.homePath() + "/Pictures"
                self.path_bar.setText(pictures_path)
            elif location == "Music":
                music_path = QDir.homePath() + "/Music"
                self.path_bar.setText(music_path)
            elif location == "Videos":
                videos_path = QDir.homePath() + "/Videos"
                self.path_bar.setText(videos_path)
            elif location == "C:\\":
                c_drive_path = QDir.rootPath()
                self.path_bar.setText(c_drive_path)
        # Linux paths

    def panel_locations(self) -> QListWidget:
        locations = QListWidget()
        if MAC:
            locations.addItem("Applications")
            locations.addItem("Desktop")
            locations.addItem("Documents")
            locations.addItem("Downloads")
            locations.addItem("Pictures")
            locations.addItem("Music")
            locations.addItem("Movies")
        elif WINDOWS:
            locations.addItem("Desktop")
            locations.addItem("Downloads")
            locations.addItem("Documents")
            locations.addItem("Pictures")
            locations.addItem("Music")
            locations.addItem("Videos")
            locations.addItem("C:\\")
        elif LINUX:
            locations.addItem("Desktop")
            locations.addItem("Documents")
            locations.addItem("Downloads")

        locations.setFixedWidth(80)
        locations.setSpacing(3)
        # Handle clicks on the locations list to navigate to the selected location
        locations.itemClicked.connect(self.navigate_to_location)
        return locations
