# coding: utf-8
""" Utilities to log nxdrive operations and failures. """

import logging
import os
from logging.handlers import BufferingHandler, TimedRotatingFileHandler
from typing import Any, List
from zipfile import ZIP_DEFLATED, ZipFile

from . import constants
from .options import Options

__all__ = ("configure", "get_handler")

FILE_HANDLER = None
TRACE = 5
TRACE_ADDED = False

# Default formatter
FORMAT = logging.Formatter(
    "%(asctime)s %(process)d %(thread)d %(levelname)-8s %(name)-18s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Singleton logging context for each process.
# Alternatively we could use the setproctitle to handle the command name
# package and directly change the real process name but this requires to build
# a compiled extension under Windows...

_logging_context = dict()

is_logging_configured = False


def add_trace_level() -> None:
    """ Add 'trace' level to all loggers. """

    global TRACE_ADDED
    if TRACE_ADDED:
        return

    logging.addLevelName(TRACE, "TRACE")
    logging.TRACE = TRACE

    def trace(self, message, *args, **kws):
        if self.isEnabledFor(TRACE):
            self._log(TRACE, message, args, **kws)

    logging.Logger.trace = trace
    TRACE_ADDED = True


add_trace_level()


class CustomMemoryHandler(BufferingHandler):
    def __init__(self, capacity: int = constants.MAX_LOG_DISPLAYED) -> None:
        super().__init__(capacity)

    def get_buffer(self, size: int) -> List[str]:
        """
        If `size` is positive, returns the first `size` lines from the memory buffer.
        If `size` is negative, returns the last `size` lines from the memory buffer.
        By default, `size` is equal to the buffer length, so the entire buffer is returned.
        """
        self.acquire()
        try:
            return self.buffer[:size] if size > 0 else self.buffer[size:]
        finally:
            self.release()


class TimedCompressedRotatingFileHandler(TimedRotatingFileHandler):
    """
    Extended version of TimedRotatingFileHandler that compress logs on rollover.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Set UTF-8 as default encoding to prevent logging issues
        on Windows with non-latin characters."""
        kwargs["encoding"] = "utf-8"
        super().__init__(*args, **kwargs)

    def find_last_rotated_file(self) -> str:
        dir_name, base_name = os.path.split(self.baseFilename)
        file_names = os.listdir(dir_name)
        result = []
        # We want to find a rotated file with eg filename.2017-04-26... name
        prefix = f"{base_name}.20"
        for file_name in file_names:
            if file_name.startswith(prefix) and not file_name.endswith(".zip"):
                result.append(file_name)
        result.sort()
        return os.path.join(dir_name, result[0])

    def doRollover(self) -> None:
        super().doRollover()

        dfn = self.find_last_rotated_file()
        dfn_zipped = f"{dfn}.zip"
        with open(dfn, "rb") as reader, ZipFile(dfn_zipped, mode="w") as zip_:
            zip_.writestr(os.path.basename(dfn), reader.read(), ZIP_DEFLATED)
        os.remove(dfn)


def configure(
    log_filename: str = None,
    file_level: str = "TRACE",
    console_level: str = "INFO",
    command_name: str = None,
    force_configure: bool = False,
    formatter: logging.Formatter = None,
) -> None:

    global is_logging_configured
    global FILE_HANDLER

    if not is_logging_configured or force_configure:
        is_logging_configured = True

        _logging_context["command"] = command_name

        if not file_level:
            file_level = "TRACE"
        file_level = getattr(logging, file_level.upper())
        console_level = getattr(logging, console_level.upper())

        # Find the minimum level to avoid filtering by the root logger itself
        root_logger = logging.getLogger()
        min_level = min(file_level, console_level)
        root_logger.setLevel(min_level)

        # Define the formatter
        formatter = formatter or FORMAT

        # Define a Handler which writes INFO messages or higher to the
        # sys.stderr
        console_handler_name = "console"
        console_handler = get_handler(root_logger, console_handler_name)
        if not console_handler:
            console_handler = logging.StreamHandler()
            console_handler.set_name(console_handler_name)
            console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)

        # Add the console handler to the root logger and all descendants
        root_logger.addHandler(console_handler)

        # Define a Handler for file based log with rotation if needed
        if log_filename:
            file_handler = TimedCompressedRotatingFileHandler(
                log_filename, when="midnight", backupCount=30
            )
            file_handler.set_name("file")
            file_handler.setLevel(file_level)
            file_handler.setFormatter(formatter)
            FILE_HANDLER = file_handler
            root_logger.addHandler(file_handler)

        # Add memory logger to allow instant report
        memory_handler = CustomMemoryHandler()
        memory_handler.setLevel(TRACE)
        memory_handler.set_name("memory")
        memory_handler.setFormatter(formatter)
        root_logger.addHandler(memory_handler)


def get_handler(logger: logging.Logger, name: str):
    for handler in logger.handlers:
        if name == handler.get_name():
            return handler
    return None


def update_logger_console(log_level: str) -> None:
    logging.getLogger().setLevel(
        min(getattr(logging, log_level), logging.getLogger().getEffectiveLevel())
    )


def update_logger_file(log_level: str) -> None:
    if FILE_HANDLER:
        FILE_HANDLER.setLevel(log_level)


# Install logs callbacks
Options.callbacks["log_level_console"] = update_logger_console
Options.callbacks["log_level_file"] = update_logger_file
