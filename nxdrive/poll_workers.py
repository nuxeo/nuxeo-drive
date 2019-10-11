# coding: utf-8
import logging
from typing import TYPE_CHECKING

from PyQt5.QtCore import pyqtSlot

from .engine.workers import PollWorker
from .options import Options
from .updater.constants import UPDATE_STATUS_UPDATING
from .utils import normalize_and_expand_path

if TYPE_CHECKING:
    from .manager import Manager  # noqa


log = logging.getLogger(__name__)


class DatabaseBackupWorker(PollWorker):
    """ Class for making backups of the manager and engine databases. """

    def __init__(self, manager: "Manager"):
        # Backup every hour
        super().__init__(60 * 60)
        self.manager = manager

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """ Perform the backups. """

        if not self.manager:
            return False

        if self.manager.dao:
            self.manager.dao.save_backup()

        for engine in self.manager.engines.copy().values():
            if engine.dao:
                engine.dao.save_backup()

        return True


class ServerOptionsUpdater(PollWorker):
    """ Class for checking the server's config.json updates. """

    def __init__(self, manager: "Manager"):
        super().__init__(Options.update_check_delay)
        self.manager = manager

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """ Check for the configuration file and apply updates. """

        for engine in self.manager.engines.copy().values():
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


class SyncAndQuitWorker(PollWorker):
    """Class for checking if the application needs to be exited."""

    def __init__(self, manager: "Manager"):
        """Check every 10 seconds.
        """
        super().__init__(10)
        self.manager = manager

        # Skip the first check to let engines having time to start
        self._first_check = True

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """Check for the synchronization state."""

        if self._first_check:
            self._first_check = False
            return True

        if (
            Options.sync_and_quit
            and self.manager.is_started()
            and not self.manager.is_syncing()
            and self.manager.updater.status != UPDATE_STATUS_UPDATING
            and hasattr(self.manager, "application")
        ):
            log.info(
                "The 'sync_and_quit' option is True and the synchronization is over."
            )
            self.manager.application.quit()

        return True
