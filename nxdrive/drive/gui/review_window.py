"""The Direct Transfer selection review window.

Lists every local path queued for a Direct Transfer, as a tree, and allows the
user to deselect some of them before starting the upload.
"""

from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List

from ..qt import constants as qt
from ..qt.imports import (
    QDialog,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QStandardItem,
    QStandardItemModel,
    Qt,
    QTreeView,
    QVBoxLayout,
    Signal,
)
from ..translator import Translator
from ..utils import sizeof_fmt

if TYPE_CHECKING:
    from .folders_dialog import FoldersDialog  # noqa

__all__ = ("ReviewFileModel", "ReviewSelectionDialog")

log = getLogger(__name__)


class ReviewFileModel(QStandardItemModel):
    """The model backing the Direct Transfer selection review tree view.

    One row per selected local path, nested the same way the local paths are:
    a folder owns the rows of everything it contains. The *Name* column holds
    the checkbox and, for folders, the expand/collapse icon.
    """

    # Columns
    NAME = 0
    TYPE = 1
    SIZE = 2
    PATH = 3

    # Custom roles set on the *Name* item
    PATH_ROLE = qt.UserRole + 1  # the real Path object
    STATE_ROLE = qt.UserRole + 2  # the last known check state

    # Emitted once per user action, when the check states have settled
    selectionChanged = Signal()

    def __init__(self, paths: Dict[Path, int], parent: QDialog = None, /) -> None:
        super().__init__(parent)

        # Guard against the recursive itemChanged() emitted by our own updates
        self._updating = False

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

        self._build_tree(paths)

        self.itemChanged.connect(self._on_item_changed)

    #
    # Tree construction
    #

    def _build_tree(self, paths: Dict[Path, int], /) -> None:
        """Nest *paths* so that a folder owns the rows of its contents."""
        children: Dict[Path, List[Path]] = {}
        roots: List[Path] = []

        for path in sorted(paths):
            if path.parent in paths:
                children.setdefault(path.parent, []).append(path)
            else:
                roots.append(path)

        counts: Dict[Path, int] = {}

        def count_contents(path: Path, /) -> int:
            """Total number of items held by *path*, at any depth."""
            if path not in counts:
                own = children.get(path, [])
                counts[path] = len(own) + sum(count_contents(child) for child in own)
            return counts[path]

        def append(path: Path, parent: QStandardItem, /) -> None:
            row = self._make_row(path, paths[path], count_contents(path))
            parent.appendRow(row)
            for child in children.get(path, []):
                append(child, row[self.NAME])

        root = self.invisibleRootItem()
        for path in roots:
            append(path, root)

    def _make_row(self, path: Path, size: int, contents: int, /) -> List[QStandardItem]:
        """Build the 4 items of the row standing for *path*.

        *contents* is the number of items the path holds, shown in parentheses
        next to the name of a folder.
        """
        is_folder = path.is_dir()

        label = path.name or str(path)
        name = QStandardItem(f"{label} ({contents:,})" if is_folder else label)
        name.setCheckable(True)
        name.setCheckState(qt.Unchecked)
        name.setEditable(False)
        # Sorted on the bare name, so that the count does not interfere
        name.setData(label.lower(), qt.UserRole)
        name.setData(path, self.PATH_ROLE)
        name.setData(qt.Unchecked, self.STATE_ROLE)

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

        return [name, type_, size_, full_path]

    #
    # Iteration helpers
    #

    def iter_items(self, parent: QStandardItem = None, /) -> Iterator[QStandardItem]:
        """Yield the *Name* item of every row below *parent*, depth-first."""
        root = parent if parent is not None else self.invisibleRootItem()
        for row in range(root.rowCount()):
            item = root.child(row, self.NAME)
            if item is None:
                continue
            yield item
            yield from self.iter_items(item)

    def checked_paths(self) -> List[Path]:
        """Return the paths of every checked row."""
        paths: List[Path] = []
        for item in self.iter_items():
            if item.checkState() == qt.Checked:
                path = item.data(self.PATH_ROLE)
                if path is not None:
                    paths.append(path)
        return paths

    def is_all_checked(self) -> bool:
        """Is every single row checked?"""
        items = list(self.iter_items())
        return bool(items) and all(item.checkState() == qt.Checked for item in items)

    def has_checked(self) -> bool:
        """Is at least 1 row checked?"""
        return any(item.checkState() == qt.Checked for item in self.iter_items())

    #
    # Check states propagation
    #

    def _set_state(self, item: QStandardItem, state: Qt.CheckState, /) -> None:
        """Set the check state of *item*, flagged as already handled."""
        if item.checkState() == state:
            return
        # The role is set first so that the itemChanged() triggered by
        # setCheckState() is seen as a no-op by _on_item_changed().
        item.setData(state, self.STATE_ROLE)
        item.setCheckState(state)

    def _on_item_changed(self, item: QStandardItem, /) -> None:
        """Propagate the check state the user just set on *item*."""
        if self._updating or item.column() != self.NAME:
            return

        state = item.checkState()
        if item.data(self.STATE_ROLE) == state:
            # Not a check state change (icon update, text change, ...)
            return

        self._updating = True
        try:
            item.setData(state, self.STATE_ROLE)

            # Down: selecting (or deselecting) a folder does the same to its
            # whole contents. Only done for the row the user clicked on.
            self._apply_to_children(item, state)

            # Up: deselecting a row also deselects the folders holding it, its
            # siblings keeping their own state. Selecting a row only selects
            # the parent folder once all of its contents are selected.
            self._update_parents(item, state)
        finally:
            self._updating = False

        self.selectionChanged.emit()

    def _apply_to_children(self, item: QStandardItem, state: Qt.CheckState, /) -> None:
        """Recursively set *state* on everything *item* contains."""
        for child in self.iter_items(item):
            self._set_state(child, state)

    def _update_parents(self, item: QStandardItem, state: Qt.CheckState, /) -> None:
        """Walk up the tree and adjust the folders holding *item*."""
        parent = item.parent()
        while parent is not None:
            if state == qt.Checked:
                # A folder is checked only when all of its contents are
                children = (
                    parent.child(row, self.NAME) for row in range(parent.rowCount())
                )
                if not all(
                    child is not None and child.checkState() == qt.Checked
                    for child in children
                ):
                    break

            if parent.checkState() == state:
                break

            self._set_state(parent, state)
            parent = parent.parent()

    def set_all_checked(self, checked: bool, /) -> None:
        """Check, or uncheck, every single row at once."""
        state = qt.Checked if checked else qt.Unchecked

        self._updating = True
        try:
            for item in self.iter_items():
                self._set_state(item, state)
        finally:
            self._updating = False

        self.selectionChanged.emit()


class ReviewSelectionDialog(QDialog):
    """The window allowing to review the local paths selected for a Direct Transfer."""

    def __init__(self, folder_dialog: "FoldersDialog", /) -> None:
        super().__init__(folder_dialog)

        self.folder_dialog = folder_dialog

        self.setWindowTitle(Translator.get("REVIEW_SELECTION"))
        self.resize(760, 420)

        layout = QVBoxLayout(self)

        # The search box, filtering the tree on the fly
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(Translator.get("REVIEW_SEARCH"))
        self.search.setClearButtonEnabled(True)
        self.search.setTextMargins(5, 0, 5, 0)
        self.search.textChanged.connect(self._filter)
        layout.addWidget(self.search)

        # The selection tree
        self.model = ReviewFileModel(folder_dialog.paths, self)

        self.tree_view = QTreeView(self)
        self.tree_view.setModel(self.model)
        # Folders show Qt's own branch arrow, on the left of the checkbox, and
        # everything starts collapsed: their contents are only shown once that
        # arrow is clicked, not on a double click on the row itself.
        self.tree_view.setRootIsDecorated(True)
        self.tree_view.setItemsExpandable(True)
        self.tree_view.setExpandsOnDoubleClick(False)
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

        self.select_all_button = QPushButton(Translator.get("REVIEW_SELECT_ALL"))
        self.select_all_button.clicked.connect(self._select_unselect_all)
        h_button_layout.addWidget(self.select_all_button)

        h_button_layout.addStretch(1)

        self.cancel_button = QPushButton(Translator.get("CANCEL"))
        self.cancel_button.clicked.connect(self.reject)
        h_button_layout.addWidget(self.cancel_button)

        self.remove_selection_button = QPushButton(Translator.get("REMOVE_SELECTION"))
        self.remove_selection_button.clicked.connect(self.accept)
        h_button_layout.addWidget(self.remove_selection_button)

        layout.addLayout(h_button_layout)

        # Connected last so that the buttons already exist when the signal fires
        self.model.selectionChanged.connect(self._buttons_state)
        self._buttons_state()

    #
    # Search
    #

    def _filter(self, text: str, /) -> None:
        """Show only the rows matching *text*, and the folders holding them."""
        self._filter_rows(self.model.invisibleRootItem(), text.strip().lower(), False)

    def _filter_rows(
        self, parent: QStandardItem, pattern: str, forced: bool, /
    ) -> bool:
        """Hide the rows below *parent* that do not match *pattern*.

        *forced* is True when a folder above already matched: everything it
        holds is then kept visible. A folder is kept when any of its contents
        matches, and is expanded so that the matches can be seen. Returns True
        when at least 1 row below *parent* is shown.
        """
        index = parent.index()
        shown = False

        for row in range(parent.rowCount()):
            item = parent.child(row, ReviewFileModel.NAME)
            if item is None:
                continue

            # The bare name, lowercased, is kept in UserRole: the displayed
            # text of a folder also holds its contents count.
            name = item.data(qt.UserRole) or ""
            matched = forced or not pattern or pattern in name

            below = self._filter_rows(item, pattern, matched)
            visible = matched or below

            self.tree_view.setRowHidden(row, index, not visible)

            if item.hasChildren():
                if not pattern:
                    # Back to the default: everything collapsed
                    self.tree_view.collapse(item.index())
                elif visible:
                    self.tree_view.expand(item.index())

            shown = shown or visible

        return shown

    #
    # Buttons
    #

    def _select_unselect_all(self) -> None:
        """Check, or uncheck, every single row of the tree."""
        self.model.set_all_checked(not self.model.is_all_checked())

    def _buttons_state(self) -> None:
        """Refresh the state and the label of the buttons.

        - *Remove Selection* is enabled only when at least 1 checkbox is checked.
        - *Select All* becomes *Deselect All* as soon as everything is checked,
          and goes back to *Select All* when any row gets unchecked.
        """
        self.remove_selection_button.setEnabled(self.model.has_checked())
        self.select_all_button.setText(
            Translator.get(
                "REVIEW_DESELECT_ALL"
                if self.model.is_all_checked()
                else "REVIEW_SELECT_ALL"
            )
        )

    #
    # Dialog
    #

    def accept(self) -> None:
        """Remove the checked paths from the selection, then close the window."""
        self.folder_dialog.remove_local_paths(self.model.checked_paths())
        super().accept()
