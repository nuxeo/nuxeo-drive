# coding: utf-8
from pathlib import Path
from typing import Union, TYPE_CHECKING

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from .folders_treeview import DocumentTreeView, FolderTreeView
from .folders_model import FoldersOnly, FilteredDocuments
from ..constants import APP_NAME
from ..engine.engine import Engine
from ..translator import Translator
from ..utils import sizeof_fmt

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

        # Add a new widget at 1st position: a text input with the local file to upload
        local_file_layout = QHBoxLayout()
        local_file_lbl = QLabel(Translator.get("LOCAL_FILE"))
        local_file_size_lbl = QLabel(sizeof_fmt(path.stat().st_size))
        local_file = QLineEdit()
        local_file.setTextMargins(5, 0, 5, 0)
        local_file.setText(str(path))
        local_file.setReadOnly(True)
        local_file_layout.addWidget(local_file_lbl)
        local_file_layout.addWidget(local_file)
        local_file_layout.addWidget(local_file_size_lbl)
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

        # Do not allow the click on OK until a folder is selected
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

    def get_tree_view(self) -> FolderTreeView:
        """Render the folders tree."""
        self.resize(640, 320)
        client = FoldersOnly(self.engine.remote)
        return FolderTreeView(self, client)

    def accept(self) -> None:
        """Action to do when the OK button is clicked."""

        # Save the remote folder's path into the file xattr
        self.engine.local.set_remote_id(self.path, self.remote_folder.text())

        # Add the file into the database and plan the upload
        info = self.engine.local.get_info(self.path)
        self.engine.dao.insert_local_state(info, None, local_state="direct")

        super().accept()
