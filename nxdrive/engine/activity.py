# coding: utf-8
from pathlib import Path
from threading import current_thread
from typing import Dict, Optional

from ..utils import current_milli_time

__all__ = ("Action", "FileAction", "IdleAction", "tooltip")


class Action:
    actions: Dict[int, Optional["Action"]]
    lastFileActions: Dict[int, Optional["FileAction"]]

    progress = None
    type = None
    finished = False
    suspend = False

    def __init__(
        self, action_type: str = None, progress: float = None, thread_id: int = None
    ) -> None:
        self.progress = progress
        self.type = action_type
        idx = thread_id or current_thread().ident
        if idx:
            Action.actions[idx] = self

    def get_percent(self) -> Optional[float]:
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
            action.finished = True
            if isinstance(action, FileAction):
                action.end_time = current_milli_time()

                # Save last file actions
                Action.lastFileActions[thread_id] = action

        Action.actions[thread_id] = None

    def __repr__(self) -> str:
        if self.progress is None:
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

    def __init__(
        self, action_type: str, filepath: Path, filename: str = None, size: int = None
    ) -> None:
        super().__init__(action_type, 0)
        self.filepath = filepath
        self.filename = filename or filepath.name
        if size is None:
            self.size = filepath.stat().st_size
        else:
            self.size = size
        self.start_time = current_milli_time()

    def get_percent(self) -> Optional[float]:
        if self.size <= 0 or not self.progress:
            return None
        if self.progress > self.size:
            return 100
        return self.progress * 100 // self.size

    def __repr__(self) -> str:
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return f"{self.type}({self.filename!r})"
        percent = self.get_percent()
        if percent is None:
            return f"{self.type}({self.filename!r}[{self.size}])"
        return f"{self.type}({self.filename!r}[{self.size}]-{percent})"


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
