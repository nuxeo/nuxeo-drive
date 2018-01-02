# coding: utf-8
from PyQt4 import QtCore, QtGui

from nxdrive.gui.folders_treeview import FilteredFsClient, FolderTreeview
from nxdrive.wui.translator import Translator


class FiltersDialog(QtGui.QDialog):

    def __init__(self, application, engine, parent=None):
        super(FiltersDialog, self).__init__(parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle(Translator.get('FILTERS_WINDOW_TITLE'))

        self.vertical_layout = QtGui.QVBoxLayout(self)
        self.vertical_layout.setContentsMargins(0, 0, 0, 0)

        self._engine = engine
        self.syncing = self._engine.is_syncing()  # NXDRIVE-959
        self.application = application
        icon = self.application.get_window_icon()
        if icon is not None:
            self.setWindowIcon(QtGui.QIcon(icon))

        self.tree_view = self.get_tree_view()
        self.vertical_layout.addWidget(self.tree_view)

        self.button_box = QtGui.QDialogButtonBox(self)
        self.button_box.setOrientation(QtCore.Qt.Horizontal)
        buttons = QtGui.QDialogButtonBox.Ok
        if not self.syncing:
            buttons |= QtGui.QDialogButtonBox.Cancel
        self.button_box.setStandardButtons(buttons)
        self.vertical_layout.addWidget(self.button_box)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

    def get_tree_view(self):
        if self.syncing:
            # Prevent filter modifications while syncing
            label = QtGui.QLabel(Translator.get('FILTERS_DISABLED'))
            label.setMargin(15)
            label.setAlignment(QtCore.Qt.AlignHCenter | QtCore.Qt.AlignVCenter)
            return label

        self.resize(491, 443)
        filters = self._engine.get_dao().get_filters()
        fs_client = self._engine.get_remote_client(filtered=False)
        client = FilteredFsClient(fs_client, filters)
        return FolderTreeview(self, client)

    def accept(self):
        """ When you click on the OK button. """

        if not self.syncing:
            # Prevent filter modifications while syncing
            self.apply_filters()

        super(FiltersDialog, self).accept()

    def apply_filters(self):
        for item in self.tree_view.dirty_items:
            path = item.get_path()
            if item.get_checkstate() == QtCore.Qt.Unchecked:
                self._engine.add_filter(path)
            elif item.get_checkstate() == QtCore.Qt.Checked:
                self._engine.remove_filter(path)
            elif item.get_old_value() == QtCore.Qt.Unchecked:
                # Now partially checked and was before a filter

                # Remove current parent filter and need to commit to enable the
                # add
                self._engine.remove_filter(path)

                # We need to browse every child and create a filter for
                # unchecked as they are not dirty but has become root filter
                for child in item.get_children():
                    if child.get_checkstate() == QtCore.Qt.Unchecked:
                        self._engine.add_filter(child.get_path())

        if not self._engine.is_started():
            self._engine.start()
