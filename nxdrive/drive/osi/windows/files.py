from contextlib import suppress
from pathlib import Path
from typing import Iterator

from win32com.client import GetActiveObject

from ...objects import Item
from ...utils import compute_fake_pid_from_path

__all__ = ("get_other_opened_files",)


def _get_opened_files_adobe_cc(obj: str, /) -> Iterator[Item]:
    """
    Retrieve documents path of opened files of the given *obj* (application).
    Where application is one of the Adobe Creative Suite:

        >>> get_opened_files_via_com("Illustrator.Application")
        >>> get_opened_files_via_com("Photoshop.Application")

    Complete specs of supported applications:
        - Illustrator: https://www.adobe.com/devnet/illustrator/scripting.html
        - Photoshop: https://www.adobe.com/devnet/photoshop/scripting.html
    """
    with suppress(Exception):
        app = GetActiveObject(obj)
        for doc in app.Application.Documents:
            path = doc.fullName
            pid = compute_fake_pid_from_path(path)
            yield pid, Path(path)


def get_other_opened_files() -> Iterator[Item]:
    """
    This is the function that calls other functions specialized in the
    retrieval of opened files that are not listed in the process list.
    See autolocker.py::get_opened_files() for those ones.
    """
    yield from _get_opened_files_adobe_cc("Photoshop.Application")
    yield from _get_opened_files_adobe_cc("Illustrator.Application")
