# coding: utf-8
import os

from PyQt5.QtCore import QAbstractListModel, QModelIndex, Qt, QUrl, pyqtSlot
from PyQt5.QtGui import QColor, QCursor
from PyQt5.QtQuick import QQuickView
from PyQt5.QtWidgets import QApplication, QMenu, QStyle, QSystemTrayIcon

from ..constants import MAC
from ..options import Options
from ..updater.constants import (UPDATE_STATUS_DOWNGRADE_NEEDED,
                                 UPDATE_STATUS_UPDATE_AVAILABLE)
from .dialog import WebDialog, WebDriveApi
from .translator import Translator


class DriveSystrayIcon(QSystemTrayIcon):

    __menu_left = None
    __menu_right = None
    use_old_menu = MAC or os.environ.get('USE_OLD_MENU', False)

    def __init__(self, application):
        super(DriveSystrayIcon, self).__init__(application)
        self.application = application
        self.messageClicked.connect(self.application.message_clicked)
        self.activated.connect(self.handle_mouse_click)

        # Windows bug: the systray icon is still visible
        self.application.aboutToQuit.connect(self.hide)

        if not self.use_old_menu:
            # On macOS, only the left click is detected, so the context
            # menu is useless.  It is better to not define it else it
            # will show up every click on the systray icon.
            self.setContextMenu(self.menu_right)

    def handle_mouse_click(self, reason):
        """
        Handle any mouse click on the systray icon.
        It is not needed to handle the right click as it
        is the native behavior and will open the context
        menu (right click menu).

        Note: only the left click is detected on macOS.
        """

        if reason == QSystemTrayIcon.Trigger:
            # On left click, open the usual menu with engines and sync files
            self.menu_left.popup(QCursor.pos())
        elif reason == QSystemTrayIcon.MiddleClick:
            # On middle click, open settings.  Yeah, it rocks!
            self.application.show_settings()

    @property
    def menu_left(self):
        """
        Create the usual menu with engines and sync files.
        It shows up on left click.
        """

        if not self.__menu_left:
            self.__menu_left = WebSystray(self, self.application)
        return self.__menu_left

    @property
    def menu_right(self):
        """
        Create the context menu.
        It shows up on left click.

        Note: icons will not be displayed on every GNU/Linux
        distributions, it depends on the graphical environment.
        """

        if not self.__menu_right:
            style = QApplication.style()
            menu = QMenu()
            menu.addAction(
                style.standardIcon(QStyle.SP_FileDialogInfoView),
                Translator.get('SETTINGS'),
                self.application.show_settings,
            )
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_MessageBoxQuestion),
                Translator.get('HELP'),
                self.application.open_help)
            menu.addSeparator()
            menu.addAction(
                style.standardIcon(QStyle.SP_DialogCloseButton),
                Translator.get('QUIT'),
                self.application.quit)
            self.__menu_right = menu

        return self.__menu_right


class WebSystrayApi(WebDriveApi):

    menu = None

    @pyqtSlot(str)
    def show_settings(self, page):
        self.dialog.hide()
        super(WebSystrayApi, self).show_settings(page)

    @pyqtSlot(str)
    def show_conflicts_resolution(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).show_conflicts_resolution(uid)

    @pyqtSlot(str, str)
    def show_metadata(self, uid, ref):
        self.dialog.hide()
        super(WebSystrayApi, self).show_metadata(uid, ref)

    @pyqtSlot(str)
    def open_remote(self, uid):
        self.dialog.hide()
        super(WebSystrayApi, self).open_remote(uid)

    @pyqtSlot(str, str)
    def open_local(self, uid, path):
        self.dialog.hide()
        super(WebSystrayApi, self).open_local(uid, path)

    @pyqtSlot()
    def open_help(self):
        self.dialog.hide()
        self._manager.open_help()

    @pyqtSlot(str)
    def trigger_notification(self, id_):
        self.dialog.hide()
        super(WebSystrayApi, self).trigger_notification(id_)

    @pyqtSlot(bool)
    def suspend(self, start):
        if start:
            self._manager.resume()
        else:
            self._manager.suspend()

    @pyqtSlot(result=bool)
    def is_paused(self):
        return self._manager.is_paused()

    @pyqtSlot(result=bool)
    def need_adv_menu(self):
        """
        Do we need to display the left click advanced menu?  Yes if:
          - on debug
          - on macOS
          - when the envar USE_OLD_MENU is set
            (for Unity that does not see right click into the systray)
        """
        return Options.debug or MAC or os.environ.get('USE_OLD_MENU', False)

    @pyqtSlot(str, result=int)
    def get_syncing_items(self, uid):
        count = 0
        engine = self._get_engine(str(uid))
        if engine:
            count = engine.get_dao().get_syncing_count()
        return count

    @pyqtSlot()
    def advanced_systray(self):
        if not self.need_adv_menu():
            return

        if self.menu:
            return self.menu.popup(QCursor.pos())

        self.menu = QMenu()

        if Options.debug:
            self.application.create_debug_menu(self.menu)

        self.menu.addSeparator()
        self.menu.addAction(Translator.get('SETTINGS'),
                            self.application.show_settings)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get('HELP'),
                            self.application.open_help)
        self.menu.addSeparator()
        self.menu.addAction(Translator.get('QUIT'), self.application.quit)

        self.menu.popup(QCursor.pos())


class WebSystray(QMenu):
    """ Left-click menu, also the entire menu on macOS. """

    __dialog = None

    def __init__(self, systray_icon, application):
        super(WebSystray, self).__init__()
        self.application = application
        self.systray_icon = systray_icon

    @property
    def dialog(self):
        if not self.__dialog:
            self.__dialog = SystrayView(self.application, self.systray_icon)
            self.__dialog.icon = self.systray_icon
        return self.__dialog

    @pyqtSlot()
    def popup(self, _):
        # Not the best, but works for now

        self.dialog.reload()
        self.dialog.show()

        # macOs bug: if you click on the advanced menu and then elsewhere
        # when you will re-click on the menu, nothing will appear.
        self.dialog.raise_()


class EngineModel(QAbstractListModel):
    UID_ROLE = Qt.UserRole + 1
    TYPE_ROLE = Qt.UserRole + 2
    SERVER_ROLE = Qt.UserRole + 3

    def __init__(self, parent=None):
        super(EngineModel, self).__init__(parent)
        self.engines = []

    def roleNames(self):
        return {
            self.UID_ROLE: b'uid',
            self.TYPE_ROLE: b'type',
            self.SERVER_ROLE: b'server'
        }

    def addEngines(self, engines, parent=QModelIndex()):
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(engines) - 1)
        self.engines.extend(engines)
        self.endInsertRows()

    def removeEngine(self, uid):
        for idx, engine in enumerate(self.engines):
            if engine.uid == uid:
                self.removeRows(idx, 1)
                break

    def data(self, index, role=TYPE_ROLE):
        row = self.engines[index.row()]
        if role == self.UID_ROLE:
            return row['uid']
        if role == self.TYPE_ROLE:
            return row['type']
        if role == self.SERVER_ROLE:
            return row['server']
        return None

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(count):
            self.engines.pop(row)
        self.endRemoveRows()

    def empty(self):
        count = self.rowCount()
        self.removeRows(0, count)

    def rowCount(self, parent=QModelIndex()):
        return len(self.engines)


class FileModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    TIME_ROLE = Qt.UserRole + 2
    TRANSFER_ROLE = Qt.UserRole + 3
    PATH_ROLE = Qt.UserRole + 4

    def __init__(self, parent=None):
        super(FileModel, self).__init__(parent)
        self.files = []

    def roleNames(self):
        return {
            self.NAME_ROLE: b'name',
            self.TIME_ROLE: b'time',
            self.TRANSFER_ROLE: b'transfer',
            self.PATH_ROLE: b'path'
        }

    def addFiles(self, files, parent=QModelIndex()):
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(files) - 1)
        self.files.extend(files)
        self.endInsertRows()

    def data(self, index, role=NAME_ROLE):
        row = self.files[index.row()]
        if role == self.NAME_ROLE:
            data = row['name']
        if role == self.TIME_ROLE:
            data = row['last_sync_date']
        if role == self.TRANSFER_ROLE:
            data = row['last_transfer'].replace('load', '')
        if role == self.PATH_ROLE:
            data = row['local_path']
        return data

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(count):
            self.files.pop(row)
        self.endRemoveRows()

    def empty(self):
        count = self.rowCount()
        self.removeRows(0, count)

    def rowCount(self, parent=QModelIndex()):
        return len(self.files)


class SystrayView(QQuickView):

    def __init__(self, application, icon):
        super(SystrayView, self).__init__()

        self.application = application
        self.icon = icon
        self.api = WebSystrayApi(application, self)
        self.setColor(QColor.fromRgba64(0, 0, 0, 0))

        self.engine_model = EngineModel()
        self.add_engines(
            list(self.application.manager._engines.values()), init=True)
        self.file_model = FileModel()
        self.setFlags(Qt.FramelessWindowHint | Qt.Popup)

        context = self.rootContext()
        context.setContextProperty('Systray', self)
        context.setContextProperty('EngineModel', self.engine_model)
        context.setContextProperty('FileModel', self.file_model)
        self.load_text()
        self.load_colors()

        self.application.manager.newEngine.connect(self.add_engines)
        self.application.manager.initEngine.connect(self.add_engines)
        self.application.manager.dropEngine.connect(self.remove_engine)
        self.application.manager.updater.updateAvailable.connect(
            self.update_info)

    def add_engines(self, engines, init=False):
        if not engines:
            return

        need_reload = not self.engine_model.rowCount() and not init
        engines = engines if isinstance(engines, list) else [engines]

        self.engine_model.addEngines([{
            'uid': e.uid,
            'type': e.type,
            'server': e.name
        } for e in engines])

        if need_reload:
            self.reload()

    def remove_engine(self, engine):
        self.engine_model.removeEngine(engine.uid)
        if not self.engine_model.rowCount():
            self.reload()

    def load_colors(self):
        colors = {
            'darkBlue': '#1F28BF',
            'nuxeoBlue': '#0066FF',
            'lightBlue': '#00ADED',
            'teal': '#73D2CF',
            'purple': '#8400FF',
            'red': '#D20038',
            'orange': '#FF9E00',
            'mediumGray': '#7F8284',
            'lightGray': '#F5F5F5',
        }

        context = self.rootContext()
        for name, value in colors.items():
            context.setContextProperty(name, value)

    def load_text(self):
        messages = {
            'settingsText': 'SETTINGS',
            'helpText': 'HELP',
            'quitText': 'QUIT',
            'recentlyUpdated': 'RECENTLY_UPDATED',
            'autoUpdateMessage': 'AUTOUPDATE',
            'updateText': 'UPDATE',
            'cancelText': 'DIRECT_EDIT_CONFLICT_CANCEL',
        }

        context = self.rootContext()
        for name, value in messages.items():
            context.setContextProperty(name, Translator.get(value))

    def get_last_files(self, uid):
        files = self.api.get_last_files(uid, 10, '')
        self.file_model.empty()
        self.file_model.addFiles(files)

    def update_info(self, in_context=False):
        status = self.application.manager.updater.last_status
        channel = self.application.manager.updater.nature
        update_version = status[1]

        if status[0] == UPDATE_STATUS_DOWNGRADE_NEEDED:
            update_type = 'downgrade'
            update_message = Translator.get('NOTIF_UPDATE_DOWNGRADE',
                                            {'version': update_version})
        elif status[0] == UPDATE_STATUS_UPDATE_AVAILABLE:
            update_type = 'upgrade'
            update_message = Translator.get('UPGRADE_AVAILABLE',
                                            {'version': update_version})
        if not update_version:
            update_confirm = update_type = update_message = ""
        else:
            update_confirm = Translator.get('CONFIRM_UPDATE_MESSAGE',
                                            {'version': update_version,
                                             'update_channel': channel})
        if in_context:
            context = self.rootContext()
            context.setContextProperty('updateMessage', update_message)
            context.setContextProperty('updateConfirm', update_confirm)
            context.setContextProperty('updateType', update_type)
            context.setContextProperty('updateVersion', update_version)
            context.setContextProperty(
                'autoUpdateValue', self.application.manager.get_auto_update())
        else:
            self.rootObject().updateInfo.emit(
                update_message, update_confirm, update_type, update_version)

    def refresh(self, uid):
        items_count = self.api.get_syncing_items(uid)
        conflicts_count = len(self.api.get_conflicts(uid))
        errors_count = len(self.api.get_errors(uid))

        items_left = ("" if not items_count
                      else Translator.get('SYNCHRONIZATION_ITEMS_LEFT',
                                          {'number': str(items_count)}))
        conflicts = ("" if not conflicts_count
                     else Translator.get(
                         'CONFLICTS_SYSTRAY',
                         {'conflicted_files': str(conflicts_count)}))
        errors = ("" if not errors_count
                  else Translator.get(
                      'ERRORS_SYSTRAY',
                      {'error_files': str(errors_count)}))
        root = self.rootObject()
        root.syncingItems.emit(items_left)
        root.setConflicts.emit(conflicts)
        root.setErrors.emit(errors)

    def set_engine(self, uid):
        self.get_last_files(uid)

    def set_tray_position(self, x, y):
        self.rootObject().setTrayPosition.emit(x, y)

    def reload(self):
        """
        Resize and move the system tray menu accordingly to
        the system tray icon position.
        """

        if not self.icon.application.manager.get_engines():
            height = 280
            self.setSource(QUrl('nxdrive/data/qml/NoEngineSystray.qml'))
            root = self.rootObject()
        else:
            height = 370
            self.update_info(in_context=True)
            self.setSource(QUrl('nxdrive/data/qml/Systray.qml'))
            root = self.rootObject()
            # Connect signals for systray
            root.getLastFiles.connect(self.get_last_files)
            root.openLocal.connect(self.api.open_local)
            root.openMenu.connect(self.api.advanced_systray)
            root.openMetadata.connect(self.api.show_metadata)
            root.openRemote.connect(self.api.open_remote)
            root.showConflicts.connect(self.api.show_conflicts_resolution)
            root.showHelp.connect(self.api.open_help)
            root.refresh.connect(self.refresh)
            root.setEngine.connect(self.set_engine)
            root.suspend.connect(self.api.suspend)
            self.application.manager.updater.updateAvailable.connect(
                self.update_info)
            # When the ListView loads, the engine is not yet set
            # so we fill it "manually"
            self.get_last_files(self.engine_model.engines[0]['uid'])
        # Signals valid for both
        root.hide.connect(self.hide)
        root.quit.connect(self.application.quit)
        root.showSettings.connect(self.api.show_settings)

        geometry = self.geometry()
        icon = self.icon.geometry()

        pos_x = max(0, icon.x() + icon.width() - 300)
        pos_y = icon.y() - height
        if pos_y < 0:
            pos_y = icon.y() + icon.height()
        self.set_tray_position(pos_x, pos_y)
