# conding: utfr-8
import codecs
import os
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED

from nxdrive.logging_config import MAX_LOG_DISPLAYED, get_handler, get_logger

log = get_logger(__name__)


class Report(object):

    def __init__(self, manager, report_path=None):
        self._manager = manager
        if not report_path:
            self._report_name = 'report_' \
                                + datetime.now().strftime('%y%m%d_%H%M%S')
            folder = os.path.join(self._manager.get_configuration_folder(),
                                  'reports')
        else:
            self._report_name = os.path.basename(report_path)
            folder = os.path.dirname(report_path)
        if not os.path.exists(folder):
            os.mkdir(folder)
        self._zipfile = os.path.join(folder, self._report_name + '.zip')

    def copy_logs(self, myzip):
        folder = os.path.join(self._manager.get_configuration_folder(), 'logs')
        if not os.path.isdir(folder):
            return

        for filename in os.listdir(folder):
            path = os.path.join(folder, filename)
            if os.path.isfile(path):
                myzip.write(path, os.path.join('logs', filename))

    @staticmethod
    def copy_db(myzip, dao):
        # Lock to avoid inconsistence
        dao._lock.acquire()
        try:
            myzip.write(dao._db, os.path.basename(dao._db))
        finally:
            dao._lock.release()

    def get_path(self):
        return self._zipfile

    @staticmethod
    def _export_logs():
        logger = get_logger(None)
        handler = get_handler(logger, 'memory')
        log_buffer = handler.get_buffer(MAX_LOG_DISPLAYED)
        for record in log_buffer:
            line = handler.format(record)
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            yield line

    def generate(self):
        log.debug('Create report %r', self._report_name)
        log.debug('Manager metrics: %r', self._manager.get_metrics())
        with ZipFile(self._zipfile, mode='w', compression=ZIP_DEFLATED) as zip_:
            dao = self._manager.get_dao()
            self.copy_db(zip_, dao)
            for engine in self._manager.get_engines().values():
                log.debug('Engine metrics: %r', engine.get_metrics())
                self.copy_db(zip_, engine.get_dao())
                # Might want threads too here
            self.copy_logs(zip_)

            # Memory efficient debug.log creation
            with codecs.open('debug.log', mode='wb', encoding='utf-8',
                             errors='replace') as output:
                for line in self._export_logs():
                    output.write(line + '\n')
            zip_.write('debug.log')
            os.unlink('debug.log')
