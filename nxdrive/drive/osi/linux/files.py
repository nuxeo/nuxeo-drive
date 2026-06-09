from typing import Iterator

from ...objects import Item

__all__ = ("get_other_opened_files",)


def get_other_opened_files() -> Iterator[Item]:
    """
    This is the function that calls other functions specialized in the
    retrieval of opened files that are not listed in the process list.
    See autolocker.py::get_opened_files() for those ones.
    """
    yield from []
