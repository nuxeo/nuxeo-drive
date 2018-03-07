# coding: utf-8
from .base import BaseUpdater


class Updater(BaseUpdater):
    """ Fake updater that does nothing. """

    _enable = False

    def force_status(self, *args, **kwargs):
        pass

    def install(self, *args, **kwargs):
        pass

    def refresh_status(self, *args, **kwargs):
        pass
