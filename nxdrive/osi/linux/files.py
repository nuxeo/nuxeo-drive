# coding: utf-8
from typing import Iterator

from ...objects import Items

__all__ = ("get_other_opened_files",)


def get_other_opened_files() -> Iterator[Items]:
    """
    This is the function that calls other functions specialized in the
    retrieval of opened files that are not listed in the process list.
    See autolocker.py::get_opened_files() for those ones.
    """
    yield from []
