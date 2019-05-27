# coding: utf-8
import uuid
from contextlib import suppress
from pathlib import Path
from threading import current_thread
from time import monotonic
from typing import Any, Dict, Optional

from PyQt5.QtCore import pyqtSignal, QObject

__all__ = (
    "Action",
    "DownloadAction",
    "FileAction",
    "IdleAction",
    "UploadAction",
    "tooltip",
)


class Action(QObject):
    actions: Dict[int, Optional["Action"]] = {}
    lastFileActions: Dict[int, Optional["FileAction"]] = {}

    def __init__(
        self, action_type: str = None, progress: float = 0.0, thread_id: int = None
    ) -> None:
        super().__init__()

        self.type = action_type
        self._progress = progress

        self.size = 0.0
        self.uid = str(uuid.uuid4())
        self.finished = False
        self.suspend = False

        idx = thread_id or current_thread().ident
        if idx:
            Action.actions[idx] = self

    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float) -> None:
        self._progress = value

    def get_percent(self) -> float:
        return self.progress

    @staticmethod
    def get_actions() -> Dict[int, Optional["Action"]]:
        return Action.actions.copy()

    @staticmethod
    def get_current_action(thread_id: int = None) -> Optional["Action"]:
        idx = thread_id or current_thread().ident
        return Action.actions.get(idx, None) if idx else None

    @staticmethod
    def get_last_file_action(thread_id: int = None) -> Optional["FileAction"]:
        idx = thread_id or current_thread().ident
        return Action.lastFileActions.get(idx, None) if idx else None

    @staticmethod
    def finish_action() -> None:
        thread_id = current_thread().ident
        if not thread_id:
            return

        action = Action.actions.pop(thread_id, None)
        if action:
            action.finish()
            if isinstance(action, FileAction):
                Action.lastFileActions[thread_id] = action

    def finish(self) -> None:
        self.finished = True

    def export(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "last_transfer": self.type,
            "progress": self.get_percent(),
        }

    def __repr__(self) -> str:
        if not self.progress:
            return str(self.type)
        return f"{self.type}({self.progress}%)"


class IdleAction(Action):
    def __init__(self):
        super().__init__(action_type="Idle")


class FileAction(Action):
    started = pyqtSignal(Action)
    progressing = pyqtSignal(Action)
    done = pyqtSignal(Action)

    def __init__(
        self,
        action_type: str,
        filepath: Path,
        filename: str = None,
        size: float = 0.0,
        reporter: Any = None,
    ) -> None:
        super().__init__(action_type=action_type)

        self.filepath = filepath
        self.filename = filename or filepath.name
        if not size:
            with suppress(OSError):
                size = filepath.stat().st_size
        self.size = size

        self.start_time = monotonic()
        self.end_time = 0.0
        self.transfer_duration = 0.0

        self._connect_reporter(reporter)
        self.started.emit(self)

    def _connect_reporter(self, reporter):
        if not reporter:
            return
        for evt in {"started", "progressing", "done"}:
            signal = getattr(reporter, f"action_{evt}", None)
            if signal:
                getattr(self, evt).connect(signal)

    @property
    def progress(self) -> float:
        return self._progress

    @progress.setter
    def progress(self, value: float) -> None:
        self._progress = value
        self.progressing.emit(self)

    def get_percent(self) -> float:
        if self.size <= 0 or self.progress <= 0:
            return 0.0
        if self.progress > self.size:
            return 100.0
        return self.progress * 100 / self.size

    def finish(self) -> None:
        super().finish()
        self.end_time = monotonic()
        self.done.emit(self)

    def export(self) -> Dict[str, Any]:
        return {
            **super().export(),
            "size": self.size,
            "name": self.filename,
            "filepath": str(self.filepath),
        }

    def __repr__(self) -> str:
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return f"{self.type}({self.filename!r})"
        percent = self.get_percent()
        if percent > 0.0:
            return f"{self.type}({self.filename!r}[{self.size}]-{percent})"
        return f"{self.type}({self.filename!r}[{self.size}])"


class DownloadAction(FileAction):
    action_type = "Download"

    def __init__(
        self, filepath: Path, filename: str = None, reporter: Any = None
    ) -> None:
        super(DownloadAction, self).__init__(
            self.action_type, filepath, filename=filename, reporter=reporter
        )


class UploadAction(FileAction):
    action_type = "Upload"

    def __init__(
        self, filepath: Path, filename: str = None, reporter: Any = None
    ) -> None:
        super(UploadAction, self).__init__(
            self.action_type,
            filepath,
            filename=filename,
            size=filepath.stat().st_size,
            reporter=reporter,
        )


def tooltip(doing: str):
    def action_decorator(func):
        def func_wrapper(*args, **kwargs):
            Action(doing)
            try:
                func(*args, **kwargs)
            finally:
                Action.finish_action()

        return func_wrapper

    return action_decorator
