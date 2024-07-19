"""Poll Worker for Tasks Management Feature"""

from typing import TYPE_CHECKING

from nxdrive.engine.workers import PollWorker
from nxdrive.feature import Feature

from ..qt.imports import pyqtSlot

if TYPE_CHECKING:
    from ..manager import Manager  # noqa


class WorkflowWorker(PollWorker):
    """Class to check new Tasks for document review"""

    def __init__(self, manager: "Manager", /):
        """Check every hour"""
        super().__init__(60 * 60, "WorkflowWorker")
        self.manager = manager

        self._first_workflow_check = True

    @pyqtSlot(result=bool)
    def _poll(self) -> bool:
        """Start polling workflow after an hour. Initial trigger is via application"""

        if not self.manager:
            return False

        if self._first_workflow_check:
            self._first_workflow_check = False
            return True

        if self.manager.engines and Feature.tasks_management:
            self.app = self.manager.application
            self.workflow = self.app.workflow
            for engine in self.manager.engines.copy().values():
                self.workflow.get_pending_tasks(engine)
                if engine.uid == self.app.last_engine_uid:
                    task_list = str(
                        self.app.api.get_Tasks_list(
                            engine.uid, False, self.app.api.hide_refresh_button
                        )
                    )
                    if task_list != self.app.api.last_task_list:
                        self.app.api.last_task_list = task_list
                        if not self.app.api.engine_changed:
                            self.app.show_hide_refresh_button(30)
                            self.app.api.hide_refresh_button = False
                        else:
                            self.app.api.engine_changed = False

        return True
