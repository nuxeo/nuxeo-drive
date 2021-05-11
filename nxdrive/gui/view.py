from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from dateutil.tz import tzlocal

from ..constants import DT_ACTIVE_SESSIONS_MAX_ITEMS, DT_MONITORING_MAX_ITEMS
from ..qt import constants as qt
from ..qt.imports import (
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
    uiChanged = pyqtSignal(str)
    authChanged = pyqtSignal(str)

    UID_ROLE = qt.UserRole + 1
    TYPE_ROLE = qt.UserRole + 2
    FOLDER_ROLE = qt.UserRole + 3
    URL_ROLE = qt.UserRole + 4
    UI_ROLE = qt.UserRole + 5
    FORCE_UI_ROLE = qt.UserRole + 6
    ACCOUNT_ROLE = qt.UserRole + 7

    def __init__(
        self, application: "Application", /, *, parent: QObject = None
    ) -> None:
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

    def addEngine(self, uid: str, /, *, parent: QModelIndex = QModelIndex()) -> None:
        if uid in self.engines_uid:
            return
        count = self.rowCount()
        self.beginInsertRows(parent, count, count)
        self.engines_uid.append(uid)
        self.endInsertRows()
        self._connect_engine(self.application.manager.engines[uid])
        self.engineChanged.emit()

    def removeEngine(self, uid: str, /) -> None:
        idx = self.engines_uid.index(uid)
        self.removeRows(idx, 1)
        self.engineChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> str:
        index = index.row()
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager.engines.get(uid)
        if not engine:
            return ""

        return getattr(engine, self.names[role].decode())

    @pyqtSlot(int, str, result=str)
    def get(self, index: int, role: str = "uid", /) -> str:
        if index < 0 or index >= self.count:
            return ""

        uid = self.engines_uid[index]
        engine = self.application.manager.engines.get(uid)
        if not engine:
            return ""

        return getattr(engine, role)

    def removeRows(
        self, row: int, count: int, /, *, parent: QModelIndex = QModelIndex()
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

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
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

    ID = qt.UserRole + 1
    NAME = qt.UserRole + 2
    STATUS = qt.UserRole + 3
    PROGRESS = qt.UserRole + 4
    TYPE = qt.UserRole + 5
    ENGINE = qt.UserRole + 6
    IS_DIRECT_EDIT = qt.UserRole + 7
    FINALIZING = qt.UserRole + 8
    PROGRESS_METRICS = qt.UserRole + 9

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
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

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.transfers)

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()

    def set_transfers(
        self, transfers: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.transfers.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(transfers) - 1)
        self.transfers.extend(transfers)
        self.endInsertRows()

        self.fileChanged.emit()

    def get_progress(self, row: Dict[str, Any], /) -> str:
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

    def data(self, index: QModelIndex, role: int, /) -> Any:
        row = self.transfers[index.row()]
        if role == self.STATUS:
            return row["status"].name
        if role == self.FINALIZING:
            return row.get("finalizing", False)
        if role == self.PROGRESS_METRICS:
            return self.get_progress(row)
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.transfers[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(dict)
    def set_progress(self, action: Dict[str, Any], /) -> None:
        for i, item in enumerate(self.transfers):
            if item["name"] != action["name"]:
                continue
            idx = self.createIndex(i, 0)

            if action["action_type"] in ("Linking", "Verification"):
                # Disable the speed to not show the speed at the final step
                item["speed"] = 0
            else:
                item["speed"] = action["speed"]

            self.setData(idx, action["progress"], role=self.PROGRESS)
            self.setData(idx, action["progress"], role=self.PROGRESS_METRICS)
            if action["action_type"] in ("Linking", "Verification"):
                self.setData(idx, True, role=self.FINALIZING)

    def flags(self, index: QModelIndex, /) -> Qt.ItemFlags:
        return qt.ItemIsEditable | qt.ItemIsEnabled | qt.ItemIsSelectable


class DirectTransferModel(QAbstractListModel):
    fileChanged = pyqtSignal()

    ID = qt.UserRole + 1
    NAME = qt.UserRole + 2
    STATUS = qt.UserRole + 3
    PROGRESS = qt.UserRole + 4
    ENGINE = qt.UserRole + 5
    FINALIZING = qt.UserRole + 6
    SIZE = qt.UserRole + 7
    TRANSFERRED = qt.UserRole + 8
    REMOTE_PARENT_PATH = qt.UserRole + 9
    REMOTE_PARENT_REF = qt.UserRole + 10
    SHADOW = qt.UserRole + 11  # Tell the interface if the row should be visible or not
    DOC_PAIR = qt.UserRole + 12

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
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
            self.SHADOW: b"shadow",
            self.DOC_PAIR: b"doc_pair",
        }
        # Pretty print
        self.psize = partial(sizeof_fmt, suffix=self.tr("BYTE_ABBREV"))
        self.shadow_item: Dict[str, Any] = {}

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.items)

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def set_items(
        self, items: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        if items and not self.shadow_item:
            # Copy the first element from items and use it as shadow_item
            self.shadow_item = items[0].copy()
            self.shadow_item["shadow"] = True
            self.shadow_item["finalizing"] = False

        # Create the items list with real datas from items.
        for n_item in items:
            self.add_item(parent, n_item)

        # Add shadow_items to complete items list up to limit
        while len(self.items) < DT_MONITORING_MAX_ITEMS:
            self.add_item(parent, self.shadow_item)

        self.fileChanged.emit()

    def update_items(
        self,
        updated_items: List[Dict[str, Any]],
        /,
        *,
        parent: QModelIndex = QModelIndex(),
    ) -> None:
        """Update items with *updated_items*."""
        # Edit the first rows of the list with real datas from updated_items.
        for row, n_item in enumerate(updated_items):
            self.edit_item(row, n_item)

        # Use the shadow_item for the rest of the list if updated_items is too short.
        for x in range(len(updated_items), len(self.items)):
            self.edit_item(x, self.shadow_item)

        self.fileChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
        row = self.items[index.row()]
        if role == self.STATUS:
            return row["status"].name
        if role == self.PROGRESS:
            return f"{row['progress']:,.1f}"
        if role == self.FINALIZING:
            return row.get("finalizing", False)
        if role == self.SHADOW:
            return row.get("shadow", False)
        if role == self.SIZE:
            return self.psize(row["filesize"])
        if role == self.TRANSFERRED:
            return self.psize(row["filesize"] * row["progress"] / 100)
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.items[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(dict)
    def set_progress(self, action: Dict[str, Any], /) -> None:
        for i, item in enumerate(self.items):
            if (
                item["engine"] != action["engine"]
                or item["doc_pair"] != action["doc_pair"]
            ):

                continue
            idx = self.createIndex(i, 0)
            self.setData(idx, action["progress"], role=self.PROGRESS)
            self.setData(idx, action["progress"], role=self.TRANSFERRED)
            if action["action_type"] == "Linking":
                self.setData(idx, True, role=self.FINALIZING)

    def add_item(self, parent: QModelIndex, n_item: Dict[str, Any], /) -> None:
        """Add an item to existing list."""
        self.beginInsertRows(parent, self.rowCount(), self.rowCount())
        self.items.append(n_item)
        self.endInsertRows()

    def edit_item(self, row: int, n_item: Dict[str, Any], /) -> None:
        """Replace an existing item with *n_item*."""
        idx = self.index(row, 0)
        if "finalizing" not in n_item:
            n_item["finalizing"] = False
        self.items[row] = n_item
        self.dataChanged.emit(idx, idx, self.roleNames())


class ActiveSessionModel(QAbstractListModel):
    sessionChanged = pyqtSignal()

    UID = qt.UserRole + 1
    STATUS = qt.UserRole + 2
    REMOTE_REF = qt.UserRole + 3
    REMOTE_PATH = qt.UserRole + 4
    UPLOADED = qt.UserRole + 5
    TOTAL = qt.UserRole + 6
    ENGINE = qt.UserRole + 7
    CREATED_ON = qt.UserRole + 8
    COMPLETED_ON = qt.UserRole + 9
    DESCRIPTION = qt.UserRole + 10
    PROGRESS = qt.UserRole + 11
    SHADOW = qt.UserRole + 12  # Tell the interface if the row should be visible or not

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
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
            self.SHADOW: b"shadow",
        }
        self.shadow_session: Dict[str, Any] = {}

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.sessions)

    def row_count_no_shadow(self, *, parent: QModelIndex = QModelIndex()) -> int:
        return len([session for session in self.sessions if "shadow" not in session])

    def set_sessions(
        self, sessions: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        if sessions and not self.shadow_session:
            # Copy the first element from sessions and use it as shadow_session
            self.shadow_session = sessions[0].copy()
            self.shadow_session["shadow"] = True

        # Create the sessions list with real datas from sessions.
        for n_session in sessions:
            self.add_session(parent, n_session)

        # Add shadow_items to complete sessions list up to limit
        while len(self.sessions) < DT_ACTIVE_SESSIONS_MAX_ITEMS:
            self.add_session(parent, self.shadow_session)

        self.sessionChanged.emit()

    def update_sessions(
        self,
        updated_sessions: List[Dict[str, Any]],
        /,
        *,
        parent: QModelIndex = QModelIndex(),
    ) -> None:
        """Update sessions with *updated_sessions*."""
        # Edit the first rows of the list with real datas from updated_sessions.
        for row, n_session in enumerate(updated_sessions):
            self.edit_session(row, n_session)

        # Use the shadow_item for the rest of the list if updated_items is too short.
        for x in range(len(updated_sessions), len(self.sessions)):
            self.edit_session(x, self.shadow_session)

        self.sessionChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
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
            return self.tr(label, values=args)
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
            return self.tr(label, values=args)
        elif role == self.PROGRESS:
            return f"[{row['uploaded']:,} / {row['total']:,}]"
        elif role == self.SHADOW:
            return row.get("shadow", False)
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.sessions[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    def add_session(self, parent: QModelIndex, n_session: Dict[str, Any], /) -> None:
        """Add a session to existing list."""
        self.beginInsertRows(parent, self.rowCount(), self.rowCount())
        self.sessions.append(n_session)
        self.endInsertRows()

    def edit_session(self, row: int, n_session: Dict[str, Any], /) -> None:
        """Replace an existing session with *n_session*."""
        idx = self.index(row, 0)
        self.sessions[row] = n_session
        self.dataChanged.emit(idx, idx, self.roleNames())

    @pyqtProperty("int", notify=sessionChanged)
    def count(self) -> int:
        return self.rowCount()

    @pyqtProperty("int", notify=sessionChanged)
    def count_no_shadow(self) -> int:
        return self.row_count_no_shadow()

    @pyqtProperty("bool", notify=sessionChanged)
    def is_full(self) -> bool:
        return self.row_count_no_shadow() >= DT_ACTIVE_SESSIONS_MAX_ITEMS


class CompletedSessionModel(QAbstractListModel):
    sessionChanged = pyqtSignal()

    UID = qt.UserRole + 1
    STATUS = qt.UserRole + 2
    REMOTE_REF = qt.UserRole + 3
    REMOTE_PATH = qt.UserRole + 4
    UPLOADED = qt.UserRole + 5
    TOTAL = qt.UserRole + 6
    ENGINE = qt.UserRole + 7
    CREATED_ON = qt.UserRole + 8
    COMPLETED_ON = qt.UserRole + 9
    DESCRIPTION = qt.UserRole + 10
    PROGRESS = qt.UserRole + 11
    SHADOW = qt.UserRole + 12
    CSV_PATH = qt.UserRole + 13

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
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
            self.SHADOW: b"shadow",
            self.CSV_PATH: b"csv_path",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.sessions)

    def set_sessions(
        self, sessions: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.sessions.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(sessions) - 1)
        self.sessions.extend(sessions)
        self.endInsertRows()
        self.sessionChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
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
            return self.tr(label, values=args)
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
            return self.tr(label, values=args)
        elif role == self.PROGRESS:
            return f"[{row['uploaded']:,} / {row['planned_items']:,}]"
        elif role == self.SHADOW:
            return False  # User can't add or remove completed sessions so no need to use the shadow mechanism
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
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

    ID = qt.UserRole + 1
    DETAILS = qt.UserRole + 2
    FOLDERISH = qt.UserRole + 3
    LAST_CONTRIBUTOR = qt.UserRole + 4
    LAST_ERROR = qt.UserRole + 5
    LAST_REMOTE_UPDATE = qt.UserRole + 6
    LAST_SYNC_DATE = qt.UserRole + 7
    LAST_TRANSFER = qt.UserRole + 8
    LOCAL_PARENT_PATH = qt.UserRole + 9
    LOCAL_PATH = qt.UserRole + 10
    NAME = qt.UserRole + 11
    REMOTE_NAME = qt.UserRole + 12
    REMOTE_REF = qt.UserRole + 13
    STATE = qt.UserRole + 14
    SIZE = qt.UserRole + 15

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
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

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.files)

    def add_files(
        self, files: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        self.beginRemoveRows(parent, 0, self.rowCount() - 1)
        self.files.clear()
        self.endRemoveRows()

        self.beginInsertRows(parent, 0, len(files) - 1)
        self.files.extend(files)
        self.endInsertRows()
        self.fileChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
        row = self.files[index.row()]
        if role == self.LOCAL_PARENT_PATH:
            return str(row["local_parent_path"])
        elif role == self.LOCAL_PATH:
            return str(row["local_path"])
        elif role == self.SIZE:
            suffix = self.tr("BYTE_ABBREV")
            return f"({sizeof_fmt(row['size'], suffix=suffix)})"
        return row[self.names[role].decode()]

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None:
            return
        key = force_decode(self.roleNames()[role])
        self.files[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtProperty("int", notify=fileChanged)
    def count(self) -> int:
        return self.rowCount()

    def flags(self, index: QModelIndex, /) -> Qt.ItemFlags:
        return qt.ItemIsEditable | qt.ItemIsEnabled | qt.ItemIsSelectable


class LanguageModel(QAbstractListModel):
    NAME_ROLE = qt.UserRole + 1
    TAG_ROLE = qt.UserRole + 2

    def __init__(self, *, parent: QObject = None) -> None:
        super().__init__(parent)
        self.languages: List[Tuple[str, str]] = []

    def roleNames(self) -> Dict[int, bytes]:
        return {self.NAME_ROLE: b"name", self.TAG_ROLE: b"tag"}

    def addLanguages(
        self,
        languages: List[Tuple[str, str]],
        /,
        *,
        parent: QModelIndex = QModelIndex(),
    ) -> None:
        count = self.rowCount()
        self.beginInsertRows(parent, count, count + len(languages) - 1)
        self.languages.extend(languages)
        self.endInsertRows()

    def data(self, index: QModelIndex, role: int, /) -> str:
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
        self, row: int, count: int, /, *, parent: QModelIndex = QModelIndex()
    ) -> bool:
        try:
            self.beginRemoveRows(parent, row, row + count - 1)
            for _ in range(count):
                self.languages.pop(row)
            self.endRemoveRows()
            return True
        except Exception:
            return False

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.languages)


class FeatureModel(QObject):

    stateChanged = pyqtSignal()

    def __init__(self, enabled: bool, /, *, restart_needed: bool = False) -> None:
        super().__init__()
        self._enabled = enabled
        self._restart_needed = restart_needed

    @pyqtProperty(bool, notify=stateChanged)
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter  # type: ignore
    # See https://github.com/python/mypy/issues/9911
    def enabled(self, enabled: bool) -> None:
        self._enabled = enabled
        self.stateChanged.emit()

    @property
    def restart_needed(self) -> bool:
        return self._restart_needed
