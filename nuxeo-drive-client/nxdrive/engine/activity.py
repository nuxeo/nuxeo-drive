# coding: utf-8
import os
from threading import current_thread

from nxdrive.utils import current_milli_time


class Action(object):
    progress = None
    type = None
    finished = False
    suspend = False

    def __init__(self, action_type, progress=None, thread_id=None):
        self.progress = progress
        self.type = action_type
        Action.actions[thread_id or current_thread().ident] = self

    def get_percent(self):
        return self.progress

    @staticmethod
    def get_actions():
        return Action.actions.copy()

    @staticmethod
    def get_current_action(thread_id=None):
        return Action.actions.get(thread_id or current_thread().ident)

    @staticmethod
    def get_last_file_action(thread_id=None):
        return Action.lastFileActions.get(thread_id or current_thread().ident)

    @staticmethod
    def finish_action():
        thread_id = current_thread().ident

        action = Action.actions.get(thread_id)
        if action:
            Action.actions[thread_id].finished = True
            if isinstance(Action.actions[thread_id], FileAction):
                Action.actions[thread_id].end_time = current_milli_time()

                # Save last file actions
                Action.lastFileActions[thread_id] = Action.actions[thread_id]

        Action.actions[thread_id] = None

    def __repr__(self):
        if self.progress is None:
            return str(self.type)
        return '%s(%s%%)' % (self.type, self.progress)


class IdleAction(Action):
    def __init__(self):
        self.type = 'Idle'

    def get_percent(self):
        return None


class FileAction(Action):
    filepath = None
    filename = None
    size = None
    transfer_duration = None

    def __init__(self, action_type, filepath, filename=None, size=None):
        super(FileAction, self).__init__(action_type, 0)
        self.filepath = filepath
        self.filename = filename or os.path.basename(filepath)
        if size is None:
            self.size = os.path.getsize(filepath)
        else:
            self.size = size
        self.start_time = current_milli_time()
        self.end_time = None

    def get_percent(self):
        if self.size <= 0:
            return None
        if self.progress > self.size:
            return 100
        return self.progress * 100 / self.size

    def __repr__(self):
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return '%s(%r)' % (self.type, self.filename)
        percent = self.get_percent()
        if percent is None:
            return '%s(%r[%d])' % (self.type, self.filename, self.size)
        return '%s(%r[%d]-%f%%)' % (self.type, self.filename, self.size, percent)


Action.actions = dict()
Action.lastFileActions = dict()
