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
    QPushButton,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
)

log = getLogger(__name__)


class MultiFolderDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Files/Folders")

        # Set minimum size
        self.setMinimumSize(500, 450)

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
        layout.addWidget(self.tree)

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
