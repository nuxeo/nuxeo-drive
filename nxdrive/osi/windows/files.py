# coding: utf-8
from binascii import crc32
from contextlib import suppress
from pathlib import Path
from sys import getdefaultencoding
from typing import Iterator

from win32com.client import GetActiveObject

from ...objects import Items

__all__ = ("get_other_opened_files",)


def _compute_pid(path: str) -> int:
    """
    We have no way to find the PID of the apps using the opened file.
    This is a limitation (or a feature) of COM objects.
    To bypass this, we compute a unique ID for a given path.
    """
    if not isinstance(path, bytes):
        path = path.encode(getdefaultencoding(), errors="ignore")  # type: ignore
    return crc32(path)


def _get_opened_files_adobe_cc(obj: str) -> Iterator[Items]:
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
            yield _compute_pid(doc.fullName), Path(doc.FullName)


def get_other_opened_files() -> Iterator[Items]:
    """
    This is the function that calls other functions specialized in the
    retrieval of opened files that are not listed in the process list.
    See autolocker.py::get_opened_files() for those ones.
    """
    yield from _get_opened_files_adobe_cc("Photoshop.Application")
    yield from _get_opened_files_adobe_cc("Illustrator.Application")
