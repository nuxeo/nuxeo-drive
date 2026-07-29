"""Unit tests for :mod:`nxdrive.alfresco.registration`.

The module wires an Alfresco-specific auth factory and re-login handler
into :mod:`nxdrive.drive.server_type`. These tests exercise the small
pure helpers directly; the ``register`` side-effect is exercised as
part of the wider engine integration tests.
"""

from unittest.mock import MagicMock, patch

import pytest


class TestAuthFactory:
    """``_alfresco_auth_factory`` picks the right auth handler by token type."""

    def test_dict_token_returns_oauth_authentication(self) -> None:
        from nxdrive.alfresco import registration as reg

        fake_auth = object()
        with patch(
            "nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication",
            return_value=fake_auth,
        ) as ctor:
            got = reg._alfresco_auth_factory(
                "https://alfresco.example.com/alfresco",
                {"access_token": "x", "refresh_token": "y"},
                dao=MagicMock(),
            )
        assert got is fake_auth
        # The host is forwarded verbatim.
        ctor.assert_called_once()
        assert ctor.call_args.args[0] == "https://alfresco.example.com/alfresco"

    def test_string_token_returns_token_authentication(self) -> None:
        from nxdrive.alfresco import registration as reg

        fake_auth = object()
        with patch(
            "nxdrive.drive.auth.token.TokenAuthentication",
            return_value=fake_auth,
        ) as ctor:
            got = reg._alfresco_auth_factory(
                "https://alfresco.example.com/alfresco",
                "some-opaque-ticket",
                dao=MagicMock(),
            )
        assert got is fake_auth
        ctor.assert_called_once()


class TestPasswordAuthHandler:
    """The password handler delegates to ``basic_auth`` from the GUI package."""

    def test_delegates_to_basic_auth(self) -> None:
        from nxdrive.alfresco import registration as reg

        api = MagicMock()
        with patch("nxdrive.alfresco.gui.auth.basic_auth") as basic_auth:
            reg._alfresco_password_auth_handler(
                api,
                "/tmp/local",
                "https://alfresco.example.com/alfresco",
                "admin",
                "secret",
            )
        basic_auth.assert_called_once_with(
            api,
            "/tmp/local",
            "https://alfresco.example.com/alfresco",
            "admin",
            "secret",
        )


class TestRegistrationImport:
    """Importing the module must not raise even if the alfresco package
    version cannot be detected.
    """

    def test_module_importable(self) -> None:
        import importlib

        module = importlib.import_module("nxdrive.alfresco.registration")
        # ``_client_version`` is set to the alfresco package version or "".
        assert hasattr(module, "_client_version")
        assert isinstance(module._client_version, str)


@pytest.mark.parametrize(
    "token,expected_dict_branch",
    [
        ({"access_token": "a"}, True),
        ({}, True),  # still a dict → OAuth branch
        ("ticket-string", False),
        (None, False),
    ],
)
def test_factory_branch_selection(token, expected_dict_branch) -> None:
    """Verify the branch selection matches the token type."""
    from nxdrive.alfresco import registration as reg

    with patch(
        "nxdrive.alfresco.auth.oauth2.AlfrescoOAuthentication",
        return_value="oauth",
    ), patch("nxdrive.drive.auth.token.TokenAuthentication", return_value="token"):
        got = reg._alfresco_auth_factory(
            "https://alfresco.example.com/alfresco",
            token,
            dao=MagicMock(),
        )
    assert got == ("oauth" if expected_dict_branch else "token")
