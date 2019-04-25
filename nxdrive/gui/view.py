# coding: utf-8
from contextlib import suppress
from typing import Any, Dict, List, Tuple, TYPE_CHECKING

from PyQt5.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from ..utils import force_decode

if TYPE_CHECKING:
    from .application import Application  # noqa
    from ..engine.engine import Engine  # noqa

__all__ = ("FileModel", "LanguageModel")


class EngineModel(QAbstractListModel):
    engineChanged = pyqtSignal()
    statusChanged = pyqtSignal(object)
    uiChanged = pyqtSignal()
    authChanged = pyqtSignal()

    UID_ROLE = Qt.UserRole + 1
    TYPE_ROLE = Qt.UserRole + 2
    FOLDER_ROLE = Qt.UserRole + 3
    URL_ROLE = Qt.UserRole + 4
    UI_ROLE = Qt.UserRole + 5
    FORCE_UI_ROLE = Qt.UserRole + 6
    ACCOUNT_ROLE = Qt.UserRole + 7

    def __init__(self, application: "Application", parent: QObject = None) -> None:
        super(EngineModel, self).__init__(parent)
        self.application = application
        self.engines_uid: List[str] = []
        self.names = {
            self.UID_ROLE: b"uid",
            self.TYPE_ROLE: b"type",
            self.FOLDER_ROLE: b"folder",
            self.URL_ROLE: b"server_url",
            self.UI_ROLE: b"wui",
            self.FORCE_UI_ROLE: b"force_ui",
            self.ACCOUNT_ROLE: b"account",
        }
        self.roles = {value: key for key, value in self.names.items()}

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def nameRoles(self) -> Dict[bytes, int]:
        return self.roles

    def addEngine(self, uid: str, parent: QModelIndex = QModelIndex()) -> None:
        if uid in self.engines_uid:
            return
        count = self.rowCount()
        self.beginInsertRows(parent, count, count)
        self.engines_uid.append(uid)
        self.endInsertRows()
        self._connect_engine(self.application.manager._engines[uid])
        self.engineChanged.emit()

    def removeEngine(self, uid: str) -> None:
        with suppress(ValueError):
            idx = self.engines_uid.index(uid)
            self.removeRows(idx, 1)
            self.engineChanged.emit()

    def data(self, index: QModelIndex, role: int = UID_ROLE) -> str:
        index = index.row()
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager._engines[uid]
        return getattr(engine, self.names[role].decode())

    @pyqtSlot(int, str, result=str)
    def get(self, index: int, role: str = "uid") -> str:
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager._engines[uid]
        return getattr(engine, role)

    def removeRows(
        self, row: int, count: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for _ in range(count):
                self.engines_uid.pop(row)
            self.endRemoveRows()
            return True
        except Exception:
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
        engine.uiChanged.connect(self.uiChanged)
        engine.authChanged.connect(self.authChanged)

    def _relay_engine_events(self):
        engine = self.sender()
        self.statusChanged.emit(engine)


class TransferModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = Qt.UserRole + 1
    NAME = Qt.UserRole + 2
    STATUS = Qt.UserRole + 3
    PROGRESS = Qt.UserRole + 4
    TYPE = Qt.UserRole + 5

    def __init__(self, parent: QObject = None) -> None:
        super(TransferModel, self).__init__(parent)
        self.transfers: List[Dict[str, Any]] = []
        self.names = {
            self.ID: b"uid",
            self.NAME: b"name",
            self.STATUS: b"status",
            self.PROGRESS: b"progress",
            self.TYPE: b"transfer_type",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    @pyqtProperty("int", notify=fileChanged)
    def count(self):
        return self.rowCount()

    def rowCount(self, parent: QModelIndex = QModelIndex(), **kwargs: Any) -> int:
        return len(self.transfers)

    def set_transfers(
        self, transfers: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, len(self.transfers) - 1)
        self.transfers.clear()
        self.endRemoveRows()
        self.beginInsertRows(parent, 0, len(transfers) - 1)
        self.transfers.extend(transfers)
        self.fileChanged.emit()
        self.endInsertRows()

    def data(self, index: QModelIndex, role: int = NAME) -> Any:
        row = self.transfers[index.row()]
        if role == self.STATUS:
            return row["status"].name
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.transfers[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(dict)
    def set_progress(self, action: Dict[str, Any]) -> None:
        for i, item in enumerate(self.transfers):
            if item["name"] == action["name"]:
                self.setData(self.createIndex(i, 0), action["progress"], self.PROGRESS)
                break

    def flags(self, index: QModelIndex):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable


class FileModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    DETAILS = Qt.UserRole + 1
    FOLDERISH = Qt.UserRole + 2
    LAST_CONTRIBUTOR = Qt.UserRole + 3
    LAST_ERROR = Qt.UserRole + 4
    LAST_REMOTE_UPDATE = Qt.UserRole + 5
    LAST_SYNC_DATE = Qt.UserRole + 6
    LAST_TRANSFER = Qt.UserRole + 7
    LOCAL_PARENT_PATH = Qt.UserRole + 8
    LOCAL_PATH = Qt.UserRole + 9
    NAME = Qt.UserRole + 10
    REMOTE_NAME = Qt.UserRole + 11
    REMOTE_REF = Qt.UserRole + 12
    STATE = Qt.UserRole + 13

    def __init__(self, parent: QObject = None) -> None:
        super(FileModel, self).__init__(parent)
        self.files: List[Dict[str, Any]] = []
        self.names = {
            self.DETAILS: b"last_error_details",
            self.FOLDERISH: b"folderish",
            self.LAST_CONTRIBUTOR: b"last_contributor",
            self.LAST_ERROR: b"last_error",
            self.LAST_REMOTE_UPDATE: b"last_remote_update",
            self.LAST_SYNC_DATE: b"last_sync_date",
            self.LAST_TRANSFER: b"last_transfer",
            self.LOCAL_PARENT_PATH: b"local_parent_path",
            self.LOCAL_PATH: b"local_path",
            self.NAME: b"name",
            self.REMOTE_NAME: b"remote_name",
            self.REMOTE_REF: b"remote_ref",
            self.STATE: b"state",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

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
        if role == self.LOCAL_PARENT_PATH:
            return str(row["local_parent_path"])
        elif role == self.LOCAL_PATH:
            return str(row["local_path"])
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.files[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(int, int)
    def removeRows(
        self, row: int, count: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for _ in range(count):
                self.files.pop(row)
            self.fileChanged.emit()
            self.endRemoveRows()
            return True
        except Exception:
            return False

    def insertRows(
        self, files: List[Dict[str, Any]], row: int, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginInsertRows(parent, row, row + len(files) - 1)
            for f in files[::-1]:
                self.files.insert(row, f)
            self.fileChanged.emit()
            self.endInsertRows()
            return True
        except Exception:
            return False

    def empty(self) -> None:
        count = self.rowCount()
        self.removeRows(0, count)

    def rowCount(self, parent: QModelIndex = QModelIndex(), **kwargs: Any) -> int:
        return len(self.files)

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()

    def flags(self, index: QModelIndex):
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable


class LanguageModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    TAG_ROLE = Qt.UserRole + 2

    def __init__(self, parent: QObject = None) -> None:
        super(LanguageModel, self).__init__(parent)
        self.languages: List[Tuple[str, str]] = []

    def roleNames(self) -> Dict[int, bytes]:
        return {self.NAME_ROLE: b"name", self.TAG_ROLE: b"tag"}

    def addLanguages(
        self, languages: List[Tuple[str, str]], parent: QModelIndex = QModelIndex()
    ) -> None:
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(languages) - 1)
        self.languages.extend(languages)
        self.endInsertRows()

    def data(self, index: QModelIndex, role: int = TAG_ROLE) -> str:
        row = self.languages[index.row()]
        if role == self.NAME_ROLE:
            return row[1]
        elif role == self.TAG_ROLE:
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
            for _ in range(count):
                self.languages.pop(row)
            self.endRemoveRows()
            return True
        except Exception:
            return False

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.languages)
