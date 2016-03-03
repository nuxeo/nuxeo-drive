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

    def __init__(self, manager, report_path=None):
        '''
        Constructor
        '''
        self._manager = manager
        if report_path is None:
            self._report_name = 'report_' + datetime.now().strftime('%y%m%d_%H%M%S')
            folder = os.path.join(self._manager.get_configuration_folder(), 'reports')
        else:
            self._report_name = os.path.basename(report_path)
            folder = os.path.dirname(report_path)
        if not os.path.exists(folder):
            os.mkdir(folder)
        self._zipfile = os.path.join(folder, self._report_name + '.zip')

    def copy_logs(self, myzip):
        try:
            folder = os.path.join(self._manager.get_configuration_folder(), 'logs')
            for filename in os.listdir(folder):
                path = os.path.join(folder, filename)
                if not os.path.isfile(path):
                    continue
                myzip.write(path, os.path.join('logs/', filename))
        except:
            # Do not prevent report to work on copy errors
            pass

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
        logs = u""
        logger = get_logger(None)
        handler = get_handler(logger, "memory")
        log_buffer = handler.get_buffer(MAX_LOG_DISPLAYED)
        for record in log_buffer:
            try:
                log = handler.format(record).decode("utf-8", errors="replace")
            except UnicodeEncodeError:
                log = handler.format(record)
            logs = logs + log + u"\n"
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
            self.copy_logs(myzip)
            myzip.writestr("debug.log", self._export_logs().encode('utf-8', errors="ignore").strip())
