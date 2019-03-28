# coding: utf-8
import uuid
from pathlib import Path
from threading import current_thread
from typing import Any, Dict, Optional

from PyQt5.QtCore import pyqtSignal, QObject

from ..utils import current_milli_time

__all__ = ("Action", "FileAction", "IdleAction", "tooltip")


class Action(QObject):
    actions: Dict[int, Optional["Action"]]
    lastFileActions: Dict[int, Optional["FileAction"]]

    _progress = .0
    type = None
    finished = False
    suspend = False

    def __init__(
        self, action_type: str = None, progress: float = .0, thread_id: int = None
    ) -> None:
        super().__init__()
        self.uid = str(uuid.uuid4())
        self._progress = progress
        self.type = action_type
        idx = thread_id or current_thread().ident
        if idx:
            Action.actions[idx] = self

    @property
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value

    def get_percent(self) -> float:
        return self.progress

    @staticmethod
    def get_actions() -> Dict[int, Optional["Action"]]:
        return Action.actions.copy()

    @staticmethod
    def get_current_action(thread_id: int = None) -> Optional["Action"]:
        idx = thread_id or current_thread().ident
        return Action.actions.get(idx) if idx else None

    @staticmethod
    def get_last_file_action(thread_id: int = None) -> Optional["FileAction"]:
        idx = thread_id or current_thread().ident
        return Action.lastFileActions.get(idx) if idx else None

    @staticmethod
    def finish_action() -> None:
        thread_id = current_thread().ident
        if thread_id is None:
            return

        action = Action.actions.get(thread_id)
        if action:
            action.finish()
            if isinstance(action, FileAction):
                Action.lastFileActions[thread_id] = action

        Action.actions[thread_id] = None

    def finish(self) -> None:
        self.finished = True

    def __repr__(self) -> str:
        if not self.progress:
            return str(self.type)
        return f"{self.type}({self.progress}%)"


class IdleAction(Action):
    type = "Idle"


class FileAction(Action):
    filepath: Path
    filename: str
    size: float
    end_time: int
    transfer_duration: float = 0

    started = pyqtSignal(Action)
    progressing = pyqtSignal(Action)
    done = pyqtSignal(Action)

    def __init__(
        self,
        action_type: str,
        filepath: Path,
        filename: str = None,
        size: float = None,
        reporter: Any = None,
    ) -> None:
        super().__init__(action_type, 0)
        self.filepath = filepath
        self.filename = filename or filepath.name
        if size is None:
            self.size = filepath.stat().st_size
        else:
            self.size = size
        self.start_time = current_milli_time()

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
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, value):
        self._progress = value
        self.progressing.emit(self)

    def get_percent(self) -> Optional[float]:
        if self.size <= 0 or not self.progress:
            return .0
        if self.progress > self.size:
            return 100.0
        return self.progress * 100 / self.size

    def finish(self) -> None:
        super().finish()
        self.end_time = current_milli_time()
        self.done.emit(self)

    def __repr__(self) -> str:
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return f"{self.type}({self.filename!r})"
        percent = self.get_percent()
        if percent > .0:
            return f"{self.type}({self.filename!r}[{self.size}]-{percent})"
        return f"{self.type}({self.filename!r}[{self.size}])"


Action.actions = dict()
Action.lastFileActions = dict()


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
