# conding: utfr-8
import os
from datetime import datetime
from logging import getLogger
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

from nxdrive.logging_config import MAX_LOG_DISPLAYED, get_handler

log = getLogger(__name__)


class Report(object):
    """
    Class to create a complete report useful for bug reports.

    Usage:

        report = Report(manager, output_dir)
        report.generate()
        final_path = report.get_path()

    TODO: More pythonic class

        with Report(manager, output_dir) as report:
            report.generate()
            final_path = report.path
    """

    def __init__(self, manager, report_path=None):
        self._manager = manager
        if not report_path:
            self._report_name = ('report_'
                                 + datetime.now().strftime('%y%m%d_%H%M%S'))
            folder = os.path.join(self._manager.nxdrive_home, 'reports')
        else:
            self._report_name = os.path.basename(report_path)
            folder = os.path.dirname(report_path)
        if not os.path.exists(folder):
            os.mkdir(folder)
        if not self._report_name.endswith('.zip'):
            self._report_name += '.zip'
        self._zipfile = os.path.join(folder, self._report_name)

    def copy_logs(self, myzip):
        """
        Copy all log files to the ZIP report.
        If one log file fails, we just try the next one.
        """

        folder = os.path.join(self._manager.nxdrive_home, 'logs')
        if not os.path.isdir(folder):
            return

        for fname in os.listdir(folder):
            path = os.path.join(folder, fname)
            if not os.path.isfile(path):
                continue
            if (fname not in ('nxdrive.log', 'segfault.log')
                    and not fname.endswith('.zip')):
                continue

            comp = ZIP_DEFLATED if fname.endswith('.log') else ZIP_STORED
            rel_path = os.path.join('logs', fname)
            try:
                myzip.write(path, rel_path, compress_type=comp)
            except:
                log.exception('Impossible to copy the log %s', rel_path)

    @staticmethod
    def copy_db(myzip, dao):
        """
        Copy a databse file to the ZIP report.
        If it fails, we just try ignore the file.
        """

        # Lock to avoid inconsistence
        dao._lock.acquire()
        try:
            myzip.write(dao._db, os.path.basename(dao._db),
                        compress_type=ZIP_DEFLATED)
        except:
            log.exception('Impossible to copy the database %s',
                          os.path.basename(dao._db))
        finally:
            dao._lock.release()

    def get_path(self):
        return self._zipfile

    @staticmethod
    def _export_logs():
        """
        Export all lines from the memory logger.

        :return bytes: bytes needed by zipfile.writestr()
        """

        handler = get_handler(getLogger(), 'memory')
        log_buffer = handler.get_buffer(MAX_LOG_DISPLAYED)

        for record in log_buffer:
            line = handler.format(record)
            if not isinstance(line, bytes):
                line = line.encode('utf-8', errors='replace')
            yield line

    def generate(self):
        """ Create the ZIP report with all interesting files. """

        log.debug('Create report %r', self._zipfile)
        log.debug('Manager metrics: %r', self._manager.get_metrics())
        dao = self._manager.get_dao()
        with ZipFile(self._zipfile, mode='w', allowZip64=True) as zip_:
            # Databases
            self.copy_db(zip_, dao)
            for engine in self._manager.get_engines().values():
                log.debug('Engine metrics: %r', engine.get_metrics())
                self.copy_db(zip_, engine.get_dao())

            # Logs
            self.copy_logs(zip_)

            # Memory logger -> debug.log
            try:
                lines = b'\n'.join(list(self._export_logs()))
                zip_.writestr('debug.log', lines, compress_type=ZIP_DEFLATED)
            except:
                log.exception('Impossible to get lines from the memory logger')
