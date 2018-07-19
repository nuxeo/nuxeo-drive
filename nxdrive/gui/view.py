# coding: utf-8
from contextlib import suppress
from typing import Any, Dict, List, Tuple, Union

from PyQt5.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)
from PyQt5.QtGui import QIcon
from PyQt5.QtQuick import QQuickView

from ..translator import Translator

__all__ = ("FileModel", "LanguageModel", "NuxeoView")


class EngineModel(QAbstractListModel):
    engineChanged = pyqtSignal()
    statusChanged = pyqtSignal(object)

    UID_ROLE = Qt.UserRole + 1
    TYPE_ROLE = Qt.UserRole + 2
    SERVER_ROLE = Qt.UserRole + 3
    FOLDER_ROLE = Qt.UserRole + 4
    USERNAME_ROLE = Qt.UserRole + 5
    URL_ROLE = Qt.UserRole + 6
    UI_ROLE = Qt.UserRole + 7
    FORCE_UI_ROLE = Qt.UserRole + 8

    def __init__(self, parent: QObject = None) -> None:
        super(EngineModel, self).__init__(parent)
        self.engines_uid = []
        self.engines = {}

    def roleNames(self) -> Dict[int, bytes]:
        return {
            self.UID_ROLE: b"uid",
            self.TYPE_ROLE: b"type",
            self.SERVER_ROLE: b"server",
            self.FOLDER_ROLE: b"folder",
            self.USERNAME_ROLE: b"username",
            self.URL_ROLE: b"url",
            self.UI_ROLE: b"ui",
            self.FORCE_UI_ROLE: b"forceUi",
        }

    def nameRoles(self) -> Dict[bytes, int]:
        return {
            b"uid": self.UID_ROLE,
            b"type": self.TYPE_ROLE,
            b"server": self.SERVER_ROLE,
            b"folder": self.FOLDER_ROLE,
            b"username": self.USERNAME_ROLE,
            b"url": self.URL_ROLE,
            b"ui": self.UI_ROLE,
            b"forceUi": self.FORCE_UI_ROLE,
        }

    def addEngine(self, engine: "Engine", parent: QModelIndex = QModelIndex()) -> None:
        uid = engine.uid
        if uid in self.engines_uid:
            return
        count = self.rowCount()
        self.beginInsertRows(parent, count, count)
        self.engines_uid.append(uid)
        self.engines[uid] = engine
        self.endInsertRows()
        self._connect_engine(engine)
        self.engineChanged.emit()

    def removeEngine(self, uid: str) -> None:
        with suppress(ValueError):
            idx = self.engines_uid.index(uid)
            self.removeRows(idx, 1)
            self.engineChanged.emit()

    def data(self, index: QModelIndex, role: int = UID_ROLE) -> Any:
        index = index.row()
        if index < 0 or index >= self.count:
            return None
        uid = self.engines_uid[index]
        row = self.engines[uid]
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

    @pyqtSlot(int, str, result=str)
    def get(self, index: int, role: str = "uid") -> str:
        if index < 0 or index >= self.count:
            return ""
        uid = self.engines_uid[index]
        row = self.engines[uid]
        if role == "uid":
            return row.uid
        if role == "type":
            return row.type
        if role == "server":
            return row.name
        if role == "folder":
            return row.local_folder
        if role == "username":
            return row._remote_user
        if role == "url":
            return row._server_url
        if role == "ui":
            return row._ui
        if role == "forceUi":
            return row._force_ui or row._ui
        return ""

    def removeRows(
        self, row: int, count: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for i in range(count):
                uid = self.engines_uid.pop(row)
                del self.engines[uid]
            self.endRemoveRows()
            return True
        except:
            return False

    def empty(self) -> None:
        count = self.rowCount()
        self.removeRows(0, count)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.engines_uid)

    @pyqtProperty("int", notify=engineChanged)
    def count(self) -> int:
        return self.rowCount()

    def _connect_engine(self, engine: "Engine") -> None:
        engine.invalidAuthentication.connect(self._relay_engine_events)
        engine.newConflict.connect(self._relay_engine_events)
        engine.newError.connect(self._relay_engine_events)
        engine.syncCompleted.connect(self._relay_engine_events)
        engine.syncResumed.connect(self._relay_engine_events)
        engine.syncStarted.connect(self._relay_engine_events)
        engine.syncSuspended.connect(self._relay_engine_events)

    def _relay_engine_events(self):
        engine = self.sender()
        self.statusChanged.emit(engine)


class FileModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = Qt.UserRole + 1
    DETAILS = Qt.UserRole + 2
    FOLDERISH = Qt.UserRole + 3
    LAST_CONTRIBUTOR = Qt.UserRole + 4
    LAST_ERROR = Qt.UserRole + 5
    LAST_LOCAL_UDPATE = Qt.UserRole + 6
    LAST_REMOTE_UDPATE = Qt.UserRole + 7
    LAST_SYNC_DATE = Qt.UserRole + 8
    LAST_TRANSFER = Qt.UserRole + 9
    LOCAL_PARENT_PATH = Qt.UserRole + 10
    LOCAL_PATH = Qt.UserRole + 11
    NAME = Qt.UserRole + 12
    REMOTE_CAN_RENAME = Qt.UserRole + 13
    REMOTE_CAN_UPDATE = Qt.UserRole + 14
    REMOTE_NAME = Qt.UserRole + 15
    REMOTE_REF = Qt.UserRole + 16
    STATE = Qt.UserRole + 17

    def __init__(self, parent: QObject = None) -> None:
        super(FileModel, self).__init__(parent)
        self.files = []

    def roleNames(self) -> Dict[int, bytes]:
        return {
            self.ID: b"id",
            self.DETAILS: b"details",
            self.FOLDERISH: b"folderish",
            self.LAST_CONTRIBUTOR: b"last_contributor",
            self.LAST_ERROR: b"last_error",
            self.LAST_LOCAL_UDPATE: b"last_local_update",
            self.LAST_REMOTE_UDPATE: b"last_remote_update",
            self.LAST_SYNC_DATE: b"last_sync_date",
            self.LAST_TRANSFER: b"last_transfer",
            self.LOCAL_PARENT_PATH: b"local_parent_path",
            self.LOCAL_PATH: b"local_path",
            self.NAME: b"name",
            self.REMOTE_CAN_RENAME: b"remote_can_rename",
            self.REMOTE_CAN_UPDATE: b"remote_can_update",
            self.REMOTE_NAME: b"remote_name",
            self.REMOTE_REF: b"remote_ref",
            self.STATE: b"state",
        }

    def addFiles(
        self, files: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(files) - 1)
        self.files.extend(files)
        self.fileChanged.emit()
        self.endInsertRows()

    def data(self, index: QModelIndex, role: int = NAME) -> Any:
        row = self.files[index.row()]
        if role == self.ID:
            return row["id"]
        if role == self.DETAILS:
            return row["details"]
        if role == self.FOLDERISH:
            return row["folderish"]
        if role == self.LAST_CONTRIBUTOR:
            return row["last_contributor"]
        if role == self.LAST_ERROR:
            return row["last_error"]
        if role == self.LAST_LOCAL_UDPATE:
            return row["last_local_update"]
        if role == self.LAST_REMOTE_UDPATE:
            return row["last_remote_update"]
        if role == self.LAST_SYNC_DATE:
            return row["last_sync_date"]
        if role == self.LAST_TRANSFER:
            return row["last_transfer"].replace("load", "")
        if role == self.LOCAL_PARENT_PATH:
            return row["local_parent_path"]
        if role == self.LOCAL_PATH:
            return row["local_path"]
        if role == self.NAME:
            return row["name"]
        if role == self.REMOTE_CAN_RENAME:
            return row["remote_can_rename"]
        if role == self.REMOTE_CAN_UPDATE:
            return row["remote_can_update"]
        if role == self.REMOTE_NAME:
            return row["remote_name"]
        if role == self.REMOTE_REF:
            return row["remote_ref"]
        if role == self.STATE:
            return row["state"]
        return ""

    @pyqtSlot(int, int)
    def removeRows(
        self, row: int, count: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for i in range(count):
                self.files.pop(row)
            self.fileChanged.emit()
            self.endRemoveRows()
            return True
        except:
            return False

    def empty(self) -> None:
        count = self.rowCount()
        self.removeRows(0, count)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.files)

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()


class LanguageModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    TAG_ROLE = Qt.UserRole + 2

    def __init__(self, parent: QObject = None) -> None:
        super(LanguageModel, self).__init__(parent)
        self.languages = []

    def roleNames(self) -> Dict[int, bytes]:
        return {self.NAME_ROLE: b"name", self.TAG_ROLE: b"tag"}

    def addLanguages(
        self, languages: Tuple[str, str], parent: QModelIndex = QModelIndex()
    ) -> None:
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(languages) - 1)
        self.languages.extend(languages)
        self.endInsertRows()

    def data(self, index: QModelIndex, role: int = TAG_ROLE) -> str:
        row = self.languages[index.row()]
        if role == self.NAME_ROLE:
            return row[1]
        if role == self.TAG_ROLE:
            return row[0]
        return ""

    @pyqtSlot(int, result=str)
    def getTag(self, index: int) -> str:
        return self.languages[index][0]

    @pyqtSlot(int, result=str)
    def getName(self, index: int) -> str:
        return self.languages[index][1]

    def removeRows(
        self, row: int, count: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for i in range(count):
                self.languages.pop(row)
            self.endRemoveRows()
            return True
        except:
            return False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.languages)


class NuxeoView(QQuickView):
    def __init__(self, application: "Application", api: "QMLDriveApi") -> None:
        super().__init__()
        self.application = application
        self.api = api
        self.setIcon(QIcon(application.get_window_icon()))

        self.engine_model = EngineModel()

        self.add_engines(list(self.application.manager._engines.values()))
        context = self.rootContext()
        context.setContextProperty("EngineModel", self.engine_model)
        context.setContextProperty("tl", Translator._singleton)
        context.setContextProperty("api", self.api)
        context.setContextProperty("application", self.application)
        context.setContextProperty("manager", self.application.manager)
        context.setContextProperty("ratio", self.application.ratio)

    def init(self) -> None:
        self.load_colors()

        self.application.manager.newEngine.connect(self.add_engines)
        self.application.manager.initEngine.connect(self.add_engines)
        self.application.manager.dropEngine.connect(self.remove_engine)

    def reload(self) -> None:
        self.init()

    def load_colors(self) -> None:
        colors = {
            "darkBlue": "#1F28BF",
            "nuxeoBlue": "#0066FF",
            "lightBlue": "#00ADED",
            "teal": "#73D2CF",
            "purple": "#8400FF",
            "red": "#C02828",
            "orange": "#FF9E00",
            "darkGray": "#495055",
            "mediumGray": "#7F8284",
            "lightGray": "#BCBFBF",
            "lighterGray": "#F5F5F5",
        }

        context = self.rootContext()
        for name, value in colors.items():
            context.setContextProperty(name, value)

    def add_engines(self, engines: Union["Engine", List["Engine"]]) -> None:
        if not engines:
            return

        engines = engines if isinstance(engines, list) else [engines]
        for engine in engines:
            self.engine_model.addEngine(engine)

    def remove_engine(self, uid: str) -> None:
        self.engine_model.removeEngine(uid)
