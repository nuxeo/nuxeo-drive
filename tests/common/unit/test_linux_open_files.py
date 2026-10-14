"""Open-file detection on GNU/Linux (``osi/linux/linux.py``).

The helper script is exercised separately; what is pinned here is the contract
between it and the rest of the application. Above all: anything other than a
definite ``TRUE``/``FALSE`` is ``None``, and ``None`` must never be read as
"closed" — a wrong "closed" overwrites work the user has not saved.
"""

import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from nxdrive.drive.osi.linux import linux
from nxdrive.drive.osi.linux.linux import LinuxIntegration

SCRIPT = Path("/res/utilities/check_open_files.sh")


@pytest.fixture
def integration():
    instance = LinuxIntegration.__new__(LinuxIntegration)
    instance._check_open_path = None
    return instance


def _found(monkeypatch, *, exists=True):
    script = Mock(spec=Path)
    script.is_file.return_value = exists
    script.__str__ = Mock(return_value=str(SCRIPT))
    monkeypatch.setattr(linux, "find_resource", Mock(return_value=script))
    return script


def _answers(monkeypatch, stdout):
    run = Mock(return_value=Mock(stdout=stdout, returncode=0))
    monkeypatch.setattr(linux.subprocess, "run", run)
    return run


class TestDetectionAvailability:
    def test_a_shipped_script_enables_detection(self, integration, monkeypatch):
        _found(monkeypatch)
        assert integration.has_file_open_detection() is True

    def test_a_missing_script_disables_detection(self, integration, monkeypatch):
        _found(monkeypatch, exists=False)
        assert integration.has_file_open_detection() is False

    def test_the_script_is_looked_for_once(self, integration, monkeypatch):
        find = Mock(return_value=_found(monkeypatch))
        monkeypatch.setattr(linux, "find_resource", find)

        integration.has_file_open_detection()
        integration.has_file_open_detection()

        find.assert_called_once()

    def test_a_missing_script_answers_unknown(self, integration, monkeypatch):
        _found(monkeypatch, exists=False)
        assert integration.is_file_open(Path("/sync/f.txt")) is None


class TestAnswers:
    @pytest.mark.parametrize(
        "stdout, expected",
        (
            ("TRUE\n", True),
            ("FALSE\n", False),
            ("UNKNOWN\n", None),
            ("", None),
            ("something else", None),
        ),
    )
    def test_only_a_definite_answer_is_believed(
        self, integration, monkeypatch, stdout, expected
    ):
        _found(monkeypatch)
        _answers(monkeypatch, stdout)

        assert integration.is_file_open(Path("/sync/f.txt")) is expected

    def test_our_own_pid_is_passed_so_transfers_do_not_count(
        self, integration, monkeypatch
    ):
        _found(monkeypatch)
        run = _answers(monkeypatch, "FALSE")
        monkeypatch.setattr(linux.os, "getpid", lambda: 4242)

        integration.is_file_open(Path("/sync/f.txt"))

        argv = run.call_args.args[0]
        assert argv[0] == "bash"
        assert argv[1] == str(SCRIPT)
        # str() so the assertion survives a Windows runner, where a PurePath
        # renders with backslashes.
        assert argv[2] == str(Path("/sync/f.txt"))
        assert argv[3] == "4242"

    def test_the_probe_is_bounded(self, integration, monkeypatch):
        _found(monkeypatch)
        run = _answers(monkeypatch, "FALSE")

        integration.is_file_open(Path("/sync/f.txt"))

        assert run.call_args.kwargs["timeout"] == linux.CHECK_OPEN_TIMEOUT

    def test_a_timeout_is_unknown_not_closed(self, integration, monkeypatch):
        _found(monkeypatch)
        monkeypatch.setattr(
            linux.subprocess,
            "run",
            Mock(side_effect=subprocess.TimeoutExpired("bash", 5.0)),
        )

        assert integration.is_file_open(Path("/sync/f.txt")) is None

    def test_a_missing_shell_is_unknown_not_closed(self, integration, monkeypatch):
        _found(monkeypatch)
        monkeypatch.setattr(
            linux.subprocess, "run", Mock(side_effect=OSError("no bash"))
        )

        assert integration.is_file_open(Path("/sync/f.txt")) is None
