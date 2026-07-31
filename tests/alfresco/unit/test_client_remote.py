"""Unit tests for :mod:`nxdrive.alfresco.client.remote`.

These are pure unit tests — the underlying ``alfresco.Alfresco`` client
is mocked so no network is touched.
"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def _client_patch():
    """Patch out the heavy ``alfresco.Alfresco`` constructor.

    Also stub :mod:`alfresco.auth` handlers so we don't need to build
    real ``BasicAuth`` / ``TicketAuth`` objects with valid arguments.
    """
    with patch("nxdrive.alfresco.client.remote.Alfresco") as fake_alfresco, patch(
        "nxdrive.alfresco.client.remote.BasicAuth", return_value=object()
    ), patch("nxdrive.alfresco.client.remote.TicketAuth", return_value=object()):
        fake_alfresco.return_value = MagicMock(
            session=MagicMock(headers={}),
        )
        yield fake_alfresco


class TestConstructor:
    """Cover the various auth strategies encoded in ``__init__``."""

    def test_basic_auth_when_no_credentials(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        assert remote.server_url == "https://alfresco.example.com/alfresco"
        assert remote.user_id == "admin"
        assert remote.device_id == "device-1"
        assert remote.version == "1.0.0"

    def test_positive_timeout_is_preserved(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
            timeout=60,
        )
        assert remote.timeout == 60

    def test_non_positive_timeout_defaults_to_30(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
            timeout=0,
        )
        assert remote.timeout == 30

    def test_base_url_strips_trailing_alfresco(self, _client_patch) -> None:
        """The vendor client re-adds ``/alfresco/api/...`` so we must
        strip that suffix from the caller-supplied URL to avoid a
        doubled path segment.
        """
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        # The Alfresco class was called with the trimmed URL.
        call_kwargs = _client_patch.call_args.kwargs
        assert call_kwargs["url"] == "https://alfresco.example.com"

    def test_ticket_auth_when_alfresco_ticket_passed(self, _client_patch) -> None:
        from nxdrive.alfresco.client import remote as remote_mod
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        with patch.object(
            remote_mod.TicketAuth, "from_ticket", return_value=object()
        ) as from_ticket:
            AlfrescoRemote(
                "https://alfresco.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                alfresco_ticket="TICKET-abc",
            )
        from_ticket.assert_called_once_with("admin", "TICKET-abc")

    def test_string_token_uses_oauth2_bearer(self, _client_patch) -> None:
        from nxdrive.alfresco.client import remote as remote_mod
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        with patch.object(
            remote_mod.OAuth2Auth, "from_token", return_value=object()
        ) as from_token:
            AlfrescoRemote(
                "https://alfresco.example.com/alfresco",
                "admin",
                "device-1",
                "1.0.0",
                token="bearer-string",
            )
        from_token.assert_called_once_with(access_token="bearer-string")


class TestRepr:
    """`__repr__` should be a stable one-liner containing url + user_id."""

    def test_repr_contains_url_and_user(self, _client_patch) -> None:
        from urllib.parse import urlparse

        from nxdrive.alfresco.client.remote import AlfrescoRemote

        url = "https://alfresco.example.com/alfresco"
        remote = AlfrescoRemote(
            url,
            "admin",
            "device-1",
            "1.2.3",
        )
        rendered = repr(remote)
        assert rendered.startswith("<AlfrescoRemote ")
        assert "admin" in rendered
        # Validate the full hostname from the URL appears in the repr
        expected_host = urlparse(url).hostname
        assert expected_host is not None
        assert expected_host == "alfresco.example.com"
        assert expected_host in rendered


class TestNoOpMetricsAndTasks:
    """The nested no-op stubs exist so the engine can call metrics/tasks
    without knowing whether the flavor supports them.
    """

    def test_metrics_send_does_not_raise(self) -> None:
        from nxdrive.alfresco.client.remote import _NoOpMetrics

        _NoOpMetrics().send()
        _NoOpMetrics().push_sync_event()
        _NoOpMetrics().force_poll()
        _NoOpMetrics().start()

    def test_tasks_get_returns_empty_list(self) -> None:
        from nxdrive.alfresco.client.remote import _NoOpTasks

        assert _NoOpTasks().get() == []
        assert _NoOpTasks().get("uid", limit=10) == []


class TestClose:
    """``close()`` must not raise when the underlying client is missing."""

    def test_close_is_safe(self, _client_patch) -> None:
        from nxdrive.alfresco.client.remote import AlfrescoRemote

        remote = AlfrescoRemote(
            "https://alfresco.example.com/alfresco",
            "admin",
            "device-1",
            "1.0.0",
        )
        # Should not raise.
        remote.close()
