# coding: utf-8
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from dateutil.tz import tzlocal
from PyQt5.QtCore import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    Qt,
    pyqtProperty,
    pyqtSignal,
    pyqtSlot,
)

from ..translator import Translator
from ..utils import force_decode, get_date_from_sqlite, sizeof_fmt

if TYPE_CHECKING:
    from .application import Application  # noqa
    from ..engine.engine import Engine  # noqa

__all__ = ("DirectTransferModel", "EngineModel", "FileModel", "LanguageModel")


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
        super().__init__(parent)
        self.application = application
        self.engines_uid: List[str] = []
        self.names = {
            self.UID_ROLE: b"uid",
            self.TYPE_ROLE: b"type",
            self.FOLDER_ROLE: b"folder",
            self.URL_ROLE: b"server_url",
            self.UI_ROLE: b"wui",
            self.FORCE_UI_ROLE: b"force_ui",
            self.ACCOUNT_ROLE: b"remote_user",
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
        self._connect_engine(self.application.manager.engines[uid])
        self.engineChanged.emit()

    def removeEngine(self, uid: str) -> None:
        idx = self.engines_uid.index(uid)
        self.removeRows(idx, 1)
        self.engineChanged.emit()

    def data(self, index: QModelIndex, role: int = UID_ROLE) -> str:
        index = index.row()
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager.engines.get(uid)
        if not engine:
            return ""

        return getattr(engine, self.names[role].decode())

    @pyqtSlot(int, str, result=str)
    def get(self, index: int, role: str = "uid") -> str:
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager.engines.get(uid)
        if not engine:
            return ""

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

    def _relay_engine_events(self) -> None:
        engine = self.sender()
        self.statusChanged.emit(engine)


class TransferModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = Qt.UserRole + 1
    NAME = Qt.UserRole + 2
    STATUS = Qt.UserRole + 3
    PROGRESS = Qt.UserRole + 4
    TYPE = Qt.UserRole + 5
    ENGINE = Qt.UserRole + 6
    IS_DIRECT_EDIT = Qt.UserRole + 7
    FINALIZING = Qt.UserRole + 8
    PROGRESS_METRICS = Qt.UserRole + 9

    def __init__(self, translate: Callable, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.transfers: List[Dict[str, Any]] = []
        self.names = {
            self.ID: b"uid",
            self.NAME: b"name",
            self.STATUS: b"status",
            self.PROGRESS: b"progress",
            self.TYPE: b"transfer_type",
            self.ENGINE: b"engine",
            self.IS_DIRECT_EDIT: b"is_direct_edit",
            self.PROGRESS_METRICS: b"progress_metrics",
            # The is the Verification step for downloads
            # and Linking step for uploads.
            self.FINALIZING: b"finalizing",
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.transfers)

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()

    def set_transfers(
        self, transfers: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.transfers.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(transfers) - 1)
        self.transfers.extend(transfers)
        self.endInsertRows()

        self.fileChanged.emit()

    def get_progress(self, row: Dict[str, Any]) -> str:
        """Return a nicely formatted line to know the transfer progression.
        E.g: 10.0 MiB / 42.0 MiB [24%]
        """
        size = row["filesize"]
        if row["transfer_type"] == "download":
            try:
                progress = row["tmpname"].stat().st_size
            except FileNotFoundError:
                progress = 0
        else:
            progress = size * (row["progress"] or 0.0) / 100

        # Pretty print
        suffix = self.tr("BYTE_ABBREV")
        psize = partial(sizeof_fmt, suffix=suffix)

        percent = int(min(100, progress * 100 / (size or 1)))
        speed = row.get("speed", 0)
        txt = f"{psize(progress)} / {psize(size)} ({percent}%)"
        if speed:
            icon = "↓" if row["transfer_type"] == "download" else "↑"
            txt += f" {icon} {psize(speed)}/s"
        return txt

    def data(self, index: QModelIndex, role: int = NAME) -> Any:
        row = self.transfers[index.row()]
        if role == self.STATUS:
            return row["status"].name
        if role == self.FINALIZING:
            return row.get("finalizing", False)
        if role == self.PROGRESS_METRICS:
            return self.get_progress(row)
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
            if item["name"] != action["name"]:
                continue
            idx = self.createIndex(i, 0)

            if action["action_type"] in ("Linking", "Verification"):
                # Disable the speed to not show the speed at the final step
                item["speed"] = 0
            else:
                item["speed"] = action["speed"]

            self.setData(idx, action["progress"], self.PROGRESS)
            self.setData(idx, action["progress"], self.PROGRESS_METRICS)
            if action["action_type"] in ("Linking", "Verification"):
                self.setData(idx, True, self.FINALIZING)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable


class DirectTransferModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = Qt.UserRole + 1
    NAME = Qt.UserRole + 2
    STATUS = Qt.UserRole + 3
    PROGRESS = Qt.UserRole + 4
    ENGINE = Qt.UserRole + 5
    FINALIZING = Qt.UserRole + 6
    SIZE = Qt.UserRole + 7
    TRANSFERRED = Qt.UserRole + 8
    REMOTE_PARENT_PATH = Qt.UserRole + 9
    REMOTE_PARENT_REF = Qt.UserRole + 10

    def __init__(self, translate: Callable, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.items: List[Dict[str, Any]] = []
        self.names = {
            self.ID: b"uid",
            self.NAME: b"name",
            self.STATUS: b"status",
            self.PROGRESS: b"progress",
            self.ENGINE: b"engine",
            self.SIZE: b"filesize",
            self.FINALIZING: b"finalizing",  # Linking action
            self.TRANSFERRED: b"transferred",
            self.REMOTE_PARENT_PATH: b"remote_parent_path",
            self.REMOTE_PARENT_REF: b"remote_parent_ref",
        }
        # Pretty print
        self.psize = partial(sizeof_fmt, suffix=self.tr("BYTE_ABBREV"))

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.items)

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def set_items(
        self, items: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.items.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(items) - 1)
        self.items.extend(items)
        self.endInsertRows()

        self.fileChanged.emit()

    def data(self, index: QModelIndex, role: int = NAME) -> Any:
        row = self.items[index.row()]
        if role == self.STATUS:
            return row["status"].name
        if role == self.PROGRESS:
            return f"{row['progress']:,.1f}"
        if role == self.FINALIZING:
            return row.get("finalizing", False)
        if role == self.SIZE:
            return self.psize(row["filesize"])
        if role == self.TRANSFERRED:
            return self.psize(row["filesize"] * row["progress"] / 100)
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.items[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(dict)
    def set_progress(self, action: Dict[str, Any]) -> None:
        for i, item in enumerate(self.items):
            if (item["engine"], item["name"]) != (action["engine"], action["name"]):
                continue

            idx = self.createIndex(i, 0)
            self.setData(idx, action["progress"], self.PROGRESS)
            self.setData(idx, action["progress"], self.TRANSFERRED)
            if action["action_type"] == "Linking":
                self.setData(idx, True, self.FINALIZING)


class ActiveSessionModel(QAbstractListModel):
    sessionChanged = pyqtSignal()

    UID = Qt.UserRole + 1
    STATUS = Qt.UserRole + 2
    REMOTE_REF = Qt.UserRole + 3
    REMOTE_PATH = Qt.UserRole + 4
    UPLOADED = Qt.UserRole + 5
    TOTAL = Qt.UserRole + 6
    ENGINE = Qt.UserRole + 7
    CREATED_ON = Qt.UserRole + 8
    COMPLETED_ON = Qt.UserRole + 9
    DESCRIPTION = Qt.UserRole + 10
    PROGRESS = Qt.UserRole + 11

    def __init__(self, translate: Callable, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.sessions: List[Dict[str, Any]] = []
        self.names = {
            self.UID: b"uid",
            self.STATUS: b"status",
            self.REMOTE_REF: b"remote_ref",
            self.REMOTE_PATH: b"remote_path",
            self.UPLOADED: b"uploaded",
            self.TOTAL: b"total",
            self.ENGINE: b"engine",
            self.CREATED_ON: b"created_on",
            self.COMPLETED_ON: b"completed_on",
            self.DESCRIPTION: b"description",
            self.PROGRESS: b"progress",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.sessions)

    def set_sessions(
        self, sessions: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.sessions.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(sessions) - 1)
        self.sessions.extend(sessions)
        self.endInsertRows()
        self.sessionChanged.emit()

    def data(self, index: QModelIndex, role: int = REMOTE_PATH) -> Any:
        row = self.sessions[index.row()]
        if role == self.REMOTE_PATH:
            return str(row["remote_path"])
        elif role == self.STATUS:
            status = row["status"].name
            if status == "DONE":
                status = "COMPLETED"
            return status
        elif role == self.DESCRIPTION:
            description = row["description"]
            if not description:
                description = f"Session {row['uid']}"
            return description
        elif role == self.CREATED_ON:
            label = "STARTED"
            args = []
            datetime = get_date_from_sqlite(row["created_on"])
            if datetime:
                label += "_ON"
                # As date_time is in UTC
                offset = tzlocal().utcoffset(datetime)
                if offset:
                    datetime += offset
                args.append(Translator.format_datetime(datetime))
            return self.tr(label, args)
        elif role == self.COMPLETED_ON:
            label = "COMPLETED" if row["status"].name == "DONE" else "CANCELLED"
            args = []
            datetime = get_date_from_sqlite(row["completed_on"])
            if datetime:
                label += "_ON"
                offset = tzlocal().utcoffset(datetime)
                if offset:
                    datetime += offset
                args.append(Translator.format_datetime(datetime))
            return self.tr(label, args)
        elif role == self.PROGRESS:
            return f"[{row['uploaded']:,} / {row['total']:,}]"
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.sessions[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtProperty("int", notify=sessionChanged)
    def count(self) -> int:
        return self.rowCount()


class CompletedSessionModel(QAbstractListModel):
    sessionChanged = pyqtSignal()

    UID = Qt.UserRole + 1
    STATUS = Qt.UserRole + 2
    REMOTE_REF = Qt.UserRole + 3
    REMOTE_PATH = Qt.UserRole + 4
    UPLOADED = Qt.UserRole + 5
    TOTAL = Qt.UserRole + 6
    ENGINE = Qt.UserRole + 7
    CREATED_ON = Qt.UserRole + 8
    COMPLETED_ON = Qt.UserRole + 9
    DESCRIPTION = Qt.UserRole + 10
    PROGRESS = Qt.UserRole + 11

    def __init__(self, translate: Callable, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.sessions: List[Dict[str, Any]] = []
        self.names = {
            self.UID: b"uid",
            self.STATUS: b"status",
            self.REMOTE_REF: b"remote_ref",
            self.REMOTE_PATH: b"remote_path",
            self.UPLOADED: b"uploaded",
            self.TOTAL: b"total",
            self.ENGINE: b"engine",
            self.CREATED_ON: b"created_on",
            self.COMPLETED_ON: b"completed_on",
            self.DESCRIPTION: b"description",
            self.PROGRESS: b"progress",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.sessions)

    def set_sessions(
        self, sessions: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.sessions.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(sessions) - 1)
        self.sessions.extend(sessions)
        self.endInsertRows()
        self.sessionChanged.emit()

    def data(self, index: QModelIndex, role: int = REMOTE_PATH) -> Any:
        row = self.sessions[index.row()]
        if role == self.REMOTE_PATH:
            return str(row["remote_path"])
        elif role == self.STATUS:
            status = row["status"].name
            if status == "DONE":
                status = "COMPLETED"
            return status
        elif role == self.DESCRIPTION:
            description = row["description"]
            if not description:
                description = f"Session {row['uid']}"
            return description
        elif role == self.CREATED_ON:
            label = "STARTED"
            args = []
            datetime = get_date_from_sqlite(row["created_on"])
            if datetime:
                label += "_ON"
                # As date_time is in UTC
                offset = tzlocal().utcoffset(datetime)
                if offset:
                    datetime += offset
                args.append(Translator.format_datetime(datetime))
            return self.tr(label, args)
        elif role == self.COMPLETED_ON:
            label = "COMPLETED" if row["status"].name == "DONE" else "CANCELLED"
            args = []
            datetime = get_date_from_sqlite(row["completed_on"])
            if datetime:
                label += "_ON"
                offset = tzlocal().utcoffset(datetime)
                if offset:
                    datetime += offset
                args.append(Translator.format_datetime(datetime))
            return self.tr(label, args)
        elif role == self.PROGRESS:
            return f"[{row['uploaded']:,} / {row['planned_items']:,}]"
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.sessions[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtProperty("int", notify=sessionChanged)
    def count(self) -> int:
        return self.rowCount()


class FileModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = Qt.UserRole + 1
    DETAILS = Qt.UserRole + 2
    FOLDERISH = Qt.UserRole + 3
    LAST_CONTRIBUTOR = Qt.UserRole + 4
    LAST_ERROR = Qt.UserRole + 5
    LAST_REMOTE_UPDATE = Qt.UserRole + 6
    LAST_SYNC_DATE = Qt.UserRole + 7
    LAST_TRANSFER = Qt.UserRole + 8
    LOCAL_PARENT_PATH = Qt.UserRole + 9
    LOCAL_PATH = Qt.UserRole + 10
    NAME = Qt.UserRole + 11
    REMOTE_NAME = Qt.UserRole + 12
    REMOTE_REF = Qt.UserRole + 13
    STATE = Qt.UserRole + 14
    SIZE = Qt.UserRole + 15

    def __init__(self, translate: Callable, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.files: List[Dict[str, Any]] = []
        self.names = {
            self.ID: b"id",
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
            self.SIZE: b"size",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self.files)

    def add_files(
        self, files: List[Dict[str, Any]], parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.files.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(files) - 1)
        self.files.extend(files)
        self.endInsertRows()
        self.fileChanged.emit()

    def data(self, index: QModelIndex, role: int = NAME) -> Any:
        row = self.files[index.row()]
        if role == self.LOCAL_PARENT_PATH:
            return str(row["local_parent_path"])
        elif role == self.LOCAL_PATH:
            return str(row["local_path"])
        elif role == self.SIZE:
            suffix = self.tr("BYTE_ABBREV")
            return f"({sizeof_fmt(row['size'], suffix=suffix)})"
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.files[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable


class LanguageModel(QAbstractListModel):
    NAME_ROLE = Qt.UserRole + 1
    TAG_ROLE = Qt.UserRole + 2

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
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
