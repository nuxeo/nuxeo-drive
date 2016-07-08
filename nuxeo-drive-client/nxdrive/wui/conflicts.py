'''
Created on 10 mars 2015

@author: Remi Cattiau
'''
from nxdrive.logging_config import get_logger
from nxdrive.wui.dialog import WebDialog, WebDriveApi
from nxdrive.wui.translator import Translator
from PyQt4 import QtCore
from Queue import PriorityQueue
from time import sleep
from datetime import timedelta, datetime
from nxdrive.engine.workers import Worker


log = get_logger(__name__)


class UserNameResolver(Worker):
    '''
        A separate thread to resolve the user-names one by one (id -> full user name)
    '''
    def __init__(self, results=dict(), to_resolve=PriorityQueue(), pending=set(), engine=None):
        super(UserNameResolver, self).__init__()
        self.to_resolve = to_resolve
        self.pending = pending
        self.results = results
        self.engine = engine
        self.started = False
        self.finished = False
        self._thread.started.connect(self.run)

    def restart(self):
        result = self
        if self.finished:
            result = UserNameResolver(self.results, self.to_resolve, self.pending, self.engine)
        if not result.started:
            log.trace("Starting UserNameResolver ...")
            result.start()
        return result

    def expired(self, last_refreshed):
        last_refreshed = datetime.strptime(last_refreshed.split('.')[0], '%Y-%m-%d %H:%M:%S')
        return last_refreshed < (datetime.now() - timedelta(days=1))

    def resolve_user(self, user_id):
        '''
            Get the user_info for given user_id
        '''
        if user_id in self.results:
            user_info = self.results[user_id]
        else:
            user_info = self.engine._dao.get_user_info(user_id)
            if user_info:
                self.results[user_id] = user_info

        # Queue the user_id, if it is not resolved or expired
        if user_info and not self.expired(user_info.last_refreshed):
            return user_info, False

        self.enqueue(user_id, user_info)
        return user_info, True

    def enqueue(self, user_id, user_info):
        '''
            Add the user_id to the PriorityQueue for resolution
        '''
        if user_id in self.pending:
            return
        # low priority for refreshing user full name
        if user_info:
            priority = 2
        else:
            priority = 1
        self.to_resolve.put((priority, user_id))
        self.pending.add(user_id)

    def update(self, user_id, user_info):
        self.results[user_id] = user_info
        self.pending.remove(user_id)

    def _execute(self):
        self.started = True
        while not self.to_resolve.empty():
            self._interact()
            priority, user_id = self.to_resolve.get()
            try:
                log.trace("retrieving %r" % user_id)
                user_info = self.engine.get_user_full_name(user_id)
                self.update(user_id, user_info)
            except Exception as e:
                log.exception(e)
                self.to_resolve.put((priority, user_id))
            sleep(0.01)
        self.finished = True


class WebConflictsApi(WebDriveApi):
    def __init__(self, application, engine, dlg=None):
        super(WebConflictsApi, self).__init__(application, dlg)
        self._manager = application.manager
        self._application = application
        self._dialog = dlg
        self._engine = engine
        self.resolver = UserNameResolver(engine=engine)

    def set_engine(self, engine):
        self._engine = engine

    @QtCore.pyqtSlot(result=str)
    def get_ignoreds(self):
        return super(WebConflictsApi, self).get_unsynchronizeds(self._engine._uid)

    @QtCore.pyqtSlot(result=str)
    def get_errors(self):
        return super(WebConflictsApi, self).get_errors(self._engine._uid)

    @QtCore.pyqtSlot(result=str)
    def get_conflicts(self):
        log.warn("Retrieving conflicts ...")
        return super(WebConflictsApi, self).get_conflicts(self._engine._uid)

    @QtCore.pyqtSlot(int)
    def resolve_with_local(self, state_id):
        try:
            self._engine.resolve_with_local(state_id)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(int)
    def resolve_with_remote(self, state_id):
        try:
            self._engine.resolve_with_remote(state_id)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(int)
    def resolve_with_duplicate(self, state_id):
        try:
            self._engine.resolve_with_duplicate(state_id)
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(int)
    def retry_pair(self, state_id):
        try:
            self._engine.retry_pair(int(state_id))
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(int)
    def unsynchronize_pair(self, state_id):
        try:
            self._engine.unsynchronize_pair(int(state_id), "MANUAL")
        except Exception as e:
            log.exception(e)

    @QtCore.pyqtSlot(str, result=str)
    def open_local(self, path):
        return super(WebConflictsApi, self).open_local(self._engine._uid, path)

    @QtCore.pyqtSlot(str, str, result=str)
    def open_remote(self, remote_ref, remote_name):
        remote_ref = str(remote_ref)
        remote_name = unicode(remote_name)
        log.debug("Should open this : %s (%s)", remote_name, remote_ref)
        try:
            self._engine.open_edit(remote_ref, remote_name)
        except Exception as e:
            log.exception(e)
        return ""

    def _export_state(self, state):
        if state is None:
            return None
        result = super(WebConflictsApi, self)._export_state(state)
        result["last_contributor"] = " "
        if state.last_remote_modifier:
            user_info, need_refresh = self.resolver.resolve_user(state.last_remote_modifier)
            if user_info:
                result["last_contributor"] = ("%s %s" % (user_info.first_name, user_info.last_name)).strip('(').strip(')')
            result["need_refresh"] = need_refresh
            if need_refresh:
                self.resolver = self.resolver.restart()
        date_time = self.get_date_from_sqlite(state.last_remote_updated)
        result["last_remote_update"] = "" if date_time == 0 else Translator.format_datetime(date_time)
        date_time = self.get_date_from_sqlite(state.last_local_updated)
        result["last_local_update"] = "" if date_time == 0 else Translator.format_datetime(date_time)
        result["remote_can_update"] = state.remote_can_update
        return result


class WebConflictsDialog(WebDialog):
    def set_engine(self, engine):
        self._api.set_engine(engine)