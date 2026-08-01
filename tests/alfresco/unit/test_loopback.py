"""Unit tests for nxdrive.alfresco.auth.loopback."""

import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from nxdrive.alfresco.auth.loopback import (
    LoopbackAuthServer,
    _CallbackHandler,
    _LoopbackHTTPServer,
)


class TestLoopbackHTTPServer:
    """Tests for the internal _LoopbackHTTPServer."""

    def test_deliver_invokes_callback(self):
        callback = MagicMock()
        on_delivered = MagicMock()
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, callback, on_delivered
        )
        try:
            query = {"code": "abc", "state": "xyz"}
            server.deliver(query)
            callback.assert_called_once_with(query)
            on_delivered.assert_called_once()
            assert server.delivered is True
        finally:
            server.server_close()

    def test_deliver_only_once(self):
        callback = MagicMock()
        on_delivered = MagicMock()
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, callback, on_delivered
        )
        try:
            server.deliver({"code": "a", "state": "b"})
            server.deliver({"code": "c", "state": "d"})
            # Second call is a no-op
            assert callback.call_count == 1
        finally:
            server.server_close()

    def test_deliver_callback_exception_does_not_propagate(self):
        callback = MagicMock(side_effect=RuntimeError("boom"))
        on_delivered = MagicMock()
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, callback, on_delivered
        )
        try:
            # Should not raise
            server.deliver({"code": "a", "state": "b"})
            assert server.delivered is True
            on_delivered.assert_called_once()
        finally:
            server.server_close()

    def test_delivered_property_initially_false(self):
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, MagicMock(), MagicMock()
        )
        try:
            assert server.delivered is False
        finally:
            server.server_close()


class TestLoopbackAuthServer:
    """Tests for the public LoopbackAuthServer."""

    def test_start_returns_redirect_uri(self):
        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            assert uri.startswith("http://127.0.0.1:")
            assert uri.endswith("/callback")
            assert server.is_running is True
        finally:
            server.shutdown()

    def test_start_twice_raises(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=5)
        try:
            with pytest.raises(RuntimeError, match="already started"):
                server.start(on_callback=MagicMock(), timeout=5)
        finally:
            server.shutdown()

    def test_shutdown_is_idempotent(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=5)
        server.shutdown()
        assert server.is_running is False
        # Second shutdown should not raise
        server.shutdown()
        assert server.is_running is False

    def test_is_running_false_initially(self):
        server = LoopbackAuthServer()
        assert server.is_running is False

    def test_timeout_triggers_shutdown(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=0.3)
        assert server.is_running is True
        time.sleep(0.6)
        assert server.is_running is False

    def test_callback_receives_query_params(self):
        """End-to-end: simulate a browser redirect hitting the loopback."""
        import urllib.request

        received = {}

        def on_callback(query):
            received.update(query)

        server = LoopbackAuthServer()
        uri = server.start(on_callback=on_callback, timeout=5)
        try:
            # Simulate the IdP redirect
            url = uri + "?code=test_code&state=test_state"
            req = urllib.request.Request(url)
            resp = urllib.request.urlopen(req, timeout=3)
            assert resp.status == 200
            # Give the delivery thread a moment
            time.sleep(0.3)
            assert received == {"code": "test_code", "state": "test_state"}
        finally:
            server.shutdown()

    def test_invalid_path_returns_404(self):
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            # Hit a wrong path
            port = uri.split(":")[2].split("/")[0]
            url = f"http://127.0.0.1:{port}/wrong"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=3)
            assert exc_info.value.code == 404
        finally:
            server.shutdown()

    def test_missing_params_returns_400(self):
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            # Hit callback without code/state
            url = uri + "?foo=bar"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=3)
            assert exc_info.value.code == 400
        finally:
            server.shutdown()
