# coding: utf-8
from logging import getLogger
from typing import Any, Dict, List

from PyQt5.QtCore import QSize, QUrl, pyqtSlot

from .dialog import QMLDriveApi
from .view import FileModel, NuxeoView
from ..translator import Translator
from ..utils import find_resource

__all__ = ("ConflictsView",)

log = getLogger(__name__)

ListDict = List[Dict[str, Any]]


class QMLConflictsApi(QMLDriveApi):
    def __init__(self, application: "Application", engine: "Engine") -> None:
        super().__init__(application)
        self._manager = application.manager
        self.application = application
        self._engine = engine

    def set_engine(self, engine: "Engine") -> None:
        self._engine = engine

    def get_ignoreds(self) -> ListDict:
        return super().get_unsynchronizeds(self._engine.uid)

    def get_errors(self) -> ListDict:
        return super().get_errors(self._engine.uid)

    def get_conflicts(self) -> ListDict:
        return super().get_conflicts(self._engine.uid)

    @pyqtSlot(int)
    def resolve_with_local(self, state_id: int) -> None:
        self._engine.resolve_with_local(state_id)

    @pyqtSlot(int)
    def resolve_with_remote(self, state_id: int) -> None:
        self._engine.resolve_with_remote(state_id)

    @pyqtSlot(int)
    def retry_pair(self, state_id: int) -> None:
        self._engine.retry_pair(state_id)

    @pyqtSlot(int, str)
    def unsynchronize_pair(self, state_id: int, reason: str = "UNKNOWN") -> None:
        self._engine.unsynchronize_pair(state_id, reason=reason)

    @pyqtSlot(str)
    def open_local(self, path: str) -> None:
        super().open_local(self._engine.uid, path)

    @pyqtSlot(str, str)
    def open_remote(self, remote_ref: str, remote_name: str) -> None:
        log.debug("Should open this : %s (%s)", remote_name, remote_ref)
        try:
            self._engine.open_edit(remote_ref, remote_name)
        except OSError:
            log.exception("Remote open error")

    def _export_state(self, state: "DocPair" = None) -> Dict[str, Any]:
        if state is None:
            return {}
        result = super()._export_state(state)
        result["last_contributor"] = (
            ""
            if state.last_remote_modifier is None
            else self._engine.get_user_full_name(
                state.last_remote_modifier, cache_only=True
            )
        )
        date_time = self.get_date_from_sqlite(state.last_remote_updated)
        result["last_remote_update"] = (
            Translator.format_datetime(date_time) if date_time else ""
        )
        date_time = self.get_date_from_sqlite(state.last_local_updated)
        result["last_local_update"] = (
            Translator.format_datetime(date_time) if date_time else ""
        )
        result["remote_can_update"] = state.remote_can_update
        result["remote_can_rename"] = state.remote_can_rename
        result["details"] = state.last_error_details or ""
        return result


class ConflictsView(NuxeoView):
    def __init__(self, application: "Application", engine: "Engine") -> None:
        super().__init__(application, QMLConflictsApi(application, engine))

        size = QSize(550, 600)
        self.setMinimumSize(size)
        self.setMaximumSize(size)

        self.conflicts_model = FileModel()
        self.ignoreds_model = FileModel()

        context = self.rootContext()
        context.setContextProperty("Conflicts", self)
        context.setContextProperty("ConflictsModel", self.conflicts_model)
        context.setContextProperty("IgnoredsModel", self.ignoreds_model)

        self.init()

    def init(self) -> None:
        super().init()

        self.setSource(QUrl.fromLocalFile(find_resource("qml", "Conflicts.qml")))
        self.rootObject().changed.connect(self.refresh_models)

    def refresh_models(self) -> None:
        self.conflicts_model.empty()
        self.ignoreds_model.empty()

        self.conflicts_model.addFiles(self.api.get_conflicts())
        self.conflicts_model.addFiles(self.api.get_errors())
        self.ignoreds_model.addFiles(self.api.get_ignoreds())

    def set_engine(self, engine: "Engine") -> None:
        self.api.set_engine(engine)
        self.refresh_models()
