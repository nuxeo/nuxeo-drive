# coding: utf-8
""" Utilities to log nxdrive operations and failures. """

import logging
import os
import os.path
from logging import Formatter
from logging.handlers import BufferingHandler, TimedRotatingFileHandler
from typing import Any, Generator, List
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
        self.checkup()

    def checkup(self) -> None:
        """Ensure the log files are purged and compressed."""
        self.compress_all()
        self.remove_old_files()

    def find_rotated_files(self) -> Generator[str, None, None]:
        """Find all rotated log files (compressed and raw)."""
        folder, filename = os.path.split(self.baseFilename)
        for file in os.listdir(folder):
            # We want to find a rotated file with e.g. "file.log.2017-04-26" and "file.log.2019-09-25.zip" names
            if file.startswith(f"{filename}.20"):
                yield os.path.join(folder, file)

    def compress(self, file: str) -> None:
        """Compress one rotated log file."""
        with open(file, "rb") as f, ZipFile(f"{file}.zip", mode="w") as z:
            z.writestr(os.path.basename(file), f.read(), ZIP_DEFLATED)
        os.remove(file)

    def compress_all(self, file: str = "") -> None:
        """Compress all rotated log files."""
        for file in self.find_rotated_files():
            if not file.endswith(".zip") and os.path.isfile(file):
                try:
                    self.compress(file)
                except OSError:
                    pass

    def remove_old_files(self) -> None:
        """Remove old rotated log files. Keeping only *.backupCount* files, removing the oldest ones."""
        count = getattr(self, "backupCount", 30)
        files = sorted(self.find_rotated_files(), reverse=True)
        for number, file in enumerate(files, 1):
            if number > count and file.endswith(".zip"):
                os.remove(file)

    def doRollover(self) -> None:
        super().doRollover()
        self.checkup()


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

    # NXDRIVE-1774: filter out urllib3 logging about "Certificate did not match..."
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)


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
        logging._nameToLevel[level]  # pylint: disable=protected-access
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
