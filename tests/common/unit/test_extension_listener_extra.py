import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nxdrive.drive.osi import extension
from nxdrive.drive.osi.extension import ExtensionListener


def _connection(*, connected=True, ready=True, state=None):
    payload = Mock()
    payload.data.return_value = b'{"command": "status"}\n'
    connection = Mock()
    connection.waitForConnected.return_value = connected
    connection.waitForReadyRead.return_value = ready
    connection.readLine.return_value = payload
    connection.state.return_value = state
    return connection


def test_handle_connection_reports_connection_failure(monkeypatch):
    connection = _connection(connected=False)
    connection.errorString.return_value = "connection refused"
    listener = Mock()
    listener.nextPendingConnection.return_value = connection
    log = Mock()
    monkeypatch.setattr(extension, "log", log)

    ExtensionListener._handle_connection(listener)

    log.error.assert_called_once()
    connection.disconnectFromHost.assert_not_called()


@pytest.mark.parametrize(
    "state, disconnect_waits",
    [(extension.qt.ConnectedState, True), (object(), False)],
)
def test_handle_connection_disconnects_without_payload(state, disconnect_waits):
    connection = _connection(ready=False, state=state)
    listener = Mock()
    listener.nextPendingConnection.return_value = connection

    ExtensionListener._handle_connection(listener)

    connection.disconnectFromHost.assert_called_once_with()
    assert connection.waitForDisconnected.called is disconnect_waits
    listener._parse_payload.assert_not_called()


def test_handle_connection_logs_payload_decode_error(monkeypatch):
    connection = _connection(state=object())
    listener = Mock()
    listener.nextPendingConnection.return_value = connection
    listener._parse_payload.side_effect = UnicodeDecodeError(
        "utf-8", b"\xff", 0, 1, "bad byte"
    )
    log = Mock()
    monkeypatch.setattr(extension, "log", log)

    ExtensionListener._handle_connection(listener)

    log.info.assert_called_once()
    listener._handle_content.assert_not_called()
    connection.write.assert_not_called()
    connection.disconnectFromHost.assert_called_once_with()


@pytest.mark.parametrize("response, writes", [("response", True), (None, False)])
def test_handle_connection_writes_only_nonempty_responses(response, writes):
    connection = _connection(state=object())
    listener = Mock()
    listener.nextPendingConnection.return_value = connection
    listener._parse_payload.return_value = "payload"
    listener._handle_content.return_value = response
    listener._format_response.return_value = b"formatted"

    ExtensionListener._handle_connection(listener)

    listener._parse_payload.assert_called_once_with(
        connection.readLine.return_value.data.return_value
    )
    listener._handle_content.assert_called_once_with("payload")
    assert listener._format_response.called is writes
    assert connection.write.called is writes
    if writes:
        connection.write.assert_called_once_with(b"formatted")


def test_payload_codec_helpers():
    assert ExtensionListener._parse_payload(None, "é".encode()) == "é"
    assert ExtensionListener._format_response(None, "é") == "é".encode()


def test_handle_content_dispatches_value_and_serializes_response():
    handler = Mock(return_value={"status": "synced"})
    listener = SimpleNamespace(handlers={"get-status": handler})
    content = json.dumps({"command": "get-status", "value": "/tmp/file"})

    response = ExtensionListener._handle_content(listener, content)

    handler.assert_called_once_with("/tmp/file")
    assert json.loads(response) == {"status": "synced"}


def test_handle_content_serializes_none_handler_response():
    listener = SimpleNamespace(handlers={"ping": Mock(return_value=None)})

    assert ExtensionListener._handle_content(listener, '{"command": "ping"}') == "null"


@pytest.mark.parametrize("content", ["not json", '{"command": "unknown"}'])
def test_handle_content_rejects_invalid_or_unknown_commands(monkeypatch, content):
    listener = SimpleNamespace(handlers={})
    log = Mock()
    monkeypatch.setattr(extension, "log", log)

    assert ExtensionListener._handle_content(listener, content) is None

    log.info.assert_called_once()
