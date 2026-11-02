#
# © 2012-2026 Hyland.
# All Hyland product names are registered or unregistered trademarks of Hyland or its affiliates.
#

"""Console (terminal) EULA and open source attribution prompts."""

import io
from unittest.mock import patch

import pytest

from nxdrive.drive.gui import show_eula
from nxdrive.drive.gui.show_open_source_attribution import (
    get_open_source_attribution_console_message,
)

EULA_TEXT = "EULA TEXT"
OSA_TEXT = "OPEN SOURCE ATTRIBUTION TEXT"
QUESTION = "Enter Y to accept, N to reject:"


@pytest.fixture
def licenses(tmp_path):
    (tmp_path / "NUXEO_EULA.txt").write_text(f"{EULA_TEXT}\n", encoding="utf-8")
    (tmp_path / "NUXEO_OPEN_SOURCE_ATTRIBUTION.txt").write_text(
        f"{OSA_TEXT}\n", encoding="utf-8"
    )

    def find_resource(_folder, *, file):
        return tmp_path / file

    with patch.object(show_eula, "find_resource", side_effect=find_resource), patch(
        "nxdrive.drive.utils.find_resource", side_effect=find_resource
    ):
        yield tmp_path


def _stdin(monkeypatch, text):
    monkeypatch.setattr("sys.stdin", io.StringIO(text))


@pytest.mark.parametrize(
    "answers",
    (
        "Y\n",
        "y\n",
        " Y \n",
        "Y\r\n",
        "Y",
        "Y\n\n",
    ),
)
def test_eula_console_accepts_y_and_shows_attribution(
    licenses, monkeypatch, capsys, answers
):
    _stdin(monkeypatch, answers)

    assert show_eula.get_eula_console_message("NUXEO") is True

    out = capsys.readouterr().out
    assert EULA_TEXT in out
    assert OSA_TEXT in out


def test_eula_console_asks_again_after_invalid_answer(licenses, monkeypatch, capsys):
    _stdin(monkeypatch, "maybe\nY\n")

    assert show_eula.get_eula_console_message("NUXEO") is True
    assert capsys.readouterr().out.count(QUESTION) == 2


@pytest.mark.parametrize("answers", ("N\n", "n\n", " N \n"))
def test_eula_console_rejects_n_without_attribution(
    licenses, monkeypatch, capsys, answers
):
    _stdin(monkeypatch, answers)

    assert show_eula.get_eula_console_message("NUXEO") is False
    assert OSA_TEXT not in capsys.readouterr().out


@pytest.mark.parametrize("answers", ("", "maybe\n"))
def test_eula_console_rejects_when_input_runs_out(licenses, monkeypatch, answers):
    _stdin(monkeypatch, answers)

    assert show_eula.get_eula_console_message("NUXEO") is False


def test_eula_console_rejects_when_no_input_is_available(licenses, monkeypatch):
    monkeypatch.setattr("sys.stdin", None)

    assert show_eula.get_eula_console_message("NUXEO") is False


def test_eula_console_rejects_when_eula_file_is_missing(licenses, monkeypatch):
    (licenses / "NUXEO_EULA.txt").unlink()
    _stdin(monkeypatch, "Y\n")

    assert show_eula.get_eula_console_message("NUXEO") is False


def test_eula_console_rejects_when_eula_file_is_empty(licenses, monkeypatch):
    (licenses / "NUXEO_EULA.txt").write_text("  \n", encoding="utf-8")
    _stdin(monkeypatch, "Y\n")

    assert show_eula.get_eula_console_message("NUXEO") is False


@pytest.mark.parametrize("stdin", (io.StringIO(""), None))
def test_attribution_console_continues_without_input(
    licenses, monkeypatch, capsys, stdin
):
    monkeypatch.setattr("sys.stdin", stdin)

    assert get_open_source_attribution_console_message("NUXEO") is None
    assert OSA_TEXT in capsys.readouterr().out
