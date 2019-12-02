# coding: utf-8
from pathlib import Path
from typing import List, Union, TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QMenu,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from .folders_treeview import DocumentTreeView, FolderTreeView
from .folders_model import FoldersOnly, FilteredDocuments
from ..constants import APP_NAME
from ..engine.engine import Engine
from ..translator import Translator
from ..utils import get_tree_list, get_tree_size, sizeof_fmt

if TYPE_CHECKING:
    from .application import Application  # noqa

__all__ = ("DocumentsDialog", "FoldersDialog")


class DialogMixin(QDialog):
    """The base class for the tree view window."""

    def __init__(self, application: "Application", engine: Engine) -> None:
        super().__init__(None)

        # Customize the window
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowIcon(application.icon)
        self.setWindowTitle(Translator.get(self.title_label, values=[APP_NAME]))

        # The window doesn't raise on Windows when the app is not in focus,
        # so after the login in the browser, we open the filters window with
        # the "stay on top" hint to make sure it comes back to the front
        # instead of just having a blinking icon in the taskbar.
        self.setWindowFlags(Qt.WindowStaysOnTopHint)

        self.engine = engine
        self.application = application

        # The documents list
        self.tree_view = self.get_tree_view()
        self.tree_view.setContentsMargins(0, 0, 0, 0)

        # Buttons
        self.button_box: QDialogButtonBox = QDialogButtonBox(self)
        self.button_box.setOrientation(Qt.Horizontal)
        self.button_box.setStandardButtons(self.get_buttons())
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # The content view
        self.vertical_layout = QVBoxLayout(self)
        self.vertical_layout.addWidget(self.tree_view)
        self.vertical_layout.addWidget(self.button_box)

    def get_buttons(self):
        """Create the buttons to display at the bottom of the window."""
        return QDialogButtonBox.Ok | QDialogButtonBox.Cancel


class DocumentsDialog(DialogMixin):
    """The dialog window for synced documents. Used bu the filters feature."""

    # The windows's title
    title_label = "FILTERS_WINDOW_TITLE"

    def __init__(self, application: "Application", engine: Engine) -> None:
        super().__init__(application, engine)

        # Display something different when the user has no sync root
        self.no_root_label = self.get_no_roots_label()
        self.vertical_layout.insertWidget(0, self.no_root_label)

    def get_buttons(self):
        """Create the buttons to display at the bottom of the window."""
        # Select/Unselect roots
        self.select_all_state = True
        self.select_all_text = (
            Translator.get("UNSELECT_ALL"),
            Translator.get("SELECT_ALL"),
        )

        buttons = QDialogButtonBox.Ok
        if not self.engine.is_syncing():
            buttons |= QDialogButtonBox.Cancel
            self.select_all_button = self.button_box.addButton(
                self.select_all_text[self.select_all_state], QDialogButtonBox.ActionRole
            )
            self.select_all_button.clicked.connect(self._select_unselect_all_roots)
        return buttons

    def get_tree_view(self) -> Union[QLabel, DocumentTreeView]:
        """Render the documents tree."""

        # Prevent filter modifications while syncing, just display a message to warn the user
        if self.engine.is_syncing():
            label = QLabel(Translator.get("FILTERS_DISABLED"))
            label.setMargin(15)
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            return label

        self.resize(491, 443)
        filters = self.engine.dao.get_filters()
        remote = self.engine.remote
        client = FilteredDocuments(remote, filters)
        tree_view = DocumentTreeView(self, client)
        tree_view.noRoots.connect(self._handle_no_roots)
        return tree_view

    def get_no_roots_label(self) -> QLabel:
        """The contents of the window when there is no sync root."""
        label = QLabel(parent=self)
        text = Translator.get(
            "NO_ROOTS",
            [
                self.engine.server_url,
                "https://doc.nuxeo.com/nxdoc/nuxeo-drive/#synchronizing-a-folder",
            ],
        )
        label.setText(text)
        label.setMargin(15)
        label.setWordWrap(True)
        label.setVisible(False)
        label.setOpenExternalLinks(True)
        label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        return label

    def _handle_no_roots(self) -> None:
        """When there is no sync root, display an informal message and hide the tree view."""
        self.select_all_button.setVisible(False)
        self.tree_view.setVisible(False)
        self.tree_view.resize(0, 0)
        self.no_root_label.setVisible(True)
        self.setGeometry(self.x(), self.y() + 150, 491, 200)

    def accept(self) -> None:
        """Action to do when the OK button is clicked."""

        # Apply filters if the user has made changes
        if isinstance(self.tree_view, DocumentTreeView):
            self.apply_filters()

        super().accept()

    def apply_filters(self) -> None:
        """Apply changes made by the user."""
        items = sorted(self.tree_view.dirty_items, key=lambda x: x.get_path())
        for item in items:
            path = item.get_path()
            if item.state == Qt.Unchecked:
                self.engine.add_filter(path)
            elif item.state == Qt.Checked:
                self.engine.remove_filter(path)
            elif item.old_state == Qt.Unchecked:
                # Now partially checked and was before a filter

                # Remove current parent filter and need to commit to enable the add
                self.engine.remove_filter(path)

                # We need to browse every child and create a filter for
                # unchecked as they are not dirty but has become root filter
                for child in item.get_children():
                    if child.state == Qt.Unchecked:
                        self.engine.add_filter(child.get_path())

        if not self.engine.is_started():
            self.engine.start()

    def _select_unselect_all_roots(self, _: Qt.CheckState) -> None:
        """The Select/Unselect all roots button."""
        state = Qt.Checked if self.select_all_state else Qt.Unchecked

        roots = sorted(self.tree_view.client.roots, key=lambda x: x.get_path())
        for num, root in enumerate(roots):
            index = self.tree_view.model().index(num, 0)
            item = self.tree_view.model().itemFromIndex(index)
            if item.checkState() != state:
                item.setCheckState(state)
                self.tree_view.update_item_changed(item)

        self.select_all_state = not self.select_all_state
        self.select_all_button.setText(self.select_all_text[self.select_all_state])


class FoldersDialog(DialogMixin):
    """The dialog window for folderish documents. Used bu the Direct Transfer feature."""

    # The windows's title
    title_label = "DIRECT_TRANSFER_WINDOW_TITLE"

    def __init__(self, application: "Application", engine: Engine, path: Path) -> None:
        super().__init__(application, engine)

        self.path = path
        self.paths = set([self.path])
        self.overall_size = self._get_overall_size()
        self.overall_count = self._get_overall_count()

        # Add a new widget at 1st position:
        #   - a text input with the 1st local path (+ count of eventual other paths)
        #   - a label holding contents size
        #   - a button to add more local paths
        local_file_layout = QHBoxLayout()
        self.local_paths_size_lbl = QLabel(sizeof_fmt(self.overall_size))
        self.local_path = QLineEdit()
        self.local_path.setTextMargins(5, 0, 5, 0)
        self.local_path.setText(self._files_display())
        self.local_path.setReadOnly(True)
        add_local_path_btn = QPushButton(Translator.get("ADD_FILES"), self)
        add_local_path_btn.setMenu(self._add_sub_menu())
        local_file_layout.addWidget(self.local_path)
        local_file_layout.addWidget(self.local_paths_size_lbl)
        local_file_layout.addWidget(add_local_path_btn)
        self.vertical_layout.insertLayout(0, local_file_layout)

        # Add a new widget before the buttons: a text input with the selected remote folder to upload into
        remote_folder_layout = QHBoxLayout()
        remote_folder_lbl = QLabel(Translator.get("REMOTE_FOLDER"))
        self.remote_folder = QLineEdit()
        self.remote_folder.setTextMargins(5, 0, 5, 0)
        self.remote_folder.setReadOnly(True)
        remote_folder_layout.addWidget(remote_folder_lbl)
        remote_folder_layout.addWidget(self.remote_folder)
        self.vertical_layout.insertLayout(2, remote_folder_layout)

        # Populate the remote folder with the previously selected, if any
        self.remote_folder.setText(engine.dao.get_config("dt_last_remote_location", ""))

        # Do not allow the click on OK until a folder is selected
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.remote_folder.text())
        )

    def accept(self) -> None:
        """Action to do when the OK button is clicked."""
        super().accept()
        self.engine.direct_transfer(self.paths, self.remote_folder.text())

    def get_tree_view(self) -> FolderTreeView:
        """Render the folders tree."""
        self.resize(640, 320)
        client = FoldersOnly(self.engine.remote)
        return FolderTreeView(self, client)

    def _add_sub_menu(self) -> QMenu:
        """Ths is the sub-menu displayed when clicking on the Add button."""
        menu = QMenu()
        menu.addAction(Translator.get("ADD_FILES"), self._select_more_files)
        menu.addAction(Translator.get("ADD_FOLDER"), self._select_more_folder)
        return menu

    def _files_display(self) -> str:
        """Return the original file or folder to upload and the count of others to proceed."""
        txt = str(self.path)
        if self.overall_count > 1:
            txt += f" (+{self.overall_count - 1:,})"
        return txt

    def _get_overall_count(self) -> int:
        """Compute total number of files and folders."""
        return sum(self._get_count(p) for p in self.paths)

    def _get_overall_size(self) -> int:
        """Compute all local paths contents size."""
        return sum(self._get_size(p) for p in self.paths)

    def _get_count(self, path: Path) -> int:
        """Get the children count of a folder or return 1 if a file."""
        if path.is_dir():
            return len(list(get_tree_list(path, "")))
        return 1

    def _get_size(self, path: Path) -> int:
        """Get the local file size or its contents size when a folder."""
        if path.is_dir():
            return get_tree_size(path)
        return path.stat().st_size

    def _process_additionnal_local_paths(self, paths: List[str]) -> None:
        """Append more local paths to the upload queue."""
        if not paths:
            return

        for local_path in paths:
            path = Path(local_path)

            # Prevent to upload twice the same file
            if path in self.paths:
                continue

            # Save the path
            self.paths.add(path)

            # Recompute total size and count
            self.overall_size += self._get_size(path)
            self.overall_count += self._get_count(path)

        # Update labels with new information
        self.local_path.setText(self._files_display())
        self.local_paths_size_lbl.setText(sizeof_fmt(self.overall_size))

    def _select_more_files(self) -> None:
        """Choose additional local files to upload."""
        paths, _ = QFileDialog.getOpenFileNames(self, Translator.get("ADD_FILES"))
        self._process_additionnal_local_paths(paths)

    def _select_more_folder(self) -> None:
        """Choose an additional local folder to upload."""
        path = QFileDialog.getExistingDirectory(self, Translator.get("ADD_FOLDER"))
        self._process_additionnal_local_paths([path])
