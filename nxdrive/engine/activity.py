# coding: utf-8
import os
from threading import current_thread
from typing import Dict, Optional

from ..utils import current_milli_time

__all__ = ("Action", "FileAction", "IdleAction", "tooltip")


class Action:
    progress = None
    type = None
    finished = False
    suspend = False

    def __init__(
        self, action_type: str = None, progress: int = None, thread_id: int = None
    ) -> None:
        self.progress = progress
        self.type = action_type
        Action.actions[thread_id or current_thread().ident] = self

    def get_percent(self) -> Optional[int]:
        return self.progress

    @staticmethod
    def get_actions() -> Dict[int, "Action"]:
        return Action.actions.copy()

    @staticmethod
    def get_current_action(thread_id: int = None):
        return Action.actions.get(thread_id or current_thread().ident)

    @staticmethod
    def get_last_file_action(thread_id=None):
        return Action.lastFileActions.get(thread_id or current_thread().ident)

    @staticmethod
    def finish_action() -> None:
        thread_id = current_thread().ident

        action = Action.actions.get(thread_id)
        if action:
            Action.actions[thread_id].finished = True
            if isinstance(Action.actions[thread_id], FileAction):
                Action.actions[thread_id].end_time = current_milli_time()

                # Save last file actions
                Action.lastFileActions[thread_id] = Action.actions[thread_id]

        Action.actions[thread_id] = None

    def __repr__(self) -> str:
        if self.progress is None:
            return str(self.type)
        return "%s(%s%%)" % (self.type, self.progress)


class IdleAction(Action):
    type = "Idle"


class FileAction(Action):
    filepath = None
    filename = None
    size = None
    transfer_duration = None

    def __init__(
        self, action_type: str, filepath: str, filename: str = None, size: int = None
    ) -> None:
        super().__init__(action_type, 0)
        self.filepath = filepath
        self.filename = filename or os.path.basename(filepath)
        if size is None:
            self.size = os.path.getsize(filepath)
        else:
            self.size = size
        self.start_time = current_milli_time()
        self.end_time = None

    def get_percent(self) -> Optional[int]:
        if self.size <= 0:
            return None
        if self.progress > self.size:
            return 100
        return self.progress * 100 // self.size

    def __repr__(self) -> str:
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return "%s(%r)" % (self.type, self.filename)
        percent = self.get_percent()
        if percent is None:
            return "%s(%r[%d])" % (self.type, self.filename, self.size)
        return "%s(%r[%d]-%f%%)" % (self.type, self.filename, self.size, percent)


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
