import webbrowser
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional, Union

from ..constants import APP_NAME, INVALID_CHARS
from ..engine.engine import Engine
from ..feature import Feature
from ..options import Options
from ..qt import constants as qt
from ..qt.imports import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QEvent,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QIcon,
    QKeyEvent,
    QLabel,
    QLineEdit,
    QMenu,
    QPoint,
    QPushButton,
    QRegExp,
    QRegExpValidator,
    QSize,
    Qt,
    QVBoxLayout,
    pyqtSignal,
)
from ..translator import Translator
from ..utils import find_icon, get_tree_list, sizeof_fmt
from .constants import get_known_types_translations
from .folders_model import FilteredDocuments, FoldersOnly
from .folders_treeview import DocumentTreeView, FolderTreeView

if TYPE_CHECKING:
    from .application import Application  # noqa

__all__ = ("DocumentsDialog", "FoldersDialog")

log = getLogger(__name__)

DOC_URL = "https://doc.nuxeo.com/n/CBX/#duplicates-behavior"


def regexp_validator() -> QRegExpValidator:
    """
    Generate a validator based on a specific regexp that will check an user input.
    This code has been moved to a method to allow unit testing.
    """
    expr = QRegExp(f"^[^{INVALID_CHARS}]+")
    return QRegExpValidator(expr)


class DialogMixin(QDialog):
    """The base class for the tree view window."""

    def __init__(self, application: "Application", engine: Engine, /) -> None:
        super().__init__(None)

        self.title_label = ""

        # Customize the window
        self.setAttribute(qt.WA_DeleteOnClose)
        self.setWindowIcon(application.icon)
        self.setWindowTitle(Translator.get(self.title_label, values=[APP_NAME]))

        # The window doesn't raise on Windows when the app is not in focus,
        # so after the login in the browser, we open the filters window with
        # the "stay on top" hint to make sure it comes back to the front
        # instead of just having a blinking icon in the taskbar.
        self.setWindowFlags(qt.WindowStaysOnTopHint)

        self.engine = engine
        self.application = application

        # The documents list
        self.tree_view = self.get_tree_view()
        self.tree_view.setContentsMargins(0, 0, 0, 0)

        # Buttons
        self.button_box: QDialogButtonBox = QDialogButtonBox(self)
        self.button_box.setOrientation(qt.Horizontal)
        self.button_box.setStandardButtons(self.get_buttons())
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        # The content view
        self.vertical_layout = QVBoxLayout(self)

    def get_buttons(self) -> QDialogButtonBox.StandardButtons:
        """Create the buttons to display at the bottom of the window."""
        return qt.Ok | qt.Cancel


class DocumentsDialog(DialogMixin):
    """The dialog window for synced documents. Used by the filters feature."""

    # The windows's title
    title_label = "FILTERS_WINDOW_TITLE"

    def __init__(self, application: "Application", engine: Engine, /) -> None:
        super().__init__(application, engine)

        self.vertical_layout.addWidget(self.tree_view)
        self.vertical_layout.addWidget(self.button_box)

        # Display something different when the user has no sync root
        self.no_root_label = self.get_no_roots_label()
        self.vertical_layout.insertWidget(0, self.no_root_label)

    def get_buttons(self) -> QDialogButtonBox.StandardButtons:
        """Create the buttons to display at the bottom of the window."""
        # Select/Unselect roots
        self.select_all_state = True
        self.select_all_text = (
            Translator.get("UNSELECT_ALL"),
            Translator.get("SELECT_ALL"),
        )

        buttons = qt.Ok
        if not self.engine.is_syncing():
            buttons |= qt.Cancel
            self.select_all_button = self.button_box.addButton(
                self.select_all_text[self.select_all_state], qt.ActionRole
            )
            self.select_all_button.clicked.connect(self._select_unselect_all_roots)
        return buttons

    def get_tree_view(self) -> Union[QLabel, DocumentTreeView]:
        """Render the documents tree."""

        # Prevent filter modifications while syncing, just display a message to warn the user
        if self.engine.is_syncing():
            label = QLabel(Translator.get("FILTERS_DISABLED"))
            label.setMargin(15)
            label.setAlignment(qt.AlignHCenter | qt.AlignVCenter)
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
            values=[
                self.engine.server_url,
                "https://doc.nuxeo.com/nxdoc/nuxeo-drive/#synchronizing-a-folder",
            ],
        )
        label.setText(text)
        label.setMargin(15)
        label.setWordWrap(True)
        label.setVisible(False)
        label.setOpenExternalLinks(True)
        label.setAlignment(qt.AlignHCenter | qt.AlignVCenter)
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
            if item.state == qt.Unchecked:
                self.engine.add_filter(path)
            elif item.state == qt.Checked:
                self.engine.remove_filter(path)
            elif item.old_state == qt.Unchecked:
                # Now partially checked and was before a filter

                # Remove current parent filter and need to commit to enable the add
                self.engine.remove_filter(path)

                # We need to browse every child and create a filter for
                # unchecked as they are not dirty but has become root filter
                for child in item.get_children():
                    if child.state == qt.Unchecked:
                        self.engine.add_filter(child.get_path())

        if not self.engine.is_started():
            self.engine.start()

    def _select_unselect_all_roots(self, _: Qt.CheckState, /) -> None:
        """The Select/Unselect all roots button."""
        state = qt.Checked if self.select_all_state else qt.Unchecked

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
    """The dialog window for folderish documents. Used by the Direct Transfer feature."""

    # The windows's title
    title_label = "DIRECT_TRANSFER_WINDOW_TITLE"

    # CSS for tooltips
    _TOOLTIP_CSS = (
        # Hack to show the entire icon
        "* { background-color: transparent }"
        "QToolTip { padding: 10px; color: #000; background-color: #F4F4F4 }"
    )

    newCtxTransfer = pyqtSignal(list)

    def __init__(
        self, application: "Application", engine: Engine, path: Optional[Path], /
    ) -> None:
        """*path* is None when the dialog window is opened from a click on the systray menu icon."""

        super().__init__(application, engine)
        self.setWindowFlags(self.windowFlags() & ~qt.WindowStaysOnTopHint)

        self.path: Optional[Path] = None
        self.paths: Dict[Path, int] = {}

        self.remote_folder_ref = self.engine.dao.get_config(
            "dt_last_remote_location_ref", default=""
        )
        self.remote_folder_title = self.engine.dao.get_config(
            "dt_last_remote_location_title", default=""
        )
        self.last_remote_location = self.engine.dao.get_config(
            "dt_last_remote_location", default=""
        )
        self.last_local_selected_location = self.engine.dao.get_config(
            "dt_last_local_selected_location"
        )

        self.last_local_selected_doc_type = self.engine.dao.get_config(
            "dt_last_local_selected_doc_type", default=""
        )
        self.duplicates_behavior = self.engine.dao.get_config(
            "dt_last_duplicates_behavior", default="create"
        )

        _types = get_known_types_translations()
        self.KNOWN_FOLDER_TYPES = _types.get("FOLDER_TYPES", {})
        self.KNOWN_FILE_TYPES = _types.get("FILE_TYPES", {})
        self.DEFAULT_TYPES = _types.get("DEFAULT", {})

        self.vertical_layout.addWidget(self._add_group_local())
        self.vertical_layout.addWidget(self._add_group_remote())
        self.vertical_layout.addWidget(self._add_group_options())
        self.vertical_layout.addWidget(self.button_box)

        # Compute overall size and count, and check the button state
        self._process_additionnal_local_paths([str(path)] if path else [])

        # Handle paths added from the context menu
        self.newCtxTransfer.connect(self._process_additionnal_local_paths)

        self.tree_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.open_menu)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        # On user Esc keypress event, restore the maximized window. See NXDRIVE-2737 for details.
        if event.key() == qt.Key_Escape:
            self.showNormal()
        else:
            super().keyPressEvent(event)

    @property
    def overall_count(self) -> int:
        """Compute total number of files and folders."""
        return len(self.paths.keys())

    @property
    def overall_size(self) -> int:
        """Compute all local paths contents size."""
        return sum(self.paths.values())

    def open_menu(self, position: QPoint) -> None:
        """Open a context menu at the provided *position*."""
        menu = QMenu()

        action = menu.addAction(
            self.tr("NEW_REMOTE_FOLDER"), self._new_folder_button_action
        )

        pointed_item = self.tree_view.get_item_from_position(position)
        action.setEnabled(self.tree_view.is_item_enabled(pointed_item))
        menu.exec_(self.tree_view.viewport().mapToGlobal(position))

    def _add_group_local(self) -> QGroupBox:
        """Group box for source files."""
        groupbox = QGroupBox(Translator.get("SOURCE_FILES"))
        layout = QHBoxLayout()
        groupbox.setLayout(layout)

        layout.setContentsMargins(10, 10, 10, 10)

        self.local_paths_size_lbl = QLabel(sizeof_fmt(self.overall_size))
        self.local_path = QLineEdit()
        self.local_path.setTextMargins(5, 0, 5, 0)
        self.local_path.setText(self._files_display())
        self.local_path.setReadOnly(True)
        files_button = QPushButton(Translator.get("ADD_FILES"), self)
        files_button.clicked.connect(self._select_more_files)
        layout.addWidget(self.local_path)
        layout.addWidget(self.local_paths_size_lbl)
        layout.addWidget(files_button)
        if self.engine.have_folder_upload:
            folders_button = QPushButton(Translator.get("ADD_FOLDER"), self)
            folders_button.clicked.connect(self._select_more_folder)
            layout.addWidget(folders_button)

        return groupbox

    def _add_group_options(self) -> QGroupBox:
        """Group box for options."""
        groupbox = QGroupBox(Translator.get("ADVANCED"))
        layout = QVBoxLayout()
        groupbox.setLayout(layout)

        duplicate_sublayout = QVBoxLayout()
        layout.addLayout(duplicate_sublayout)

        self._add_subgroup_container_type(layout)
        self._add_subgroup_doc_type(layout)
        self._add_subgroup_duplicate_behavior(duplicate_sublayout)
        self.update_file_group()

        # Adjust spacing
        layout.setSpacing(2)
        duplicate_sublayout.setSpacing(2)

        return groupbox

    def _add_group_remote(self) -> QGroupBox:
        """Group box for the remote folder."""
        groupbox = QGroupBox(Translator.get("SELECT_REMOTE_FOLDER"))
        layout = QVBoxLayout()
        groupbox.setLayout(layout)

        # The remote browser
        layout.addWidget(self.tree_view)
        layout.setSpacing(15)

        sublayout = QHBoxLayout()
        layout.addLayout(sublayout)
        label = QLabel(Translator.get("SELECTED_REMOTE_FOLDER"))
        self.remote_folder = QLineEdit()
        self.remote_folder.setStyleSheet("* { background-color: rgba(0, 0, 0, 0); }")
        self.remote_folder.setReadOnly(True)
        self.remote_folder.setFrame(False)
        sublayout.addWidget(label)
        sublayout.addWidget(self.remote_folder)

        self.new_folder_button = QPushButton(Translator.get("NEW_REMOTE_FOLDER"))
        self.new_folder_button.setToolTip(Translator.get("NEW_REMOTE_FOLDER_TOOLTIP"))
        self.new_folder_button.setSizePolicy(qt.Fixed, qt.Fixed)
        self.new_folder_button.clicked.connect(self._new_folder_button_action)

        if not self.engine.have_folder_upload:
            self.new_folder_button.setHidden(True)

        sublayout.addWidget(self.new_folder_button)

        # Populate the remote folder with the previously selected, if any
        self.remote_folder.setText(self.last_remote_location)

        return groupbox

    def _add_info_icon(self, tr_label: str) -> QPushButton:
        """Create an information icon with a tooltip."""
        button = QPushButton()
        button.setStyleSheet(self._TOOLTIP_CSS)
        button.setToolTip(Translator.get(tr_label))
        button.setIcon(QIcon(str(find_icon("info_icon.svg"))))  # 16x16 px
        button.setFlat(True)
        button.setMaximumSize(QSize(16, 16))
        button.setSizePolicy(qt.Fixed, qt.Fixed)
        return button

    def _open_duplicates_doc(self, _: bool) -> None:
        """Open the duplicates management documentation in a browser tab."""
        webbrowser.open_new_tab(DOC_URL)

    def _check_for_known_types(self, is_folder_type: bool, /) -> None:
        if is_folder_type:
            for key, val in self.KNOWN_FOLDER_TYPES.items():
                if key in self.containerTypeList:
                    self.containerTypeList.remove(key)
                    self.containerTypeList.append(val)
        else:
            for key, val in self.KNOWN_FILE_TYPES.items():
                if key in self.docTypeList:
                    self.docTypeList.remove(key)
                    self.docTypeList.append(val)

    def update_file_group(self, /) -> None:
        self.cbDocType.clear()
        self.cbContainerType.clear()
        if values := list(self.DEFAULT_TYPES.values()):
            self.cbContainerType.addItem(values[0], values[1])
            self.cbDocType.addItem(values[0], values[1])
        if self.remote_folder_ref:
            self.docTypeList = self.engine.remote.get_doc_enricher(
                self.remote_folder_ref, "subtypes", False
            )
            self._check_for_known_types(False)
            self.cbDocType.addItems(self.docTypeList)
        if self.remote_folder_ref:
            self.containerTypeList = self.engine.remote.get_doc_enricher(
                self.remote_folder_ref, "subtypes", True
            )
            self._check_for_known_types(True)
            self.cbContainerType.addItems(self.containerTypeList)

    def _add_subgroup_doc_type(self, layout: QVBoxLayout, /) -> None:
        """Add a Document type option."""
        docTypelayout = QHBoxLayout()
        labelDocType = QLabel(Translator.get("DOCUMENT_TYPE"))
        labelDocType.setTextFormat(qt.RichText)
        labelDocType.setOpenExternalLinks(True)
        docTypelayout.addWidget(labelDocType)
        docTypelayout.addSpacing(5)

        self.cbDocType = QComboBox()
        self.cbDocType.setEnabled(False)
        docTypelayout.addWidget(self.cbDocType)
        docTypelayout.addStretch(0)
        layout.addLayout(docTypelayout)

    def _add_subgroup_container_type(self, layout: QVBoxLayout, /) -> None:
        """Add a Container Type option."""
        contTypelayout = QHBoxLayout()
        labelContainerType = QLabel(Translator.get("CONTAINER_TYPE"))
        labelContainerType.setTextFormat(qt.RichText)
        labelContainerType.setOpenExternalLinks(True)
        contTypelayout.addWidget(labelContainerType)
        contTypelayout.addSpacing(5)

        self.cbContainerType = QComboBox()
        self.cbContainerType.setEnabled(False)
        contTypelayout.addWidget(self.cbContainerType)

        contTypelayout.addStretch(0)
        layout.addLayout(contTypelayout)

    def _add_subgroup_duplicate_behavior(self, layout: QVBoxLayout, /) -> None:
        duplayout = QHBoxLayout()
        """Add a sub-group for the duplicates behavior option."""
        label = QLabel(Translator.get("DUPLICATE_BEHAVIOR"))
        label.setTextFormat(qt.RichText)
        label.setOpenExternalLinks(True)
        duplayout.addWidget(label)

        info_icon = self._add_info_icon("DUPLICATE_BEHAVIOR_TOOLTIP")
        info_icon.clicked.connect(self._open_duplicates_doc)
        info_icon.setCursor(qt.PointingHandCursor)
        duplayout.addWidget(info_icon)

        self.cb = QComboBox()
        self.cb.addItem(Translator.get("DUPLICATE_BEHAVIOR_CREATE"), "create")
        self.cb.addItem(Translator.get("DUPLICATE_BEHAVIOR_IGNORE"), "ignore")
        self.cb.addItem(Translator.get("DUPLICATE_BEHAVIOR_OVERRIDE"), "override")
        duplayout.addWidget(self.cb)

        # Select the last run's choice
        index = self.cb.findData(self.duplicates_behavior)
        if index != -1:
            self.cb.setCurrentIndex(index)

        # Prevent previous objects to take the whole width, that does not render well for human eyes
        duplayout.addStretch(0)
        layout.addLayout(duplayout)

    def _new_folder_button_action(self) -> None:
        """Show a dialog allowing to edit the value of *new_folder*."""
        dialog = NewFolderDialog(self)
        dialog.exec_()

    def _find_folders_duplicates(self) -> List[str]:
        """Return a list of duplicate folder(s) found on the remote path."""
        parent = self.remote_folder_ref
        folders: List[str] = []

        all_paths = self.paths.keys()
        folders.extend(
            path.name
            for path in all_paths
            if (
                path.parent not in all_paths
                and path.is_dir()
                and self.engine.remote.exists_in_parent(parent, path.name, True)
            )
        )

        if folders:
            self.engine.send_metric("direct_transfer", "dupe_folder", "1")

        return folders

    def get_known_type_key(self, is_folder: bool, type: str, /) -> str:
        if type in self.DEFAULT_TYPES.values():
            original_list = self.DEFAULT_TYPES
        else:
            original_list = (
                self.KNOWN_FOLDER_TYPES if is_folder else self.KNOWN_FILE_TYPES
            )
        try:
            return list(original_list.keys())[list(original_list.values()).index(type)]
        except Exception:
            return type

    def accept(self) -> None:
        """Action to do when the OK button is clicked."""
        super().accept()

        self.last_local_selected_doc_type = (
            self.cbDocType.currentData()
            if self.cbDocType.currentIndex() == 0
            else self.cbDocType.currentText()
        )

        if folder_duplicates := self._find_folders_duplicates():
            self.application.folder_duplicate_warning(
                folder_duplicates,
                self.remote_folder_title,
                self.engine.get_metadata_url(self.remote_folder_ref),
            )
            return

        if self.cbContainerType.currentIndex() > 0:
            cont_type = self.cbContainerType.currentText()
        else:
            cont_type = ""
        doc_type = (
            self.cbDocType.currentText() if self.cbDocType.currentIndex() != 0 else ""
        )
        doc_type = self.get_known_type_key(False, doc_type)
        cont_type = self.get_known_type_key(True, cont_type)
        self.engine.direct_transfer_async(
            self.paths,
            self.remote_folder.text(),
            self.remote_folder_ref,
            self.remote_folder_title,
            document_type=doc_type,
            container_type=cont_type,
            duplicate_behavior=self.cb.currentData(),
            last_local_selected_location=self.last_local_selected_location,
            last_local_selected_doc_type=self.last_local_selected_doc_type,
        )

    def button_ok_state(self) -> None:
        """Handle the state of the OK button. It should be enabled when particular criteria are met."""

        # Required criteria:
        #   - at least 1 local path or a new folder to create
        #   - a selected remote path
        self.button_box.button(qt.Ok).setEnabled(bool(self.paths))
        self.new_folder_button.setEnabled(
            bool(self.remote_folder_ref) and bool(self.tree_view.current)
        )
        self.cbDocType.setEnabled(
            bool(self.paths)
            and bool(self.tree_view.current)
            and bool(Feature.document_type_selection)
        )
        # Select the last run's choice
        index = (
            self.cbDocType.findText(self.last_local_selected_doc_type)
            if self.last_local_selected_doc_type
            and self.last_local_selected_doc_type != ""
            else 0
        )
        if index != -1:
            self.cbDocType.setCurrentIndex(index)

        self.cbContainerType.setEnabled(
            bool(self.path)
            and bool(self.tree_view.current)
            and bool(Feature.document_type_selection)
        )

    def get_tree_view(self) -> FolderTreeView:
        """Render the folders tree."""
        self.resize(800, 450)
        client = FoldersOnly(self.engine.remote)
        return FolderTreeView(self, client)

    def _files_display(self) -> str:
        """Return the original file or folder to upload and the count of others to proceed."""
        txt = str(self.path or "")
        if self.overall_count > 1:
            txt += f" (+{self.overall_count - 1:,})"
        return txt

    def _process_additionnal_local_paths(self, paths: List[str], /) -> None:
        """Append more local paths to the upload queue."""
        for local_path in paths:
            if not local_path:
                # When closing the folder selection, *local_path* would be an empty string.
                continue

            path = Path(local_path)

            # Check that the path can be processed
            if path.name.startswith(Options.ignored_prefixes) or path.name.endswith(
                Options.ignored_suffixes
            ):
                log.debug(f"Ignored path for Direct Transfer: {str(path)!r}")
                continue

            # Prevent to upload twice the same file
            if path in self.paths.keys():
                continue

            # Save the path
            if path.is_dir():
                for file_path, size in get_tree_list(path):
                    file_size = file_path.stat().st_size
                    if file_size == 0:
                        continue
                    self.paths[file_path] = size
            else:
                try:
                    file_size = path.stat().st_size
                    if file_size == 0:
                        continue
                    self.paths[path] = file_size
                except OSError:
                    log.warning(f"Error calling stat() on {path!r}", exc_info=True)
                    continue

            self.last_local_selected_location = path.parent

            # If .path is None, then pick the first local path to display something useful
            if not self.path:
                self.path = path

        # Update labels with new information
        self.local_path.setText(self._files_display())
        self.local_paths_size_lbl.setText(sizeof_fmt(self.overall_size))

        self.button_ok_state()

    def _select_more_files(self) -> None:
        """Choose additional local files to upload."""
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            Translator.get("ADD_FILES"),
            str(self.last_local_selected_location),
        )
        self._process_additionnal_local_paths(paths)

    def _select_more_folder(self) -> None:
        """Choose an additional local folder to upload."""
        path = QFileDialog.getExistingDirectory(
            self,
            Translator.get("ADD_FOLDER"),
            str(self.last_local_selected_location),
        )
        self._process_additionnal_local_paths([path])


class NewFolderDialog(QDialog):
    """The class for the new folder creation window."""

    def __init__(self, folder_dialog: FoldersDialog, /) -> None:
        super().__init__(folder_dialog)

        self.setWindowTitle(Translator.get("NEW_REMOTE_FOLDER"))
        self.resize(320, 200)
        self.folder_dialog = folder_dialog

        layout = QVBoxLayout()

        self.facetList = self.folder_dialog.engine.remote.get_doc_enricher(
            self.folder_dialog.remote_folder_ref, "subtypes"
        )

        self.folder_creation_frame = QFrame()
        self.operation_result_frame = QFrame()

        self._add_folder_creation_layout()
        self._add_operation_result_layout()

        layout.addWidget(self.folder_creation_frame)
        layout.addWidget(self.operation_result_frame)

        self.operation_result_frame.hide()
        self.setLayout(layout)

        self.folder_dialog.engine.directTransferNewFolderSuccess.connect(
            self.handle_creation_success
        )
        self.folder_dialog.engine.directTransferNewFolderError.connect(
            self.handle_creation_failure
        )

        self.created_remote_path = ""

    def closeEvent(self, _: QEvent) -> None:
        """Triggered when the QDialog is closed."""
        if self.created_remote_path:
            self.close_success()

    def _add_operation_result_layout(self) -> None:
        """Add the layout that will be displayed when the operation is fineshed."""

        layout = QVBoxLayout()

        self.operation_result_status = QLabel()
        self.operation_result_message = QLabel()

        self.operation_result_message.setWordWrap(True)

        buttons_box = QDialogButtonBox()
        close_button = QPushButton(Translator.get("CLOSE"), self)

        buttons_box.addButton(close_button, QDialogButtonBox.ButtonRole.RejectRole)
        buttons_box.rejected.connect(self.close_success)
        buttons_box.setContentsMargins(0, 10, 0, 5)
        layout.addWidget(self.operation_result_status)
        layout.addWidget(self.operation_result_message)
        layout.addWidget(buttons_box)

        self.operation_result_frame.setLayout(layout)

    def _add_folder_creation_layout(self) -> None:
        """Add the layout containing the new folder inputs."""

        layout = QVBoxLayout()

        self.new_folder_name = QLineEdit(parent=self)
        self.new_folder_name.setMaxLength(64)
        self.new_folder_name.setValidator(regexp_validator())
        self.new_folder_name.setClearButtonEnabled(True)
        self.new_folder_name.textChanged.connect(self._button_ok_state)

        self.cb = QComboBox()
        self.cb.addItem("Automatic", "create")
        self.cb.addItems(self.facetList)

        folder_label = QLabel(Translator.get("FOLDER_NAME"))
        type_label = QLabel(Translator.get("FOLDER_TYPE"))

        layout.addWidget(type_label)
        layout.addWidget(self.cb)
        layout.addWidget(folder_label)
        layout.addWidget(self.new_folder_name)

        self.buttons_box = QDialogButtonBox()
        self.buttons_box.setStandardButtons(qt.Cancel)
        self.buttons_box.setContentsMargins(0, 15, 0, 5)

        self.create_button = QPushButton(Translator.get("CREATE"), self)
        self.create_button.setDisabled(True)
        self.buttons_box.addButton(
            self.create_button, QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.buttons_box.accepted.connect(self.accept)
        self.buttons_box.rejected.connect(self.close)

        layout.addWidget(self.buttons_box)
        self.folder_creation_frame.setLayout(layout)

    def accept(self) -> None:
        """Start the asynchronous Direct Transfer if there is no duplicate."""

        new_folder = self.new_folder_name.text()
        if bool(new_folder) and self.folder_dialog.engine.remote.exists_in_parent(
            self.folder_dialog.remote_folder_ref, new_folder, True
        ):
            return self._show_result_message(
                Translator.get("NEW_REMOTE_FOLDER_DUPLICATE"),
                Translator.get("ERROR"),
            )

        self.folder_dialog.engine.direct_transfer_async(
            {},
            self.folder_dialog.remote_folder.text(),
            self.folder_dialog.remote_folder_ref,
            self.folder_dialog.remote_folder_title,
            document_type="",
            container_type="",
            duplicate_behavior=self.folder_dialog.cb.currentData(),
            last_local_selected_location=self.folder_dialog.last_local_selected_location,
            new_folder=self.new_folder_name.text(),
            new_folder_type=self.cb.currentText(),
        )

    def close_success(self) -> None:
        """Select the created item in the tree view."""

        self.folder_dialog.tree_view.expand_current_selected()
        self.folder_dialog.tree_view.select_item_from_path(self.created_remote_path)
        self.folder_dialog.tree_view.expand_current_selected()
        self.close()

    def _show_result_message(self, message: str, status: str) -> None:
        """Hide the creation layout and show the result message."""

        self.operation_result_message.setText(message)
        self.operation_result_status.setText(status)
        self.folder_creation_frame.hide()
        self.operation_result_frame.show()
        self.resize(320, 160)

    def _button_ok_state(self, _: str) -> None:
        """CHeck if the folder name input is not empty."""
        if bool(self.new_folder_name.text()):
            self.create_button.setDisabled(False)

    def handle_creation_success(self, new_remote_path: str) -> None:
        """Update the tree view and show the operation success result message."""

        self.created_remote_path = new_remote_path
        self.folder_dialog.tree_view.update.emit()
        return self._show_result_message(
            Translator.get("NEW_REMOTE_FOLDER_SUCCESS"), Translator.get("SUCCESS")
        )

    def handle_creation_failure(self) -> None:
        """Show the operation failure result message."""

        return self._show_result_message(
            Translator.get("NEW_REMOTE_FOLDER_FAILURE"), Translator.get("ERROR")
        )
