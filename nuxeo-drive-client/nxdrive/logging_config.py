# coding: utf-8
""" Utilities to log nxdrive operations and failures. """

import logging
import os
from logging.handlers import BufferingHandler, RotatingFileHandler, \
    TimedRotatingFileHandler
from zipfile import ZIP_DEFLATED, ZipFile

from nxdrive.options import Options

TRACE = 5
logging.addLevelName(TRACE, 'TRACE')
logging.TRACE = TRACE
FILE_HANDLER = None

# Singleton logging context for each process.
# Alternatively we could use the setproctitle to handle the command name
# package and directly change the real process name but this requires to build
# a compiled extension under Windows...

_logging_context = dict()

is_logging_configured = False
MAX_LOG_DISPLAYED = 50000


class CustomMemoryHandler(BufferingHandler):
    def __init__(self, capacity=MAX_LOG_DISPLAYED):
        super(CustomMemoryHandler, self).__init__(capacity)
        self.old_buffer_ = None

    def flush(self):
        self.acquire()
        try:
            self.old_buffer_, self.buffer = self.buffer[:], []
        finally:
            self.release()

    def get_buffer(self, size):
        self.acquire()
        try:
            result = self.buffer[:]
            if len(result) < size and self.old_buffer_:
                result += self.old_buffer_[size - len(result) - 1:]
        finally:
            self.release()
        return result


class TimedCompressedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Extended version of TimedRotatingFileHandler that compress logs on rollover.
    """

    def find_last_rotated_file(self):
        dir_name, base_name = os.path.split(self.baseFilename)
        file_names = os.listdir(dir_name)
        result = []
        # We want to find a rotated file with eg filename.2017-04-26... name
        prefix = '{}.20'.format(base_name)
        for file_name in file_names:
            if file_name.startswith(prefix) and not file_name.endswith('.zip'):
                result.append(file_name)
        result.sort()
        return os.path.join(dir_name, result[0])

    def doRollover(self):
        super(TimedCompressedRotatingFileHandler, self).doRollover()

        dfn = self.find_last_rotated_file()
        dfn_zipped = '{}.zip'.format(dfn)
        with open(dfn, 'rb') as reader, ZipFile(dfn_zipped, mode='w') as zip_:
            zip_.writestr(os.path.basename(dfn), reader.read(), ZIP_DEFLATED)
        os.remove(dfn)


def configure(use_file_handler=False, log_filename=None, file_level='TRACE',
              console_level='INFO', filter_inotify=True, command_name=None,
              log_rotate_keep=30, log_rotate_max_bytes=None,
              log_rotate_when=None, force_configure=False):

    global is_logging_configured
    global FILE_HANDLER

    if not is_logging_configured or force_configure:
        is_logging_configured = True

        _logging_context['command'] = command_name

        if not file_level:
            file_level = 'TRACE'

        # Convert string levels
        if hasattr(file_level, 'upper'):
            file_level = getattr(logging, file_level.upper())
        if hasattr(console_level, 'upper'):
            console_level = getattr(logging, console_level.upper())

        # Find the minimum level to avoid filtering by the root logger itself
        root_logger = logging.getLogger()
        min_level = min(file_level, console_level)
        root_logger.setLevel(min_level)

        # Define the formatter
        formatter = logging.Formatter('%(asctime)s %(process)d %(thread)d '
                                      '%(levelname)-8s %(name)-18s %(message)s',
                                      datefmt='%Y-%m-%d %H:%M:%S')

        # Define a Handler which writes INFO messages or higher to the
        # sys.stderr
        console_handler_name = 'console'
        console_handler = get_handler(root_logger, console_handler_name)
        if not console_handler:
            console_handler = logging.StreamHandler()
            console_handler.set_name(console_handler_name)
            # tell the console handler to use this format
            console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)

        # Add the console handler to the root logger and all descendants
        root_logger.addHandler(console_handler)

        # Define a Handler for file based log with rotation if needed
        if use_file_handler and log_filename:
            log_filename = os.path.expanduser(log_filename)
            log_folder = os.path.dirname(log_filename)
            if not os.path.exists(log_folder):
                os.makedirs(log_folder)
            if not log_rotate_when and not log_rotate_max_bytes:
                log_rotate_when = 'midnight'
            if log_rotate_when:
                file_handler = TimedCompressedRotatingFileHandler(
                    log_filename, when=log_rotate_when,
                    backupCount=log_rotate_keep)
            elif log_rotate_max_bytes:
                file_handler = RotatingFileHandler(
                    log_filename, maxBytes=log_rotate_max_bytes,
                    backupCount=log_rotate_keep)
            file_handler.set_name('file')
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            FILE_HANDLER = file_handler
            root_logger.addHandler(file_handler)

        # Add memory logger to allow instant report
        memory_handler = CustomMemoryHandler()
        memory_handler.setLevel(TRACE)
        memory_handler.set_name('memory')
        memory_handler.setFormatter(formatter)
        root_logger.addHandler(memory_handler)
        if filter_inotify:
            root_logger.addFilter(
                logging.Filter('watchdog.observers.inotify_buffer'))


def get_handler(logger, name):
    for handler in logger.handlers:
        if name == handler.get_name():
            return handler
    return None


def get_logger(name):
    logger = logging.getLogger(name)

    def trace(*args, **kwargs):
        logger.log(TRACE, *args, **kwargs)

    setattr(logger, 'trace', trace)
    return logger


def update_logger_console(log_level):
    logging.getLogger().setLevel(
        min(log_level, logging.getLogger().getEffectiveLevel()))


def update_logger_file(log_level):
    if FILE_HANDLER:
        FILE_HANDLER.setLevel(log_level)


# Install logs callbacks
Options.callbacks['log_level_console'] = update_logger_console
Options.callbacks['log_level_file'] = update_logger_file
