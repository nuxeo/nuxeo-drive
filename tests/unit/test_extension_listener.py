import pathlib
from collections import namedtuple
from unittest.mock import patch

import pytest
from PyQt5.QtNetwork import QAbstractSocket, QHostAddress

from nxdrive.osi.extension import ExtensionListener, Status, get_formatted_status

DocPair = namedtuple(
    "DocPair",
    "error_count, local_state, pair_state, processor",
    defaults=(0, "", "", 0),
)


def test_host_to_addr():
    # Bad hostname
    assert not ExtensionListener.host_to_addr("")
    assert not ExtensionListener.host_to_addr("blablabla")

    # Good hostname
    address = ExtensionListener.host_to_addr("localhost")
    assert isinstance(address, QHostAddress)
    assert address.protocol() == QAbstractSocket.IPv4Protocol
    assert address.toString() == "127.0.0.1"


@pytest.mark.parametrize(
    "doc_pair, path, status",
    [
        (DocPair(), pathlib.Path("."), Status.UNSYNCED),
        (DocPair(error_count=1), pathlib.Path("."), Status.ERROR),
        (DocPair(local_state="synchronized"), pathlib.Path("."), Status.SYNCED),
        (DocPair(pair_state="conflicted"), pathlib.Path("."), Status.CONFLICTED),
        (DocPair(pair_state="unsynchronized"), pathlib.Path("."), Status.UNSYNCED),
        (DocPair(processor=42), pathlib.Path("."), Status.SYNCING),
    ],
)
def test_get_formatted_status(doc_pair, path, status):
    fmt_status = get_formatted_status(doc_pair, path)
    assert fmt_status == {"path": ".", "value": str(status.value)}


@patch("pathlib.Path.stat")
def test_get_formatted_status_readonly(mocked_stat):
    doc_pair = DocPair()
    path = pathlib.Path(".")

    class Stat:
        st_mode = 0

    mocked_stat.return_value = Stat
    status = get_formatted_status(doc_pair, path)
    mocked_stat.reset_mock()

    assert status == {"path": ".", "value": str(Status.LOCKED.value)}


@patch("pathlib.Path.stat")
def test_get_formatted_status_permission_error(mocked_stat):
    doc_pair = DocPair()
    path = pathlib.Path(".")

    mocked_stat.side_effect = PermissionError
    status = get_formatted_status(doc_pair, path)
    mocked_stat.reset_mock()

    assert status == {"path": ".", "value": str(Status.LOCKED.value)}


def test_get_formatted_status_file_not_found():
    doc_pair = DocPair()
    path = pathlib.Path("./inexistent")
    assert get_formatted_status(doc_pair, path) is None
