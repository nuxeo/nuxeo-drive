# conding: utfr-8
import codecs
import os
from datetime import datetime
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

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

        def compress(path_, filename):
            """ Zip a log file. """

            zpath = path + '.zip'
            fmt = 'Zipping report {} ({:,} ko)'
            fmt_zipped = 'Zipped report  {}: {:,} ko -> {:,} ko'

            log.debug(fmt.format(filename, os.stat(path_).st_size / 1024))

            with ZipFile(zpath, mode='w', compression=ZIP_DEFLATED) as zip_:
                zip_.write(path_, filename)
                log.trace(fmt_zipped.format(filename,
                                            os.stat(path_).st_size / 1024,
                                            os.stat(zpath).st_size / 1024))
                os.unlink(path_)

            return zpath, filename + '.zip'

        for fname in os.listdir(folder):
            path = os.path.join(folder, fname)
            if not os.path.isfile(path):
                continue

            comp = ZIP_DEFLATED if fname.endswith('.log') else ZIP_STORED
            if fname.startswith('nxdrive.log.') and not fname.endswith('.zip'):
                path, fname = compress(path, fname)
            rel_path = os.path.join('logs', fname)
            myzip.write(path, rel_path, compress_type=comp)

    @staticmethod
    def copy_db(myzip, dao):
        # Lock to avoid inconsistence
        dao._lock.acquire()
        try:
            myzip.write(dao._db, os.path.basename(dao._db),
                        compress_type=ZIP_DEFLATED)
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
            try:
                line = handler.format(record)
            except UnicodeEncodeError:
                log.error('Log record encoding error: %r', record.__dict__)
                line = record.getMessage()
                if isinstance(line, Exception):
                    line = str(line)
            if isinstance(line, bytes):
                line = line.decode('utf-8', errors='replace')
            yield line

    def generate(self):
        log.debug('Create report %r', self._report_name)
        log.debug('Manager metrics: %r', self._manager.get_metrics())
        with ZipFile(self._zipfile, mode='w') as zip_:
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
            zip_.write('debug.log', compress_type=ZIP_DEFLATED)
            os.unlink('debug.log')
