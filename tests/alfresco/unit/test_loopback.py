"""Unit tests for nxdrive.alfresco.auth.loopback."""

from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest

from nxdrive.alfresco.auth.loopback import (
    _ERROR_HTML,
    _SUCCESS_HTML,
    LoopbackAuthServer,
    _CallbackHandler,
    _LoopbackHTTPServer,
)


def _handler(path: str = "/callback?code=code&state=state") -> _CallbackHandler:
    """Build a request handler without invoking its socket-based initializer."""
    handler = object.__new__(_CallbackHandler)
    handler.path = path
    handler.server = MagicMock()
    handler._reply = MagicMock()
    return handler


def _http_server() -> SimpleNamespace:
    """Build the HTTPServer wrapper while preventing socket allocation."""
    callback = MagicMock()
    on_delivered = MagicMock()
    delivered = MagicMock()
    delivered.is_set.return_value = False

    def mark_delivered() -> None:
        delivered.is_set.return_value = True

    delivered.set.side_effect = mark_delivered
    with patch(
        "nxdrive.alfresco.auth.loopback.HTTPServer.__init__", return_value=None
    ) as base_init, patch(
        "nxdrive.alfresco.auth.loopback.threading.Event", return_value=delivered
    ):
        server = _LoopbackHTTPServer(
            ("127.0.0.1", 0), _CallbackHandler, callback, on_delivered
        )

    return SimpleNamespace(
        base_init=base_init,
        callback=callback,
        delivered=delivered,
        on_delivered=on_delivered,
        server=server,
    )


class TestCallbackHandler:
    def test_valid_callback_replies_before_delivering_query(self) -> None:
        handler = _handler(
            "/callback?code=authorization-code&state=expected-state&extra=value"
        )
        parent = MagicMock()
        parent.attach_mock(handler._reply, "reply")
        parent.attach_mock(handler.server.deliver, "deliver")

        handler.do_GET()

        handler._reply.assert_called_once_with(200, _SUCCESS_HTML)
        handler.server.deliver.assert_called_once_with(
            {
                "code": "authorization-code",
                "state": "expected-state",
                "extra": "value",
            }
        )
        assert parent.mock_calls == [
            call.reply(200, _SUCCESS_HTML),
            call.deliver(
                {
                    "code": "authorization-code",
                    "state": "expected-state",
                    "extra": "value",
                }
            ),
        ]

    def test_callback_accepts_trailing_slash_and_first_repeated_value(self) -> None:
        handler = _handler("/callback/?code=first&code=second&state=state&ignored=")

        handler.do_GET()

        handler._reply.assert_called_once_with(200, _SUCCESS_HTML)
        handler.server.deliver.assert_called_once_with(
            {"code": "first", "state": "state"}
        )

    @pytest.mark.parametrize("path", ["/", "/other", "/callback-extra"])
    def test_unknown_path_returns_404(self, path: str) -> None:
        handler = _handler(path + "?code=code&state=state")

        handler.do_GET()

        handler._reply.assert_called_once_with(404, _ERROR_HTML)
        handler.server.deliver.assert_not_called()

    @pytest.mark.parametrize("query", ["state=state", "code=code", "code=&state=state"])
    def test_missing_required_parameter_returns_400(self, query: str) -> None:
        handler = _handler(f"/callback?{query}")

        handler.do_GET()

        handler._reply.assert_called_once_with(400, _ERROR_HTML)
        handler.server.deliver.assert_not_called()

    def test_reply_writes_headers_and_body(self) -> None:
        handler = object.__new__(_CallbackHandler)
        handler.send_response = MagicMock()
        handler.send_header = MagicMock()
        handler.end_headers = MagicMock()
        handler.wfile = MagicMock()

        handler._reply(201, b"response")

        handler.send_response.assert_called_once_with(201)
        assert handler.send_header.call_args_list == [
            call("Content-Type", "text/html; charset=utf-8"),
            call("Content-Length", "8"),
            call("Cache-Control", "no-store"),
        ]
        handler.end_headers.assert_called_once_with()
        handler.wfile.write.assert_called_once_with(b"response")

    def test_reply_suppresses_disconnected_browser_error(self) -> None:
        handler = object.__new__(_CallbackHandler)
        handler.send_response = MagicMock(side_effect=BrokenPipeError("closed"))

        with patch("nxdrive.alfresco.auth.loopback.log.debug") as debug:
            handler._reply(200, _SUCCESS_HTML)

        debug.assert_called_once_with(
            "Loopback: failed to send response", exc_info=True
        )

    def test_log_message_routes_to_debug_logger(self) -> None:
        handler = object.__new__(_CallbackHandler)
        handler.address_string = MagicMock(return_value="127.0.0.1")

        with patch("nxdrive.alfresco.auth.loopback.log.debug") as debug:
            handler.log_message("%s %d", "GET /callback", 200)

        debug.assert_called_once_with(
            "Loopback %s - %s", "127.0.0.1", "GET /callback 200"
        )


class TestLoopbackHTTPServer:
    def test_initializes_base_server_without_authentication_side_effects(self) -> None:
        mocked = _http_server()

        mocked.base_init.assert_called_once_with(("127.0.0.1", 0), _CallbackHandler)
        assert mocked.server.delivered is False

    def test_deliver_invokes_each_hook_once(self) -> None:
        mocked = _http_server()
        query = {"code": "code", "state": "state"}

        mocked.server.deliver(query)
        mocked.server.deliver({"code": "other", "state": "other"})

        mocked.delivered.set.assert_called_once_with()
        mocked.callback.assert_called_once_with(query)
        mocked.on_delivered.assert_called_once_with()
        assert mocked.server.delivered is True

    def test_callback_error_does_not_prevent_shutdown_hook(self) -> None:
        mocked = _http_server()
        mocked.callback.side_effect = RuntimeError("callback failed")

        with patch("nxdrive.alfresco.auth.loopback.log.exception") as exception:
            mocked.server.deliver({"code": "code", "state": "state"})

        exception.assert_called_once_with("Loopback: on_callback raised")
        mocked.on_delivered.assert_called_once_with()

    def test_shutdown_hook_error_is_suppressed(self) -> None:
        mocked = _http_server()
        mocked.on_delivered.side_effect = RuntimeError("shutdown failed")

        with patch("nxdrive.alfresco.auth.loopback.log.exception") as exception:
            mocked.server.deliver({"code": "code", "state": "state"})

        mocked.callback.assert_called_once_with({"code": "code", "state": "state"})
        exception.assert_called_once_with("Loopback: on_delivered raised")


class TestLoopbackAuthServerStart:
    def test_start_configures_mocked_server_thread_and_timer(self) -> None:
        callback = MagicMock()
        http_server = MagicMock()
        http_server.server_address = ("127.0.0.1", 43123)
        serve_thread = MagicMock()
        timeout_timer = MagicMock()
        server = LoopbackAuthServer()

        with patch(
            "nxdrive.alfresco.auth.loopback._LoopbackHTTPServer",
            return_value=http_server,
        ) as server_cls, patch(
            "nxdrive.alfresco.auth.loopback.threading.Thread",
            return_value=serve_thread,
        ) as thread_cls, patch(
            "nxdrive.alfresco.auth.loopback.threading.Timer",
            return_value=timeout_timer,
        ) as timer_cls:
            result = server.start(on_callback=callback, timeout=12.5)

        assert result == "http://127.0.0.1:43123/callback"
        server_cls.assert_called_once_with(
            ("127.0.0.1", 0),
            _CallbackHandler,
            callback,
            server._async_shutdown,
        )
        thread_cls.assert_called_once_with(
            target=server._serve,
            name="LoopbackAuthServer-43123",
            daemon=True,
        )
        serve_thread.start.assert_called_once_with()
        timer_cls.assert_called_once_with(12.5, server._on_timeout)
        assert timeout_timer.daemon is True
        timeout_timer.start.assert_called_once_with()
        assert server.is_running is True

    def test_start_twice_raises_without_allocating_another_server(self) -> None:
        server = LoopbackAuthServer()
        server._server = MagicMock()

        with patch(
            "nxdrive.alfresco.auth.loopback._LoopbackHTTPServer"
        ) as server_cls, pytest.raises(RuntimeError, match="already started"):
            server.start(on_callback=MagicMock())

        server_cls.assert_not_called()

    def test_bind_error_is_converted_to_runtime_error(self) -> None:
        server = LoopbackAuthServer()

        with patch(
            "nxdrive.alfresco.auth.loopback._LoopbackHTTPServer",
            side_effect=OSError("permission denied"),
        ), patch(
            "nxdrive.alfresco.auth.loopback.threading.Thread"
        ) as thread_cls, pytest.raises(
            RuntimeError, match="Cannot bind.*permission denied"
        ):
            server.start(on_callback=MagicMock())

        thread_cls.assert_not_called()
        assert server.is_running is False


class TestLoopbackAuthServerLifecycle:
    def test_serve_is_noop_without_server(self) -> None:
        server = LoopbackAuthServer()

        server._serve()

        assert server.is_running is False

    def test_serve_calls_mocked_http_server(self) -> None:
        server = LoopbackAuthServer()
        server._server = MagicMock()

        server._serve()

        server._server.serve_forever.assert_called_once_with(poll_interval=0.5)

    def test_serve_logs_mocked_http_server_error(self) -> None:
        server = LoopbackAuthServer()
        server._server = MagicMock()
        server._server.serve_forever.side_effect = RuntimeError("serve failed")

        with patch("nxdrive.alfresco.auth.loopback.log.exception") as exception:
            server._serve()

        exception.assert_called_once_with("Loopback: serve_forever raised")

    def test_async_shutdown_starts_helper_thread(self) -> None:
        server = LoopbackAuthServer()
        helper_thread = MagicMock()

        with patch(
            "nxdrive.alfresco.auth.loopback.threading.Thread",
            return_value=helper_thread,
        ) as thread_cls:
            server._async_shutdown()

        thread_cls.assert_called_once_with(
            target=server.shutdown,
            name="LoopbackAuthServer-shutdown",
            daemon=True,
        )
        helper_thread.start.assert_called_once_with()

    def test_timeout_is_noop_without_server_or_after_delivery(self) -> None:
        server = LoopbackAuthServer()
        with patch.object(server, "shutdown") as shutdown:
            server._on_timeout()
            server._server = MagicMock(delivered=True)
            server._on_timeout()

        shutdown.assert_not_called()

    def test_timeout_shuts_down_undelivered_server(self) -> None:
        server = LoopbackAuthServer()
        server._server = MagicMock(delivered=False)

        with patch.object(server, "shutdown") as shutdown, patch(
            "nxdrive.alfresco.auth.loopback.log.warning"
        ) as warning:
            server._on_timeout()

        warning.assert_called_once_with(
            "Loopback OAuth2 server timed out; shutting down"
        )
        shutdown.assert_called_once_with()

    def test_shutdown_cleans_all_mocked_resources(self) -> None:
        server = LoopbackAuthServer()
        http_server = MagicMock()
        serve_thread = MagicMock()
        serve_thread.is_alive.return_value = True
        timeout_timer = MagicMock()
        server._server = http_server
        server._thread = serve_thread
        server._timeout_timer = timeout_timer

        server.shutdown()

        assert server._server is None
        assert server._thread is None
        assert server._timeout_timer is None
        timeout_timer.cancel.assert_called_once_with()
        http_server.shutdown.assert_called_once_with()
        http_server.server_close.assert_called_once_with()
        serve_thread.join.assert_called_once_with(timeout=2.0)

    def test_shutdown_suppresses_mocked_cleanup_errors(self) -> None:
        server = LoopbackAuthServer()
        timeout_timer = MagicMock()
        timeout_timer.cancel.side_effect = RuntimeError("timer failed")
        http_server = MagicMock()
        http_server.shutdown.side_effect = RuntimeError("shutdown failed")
        http_server.server_close.side_effect = RuntimeError("close failed")
        serve_thread = MagicMock()
        serve_thread.is_alive.return_value = False
        server._timeout_timer = timeout_timer
        server._server = http_server
        server._thread = serve_thread

        with patch("nxdrive.alfresco.auth.loopback.log.debug") as debug:
            server.shutdown()

        assert debug.call_args_list == [
            call("Loopback: server.shutdown() failed", exc_info=True),
            call("Loopback: server_close() failed", exc_info=True),
        ]
        serve_thread.join.assert_not_called()

    def test_shutdown_is_idempotent(self) -> None:
        server = LoopbackAuthServer()

        server.shutdown()
        server.shutdown()

        assert server.is_running is False
