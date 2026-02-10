from datetime import date, datetime
from functools import partial
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Tuple

from dateutil.tz import tzlocal

from ..constants import DT_ACTIVE_SESSIONS_MAX_ITEMS, DT_MONITORING_MAX_ITEMS
from ..options import Options
from ..qt import constants as qt
from ..qt.imports import (
    QAbstractListModel,
    QModelIndex,
    QObject,
    QStandardItem,
    QStandardItemModel,
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

__all__ = (
    "ActiveDirectDownloadModel",
    "ActiveSessionModel",
    "CompletedDirectDownloadModel",
    "CompletedSessionModel",
    "DirectDownloadMonitoringModel",
    "DirectTransferModel",
    "EngineModel",
    "FeatureModel",
    "FileModel",
    "LanguageModel",
    "TasksModel",
    "TransferModel",
)


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
        self.application.update_workflow()

    def removeEngine(self, uid: str, /) -> None:
        idx = self.engines_uid.index(uid)
        self.removeRows(idx, 1)
        self.application.update_workflow_user_engine_list(True, uid)
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
    FINALIZING_STATUS = qt.UserRole + 13

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
            self.FINALIZING_STATUS: b"finalizing_status",
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
        if role == self.FINALIZING_STATUS:
            return row.get("finalizing_status")
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
                self.setData(
                    idx, action["finalizing_status"], role=self.FINALIZING_STATUS
                )

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


def format_file_names_for_display(all_names: List[str], max_length: int = 60) -> str:
    """
    Format file names for display, fitting as many as possible within max_length.
    If all names fit, show them all. Otherwise, show as many as fit with "+N" suffix.

    Args:
        all_names: List of file names to display
        max_length: Maximum character length for the output string

    Returns:
        Formatted string like "file1.txt, file2.txt" or "file1.txt, file2.txt +3"
    """
    if not all_names:
        return ""

    if len(all_names) == 1:
        return all_names[0]

    # Try to fit all names first
    full_text = ", ".join(all_names)
    if len(full_text) <= max_length:
        return full_text

    # Need to truncate - find how many names we can fit
    result_parts = []
    current_length = 0
    remaining_count = len(all_names)

    for i, name in enumerate(all_names):
        remaining_count = len(all_names) - i - 1

        # Calculate what the suffix would be if we stop here
        suffix = f" +{remaining_count}" if remaining_count > 0 else ""
        separator = ", " if result_parts else ""

        # Check if adding this name would exceed the limit
        potential_length = current_length + len(separator) + len(name) + len(suffix)

        if potential_length <= max_length:
            result_parts.append(name)
            current_length += len(separator) + len(name)
        else:
            # Can't fit this name, stop here
            break

    # Build the final result
    if not result_parts:
        # Even the first name is too long, just show it truncated with count
        remaining = len(all_names) - 1
        if remaining > 0:
            # Truncate first name to fit with suffix
            suffix = f" +{remaining}"
            available = max_length - len(suffix) - 3  # 3 for "..."
            if available > 0:
                return f"{all_names[0][:available]}...{suffix}"
            return f"{all_names[0][:max_length - 3]}..."
        return (
            all_names[0][: max_length - 3] + "..."
            if len(all_names[0]) > max_length
            else all_names[0]
        )

    result = ", ".join(result_parts)
    remaining = len(all_names) - len(result_parts)

    if remaining > 0:
        result += f" +{remaining}"

    return result


class ActiveDirectDownloadModel(QAbstractListModel):
    """Model for active direct downloads (pending, in_progress, paused)."""

    downloadChanged = pyqtSignal()

    UID = qt.UserRole + 1
    DOC_UID = qt.UserRole + 2
    DOC_NAME = qt.UserRole + 3
    DOWNLOAD_PATH = qt.UserRole + 4
    SERVER_URL = qt.UserRole + 5
    STATUS = qt.UserRole + 6
    BYTES_DOWNLOADED = qt.UserRole + 7
    TOTAL_BYTES = qt.UserRole + 8
    PROGRESS_PERCENT = qt.UserRole + 9
    CREATED_AT = qt.UserRole + 10
    IS_FOLDER = qt.UserRole + 11
    FOLDER_COUNT = qt.UserRole + 12
    FILE_COUNT = qt.UserRole + 13
    ENGINE = qt.UserRole + 14
    ZIP_FILE = qt.UserRole + 15
    SELECTED_ITEMS = qt.UserRole + 16
    TOTAL_SIZE_FMT = qt.UserRole + 17
    SELECTED_ITEMS_DISPLAY = qt.UserRole + 18
    SHADOW = qt.UserRole + 19
    ALL_FILE_NAMES = qt.UserRole + 20
    BATCH_COUNT = qt.UserRole + 21

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.downloads: List[Dict[str, Any]] = []
        self.names = {
            self.UID: b"uid",
            self.DOC_UID: b"doc_uid",
            self.DOC_NAME: b"doc_name",
            self.DOWNLOAD_PATH: b"download_path",
            self.SERVER_URL: b"server_url",
            self.STATUS: b"status",
            self.BYTES_DOWNLOADED: b"bytes_downloaded",
            self.TOTAL_BYTES: b"total_bytes",
            self.PROGRESS_PERCENT: b"progress_percent",
            self.CREATED_AT: b"created_at",
            self.IS_FOLDER: b"is_folder",
            self.FOLDER_COUNT: b"folder_count",
            self.FILE_COUNT: b"file_count",
            self.ENGINE: b"engine",
            self.ZIP_FILE: b"zip_file",
            self.SELECTED_ITEMS: b"selected_items",
            self.TOTAL_SIZE_FMT: b"total_size_fmt",
            self.SELECTED_ITEMS_DISPLAY: b"selected_items_display",
            self.SHADOW: b"shadow",
            self.ALL_FILE_NAMES: b"all_file_names",
            self.BATCH_COUNT: b"batch_count",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.downloads)

    def _format_selected_items(self, items_str: str) -> str:
        """Format selected items for display, truncating if necessary."""
        if not items_str:
            return ""
        items = items_str.split(", ")
        if len(items) <= 2:
            return items_str
        # Show first 2 items and count of remaining
        display = f"{items[0]}, {items[1][:10]}..."
        remaining = len(items) - 2
        if remaining > 0:
            display += f" +{remaining}"
        return display

    def set_downloads(
        self, downloads: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        """Set the downloads list, replacing all existing items."""
        # Clear existing
        self.beginRemoveRows(parent, 0, max(0, self.rowCount() - 1))
        self.downloads.clear()
        self.endRemoveRows()

        # Add new downloads
        if downloads:
            self.beginInsertRows(parent, 0, len(downloads) - 1)
            self.downloads.extend(downloads)
            self.endInsertRows()

        self.downloadChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
        if not index.isValid() or index.row() >= len(self.downloads):
            return None
        row = self.downloads[index.row()]

        if role == self.STATUS:
            return row.get("status", "PENDING")
        elif role == self.DOWNLOAD_PATH:
            return row.get("download_path") or ""
        elif role == self.TOTAL_SIZE_FMT:
            total_bytes = row.get("total_bytes", 0)
            return sizeof_fmt(total_bytes) if total_bytes else "0 B"
        elif role == self.SELECTED_ITEMS_DISPLAY:
            return self._format_selected_items(row.get("selected_items", ""))
        elif role == self.CREATED_AT:
            label = "STARTED"
            args = []
            dt = get_date_from_sqlite(row.get("created_at"))
            if dt:
                label += "_ON"
                offset = tzlocal().utcoffset(dt)
                if offset:
                    dt += offset
                args.append(Translator.format_datetime(dt))
            return self.tr(label, values=args)
        elif role == self.SHADOW:
            return row.get("shadow", False)
        elif role == self.ZIP_FILE:
            return row.get("zip_file") or row.get("doc_name", "")
        elif role == self.ALL_FILE_NAMES:
            # Format file names: fit as many as possible within max length
            all_names = row.get("all_file_names", [])
            if not all_names:
                return row.get("doc_name", "")
            return format_file_names_for_display(all_names, max_length=60)
        elif role == self.BATCH_COUNT:
            return row.get("batch_count", 1)

        key = self.names.get(role, b"").decode()
        return row.get(key, "")

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None or not index.isValid():
            return
        key = force_decode(self.roleNames()[role])
        self.downloads[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtProperty("int", notify=downloadChanged)
    def count(self) -> int:
        return self.rowCount()

    @pyqtProperty("int", notify=downloadChanged)
    def count_no_shadow(self) -> int:
        return self.row_count_no_shadow()


class CompletedDirectDownloadModel(QAbstractListModel):
    """Model for completed/cancelled direct downloads."""

    downloadChanged = pyqtSignal()

    UID = qt.UserRole + 1
    DOC_UID = qt.UserRole + 2
    DOC_NAME = qt.UserRole + 3
    DOWNLOAD_PATH = qt.UserRole + 4
    SERVER_URL = qt.UserRole + 5
    STATUS = qt.UserRole + 6
    BYTES_DOWNLOADED = qt.UserRole + 7
    TOTAL_BYTES = qt.UserRole + 8
    PROGRESS_PERCENT = qt.UserRole + 9
    CREATED_AT = qt.UserRole + 10
    IS_FOLDER = qt.UserRole + 11
    FOLDER_COUNT = qt.UserRole + 12
    FILE_COUNT = qt.UserRole + 13
    ENGINE = qt.UserRole + 14
    ZIP_FILE = qt.UserRole + 15
    SELECTED_ITEMS = qt.UserRole + 16
    TOTAL_SIZE_FMT = qt.UserRole + 17
    COMPLETED_AT = qt.UserRole + 18
    ALL_FILE_NAMES = qt.UserRole + 19
    BATCH_COUNT = qt.UserRole + 20

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.downloads: List[Dict[str, Any]] = []
        self.names = {
            self.UID: b"uid",
            self.DOC_UID: b"doc_uid",
            self.DOC_NAME: b"doc_name",
            self.DOWNLOAD_PATH: b"download_path",
            self.SERVER_URL: b"server_url",
            self.STATUS: b"status",
            self.BYTES_DOWNLOADED: b"bytes_downloaded",
            self.TOTAL_BYTES: b"total_bytes",
            self.PROGRESS_PERCENT: b"progress_percent",
            self.CREATED_AT: b"created_at",
            self.IS_FOLDER: b"is_folder",
            self.FOLDER_COUNT: b"folder_count",
            self.FILE_COUNT: b"file_count",
            self.ENGINE: b"engine",
            self.ZIP_FILE: b"zip_file",
            self.SELECTED_ITEMS: b"selected_items",
            self.TOTAL_SIZE_FMT: b"total_size_fmt",
            self.COMPLETED_AT: b"completed_at",
            self.ALL_FILE_NAMES: b"all_file_names",
            self.BATCH_COUNT: b"batch_count",
        }

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.downloads)

    def set_downloads(
        self, downloads: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        """Set the downloads list."""
        self.beginRemoveRows(parent, 0, max(0, self.rowCount() - 1))
        self.downloads.clear()
        self.endRemoveRows()

        if downloads:
            self.beginInsertRows(parent, 0, len(downloads) - 1)
            self.downloads.extend(downloads)
            self.endInsertRows()

        self.downloadChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
        if not index.isValid() or index.row() >= len(self.downloads):
            return None
        row = self.downloads[index.row()]

        if role == self.STATUS:
            return row.get("status", "COMPLETED")
        elif role == self.DOWNLOAD_PATH:
            return row.get("download_path") or ""
        elif role == self.TOTAL_SIZE_FMT:
            total_bytes = row.get("total_bytes", 0)
            return sizeof_fmt(total_bytes) if total_bytes else "0 B"
        elif role == self.COMPLETED_AT:
            status = row.get("status", "COMPLETED")
            label = "COMPLETED" if status == "COMPLETED" else "CANCELLED"
            args = []
            dt = get_date_from_sqlite(row.get("completed_at"))
            if dt:
                label += "_ON"
                offset = tzlocal().utcoffset(dt)
                if offset:
                    dt += offset
                args.append(Translator.format_datetime(dt))
            return self.tr(label, values=args)
        elif role == self.ZIP_FILE:
            return row.get("zip_file") or row.get("doc_name", "")
        elif role == self.ALL_FILE_NAMES:
            # Format file names: fit as many as possible within max length
            all_names = row.get("all_file_names", [])
            if not all_names:
                return row.get("doc_name", "")
            return format_file_names_for_display(all_names, max_length=60)
        elif role == self.BATCH_COUNT:
            return row.get("batch_count", 1)

        key = self.names.get(role, b"").decode()
        return row.get(key, "")

    @pyqtProperty("int", notify=downloadChanged)
    def count(self) -> int:
        return self.rowCount()


class DirectDownloadMonitoringModel(QAbstractListModel):
    """Model for monitoring active direct downloads with real-time progress."""

    itemChanged = pyqtSignal()

    UID = qt.UserRole + 1
    DOC_NAME = qt.UserRole + 2
    STATUS = qt.UserRole + 3
    PROGRESS = qt.UserRole + 4
    ENGINE = qt.UserRole + 5
    FILESIZE = qt.UserRole + 6
    TRANSFERRED = qt.UserRole + 7
    DOWNLOAD_PATH = qt.UserRole + 8
    SHADOW = qt.UserRole + 9

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
        super().__init__(parent)
        self.tr = translate
        self.items: List[Dict[str, Any]] = []
        self.names = {
            self.UID: b"uid",
            self.DOC_NAME: b"doc_name",
            self.STATUS: b"status",
            self.PROGRESS: b"progress",
            self.ENGINE: b"engine",
            self.FILESIZE: b"filesize",
            self.TRANSFERRED: b"transferred",
            self.DOWNLOAD_PATH: b"download_path",
            self.SHADOW: b"shadow",
        }
        # Pretty print for file sizes
        self.psize = partial(sizeof_fmt, suffix=self.tr("BYTE_ABBREV"))

    def rowCount(self, parent: QModelIndex = QModelIndex(), /) -> int:
        return len(self.items)

    def roleNames(self) -> Dict[int, bytes]:
        return self.names

    def set_items(
        self, items: List[Dict[str, Any]], /, *, parent: QModelIndex = QModelIndex()
    ) -> None:
        """Set the items list, replacing all existing items."""
        # Clear existing
        self.beginRemoveRows(parent, 0, max(0, self.rowCount() - 1))
        self.items.clear()
        self.endRemoveRows()

        # Add new items
        if items:
            self.beginInsertRows(parent, 0, len(items) - 1)
            self.items.extend(items)
            self.endInsertRows()

        self.itemChanged.emit()

    def data(self, index: QModelIndex, role: int, /) -> Any:
        if not index.isValid() or index.row() >= len(self.items):
            return None
        row = self.items[index.row()]

        if role == self.STATUS:
            status = row.get("status", "PENDING")
            return status if isinstance(status, str) else status.name
        if role == self.PROGRESS:
            return f"{row.get('progress', 0.0):,.1f}"
        if role == self.SHADOW:
            return row.get("shadow", False)
        if role == self.FILESIZE:
            return self.psize(row.get("total_bytes", 0))
        if role == self.TRANSFERRED:
            # Prefer bytes_downloaded if available, otherwise compute from progress
            bytes_dl = row.get("bytes_downloaded")
            if bytes_dl is not None and bytes_dl > 0:
                return self.psize(bytes_dl)
            total = row.get("total_bytes", 0)
            progress = row.get("progress", 0.0)
            return self.psize(total * progress / 100) if total > 0 else "0 B"
        if role == self.DOC_NAME:
            return row.get("doc_name", "")
        if role == self.DOWNLOAD_PATH:
            return row.get("download_path", "")
        if role == self.ENGINE:
            return row.get("engine", "")
        if role == self.UID:
            return row.get("uid", 0)

        key = self.names.get(role, b"").decode()
        return row.get(key, "")

    def setData(self, index: QModelIndex, value: Any, /, *, role: int = None) -> None:
        if role is None or not index.isValid():
            return
        key = force_decode(self.roleNames()[role])
        self.items[index.row()][key] = value
        self.dataChanged.emit(index, index, [role])

    @pyqtSlot(dict)
    def set_progress(self, action: Dict[str, Any], /) -> None:
        """Update download progress for a specific item."""
        for i, item in enumerate(self.items):
            if item.get("uid") != action.get("uid"):
                continue
            # Update item data directly
            item["progress"] = action.get("progress", 0.0)
            item["bytes_downloaded"] = action.get("bytes_downloaded", 0)
            item["total_bytes"] = action.get("total_bytes", item.get("total_bytes", 0))
            # Emit data changed for the row
            idx = self.createIndex(i, 0)
            self.dataChanged.emit(
                idx, idx, [self.PROGRESS, self.TRANSFERRED, self.FILESIZE]
            )
            break

    @pyqtProperty("int", notify=itemChanged)
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

        total_rows = (
            Options.feature_systray_history
            if -1 < Options.feature_systray_history < len(files)
            else len(files)
        )
        self.beginInsertRows(parent, 0, total_rows - 1)
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


class TasksModel(QObject):
    TASK_ROLE = qt.UserRole  # + 1
    TASK_ID = qt.UserRole + 1

    def __init__(self, translate: Callable, /, *, parent: QObject = None) -> None:
        super().__init__(parent)
        # self.tr = translate
        self.taskmodel = QStandardItemModel()
        self.taskmodel.setItemRoleNames(
            {
                self.TASK_ROLE: b"task",
                self.TASK_ID: b"task_id",
            }
        )

        self.self_taskmodel = QStandardItemModel()
        self.self_taskmodel.setItemRoleNames(
            {
                self.TASK_ROLE: b"task",
                self.TASK_ID: b"task_id",
            }
        )

    def get_model(self) -> QStandardItemModel:
        return self.taskmodel

    def get_self_model(self) -> QStandardItemModel:
        return self.self_taskmodel

    model = pyqtProperty(QObject, fget=get_model, constant=True)
    self_model = pyqtProperty(QObject, fget=get_self_model, constant=True)

    @pyqtSlot(list, str)
    def loadList(self, tasks_list: list, username: str, /) -> None:
        self.taskmodel.clear()
        self.self_taskmodel.clear()

        for task in tasks_list:
            diff = self.due_date_calculation(task.dueDate)
            translated_due = Translator.get("DUE")
            details = str(
                {
                    "wf_name": task.directive,
                    "name": task.name,
                    "due": f"{translated_due}: {diff}",
                    "model": task.workflowModelName,
                }
            )
            if task.actors[0]["id"] == username:
                data = {
                    "self_task_details": details,
                    "task_ids": task.id,
                }
                self.add_row(data, self.TASK_ROLE, True)
            else:
                data = {
                    "task_details": details,
                    "task_ids": task.id,
                }
                self.add_row(data, self.TASK_ROLE, False)

    def add_row(self, task: dict, role: int, self_task: bool) -> None:
        item = QStandardItem()
        item.setData(task, role)

        if self_task:
            self.self_taskmodel.appendRow(item)
        else:
            self.taskmodel.appendRow(item)

    def due_date_calculation(self, dueDate: str) -> str:
        due_date = datetime.strptime(dueDate, "%Y-%m-%dT%H:%M:%S.%f%z").date()
        now = date.today()
        time_remaing = Translator.get("DAYS")
        diff = (due_date - now).days
        if diff > 364 or diff < -364:
            diff /= 365
            time_remaing = Translator.get("YEARS")
        elif diff > 29 or diff < -29:
            diff /= 30
            time_remaing = Translator.get("MONTHS")
        ago = Translator.get("AGO")
        translated_in = Translator.get("IN")
        diff = int(diff)
        return (
            f"{-diff} {time_remaing} {ago}"
            if diff < 0
            else f"{translated_in} {diff} {time_remaing}"
        )
