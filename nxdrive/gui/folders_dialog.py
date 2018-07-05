# coding: utf-8
from typing import Union

from PyQt5.QtCore import QObject, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout

from .folders_treeview import FilteredFsClient, FolderTreeview
from ..wui.translator import Translator

__all__ = ("FiltersDialog",)


class FiltersDialog(QDialog):
    def __init__(
        self, application: "Application", engine: "Engine", parent: QObject = None
    ) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(Translator.get("FILTERS_WINDOW_TITLE"))

        self.vertical_layout = QVBoxLayout(self)
        self.vertical_layout.setContentsMargins(0, 0, 0, 0)

        self._engine = engine
        self.syncing = self._engine.is_syncing()  # NXDRIVE-959
        self.application = application
        icon = self.application.get_window_icon()
        if icon is not None:
            self.setWindowIcon(QIcon(icon))

        self.tree_view = self.get_tree_view()
        self.vertical_layout.addWidget(self.tree_view)

        self.button_box = QDialogButtonBox(self)
        self.button_box.setOrientation(Qt.Horizontal)
        buttons = QDialogButtonBox.Ok
        if not self.syncing:
            buttons |= QDialogButtonBox.Cancel
        self.button_box.setStandardButtons(buttons)
        self.vertical_layout.addWidget(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def get_tree_view(self) -> Union[QLabel, FolderTreeview]:
        if self.syncing:
            # Prevent filter modifications while syncing
            label = QLabel(Translator.get("FILTERS_DISABLED"))
            label.setMargin(15)
            label.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
            return label

        self.resize(491, 443)
        filters = self._engine.get_dao().get_filters()
        fs_client = self._engine.remote
        client = FilteredFsClient(fs_client, filters)
        return FolderTreeview(self, client)

    def accept(self) -> None:
        """ When you click on the OK button. """

        if not self.syncing:
            # Prevent filter modifications while syncing
            self.apply_filters()

        super().accept()

    def apply_filters(self) -> None:
        items = sorted(self.tree_view.dirty_items, key=lambda x: x.get_path())
        for item in items:
            path = item.get_path()
            if item.state == Qt.Unchecked:
                self._engine.add_filter(path)
            elif item.state == Qt.Checked:
                self._engine.remove_filter(path)
            elif item.old_state == Qt.Unchecked:
                # Now partially checked and was before a filter

                # Remove current parent filter and need to commit to enable the
                # add
                self._engine.remove_filter(path)

                # We need to browse every child and create a filter for
                # unchecked as they are not dirty but has become root filter
                for child in item.get_children():
                    if child.state == Qt.Unchecked:
                        self._engine.add_filter(child.get_path())

        if not self._engine.is_started():
            self._engine.start()
