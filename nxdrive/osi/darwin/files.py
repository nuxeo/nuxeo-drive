# coding: utf-8
from pathlib import Path
from typing import Iterator

from AppKit import NSWorkspace
from ScriptingBridge import SBApplication

from ...objects import Item
from ...utils import compute_fake_pid_from_path

__all__ = ("get_other_opened_files",)


def _is_running(identifier: str) -> bool:
    """
    Check if a given application bundle identifier is found in
    the list of opened applications, meaning it is running.
    """
    shared_workspace = NSWorkspace.sharedWorkspace()
    for running_app in shared_workspace.launchedApplications():
        if identifier == str(running_app.allValues()[2]):
            return True
    return False


def _get_opened_files_adobe_cc(identifier: str) -> Iterator[Item]:
    """
    Retrieve documents path of opened files of the given bundle *identifier* (application).
    Where application is one of the Adobe Creative Suite:

        >>> get_opened_files_via_com("com.adobe.Photoshop")
        >>> get_opened_files_via_com("com.adobe.Illustrator")

    Complete specs of supported applications:
        - Illustrator: https://www.adobe.com/devnet/illustrator/scripting.html
        - Photoshop: https://www.adobe.com/devnet/photoshop/scripting.html
    """
    if not _is_running(identifier):
        return

    app = SBApplication.applicationWithBundleIdentifier_(identifier)

    if not app or not app.isRunning():
        return

    for doc in app.documents():
        path = doc.filePath().path()
        pid = compute_fake_pid_from_path(path)
        yield pid, Path(path)


def get_other_opened_files() -> Iterator[Item]:
    """
    This is the function that calls other functions specialized in the
    retrieval of opened files that are not listed in the process list.
    See autolocker.py::get_opened_files() for those ones.
    """
    yield from _get_opened_files_adobe_cc("com.adobe.Photoshop")
    yield from _get_opened_files_adobe_cc("com.adobe.Illustrator")
