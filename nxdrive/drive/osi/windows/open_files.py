#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Whether a file is currently open in another application, on Windows.

Two checks, because neither covers the other's blind spot:

* the kernel knows which processes hold a handle on the file, which catches
  everything that keeps it open for as long as it is on screen (Office, PDF
  readers, most IDEs);
* applications that read a file and close it again immediately are invisible
  to the kernel, so their window titles are matched against the file name.

Every answer is ``True``, ``False`` or ``None``. ``None`` means the question
could not be answered and must never be read as "closed": a wrong "closed"
overwrites whatever the user has not saved yet, while a wrong "open" only
costs a deferral.
"""

import ctypes
import os
from ctypes import wintypes
from logging import getLogger
from pathlib import Path
from typing import Any, List, Optional

from ...utils import safe_long_path

__all__ = ("available", "is_file_open")

log = getLogger(__name__)

#: ``NtQueryInformationFile`` class listing the PIDs that hold the file open.
FILE_PROCESS_IDS_USING_FILE_INFORMATION = 47

#: How many holders to ask for. Overflowing the buffer only tells us there are
#: more than this, which already answers the question.
MAX_PROCESS_IDS = 64

#: Longest window title we read. Anything beyond this is a document viewer
#: dumping content into its title, not a file name.
MAX_TITLE_LENGTH = 512

#: What may sit immediately before the file name in a window title: nothing, a
#: path separator, or the "unsaved" marker an editor prepends.
_BEFORE_NAME = frozenset(("", " ", "\t", "*", "\\", "/", "\u25cf", "\u2022"))

#: What may follow it: nothing, or the gap before the application name.
_AFTER_NAME = frozenset(("", " ", "\t"))

ERROR_FILE_NOT_FOUND = 2
ERROR_PATH_NOT_FOUND = 3
ERROR_SHARING_VIOLATION = 32

STATUS_SUCCESS = 0x00000000
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004

FILE_READ_ATTRIBUTES = 0x0080
FILE_SHARE_ALL = 0x0001 | 0x0002 | 0x0004  # read | write | delete
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

NTSTATUS = wintypes.LONG
#: Pointer-sized on both architectures, unlike ``LARGE_INTEGER``.
ULONG_PTR = wintypes.WPARAM


class IO_STATUS_BLOCK(ctypes.Structure):
    class _STATUS(ctypes.Union):
        _fields_ = (("Status", NTSTATUS), ("Pointer", wintypes.LPVOID))

    _anonymous_ = ("_Status",)
    _fields_ = (("_Status", _STATUS), ("Information", ULONG_PTR))


class FILE_PROCESS_IDS_USING_FILE_INFORMATION_T(ctypes.Structure):
    _fields_ = (
        ("NumberOfProcessIdsInList", ULONG_PTR),
        ("ProcessIdList", ULONG_PTR * MAX_PROCESS_IDS),
    )


class _WinApi:
    """The entry points this module needs, bound once on first use.

    Loaded lazily because ``WINFUNCTYPE`` and the DLLs only exist on Windows,
    which keeps the module importable — and the pure logic testable — anywhere.
    """

    def __init__(self) -> None:
        self.enum_proc = ctypes.WINFUNCTYPE(
            wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
        )
        self.last_error = ctypes.get_last_error
        self.ntdll = ctypes.WinDLL("ntdll")
        self.kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user32 = ctypes.WinDLL("user32", use_last_error=True)

        self.kernel32.CreateFileW.restype = wintypes.HANDLE
        self.kernel32.CreateFileW.argtypes = (
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        )
        self.kernel32.CloseHandle.restype = wintypes.BOOL
        self.kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)

        self.ntdll.NtQueryInformationFile.restype = NTSTATUS
        self.ntdll.NtQueryInformationFile.argtypes = (
            wintypes.HANDLE,
            ctypes.POINTER(IO_STATUS_BLOCK),
            wintypes.LPVOID,
            wintypes.ULONG,
            wintypes.ULONG,
        )

        self.user32.EnumWindows.restype = wintypes.BOOL
        self.user32.EnumWindows.argtypes = (self.enum_proc, wintypes.LPARAM)
        self.user32.GetWindowTextW.restype = ctypes.c_int
        self.user32.GetWindowTextW.argtypes = (
            wintypes.HWND,
            wintypes.LPWSTR,
            ctypes.c_int,
        )
        self.user32.GetWindowTextLengthW.restype = ctypes.c_int
        self.user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
        self.user32.IsWindowVisible.restype = wintypes.BOOL
        self.user32.IsWindowVisible.argtypes = (wintypes.HWND,)
        self.user32.GetWindowThreadProcessId.restype = wintypes.DWORD
        self.user32.GetWindowThreadProcessId.argtypes = (
            wintypes.HWND,
            ctypes.POINTER(wintypes.DWORD),
        )


#: ``False`` once loading has been tried and failed, so it is tried only once.
_api: Any = None


def _win_api() -> Optional[_WinApi]:
    global _api

    if _api is None:
        try:
            _api = _WinApi()
        except Exception:
            log.warning(
                "Open-file detection disabled: cannot bind Win32", exc_info=True
            )
            _api = False
    return _api or None


def available() -> bool:
    """Whether :func:`is_file_open` can give a real answer on this machine."""
    return _win_api() is not None


def _holders(api: _WinApi, path: str, /) -> Optional[bool]:
    """Whether a process other than ours holds a handle on *path*.

    Opened with every sharing flag so the probe itself cannot be what makes
    another application fail to write.
    """
    handle = api.kernel32.CreateFileW(
        path,
        FILE_READ_ATTRIBUTES,
        FILE_SHARE_ALL,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )

    if handle == INVALID_HANDLE_VALUE:
        error = api.last_error()
        if error == ERROR_SHARING_VIOLATION:
            # Someone holds it without sharing: open, and nothing else to ask.
            return True
        if error in (ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND):
            return False
        log.debug(f"Cannot open {path!r} to list its holders (error {error})")
        return None

    try:
        iosb = IO_STATUS_BLOCK()
        info = FILE_PROCESS_IDS_USING_FILE_INFORMATION_T()
        status = (
            api.ntdll.NtQueryInformationFile(
                handle,
                ctypes.byref(iosb),
                ctypes.byref(info),
                ctypes.sizeof(info),
                FILE_PROCESS_IDS_USING_FILE_INFORMATION,
            )
            & 0xFFFFFFFF
        )
    finally:
        api.kernel32.CloseHandle(handle)

    if status == STATUS_INFO_LENGTH_MISMATCH:
        # More holders than the buffer takes, which is already an answer.
        return True
    if status != STATUS_SUCCESS:
        log.debug(f"Cannot list the holders of {path!r} (status {status:#010x})")
        return None

    ours = os.getpid()
    count = min(int(info.NumberOfProcessIdsInList), MAX_PROCESS_IDS)
    return any(pid and pid != ours for pid in info.ProcessIdList[:count])


def _title_names_file(title: str, name: str, /) -> bool:
    """Whether a window title names *name*, which must already be lowercase.

    The name has to sit between a boundary on each side. A bare substring
    match would make ``notes.txt`` match a window showing ``release-notes.txt``,
    and the characters a longer file name would use are therefore not
    boundaries — only path separators and the markers editors put around a
    name are.
    """
    lowered = title.lower()
    start = lowered.find(name)
    while start != -1:
        before = lowered[start - 1 : start]
        after = lowered[start + len(name) : start + len(name) + 1]
        if before in _BEFORE_NAME and after in _AFTER_NAME:
            return True
        start = lowered.find(name, start + 1)
    return False


def _window_titles(api: _WinApi, /) -> Optional[List[str]]:
    """Every visible top-level window title except our own."""
    ours = os.getpid()
    titles: List[str] = []

    def collect(hwnd: int, _: int, /) -> bool:
        if not api.user32.IsWindowVisible(hwnd):
            return True

        pid = wintypes.DWORD()
        api.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == ours:
            return True

        length = api.user32.GetWindowTextLengthW(hwnd)
        if not 0 < length <= MAX_TITLE_LENGTH:
            return True

        buffer = ctypes.create_unicode_buffer(length + 1)
        api.user32.GetWindowTextW(hwnd, buffer, length + 1)
        titles.append(buffer.value)
        return True

    try:
        # Zero means the enumeration failed; our callback never stops it early,
        # so a partial list must not pass as a complete one.
        completed = api.user32.EnumWindows(api.enum_proc(collect), 0)
    except Exception:
        log.debug("Could not enumerate windows", exc_info=True)
        return None

    if not completed:
        log.debug(f"Window enumeration failed (error {api.last_error()})")
        return None
    return titles


def _shown_in_a_window(api: _WinApi, name: str, /) -> Optional[bool]:
    """Whether a visible window names the file.

    The only signal left for an application that does not keep the file open,
    and the reason this is not kernel-only like the first check.
    """
    titles = _window_titles(api)
    if titles is None:
        return None
    return any(_title_names_file(title, name) for title in titles)


def is_file_open(path: Path, /) -> Optional[bool]:
    """Whether *path* is currently open in another application."""
    api = _win_api()
    if api is None:
        return None

    try:
        target = str(safe_long_path(path))
        held = _holders(api, target)
        if held:
            return True

        shown = _shown_in_a_window(api, path.name.lower())
        if shown:
            return True
        # Neither check could answer, so neither may say "closed".
        return False if held is False and shown is False else None
    except Exception:
        log.warning(f"Could not tell whether {str(path)!r} is open", exc_info=True)
        return None
