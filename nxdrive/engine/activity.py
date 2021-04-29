import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from ..qt.imports import QApplication, QObject, pyqtSignal
from ..utils import current_thread_id

__all__ = (
    "Action",
    "DownloadAction",
    "FileAction",
    "IdleAction",
    "LinkingAction",
    "UploadAction",
    "tooltip",
)


class Action(QObject):
    actions: Dict[int, Optional["Action"]] = {}

    def __init__(self, action_type: str, /, *, progress: float = 0.0) -> None:
        super().__init__()

        self.type = action_type
        self._progress = progress

        self.size = 0
        self.uid = str(uuid.uuid4())
        self.finished = False
        self.suspend = False

        Action.actions[current_thread_id()] = self

    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float, /) -> None:
        self._progress = value

    def get_percent(self) -> float:
        return self.progress

    @staticmethod
    def get_actions() -> Dict[int, Optional["Action"]]:
        return Action.actions.copy()

    @staticmethod
    def get_current_action(*, thread_id: int = None) -> Optional["Action"]:
        idx = thread_id or current_thread_id()
        return Action.actions.get(idx, None) if idx else None

    @staticmethod
    def finish_action() -> None:
        action = Action.actions.pop(current_thread_id(), None)
        if action:
            action.finish()

    def finish(self) -> None:
        self.finished = True

    def export(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "action_type": self.type,
            "progress": self.get_percent(),
        }

    def __repr__(self) -> str:
        if not self.progress:
            return str(self.type)
        return f"{self.type}({self.progress}%)"


class IdleAction(Action):
    def __init__(self) -> None:
        super().__init__("Idle")


class FileAction(Action):
    started = pyqtSignal(object)
    progressing = pyqtSignal(object)
    done = pyqtSignal(object)

    def __init__(
        self,
        action_type: str,
        filepath: Path,
        size: int,
        /,
        *,
        tmppath: Path = None,
        reporter: Any = None,
        engine: str = "",
        doc_pair: int = None,
    ) -> None:
        super().__init__(action_type)

        self.filepath = filepath
        self.size = size
        self.tmppath = tmppath
        self.engine = engine
        self.doc_pair = doc_pair

        # Is it an empty file?
        self.empty = size == 0

        # Is it already on the server?
        self.uploaded = False

        # Used to compute the transfer speed, updated by the Remote client
        self.chunk_size = 0
        # Used to compute the transfer speed, updated by the Remote client at each (down|up)loaded chunk
        self.chunk_transfer_start_time_ns = 0.0  # nanoseconds
        self.chunk_transfer_end_time_ns = 0.0  # nanoseconds
        # The transfer speed of the latest (down|up)loaded chunk
        self.last_chunk_transfer_speed = 0.0
        # Number of chunks transferred since the last speed computation
        self.transferred_chunks = 0

        # Used to know if the file is a Direct Transfer item
        self.is_direct_transfer = False

        self._connect_reporter(reporter)
        self.started.emit(self)

    def _connect_reporter(self, reporter: Optional[QApplication], /) -> None:
        if not reporter:
            return

        for evt in ("started", "progressing", "done"):
            signal = getattr(reporter, f"action_{evt}", None)
            if signal:
                getattr(self, evt).connect(signal)

    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float, /) -> None:
        self._progress = value

        if self.empty and not self.uploaded:
            # Even if it *is* empty, we need this to know when the file has been uploaded
            self.uploaded = True

        self.progressing.emit(self)

    def get_percent(self) -> float:
        if self.size < 0 or (self.empty and not self.uploaded):
            return 0.0
        if self.progress >= self.size:
            self.uploaded = True
            return 100.0
        return self.progress * 100.0 / self.size

    def finish(self) -> None:
        super().finish()
        try:
            self.done.emit(self)
        except RuntimeError:
            # RuntimeError: wrapped C/C++ object of type LinkingAction has been deleted
            # Happens on Windows when running old functional tests
            pass

    def export(self) -> Dict[str, Any]:
        return {
            **super().export(),
            "size": self.size,
            "name": self.filepath.name,
            "filepath": str(self.filepath),
            "tmppath": str(self.tmppath),
            "empty": self.empty,
            "uploaded": self.uploaded,
            "speed": self.last_chunk_transfer_speed,
            "is_direct_transfer": self.is_direct_transfer,
            "engine": self.engine,
            "doc_pair": self.doc_pair,
        }

    def __repr__(self) -> str:
        if self.size < 0:
            return f"{self.type}({self.filepath.name!r})"
        percent = self.get_percent()
        if percent > 0.0:
            return f"{self.type}({self.filepath.name!r}[{self.size}]-{percent})"
        return f"{self.type}({self.filepath.name!r}[{self.size}])"


class DownloadAction(FileAction):
    """Download: step 1/2 - Download the file."""

    def __init__(
        self,
        filepath: Path,
        size: int,
        /,
        *,
        tmppath: Path = None,
        reporter: Any = None,
    ) -> None:
        super().__init__("Download", filepath, size, tmppath=tmppath, reporter=reporter)


class VerificationAction(FileAction):
    """Download: step 2/2 - Checking the file integrity."""

    def __init__(self, filepath: Path, size: int, /, *, reporter: Any = None) -> None:
        super().__init__("Verification", filepath, size, reporter=reporter)


class UploadAction(FileAction):
    """Upload: step 1/2 - Upload the file."""

    def __init__(
        self,
        filepath: Path,
        size: int,
        /,
        *,
        reporter: Any = None,
        engine: str = "",
        doc_pair: int = None,
    ) -> None:
        super().__init__(
            "Upload",
            filepath,
            size,
            reporter=reporter,
            engine=engine,
            doc_pair=doc_pair,
        )


class LinkingAction(FileAction):
    """Upload: step 2/2 - Create the document on the server and link the uploaded blob to it."""

    def __init__(
        self,
        filepath: Path,
        size: int,
        /,
        *,
        reporter: Any = None,
        engine: str = "",
        doc_pair: int = None,
    ) -> None:
        super().__init__(
            "Linking",
            filepath,
            size,
            reporter=reporter,
            engine=engine,
            doc_pair=doc_pair,
        )
        self.progress = size


def tooltip(doing: str):  # type: ignore
    def action_decorator(func):  # type: ignore
        def func_wrapper(*args: Any, **kwargs: Any):  # type: ignore
            Action(doing)
            try:
                func(*args, **kwargs)
            finally:
                Action.finish_action()

        return func_wrapper

    return action_decorator
