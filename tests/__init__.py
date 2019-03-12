import logging
import os
import os.path
import shutil

import nuxeo.constants

from nxdrive.logging_config import configure


# Automatically check all operations done with the Python client
nuxeo.constants.CHECK_PARAMS = True


def _basename(path: str) -> str:
    """
    Patch shutil._basename for pathlib compatibility.
    TODO: remove when https://bugs.python.org/issue32689 is fixed (Python 3.7.3 or newer)
    """
    if isinstance(path, os.PathLike):
        return path.name

    sep = os.path.sep + (os.path.altsep or "")
    return os.path.basename(path.rstrip(sep))


shutil._basename = _basename


def configure_logs():
    """Configure the logging module."""

    formatter = logging.Formatter(
        "%(thread)-4d %(module)-14s %(levelname).1s %(message)s"
    )
    configure(
        console_level="DEBUG",
        command_name="test",
        force_configure=True,
        formatter=formatter,
    )


configure_logs()
