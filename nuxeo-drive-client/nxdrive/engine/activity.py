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
        if thread_id is None:
            thread_id = current_thread().ident
        Action.actions[thread_id] = self

    def get_percent(self):
        return self.progress

    @staticmethod
    def get_actions():
        return Action.actions.copy()

    @staticmethod
    def get_current_action(thread_id=None):
        if thread_id is None:
            thread_id = current_thread().ident
        if thread_id in Action.actions:
            return Action.actions[thread_id]

    @staticmethod
    def get_last_file_action(thread_id=None):
        if thread_id is None:
            thread_id = current_thread().ident
        if thread_id in Action.lastFileActions:
            return Action.lastFileActions[thread_id]

    @staticmethod
    def finish_action():
        if (current_thread().ident in Action.actions and
                Action.actions[current_thread().ident] is not None):
            Action.actions[current_thread().ident].finished = True
            if isinstance(Action.actions[current_thread().ident], FileAction):
                Action.actions[current_thread().ident].end_time = current_milli_time()
                # Save last file actions
                Action.lastFileActions[current_thread().ident] = Action.actions[current_thread().ident]
        Action.actions[current_thread().ident] = None

    def __repr__(self):
        if self.progress is None:
            return "%s" % self.type
        else:
            return "%s(%s%%)" % (self.type, self.progress)


class IdleAction(Action):
    def __init__(self):
        self.type = "Idle"

    def get_percent(self):
        return


class FileAction(Action):
    filepath = None
    filename = None
    size = None
    transfer_duration = None

    def __init__(self, action_type, filepath, filename=None, size=None):
        super(FileAction, self).__init__(action_type, 0)
        self.filepath = filepath
        if filename is None:
            self.filename = os.path.basename(filepath)
        else:
            self.filename = filename
        if size is None:
            self.size = os.path.getsize(filepath)
        else:
            self.size = size
        self.start_time = current_milli_time()
        self.end_time = None

    def get_percent(self):
        if self.size <= 0:
            return
        if self.progress > self.size:
            return 100
        return self.progress * 100 / self.size

    def __repr__(self):
        # Size can be None if the file disapeared right on creation
        if self.size is None:
            return "%s(%r)" % (self.type, self.filename)
        percent = self.get_percent()
        if percent is None:
            return "%s(%r[%d])" % (self.type, self.filename, self.size)
        return "%s(%r[%d]-%f%%)" % (self.type, self.filename, self.size, percent)

Action.actions = dict()
Action.lastFileActions = dict()
