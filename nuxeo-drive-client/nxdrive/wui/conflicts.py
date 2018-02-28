# coding: utf-8
from logging import getLogger

from PyQt4 import QtCore

from nxdrive.wui.dialog import Promise, WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator

log = getLogger(__name__)


class WebConflictsApi(WebDriveApi):
    def __init__(self, application, engine, dlg=None):
        super(WebConflictsApi, self).__init__(application, dlg)
        self._manager = application.manager
        self.application = application
        self.dialog = dlg
        self._engine = engine
        self.retrieve_name = False

    def set_engine(self, engine):
        self._engine = engine

    @QtCore.pyqtSlot(result=str)
    def get_ignoreds(self):
        self.retrieve_name = False
        return super(WebConflictsApi, self).get_unsynchronizeds(self._engine.uid)

    @QtCore.pyqtSlot(result=str)
    def get_errors(self):
        self.retrieve_name = False
        return super(WebConflictsApi, self).get_errors(self._engine.uid)

    @QtCore.pyqtSlot(result=QtCore.QObject)
    def get_conflicts_with_fullname_async(self):
        self.retrieve_name = True
        return Promise(super(WebConflictsApi, self).get_conflicts, self._engine.uid)

    @QtCore.pyqtSlot(result=str)
    def get_conflicts(self):
        self.retrieve_name = False
        return super(WebConflictsApi, self).get_conflicts(self._engine.uid)

    @QtCore.pyqtSlot(int)
    def resolve_with_local(self, state_id):
        self._engine.resolve_with_local(state_id)

    @QtCore.pyqtSlot(int)
    def resolve_with_remote(self, state_id):
        self._engine.resolve_with_remote(state_id)

    @QtCore.pyqtSlot(int)
    def retry_pair(self, state_id):
        self._engine.retry_pair(state_id)

    @QtCore.pyqtSlot(int, str)
    def unsynchronize_pair(self, state_id, reason='UNKNOWN'):
        self._engine.unsynchronize_pair(state_id, reason=str(reason))

    @QtCore.pyqtSlot(str, result=str)
    def open_local(self, path):
        return super(WebConflictsApi, self).open_local(self._engine.uid, path)

    @QtCore.pyqtSlot(str, str)
    def open_remote(self, remote_ref, remote_name):
        remote_ref = str(remote_ref)
        remote_name = unicode(remote_name)
        log.debug("Should open this : %s (%s)", remote_name, remote_ref)
        try:
            self._engine.open_edit(remote_ref, remote_name)
        except OSError:
            log.exception('Remote open error')

    def _export_state(self, state):
        if state is None:
            return None
        result = super(WebConflictsApi, self)._export_state(state)
        result["last_contributor"] = " " if state.last_remote_modifier is None \
            else self._engine.get_user_full_name(state.last_remote_modifier, cache_only=not self.retrieve_name)
        date_time = self.get_date_from_sqlite(state.last_remote_updated)
        result["last_remote_update"] = "" if date_time == 0 else Translator.format_datetime(date_time)
        date_time = self.get_date_from_sqlite(state.last_local_updated)
        result["last_local_update"] = "" if date_time == 0 else Translator.format_datetime(date_time)
        result["remote_can_update"] = state.remote_can_update
        result['remote_can_rename'] = state.remote_can_rename
        return result
