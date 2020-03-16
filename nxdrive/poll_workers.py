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
        """Backup every hour."""
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
        default_delay = 60 * 60  # 1 hour
        # The check will be done every *update_check_delay* seconds or *default_delay*
        # when the channel is centralized.
        super().__init__(Options.update_check_delay or default_delay)
        self.manager = manager

        # Notify the Manager that the server's config has been fetched at least one time.
        # This will be used later in the Updater.
        self.first_run = True

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """ Check for the configuration file and apply updates. """

        for engine in self.manager.engines.copy().values():
            if not engine.remote:
                continue

            conf = engine.remote.get_server_configuration()
            if not conf:
                engine.set_ui("jsf", overwrite=False)
                continue

            engine.set_ui(conf.pop("ui"), overwrite=False)

            # Compat with old servers
            beta = conf.pop("beta_channel", False)
            if beta:
                conf["channel"] = "beta"

            if "nxdrive_home" in conf:
                # Expand eventuel envars like %userprofile% and co.
                conf["nxdrive_home"] = normalize_and_expand_path(conf["nxdrive_home"])

            # We cannot use fail_on_error=True because the server may
            # be outdated and still have obsolete options.
            Options.update(conf, setter="server", fail_on_error=False)

            # Save this option so that it has direct effect at the next start
            key = "synchronization_enabled"
            if key in conf:
                value = conf[key]
                if not isinstance(value, bool):
                    log.warning(
                        f"Bad value from the server's config: {key!r}={value!r} (a boolean is required)"
                    )
                elif getattr(Options, key) is not value:
                    self.manager.dao.update_config(key, value)

                    # Does the application need to be restarted?
                    if not self.first_run:
                        self.manager.restartNeeded.emit()

            if self.first_run:
                self.first_run = False

                # Trigger a new auto-update check now that the server config has been fetched
                self.manager.updater.refresh_status()

            break

        return True


class SyncAndQuitWorker(PollWorker):
    """Class for checking if the application needs to be exited."""

    def __init__(self, manager: "Manager"):
        """Check every 10 seconds."""
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
