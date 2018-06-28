# coding: utf-8
from PyQt5.QtCore import pyqtProperty, pyqtSignal, pyqtSlot, QAbstractListModel, QModelIndex, Qt
from PyQt5.QtQuick import QQuickView

from .translator import Translator


class EngineModel(QAbstractListModel):
    engineChanged = pyqtSignal()

    UID_ROLE = Qt.UserRole + 1
    TYPE_ROLE = Qt.UserRole + 2
    SERVER_ROLE = Qt.UserRole + 3
    FOLDER_ROLE = Qt.UserRole + 4
    USERNAME_ROLE = Qt.UserRole + 5
    URL_ROLE = Qt.UserRole + 6
    UI_ROLE = Qt.UserRole + 7
    FORCE_UI_ROLE = Qt.UserRole + 8

    def __init__(self, parent=None):
        super(EngineModel, self).__init__(parent)
        self.engines = []

    def roleNames(self):
        return {
            self.UID_ROLE: b'uid',
            self.TYPE_ROLE: b'type',
            self.SERVER_ROLE: b'server',
            self.FOLDER_ROLE: b'folder',
            self.USERNAME_ROLE: b'username',
            self.URL_ROLE: b'url',
            self.UI_ROLE: b'ui',
            self.FORCE_UI_ROLE: b'forceUi',
        }

    def addEngines(self, engines, parent=QModelIndex()):
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(engines) - 1)
        self.engines.extend(engines)
        self.endInsertRows()
        self.engineChanged.emit()

    def removeEngine(self, uid):
        for idx, engine in enumerate(self.engines):
            if engine.uid == uid:
                self.removeRows(idx, 1)
                self.engineChanged.emit()
                break

    def data(self, index, role=UID_ROLE):
        row = self.engines[index.row()]
        if role == self.UID_ROLE:
            return row.uid
        if role == self.TYPE_ROLE:
            return row.type
        if role == self.SERVER_ROLE:
            return row.name
        if role == self.FOLDER_ROLE:
            return row.local_folder
        if role == self.USERNAME_ROLE:
            return row._remote_user
        if role == self.URL_ROLE:
            return row._server_url
        if role == self.UI_ROLE:
            return row._ui
        if role == self.FORCE_UI_ROLE:
            return row._force_ui or row._ui
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

    @pyqtProperty('int', notify=engineChanged)
    def count(self):
        return self.rowCount()


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
            self.PATH_ROLE: b'path',
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


class LanguageModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    TAG_ROLE = Qt.UserRole + 2

    def __init__(self, parent=None):
        super(LanguageModel, self).__init__(parent)
        self.languages = []

    def roleNames(self):
        return {
            self.NAME_ROLE: b'name',
            self.TAG_ROLE: b'tag',
        }

    def addLanguages(self, languages, parent=QModelIndex()):
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(languages) - 1)
        self.languages.extend(languages)
        self.endInsertRows()

    def data(self, index, role=TAG_ROLE):
        row = self.languages[index.row()]
        data = ''
        if role == self.NAME_ROLE:
            data = row[1]
        if role == self.TAG_ROLE:
            data = row[0]
        return data

    @pyqtSlot(int, result=str)
    def getTag(self, index):
        return self.languages[index][0]

    def removeRows(self, row, count, parent=QModelIndex()):
        self.beginRemoveRows(parent, row, row + count - 1)
        for i in range(count):
            self.languages.pop(row)
        self.endRemoveRows()

    def rowCount(self, parent=QModelIndex()):
        return len(self.languages)


class NuxeoView(QQuickView):

    def __init__(self, application, api):
        super(NuxeoView, self).__init__()
        self.application = application
        self.api = api

        self.engine_model = EngineModel()
        self.add_engines(
            list(self.application.manager._engines.values()))
        context = self.rootContext()
        context.setContextProperty('EngineModel', self.engine_model)
        context.setContextProperty('tl', Translator._singleton)
        context.setContextProperty('api', self.api)
        context.setContextProperty('application', self.application)
        context.setContextProperty('manager', self.application.manager)

    def init(self):
        self.load_colors()

        self.application.manager.newEngine.connect(self.add_engines)
        self.application.manager.initEngine.connect(self.add_engines)
        self.application.manager.dropEngine.connect(self.remove_engine)

    def reload(self):
        self.init()

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

    def add_engines(self, engines):
        if not engines:
            return
        engines = engines if isinstance(engines, list) else [engines]
        self.engine_model.addEngines(engines)


    def remove_engine(self, uid):
        self.engine_model.removeEngine(uid)
