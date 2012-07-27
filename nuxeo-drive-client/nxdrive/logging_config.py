"""Utilities to log nxdrive operations and failures"""

import logging
from logging.handlers import RotatingFileHandler
import os


def configure(log_filename, file_level='INFO', console_level='INFO',
              process_name="", log_rotate_keep=5,
              log_rotate_max_bytes=1000000):

    # convert string levels
    if hasattr(file_level, 'upper'):
        file_level = getattr(logging, file_level.upper())
    if hasattr(console_level, 'upper'):
        console_level = getattr(logging, console_level.upper())

    # find the minimum level to avoid filtering by the root logger itself:
    root_logger = logging.getLogger()
    min_level = min(file_level, console_level)
    root_logger.setLevel(min_level)

    # define a Handler for file based log with rotation
    log_filename = os.path.expanduser(log_filename)
    log_folder = os.path.dirname(log_filename)
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    file_handler = RotatingFileHandler(
        log_filename, mode='a', maxBytes=log_rotate_max_bytes,
        backupCount=log_rotate_keep)
    file_handler.setLevel(file_level)


    # define a Handler which writes INFO messages or higher to the sys.stderr
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)

    # define the formatter
    # TODO: add filter for process name and update format
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)-8s %(name)-18s %(message)s"
    )

    # tell the handler to use this format
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    # add the handler to the root logger and all descendants
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
