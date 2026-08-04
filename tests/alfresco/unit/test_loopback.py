"""Unit tests for nxdrive.alfresco.auth.loopback."""

import time
from unittest.mock import MagicMock

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


# --- NEW TESTS BELOW ---


class TestCallbackHandlerDoGET:
    """Tests for _CallbackHandler.do_GET via a real loopback server."""

    def test_valid_callback_delivers_and_returns_200(self):
        import urllib.request

        received = {}

        def on_callback(query):
            received.update(query)

        server = LoopbackAuthServer()
        uri = server.start(on_callback=on_callback, timeout=5)
        try:
            url = uri + "?code=c1&state=s1&extra=e1"
            resp = urllib.request.urlopen(url, timeout=3)
            assert resp.status == 200
            body = resp.read()
            assert b"Authentication complete" in body
            time.sleep(0.3)
            assert received["code"] == "c1"
            assert received["state"] == "s1"
            # Extra params are also delivered
            assert received["extra"] == "e1"
        finally:
            server.shutdown()

    def test_non_callback_path_returns_404(self):
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            port = uri.split(":")[2].split("/")[0]
            url = f"http://127.0.0.1:{port}/other"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=3)
            assert exc_info.value.code == 404
        finally:
            server.shutdown()

    def test_missing_code_returns_400(self):
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            url = uri + "?state=s1"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=3)
            assert exc_info.value.code == 400
        finally:
            server.shutdown()

    def test_missing_state_returns_400(self):
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            url = uri + "?code=c1"
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(url, timeout=3)
            assert exc_info.value.code == 400
        finally:
            server.shutdown()


class TestCallbackHandlerLogMessage:
    """log_message should suppress stderr by routing to logging."""

    def test_log_message_does_not_raise(self):
        """Indirectly tested: any request to the server triggers log_message."""
        import urllib.error
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=5)
        try:
            # A 404 triggers log_message; should not crash
            port = uri.split(":")[2].split("/")[0]
            url = f"http://127.0.0.1:{port}/nope"
            with pytest.raises(urllib.error.HTTPError):
                urllib.request.urlopen(url, timeout=3)
        finally:
            server.shutdown()


class TestLoopbackHTTPServerDeliver:
    """Additional tests for _LoopbackHTTPServer.deliver exception paths."""

    def test_on_delivered_exception_does_not_propagate(self):
        callback = MagicMock()
        on_delivered = MagicMock(side_effect=RuntimeError("boom"))
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, callback, on_delivered
        )
        try:
            # Should not raise even though on_delivered raises
            server.deliver({"code": "a", "state": "b"})
            assert server.delivered is True
            callback.assert_called_once()
        finally:
            server.server_close()


class TestLoopbackAuthServerTimeout:
    """Tests for the timeout mechanism."""

    def test_timeout_fires_and_stops_server(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=0.2)
        assert server.is_running is True
        time.sleep(0.5)
        assert server.is_running is False

    def test_timeout_after_delivery_is_noop(self):
        """If callback was received before timeout, timeout is a no-op."""
        import urllib.request

        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=2)
        try:
            # Deliver immediately
            url = uri + "?code=c&state=s"
            urllib.request.urlopen(url, timeout=3)
            time.sleep(0.3)
            # Server shuts down from delivery, not from timeout
            assert server.is_running is False
        finally:
            server.shutdown()


class TestLoopbackAuthServerShutdown:
    """Tests for shutdown clearing timer and server."""

    def test_shutdown_clears_internal_state(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=60)
        assert server._server is not None
        assert server._timeout_timer is not None
        server.shutdown()
        assert server._server is None
        assert server._thread is None
        assert server._timeout_timer is None

    def test_double_shutdown_is_safe(self):
        server = LoopbackAuthServer()
        server.start(on_callback=MagicMock(), timeout=5)
        server.shutdown()
        server.shutdown()  # Should not raise
        assert server.is_running is False


class TestOnTimeout:
    """Tests for _on_timeout edge cases."""

    def test_on_timeout_when_server_is_none(self):
        server = LoopbackAuthServer()
        # _server is None by default
        server._on_timeout()  # Should not raise

    def test_on_timeout_when_already_delivered(self):
        server = LoopbackAuthServer()
        uri = server.start(on_callback=MagicMock(), timeout=60)
        try:
            import urllib.request

            url = uri + "?code=c&state=s"
            urllib.request.urlopen(url, timeout=3)
            time.sleep(0.3)
            # Now _on_timeout should be a no-op because delivered is True
            server._on_timeout()
        finally:
            server.shutdown()
