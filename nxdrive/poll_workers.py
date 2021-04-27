import logging
from typing import TYPE_CHECKING

from .behavior import Behavior
from .engine.workers import PollWorker
from .options import Options
from .qt.imports import pyqtSignal, pyqtSlot
from .updater.constants import UPDATE_STATUS_UPDATING
from .utils import normalize_and_expand_path

if TYPE_CHECKING:
    from .manager import Manager  # noqa


log = logging.getLogger(__name__)


class DatabaseBackupWorker(PollWorker):
    """Class for making backups of the manager and engine databases."""

    def __init__(self, manager: "Manager", /):
        """Backup every hour."""
        super().__init__(60 * 60, "DatabaseBackup")
        self.manager = manager

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """Perform the backups."""

        if not self.manager:
            return False

        if self.manager.dao:
            self.manager.dao.save_backup()

        for engine in self.manager.engines.copy().values():
            if engine.dao:
                engine.dao.save_backup()

        return True


class ServerOptionsUpdater(PollWorker):
    """Class for checking the server's config.json updates."""

    # A signal to let other component know that the first run has been done
    firstRunCompleted = pyqtSignal()

    def __init__(self, manager: "Manager", /):
        default_delay = 60 * 60  # 1 hour
        # The check will be done every *update_check_delay* seconds or *default_delay*
        # when the channel is centralized.
        delay = Options.update_check_delay or default_delay
        super().__init__(delay, "ServerOptionsUpdater")
        self.manager = manager

        # Notify the Manager that the server's config has been fetched at least one time.
        # This will be used later in the Updater.
        self.first_run = True
        self.firstRunCompleted.connect(self._first_run_done)

    def _first_run_done(self) -> None:
        """Simple helper to set the attribute's value.
        That value will be used in other components.
        """
        self.first_run = False

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """Check for the configuration file and apply updates."""

        for engine in self.manager.engines.copy().values():
            if not engine.remote:
                continue

            conf = engine.remote.get_server_configuration()
            if not conf:
                engine.set_ui("web", overwrite=False)
                continue

            engine.set_ui(conf.pop("ui", "web"), overwrite=False)

            # Compat with old servers
            beta = conf.pop("beta_channel", False)
            if beta:
                conf["channel"] = "beta"

            if "nxdrive_home" in conf:
                # Expand eventuel envars like %userprofile% and co.
                conf["nxdrive_home"] = normalize_and_expand_path(conf["nxdrive_home"])

            # Behavior can only be set from the server config,
            # so the following logic can be kept here only.
            if "behavior" in conf:
                for behavior, value in conf["behavior"].items():
                    behavior = behavior.replace("-", "_").lower()
                    if not hasattr(Behavior, behavior):
                        log.warning(f"Invalid behavior: {behavior!r}")
                    elif not isinstance(value, bool):
                        log.warning(
                            f"Invalid behavior value: {value!r} (a boolean is required)"
                        )
                    elif getattr(Behavior, behavior) is not value:
                        log.warning(f"Updating behavior {behavior!r} to {value!r}")
                        setattr(Behavior, behavior, value)
                del conf["behavior"]

            # Features needs to be reworked to match the format in Options
            # (this is a limitation of the local config format)
            old_feature_sync = Options.feature_synchronization
            if "feature" in conf:
                for feature, value in conf["feature"].items():
                    feature = feature.replace("-", "_").lower()
                    self.manager.set_feature_state(feature, value, setter="server")
                del conf["feature"]

            # We cannot use fail_on_error=True because the server may
            # be outdated and still have obsolete options.
            Options.update(conf, setter="server", fail_on_error=False)

            #  If the feature_synchronization state has changed a restart must be done
            if (
                not self.first_run
                and Options.feature_synchronization != old_feature_sync
            ):
                self.manager.restartNeeded.emit()

            if self.first_run:
                self.firstRunCompleted.emit()

            break

        return True


class SyncAndQuitWorker(PollWorker):
    """Class for checking if the application needs to be exited."""

    def __init__(self, manager: "Manager", /):
        """Check every 10 seconds."""
        super().__init__(10, "SyncAndQuit")
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
