# coding: utf-8
import logging

from PyQt5.QtCore import pyqtSlot

from .engine.workers import PollWorker
from .options import Options
from .utils import normalize_and_expand_path

log = logging.getLogger(__name__)


class DatabaseBackupWorker(PollWorker):
    """ Class for making backups of the manager and engine databases. """

    def __init__(self, manager):
        # Backup every hour
        super().__init__(60 * 60)
        self.manager = manager

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """ Perform the backups. """

        if not self.manager:
            return False

        if self.manager._dao:
            self.manager._dao.save_backup()

        for engine in self.manager._engines.values():
            if engine._dao:
                engine._dao.save_backup()

        return True


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

                # Compat with old servers
                beta = conf.pop("beta_channel", False)
                if beta:
                    conf["channel"] = "beta"

                if "nxdrive_home" in conf:
                    # Expand potential envars
                    conf["nxdrive_home"] = normalize_and_expand_path(
                        conf["nxdrive_home"]
                    )

                # We cannot use fail_on_error=True because the server may
                # be outdated and still have obsolete options.
                Options.update(conf, setter="server", fail_on_error=False)
                break

        return True
