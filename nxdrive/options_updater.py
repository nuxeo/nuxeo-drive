# coding: utf-8
import logging

from PyQt5.QtCore import pyqtSlot

from .engine.workers import PollWorker
from .options import Options

log = logging.getLogger(__name__)


class ServerOptionsUpdater(PollWorker):
    """ Class for checking the server's config.json updates. """

    def __init__(self, manager):
        super().__init__(Options.update_check_delay)
        self.manager = manager

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """ Check for the configuration file and apply updates. """

        for _, engine in self.manager._engines.items():
            if not engine.remote:
                continue

            conf = engine.remote.get_server_configuration()
            if not conf:
                engine.set_ui("jsf", overwrite=False)
            else:
                engine.set_ui(conf.pop("ui"), overwrite=False)
                Options.update(conf, setter="server", fail_on_error=True)
                break

        return True
