"""
Loopback HTTP server for OAuth2/PKCE authorization-code redirects.

Alfresco AIMS/Keycloak does not accept the ``nxdrive://`` custom URL
scheme in its ``redirect_uri`` allow-list. It does, however, whitelist
native-app loopback URLs of the form ``http://127.0.0.1:<port>/callback``
(per RFC 8252 §7.3). This module implements a short-lived, single-shot
HTTP server on an OS-assigned ephemeral loopback port to catch the
IdP redirect and hand the query dict to the calling code.

Design notes
------------
* Binds to ``127.0.0.1`` only — unreachable from other machines.
* Uses port 0 → the kernel picks an unused port; no collision handling
  needed.
* Handles exactly one valid ``/callback?code=…&state=…`` request; any
  other path or malformed callback yields 404 / 400.
* Auto-shuts down after the first successful delivery (from a helper
  thread so the response finishes flushing to the browser first).
* Enforces a hard timeout (default 5 minutes) so an abandoned flow
  can't leak a listening socket.
* Pure-stdlib — no Qt, authlib or requests dependencies here.
"""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging import getLogger
from typing import Callable, Dict, Optional
from urllib.parse import parse_qs, urlparse

__all__ = ("LoopbackAuthServer",)

log = getLogger(__name__)


_SUCCESS_HTML = (
    b"<!DOCTYPE html>"
    b"<html lang='en'><head>"
    b"<meta charset='utf-8'>"
    b"<title>HYLAND</title>"
    b"<style>"
    b"body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;"
    b"text-align:center;padding:4em 1em;color:#222;background:#f7f7f7;}"
    b"h1{color:#0066cc;margin:0 0 .5em;}"
    b"p{color:#555;font-size:1.05em;}"
    b"</style></head><body>"
    b"<h1>Authentication complete</h1>"
    b"<p>You can close this browser tab and return to the application.</p>"
    b"</body></html>"
)

_ERROR_HTML = (
    b"<!DOCTYPE html>"
    b"<html lang='en'><head><meta charset='utf-8'>"
    b"<title>HYLAND</title></head>"
    b"<body><h1>Not a valid redirect.</h1></body></html>"
)


class _CallbackHandler(BaseHTTPRequestHandler):
    """One-shot request handler.

    Only ``GET /callback?code=…&state=…`` is honoured. Everything else
    is answered with a 404 (unknown path) or 400 (missing params).
    Responses include no user-controlled data — avoids reflected-XSS
    in the tiny confirmation page.
    """

    # Set by BaseHTTPRequestHandler; typed here for clarity.
    server: "_LoopbackHTTPServer"

    def do_GET(self) -> None:  # noqa: N802 — required by BaseHTTPRequestHandler
        parsed = urlparse(self.path)
        if parsed.path.rstrip("/") != "/callback":
            self._reply(404, _ERROR_HTML)
            return

        raw = parse_qs(parsed.query, keep_blank_values=False)
        query: Dict[str, str] = {k: v[0] for k, v in raw.items() if v}

        if "code" not in query or "state" not in query:
            self._reply(400, _ERROR_HTML)
            return

        # Send the success page *before* dispatching so the browser
        # sees the confirmation even if the delivery hook is slow.
        self._reply(200, _SUCCESS_HTML)
        self.server.deliver(query)

    def _reply(self, status: int, body: bytes) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except Exception:  # pragma: no cover — browser hung up
            log.debug("Loopback: failed to send response", exc_info=True)

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        # Silence BaseHTTPRequestHandler's stderr logging.
        log.debug("Loopback %s - %s", self.address_string(), format % args)


class _LoopbackHTTPServer(HTTPServer):
    """HTTPServer wrapper carrying the caller-supplied delivery hooks."""

    def __init__(
        self,
        address: tuple,
        handler_cls: type,
        on_callback: Callable[[Dict[str, str]], None],
        on_delivered: Callable[[], None],
    ) -> None:
        super().__init__(address, handler_cls)
        self._on_callback = on_callback
        self._on_delivered = on_delivered
        self._delivered = threading.Event()

    def deliver(self, query: Dict[str, str]) -> None:
        """Invoke the user callback (once) and trigger async shutdown."""
        if self._delivered.is_set():
            return
        self._delivered.set()
        try:
            self._on_callback(query)
        except Exception:
            log.exception("Loopback: on_callback raised")
        try:
            self._on_delivered()
        except Exception:
            log.exception("Loopback: on_delivered raised")

    @property
    def delivered(self) -> bool:
        return self._delivered.is_set()


class LoopbackAuthServer:
    """One-shot loopback HTTP server for OAuth2 authorization-code callbacks.

    Typical usage::

        server = LoopbackAuthServer()
        redirect_uri = server.start(on_callback=my_callback)
        # → open ``redirect_uri`` in the auth URL, launch browser, …
        # server auto-shuts after the first valid callback or after 5 min.
        server.shutdown()   # idempotent; safe to call from any thread

    ``on_callback`` receives a ``dict`` with (at least) the ``code``
    and ``state`` query-string parameters. It is invoked on the HTTP
    handler's background thread — the caller is responsible for any
    thread-hopping it needs (e.g. a Qt queued signal).
    """

    DEFAULT_TIMEOUT = 300  # seconds — 5 minutes

    def __init__(self) -> None:
        self._server: Optional[_LoopbackHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._timeout_timer: Optional[threading.Timer] = None
        self._lock = threading.Lock()

    def start(
        self,
        on_callback: Callable[[Dict[str, str]], None],
        *,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> str:
        """Bind the socket, launch the serving thread, arm the timeout.

        Returns the ``http://127.0.0.1:<port>/callback`` URL to hand to
        the IdP as the ``redirect_uri``. Raises ``RuntimeError`` if
        already started or if the loopback bind fails.
        """
        with self._lock:
            if self._server is not None:
                raise RuntimeError("LoopbackAuthServer already started")

            try:
                server = _LoopbackHTTPServer(
                    ("127.0.0.1", 0),
                    _CallbackHandler,
                    on_callback,
                    self._async_shutdown,
                )
            except OSError as exc:
                raise RuntimeError(
                    f"Cannot bind loopback OAuth2 server: {exc}"
                ) from exc

            port = server.server_address[1]
            self._server = server

            self._thread = threading.Thread(
                target=self._serve,
                name=f"LoopbackAuthServer-{port}",
                daemon=True,
            )
            self._thread.start()

            self._timeout_timer = threading.Timer(timeout, self._on_timeout)
            self._timeout_timer.daemon = True
            self._timeout_timer.start()

            redirect_uri = f"http://127.0.0.1:{port}/callback"
            log.info("Loopback OAuth2 server listening at %s", redirect_uri)
            return redirect_uri

    def _serve(self) -> None:
        server = self._server
        if server is None:
            return
        try:
            server.serve_forever(poll_interval=0.5)
        except Exception:  # pragma: no cover
            log.exception("Loopback: serve_forever raised")
        finally:
            log.debug("Loopback: server thread exiting")

    def _async_shutdown(self) -> None:
        """Spawn a helper thread to call :meth:`shutdown`.

        Called from within a request handler; ``server.shutdown()``
        would deadlock if invoked on the same thread as
        ``serve_forever``.
        """
        threading.Thread(
            target=self.shutdown,
            name="LoopbackAuthServer-shutdown",
            daemon=True,
        ).start()

    def _on_timeout(self) -> None:
        with self._lock:
            server = self._server
        if server is None or server.delivered:
            return
        log.warning("Loopback OAuth2 server timed out; shutting down")
        self.shutdown()

    def shutdown(self) -> None:
        """Stop the server and release the socket. Idempotent."""
        with self._lock:
            server = self._server
            thread = self._thread
            timer = self._timeout_timer
            self._server = None
            self._thread = None
            self._timeout_timer = None

        if timer is not None:
            try:
                timer.cancel()
            except Exception:  # pragma: no cover
                pass

        if server is not None:
            try:
                server.shutdown()
            except Exception:  # pragma: no cover
                log.debug("Loopback: server.shutdown() failed", exc_info=True)
            try:
                server.server_close()
            except Exception:  # pragma: no cover
                log.debug("Loopback: server_close() failed", exc_info=True)

        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)

    @property
    def is_running(self) -> bool:
        with self._lock:
            return self._server is not None
