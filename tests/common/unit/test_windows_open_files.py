"""Open-file detection on Windows (``osi/windows/open_files.py``).

The Win32 calls cannot run here, so they are faked. What is pinned instead is
the part that decides, and above all the rule that governs the whole feature:
an answer that is not known must come back as ``None``. A wrong "closed"
overwrites work the user has not saved; a wrong "open" only costs a deferral.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from nxdrive.drive.osi.windows import open_files


@pytest.fixture(autouse=True)
def _forget_the_cached_api(monkeypatch):
    monkeypatch.setattr(open_files, "_api", None)


def _api():
    """A stand-in for the bound Win32 entry points."""
    return SimpleNamespace(
        kernel32=MagicMock(),
        ntdll=MagicMock(),
        user32=MagicMock(),
        enum_proc=MagicMock(),
        last_error=MagicMock(return_value=0),
    )


class TestTitleMatching:
    @pytest.mark.parametrize(
        "title",
        (
            "file1.txt - Notepad",
            "*file1.txt - Notepad",
            "\u25cf file1.txt - conflict - Visual Studio Code",
            "C:\\sync\\file1.txt - Notepad++",
            "file1.txt",
        ),
    )
    def test_an_editor_showing_the_file_is_recognised(self, title):
        assert open_files._title_names_file(title, "file1.txt") is True

    @pytest.mark.parametrize(
        "title, name",
        (
            # The name is part of a longer one, on either side.
            ("release-notes.txt - Notepad", "notes.txt"),
            ("myfile1.txt - Notepad", "file1.txt"),
            ("file1.txt.bak - Notepad", "file1.txt"),
            ("report_2026.docx - Word", "2026.docx"),
            # Nothing to do with the file at all.
            ("Inbox - Outlook", "file1.txt"),
        ),
    )
    def test_a_different_file_is_not_a_match(self, title, name):
        assert open_files._title_names_file(title, name) is False

    def test_the_match_is_case_insensitive(self):
        assert open_files._title_names_file("FILE1.TXT - Notepad", "file1.txt") is True

    def test_a_later_occurrence_still_counts(self):
        """The first hit can be inside a longer word; keep looking."""
        title = "myfile1.txt and file1.txt - Notepad"
        assert open_files._title_names_file(title, "file1.txt") is True


class TestHolders:
    def _handle(self, api, value=1234):
        api.kernel32.CreateFileW.return_value = value

    def test_an_exclusive_lock_answers_without_asking_further(self, monkeypatch):
        api = _api()
        self._handle(api, open_files.INVALID_HANDLE_VALUE)
        api.last_error.return_value = open_files.ERROR_SHARING_VIOLATION

        assert open_files._holders(api, "C:\\f.txt") is True
        api.ntdll.NtQueryInformationFile.assert_not_called()

    def test_a_missing_file_is_not_open(self, monkeypatch):
        api = _api()
        self._handle(api, open_files.INVALID_HANDLE_VALUE)
        api.last_error.return_value = open_files.ERROR_FILE_NOT_FOUND

        assert open_files._holders(api, "C:\\f.txt") is False

    def test_an_unreadable_file_is_unknown_not_closed(self, monkeypatch):
        """Access denied says nothing about whether anyone has it open."""
        api = _api()
        self._handle(api, open_files.INVALID_HANDLE_VALUE)
        api.last_error.return_value = 5

        assert open_files._holders(api, "C:\\f.txt") is None

    def test_more_holders_than_the_buffer_takes_is_still_open(self):
        api = _api()
        self._handle(api)
        api.ntdll.NtQueryInformationFile.return_value = (
            open_files.STATUS_INFO_LENGTH_MISMATCH
        )

        assert open_files._holders(api, "C:\\f.txt") is True

    def test_an_unexpected_status_is_unknown(self):
        api = _api()
        self._handle(api)
        api.ntdll.NtQueryInformationFile.return_value = 0xC0000001  # UNSUCCESSFUL

        assert open_files._holders(api, "C:\\f.txt") is None

    def test_the_handle_is_always_closed(self):
        api = _api()
        self._handle(api, 4321)
        api.ntdll.NtQueryInformationFile.return_value = 0xC0000001

        open_files._holders(api, "C:\\f.txt")

        api.kernel32.CloseHandle.assert_called_once_with(4321)


class TestIsFileOpen:
    def _patch(self, monkeypatch, *, api=True, held=None, shown=None):
        monkeypatch.setattr(open_files, "_win_api", lambda: _api() if api else None)
        monkeypatch.setattr(open_files, "_holders", lambda *a: held)
        monkeypatch.setattr(open_files, "_shown_in_a_window", lambda *a: shown)

    def test_a_held_handle_skips_the_window_scan(self, monkeypatch):
        self._patch(monkeypatch, held=True)
        scanned = []
        monkeypatch.setattr(
            open_files, "_shown_in_a_window", lambda *a: scanned.append(1)
        )

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is True
        assert not scanned

    def test_a_window_title_catches_what_the_kernel_misses(self, monkeypatch):
        """Notepad reads the file and closes it, so only the title shows it."""
        self._patch(monkeypatch, held=False, shown=True)

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is True

    def test_both_checks_negative_means_closed(self, monkeypatch):
        self._patch(monkeypatch, held=False, shown=False)

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is False

    @pytest.mark.parametrize(
        "held, shown", ((None, False), (False, None), (None, None))
    )
    def test_an_unanswered_check_is_never_reported_as_closed(
        self, monkeypatch, held, shown
    ):
        self._patch(monkeypatch, held=held, shown=shown)

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is None

    def test_no_win32_means_unknown(self, monkeypatch):
        self._patch(monkeypatch, api=False)

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is None

    def test_an_unexpected_failure_never_escapes(self, monkeypatch):
        monkeypatch.setattr(open_files, "_win_api", lambda: _api())
        monkeypatch.setattr(
            open_files, "_holders", MagicMock(side_effect=OSError("boom"))
        )

        assert open_files.is_file_open(Path("C:/sync/f.txt")) is None


class TestWindowScan:
    """Where the false positives would come from, so it is pinned closely."""

    def _api_showing(self, windows, /, *, ours=4242):
        """*windows* maps a fake handle to ``(pid, title, visible)``."""
        api = _api()
        api.enum_proc = lambda callback: callback

        def enum(callback, _):
            for hwnd in windows:
                callback(hwnd, 0)
            return True

        def pid_of(hwnd, out):
            out._obj.value = windows[hwnd][0]
            return 0

        api.user32.EnumWindows = enum
        api.user32.GetWindowThreadProcessId = pid_of
        api.user32.IsWindowVisible = lambda hwnd: windows[hwnd][2]
        api.user32.GetWindowTextLengthW = lambda hwnd: len(windows[hwnd][1])

        def text_of(hwnd, buffer, _size):
            buffer.value = windows[hwnd][1]
            return len(windows[hwnd][1])

        api.user32.GetWindowTextW = text_of
        return api, ours

    def test_our_own_windows_are_ignored(self, monkeypatch):
        """Drive's own window naming the file is not the user editing it."""
        api, ours = self._api_showing({1: (4242, "file1.txt - Drive", True)})
        monkeypatch.setattr(open_files.os, "getpid", lambda: ours)

        assert open_files._window_titles(api) == []

    def test_hidden_windows_are_ignored(self, monkeypatch):
        api, ours = self._api_showing({1: (99, "file1.txt - Notepad", False)})
        monkeypatch.setattr(open_files.os, "getpid", lambda: ours)

        assert open_files._window_titles(api) == []

    def test_another_process_window_is_collected(self, monkeypatch):
        api, ours = self._api_showing({1: (99, "file1.txt - Notepad", True)})
        monkeypatch.setattr(open_files.os, "getpid", lambda: ours)

        assert open_files._window_titles(api) == ["file1.txt - Notepad"]

    def test_an_absurdly_long_title_is_skipped(self, monkeypatch):
        long_title = "x" * (open_files.MAX_TITLE_LENGTH + 1)
        api, ours = self._api_showing({1: (99, long_title, True)})
        monkeypatch.setattr(open_files.os, "getpid", lambda: ours)

        assert open_files._window_titles(api) == []

    def test_a_failing_enumeration_is_unknown(self):
        api = _api()
        api.enum_proc = lambda callback: callback
        api.user32.EnumWindows = MagicMock(side_effect=OSError("boom"))

        assert open_files._window_titles(api) is None

    def test_a_refused_enumeration_is_unknown_not_an_empty_scan(self):
        """``EnumWindows`` reports failure by returning zero, not by raising.

        A partial list passing as a complete one would let the file read as
        closed and the download go ahead.
        """
        api, ours = self._api_showing({1: (99, "file1.txt - Notepad", True)})
        collected = api.user32.EnumWindows

        def fails_midway(callback, lparam):
            collected(callback, lparam)
            return 0

        api.user32.EnumWindows = fails_midway

        assert open_files._window_titles(api) is None
        assert open_files._shown_in_a_window(api, "file1.txt") is None

    def test_the_verdict_comes_from_the_collected_titles(self, monkeypatch):
        api, ours = self._api_showing({1: (99, "file1.txt - Notepad", True)})
        monkeypatch.setattr(open_files.os, "getpid", lambda: ours)

        assert open_files._shown_in_a_window(api, "file1.txt") is True
        assert open_files._shown_in_a_window(api, "other.txt") is False

    def test_an_unreadable_window_list_is_unknown(self, monkeypatch):
        monkeypatch.setattr(open_files, "_window_titles", lambda api: None)

        assert open_files._shown_in_a_window(_api(), "file1.txt") is None


class TestAvailability:
    def test_binding_is_attempted_once_then_remembered(self, monkeypatch):
        attempts = []

        class _Boom:
            def __init__(self):
                attempts.append(1)
                raise OSError("not Windows")

        monkeypatch.setattr(open_files, "_WinApi", _Boom)

        assert open_files.available() is False
        assert open_files.available() is False
        assert len(attempts) == 1

    def test_a_successful_binding_is_reused(self, monkeypatch):
        bound = _api()
        monkeypatch.setattr(open_files, "_WinApi", lambda: bound)

        assert open_files.available() is True
        assert open_files._win_api() is bound
