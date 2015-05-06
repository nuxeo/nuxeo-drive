'''
Created on 6 mai 2015

@author: Remi Cattiau
'''
import os
from datetime import datetime
from nxdrive.logging_config import get_logger, get_handler, MAX_LOG_DISPLAYED
from zipfile import ZipFile

log = get_logger(__name__)


class Report(object):
    '''
    classdocs
    '''

    def __init__(self, manager):
        '''
        Constructor
        '''
        self._manager = manager
        self._report_name = 'report_' + datetime.now().strftime('%y%m%d_%H%M%S')
        folder = os.path.join(self._manager.get_configuration_folder(), 'reports')
        if not os.path.exists(folder):
            os.mkdir(folder)
        self._zipfile = os.path.join(self._manager.get_configuration_folder(),
                              'reports', self._report_name + '.zip')

    def copy_db(self, myzip, dao):
        # Lock to avoid inconsistence
        dao._lock.acquire()
        try:
            myzip.write(dao._db, os.path.basename(dao._db))
        finally:
            dao._lock.release()

    def get_path(self):
        return self._zipfile

    def _export_logs(self):
        logs = ""
        logger = get_logger(None)
        handler = get_handler(logger, "memory")
        log_buffer = handler.get_buffer(MAX_LOG_DISPLAYED)
        for record in log_buffer:
            logs = logs + handler.format(record) + "\n"
        return logs

    def generate(self):
        log.debug("Create report '%s'", self._report_name)
        log.debug("Manager metrics: '%s'", self._manager.get_metrics())
        with ZipFile(self._zipfile, 'w') as myzip:
            dao = self._manager.get_dao()
            self.copy_db(myzip, dao)
            for engine in self._manager.get_engines().values():
                log.debug("Engine metrics: '%s'", engine.get_metrics())
                self.copy_db(myzip, engine.get_dao())
                # Might want threads too here
            myzip.writestr("debug.log", self._export_logs())
