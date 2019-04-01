# coding: utf-8
""" Utilities to log nxdrive operations and failures. """

import logging
import os
from logging import Formatter
from logging.handlers import BufferingHandler, TimedRotatingFileHandler
from typing import Any, List
from zipfile import ZIP_DEFLATED, ZipFile

from . import constants
from .options import Options

__all__ = ("configure", "get_handler")

# Default formatter
FORMAT = Formatter(
    "%(asctime)s %(process)d %(thread)d %(levelname)-8s %(name)-18s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR"}
DEFAULT_LEVEL_CONSOLE = "WARNING"
DEFAULT_LEVEL_FILE = "INFO"

# Singleton logging context for each process.
# Alternatively we could use the setproctitle to handle the command name
# package and directly change the real process name but this requires to build
# a compiled extension under Windows...

_logging_context = dict()

is_logging_configured = False


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
            if size > 0:
                return self.buffer[:size]  # type: ignore
            return self.buffer[size:]  # type: ignore
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


def no_trace(level: str) -> str:
    level = level.upper()
    if level == "TRACE":
        logging.getLogger().warning(
            "TRACE level is deprecated since 4.1.0. Please use DEBUG instead."
        )
        level = "DEBUG"
    return level


def configure(
    log_filename: str = None,
    file_level: str = DEFAULT_LEVEL_FILE,
    console_level: str = DEFAULT_LEVEL_CONSOLE,
    command_name: str = None,
    force_configure: bool = False,
    formatter: Formatter = None,
) -> None:

    global is_logging_configured

    if is_logging_configured and not force_configure:
        return

    is_logging_configured = True
    _logging_context["command"] = command_name
    formatter = formatter or FORMAT

    # Set to the minimum level to avoid filtering by the root logger itself
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Add memory logger to allow instant report
    memory_handler = get_handler("memory")
    if not memory_handler:
        memory_handler = CustomMemoryHandler()
        memory_handler.set_name("memory")  # type: ignore
        memory_handler.setFormatter(formatter)
        memory_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(memory_handler)

    # Define a Handler which writes messages to sys.stderr
    console_level = get_level(console_level, DEFAULT_LEVEL_CONSOLE)
    console_handler = get_handler("nxdrive_console")
    if not console_handler:
        console_handler = logging.StreamHandler()
        console_handler.set_name("nxdrive_console")  # type: ignore
        console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)
        root_logger.addHandler(console_handler)
    else:
        console_handler.setLevel(console_level)

    # Define a handler for file based log with rotation if needed
    file_level = get_level(file_level, DEFAULT_LEVEL_FILE)
    file_handler = get_handler("nxdrive_file")
    if log_filename:
        file_handler = TimedCompressedRotatingFileHandler(
            log_filename, when="midnight", backupCount=30
        )
        file_handler.set_name("nxdrive_file")  # type: ignore
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_level)
        root_logger.addHandler(file_handler)
    elif file_handler:
        file_handler.setLevel(file_level)


def get_handler(name: str):
    for handler in logging.getLogger().handlers:
        if handler.get_name() == name:  # type: ignore
            return handler
    return None


def get_level(level: str, default: str) -> str:
    try:
        check_level(level)
        return no_trace(level)
    except ValueError as exc:
        logging.getLogger().warning(str(exc))
        return default


def check_level(level: str) -> str:
    """Handle bad logging level."""
    try:
        level = no_trace(level)
        logging._nameToLevel[level]
    except (AttributeError, ValueError, KeyError):
        err = f"Unknown logging level {level!r}, need to be one of {LOG_LEVELS}."
        raise ValueError(err)
    else:
        return level


def update_logger_console(level: str) -> None:
    handler = get_handler("nxdrive_console")
    if handler:
        handler.setLevel(level)


def update_logger_file(level: str) -> None:
    handler = get_handler("nxdrive_file")
    if handler:
        handler.setLevel(level)


# Install logs callbacks
Options.checkers["log_level_console"] = check_level
Options.checkers["log_level_file"] = check_level
Options.callbacks["log_level_console"] = update_logger_console
Options.callbacks["log_level_file"] = update_logger_file
