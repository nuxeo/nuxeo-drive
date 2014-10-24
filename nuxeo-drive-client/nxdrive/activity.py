'''
Created on 17 sept. 2014

@author: Remi Cattiau
'''
import os
from threading import current_thread


class Action(object):
    progress = None
    type = None
    finished = False

    def __init__(self, actionType, progress=None, threadId=None):
        self.progress = progress
        self.type = actionType
        if threadId is None:
            threadId = current_thread().ident
        Action.actions[threadId] = self

    def get_percent(self):
        return self.progress

    @staticmethod
    def get_actions():
        return Action.actions.copy()

    @staticmethod
    def finish_action():
        if current_thread().ident in Action.actions:
            Action.actions[current_thread().ident].finished = True
        Action.actions[current_thread().ident] = None


class FileAction(Action):
    filepath = None
    filename = None
    size = None

    def __init__(self, actionType, filepath, filename=None, size=None):
        super(FileAction, self).__init__(actionType, 0)
        self.filepath = filepath
        if filename is None:
            self.filename = os.path.basename(filepath)
        else:
            self.filename = filename
        if size is None:
            self.size = os.path.getsize(filepath)
        else:
            self.size = size

    def get_percent(self):
        if self.size <= 0:
            return None
        if self.progress > self.size:
            return 100
        else:
            return self.progress * 100 / self.size


Action.actions = dict()
