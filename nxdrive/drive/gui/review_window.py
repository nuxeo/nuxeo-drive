"""The Direct Transfer selection review window.

Lists every local path queued for a Direct Transfer and allows the user to
deselect some of them before starting the upload.
"""

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List

from ..qt import constants as qt
from ..qt.imports import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QStandardItem,
    QStandardItemModel,
    Qt,
    QTreeView,
    QVBoxLayout,
)
from ..translator import Translator
from ..utils import sizeof_fmt

if TYPE_CHECKING:
    from .folders_dialog import FoldersDialog  # noqa

__all__ = ("ReviewFileModel", "ReviewSelectionDialog")

log = getLogger(__name__)


class ReviewFileModel(QStandardItemModel):
    """The model backing the Direct Transfer selection review tree view.

    One row per selected local path, with a checkbox on the *Name* column.
    """

    # Columns
    NAME = 0
    TYPE = 1
    SIZE = 2
    PATH = 3

    # Custom role used to store the real Path object on the *Name* item
    PATH_ROLE = qt.UserRole + 1

    def __init__(self, paths: Dict[Path, int], parent: QDialog = None, /) -> None:
        super().__init__(parent)

        self.setHorizontalHeaderLabels(
            [
                Translator.get("NAME"),
                Translator.get("TYPE"),
                Translator.get("SIZE"),
                Translator.get("PATH"),
            ]
        )

        # Sort on the data stored in UserRole so that sizes are sorted
        # numerically instead of alphabetically ("9 B" < "10 KiB").
        self.setSortRole(qt.UserRole)

        for path, size in sorted(paths.items()):
            self.add_path(path, size)

    def add_path(self, path: Path, size: int, /) -> None:
        """Append a row for the given *path*."""
        is_folder = path.is_dir()

        name = QStandardItem(path.name or str(path))
        name.setCheckable(True)
        name.setCheckState(qt.Unchecked)
        name.setEditable(False)
        name.setData(name.text().lower(), qt.UserRole)
        name.setData(path, self.PATH_ROLE)

        type_ = QStandardItem(
            Translator.get("FOLDER") if is_folder else Translator.get("FILE")
        )
        type_.setEditable(False)
        type_.setData(type_.text().lower(), qt.UserRole)

        # Human readable size: B, KiB, MiB, GiB...
        size_ = QStandardItem(sizeof_fmt(size))
        size_.setEditable(False)
        size_.setData(size, qt.UserRole)

        full_path = QStandardItem(str(path))
        full_path.setEditable(False)
        full_path.setToolTip(str(path))
        full_path.setData(str(path).lower(), qt.UserRole)

        self.appendRow([name, type_, size_, full_path])

    def checked_paths(self) -> List[Path]:
        """Return the paths of every checked row."""
        paths: List[Path] = []
        for row in range(self.rowCount()):
            item = self.item(row, self.NAME)
            if item is not None and item.checkState() == qt.Checked:
                path = item.data(self.PATH_ROLE)
                if path is not None:
                    paths.append(path)
        return paths


class ReviewSelectionDialog(QDialog):
    """The window allowing to review the local paths selected for a Direct Transfer."""

    def __init__(self, folder_dialog: "FoldersDialog", /) -> None:
        super().__init__(folder_dialog)

        self.folder_dialog = folder_dialog

        self.setWindowTitle(Translator.get("REVIEW_SELECTION"))
        self.resize(760, 420)

        layout = QVBoxLayout(self)

        # The selection list
        self.model = ReviewFileModel(folder_dialog.paths, self)

        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.model)
        self.tree_view.setRootIsDecorated(False)
        self.tree_view.setAlternatingRowColors(True)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setSortingEnabled(True)
        self.tree_view.sortByColumn(ReviewFileModel.NAME, Qt.SortOrder.AscendingOrder)
        for column in (
            ReviewFileModel.NAME,
            ReviewFileModel.TYPE,
            ReviewFileModel.SIZE,
        ):
            self.tree_view.resizeColumnToContents(column)
        if header := self.tree_view.header():
            header.setStretchLastSection(True)
        layout.addWidget(self.tree_view)

        # Buttons
        h_button_layout = QHBoxLayout()

        self.cancel_button = QPushButton(Translator.get("CANCEL"))
        self.cancel_button.clicked.connect(self.reject)
        h_button_layout.addWidget(self.cancel_button)

        h_button_layout.addStretch(1)

        self.remove_selection_button = QPushButton(Translator.get("REMOVE_SELECTION"))
        self.remove_selection_button.setEnabled(False)
        self.remove_selection_button.clicked.connect(self.accept)
        h_button_layout.addWidget(self.remove_selection_button)

        layout.addLayout(h_button_layout)

        # Connected last so that the button already exists when the signal fires
        self.model.itemChanged.connect(self._button_remove_state)

    def _button_remove_state(self, _: QStandardItem = None, /) -> None:
        """*Remove Selection* is enabled only when at least 1 checkbox is checked."""
        self.remove_selection_button.setEnabled(bool(self.model.checked_paths()))

    def accept(self) -> None:
        """Remove the checked paths from the selection, then close the window."""
        self.folder_dialog.remove_local_paths(self.model.checked_paths())
        super().accept()
