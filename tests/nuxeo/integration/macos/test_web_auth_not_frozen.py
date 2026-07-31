"""Integration tests for _web_auth_not_frozen method - macOS only.

The method now delegates to the server-type's ``debug_auth_handler`` hook.
These tests verify:
- Correct delegation via server_type.detect_by_url
- The Nuxeo debug_auth_handler is called with the right arguments
- Graceful handling when no handler is registered
"""

from unittest.mock import Mock, patch

import pytest

from tests.markers import mac_only

_PATCH_ST = "nxdrive.drive.server_type"


def _call_web_auth(app, url, callback_params=None):
    """Call the real _web_auth_not_frozen on a mock app."""
    from nxdrive.drive.gui.application import Application

    Application._web_auth_not_frozen(app, url, callback_params or {})


@mac_only
class TestWebAuthNotFrozen:
    """Test suite for _web_auth_not_frozen delegation - macOS only."""

    @pytest.fixture
    def mock_app(self):
        """Create a lightweight mock Application (no real Manager)."""
        app = Mock()
        app.manager = Mock()
        app.api = Mock()
        app.api.handle_token = Mock()
        return app

    def test_web_auth_not_frozen_successful_authentication(
        self, mock_app, nuxeo_url
    ):
        """Test that debug_auth_handler is called with correct args."""
        with patch(_PATCH_ST) as mock_st:
            mock_config = Mock()
            mock_handler = Mock()
            mock_config.debug_auth_handler = mock_handler
            mock_st.detect_by_url.return_value = mock_config

            _call_web_auth(mock_app, nuxeo_url)

            mock_st.detect_by_url.assert_called_once_with(nuxeo_url)
            mock_handler.assert_called_once_with(
                nuxeo_url, mock_app.manager, mock_app.api
            )

    def test_web_auth_not_frozen_authentication_failure(self, mock_app, nuxeo_url):
        """Test that exceptions in the handler propagate normally."""
        with patch(_PATCH_ST) as mock_st:
            mock_config = Mock()
            mock_config.debug_auth_handler = Mock(
                side_effect=Exception("auth failed")
            )
            mock_st.detect_by_url.return_value = mock_config

            with pytest.raises(Exception, match="auth failed"):
                _call_web_auth(mock_app, nuxeo_url)

    def test_web_auth_not_frozen_cancel_authentication(self, mock_app, nuxeo_url):
        """Test handler is invoked even for cancel scenarios."""
        with patch(_PATCH_ST) as mock_st:
            mock_config = Mock()
            mock_config.debug_auth_handler = Mock()
            mock_st.detect_by_url.return_value = mock_config

            _call_web_auth(mock_app, nuxeo_url)

            mock_config.debug_auth_handler.assert_called_once()

    def test_web_auth_not_frozen_uses_environment_defaults(
        self, mock_app, nuxeo_url
    ):
        """Test that detect_by_url receives the correct URL."""
        with patch(_PATCH_ST) as mock_st:
            mock_config = Mock()
            mock_config.debug_auth_handler = Mock()
            mock_st.detect_by_url.return_value = mock_config

            custom_url = "https://custom.nuxeo.server/nuxeo"
            _call_web_auth(mock_app, custom_url)

            mock_st.detect_by_url.assert_called_once_with(custom_url)
            mock_config.debug_auth_handler.assert_called_once_with(
                custom_url, mock_app.manager, mock_app.api
            )

    def test_web_auth_not_frozen_proxy_and_ssl_settings(self, mock_app, nuxeo_url):
        """Test that manager is passed to handler (carries proxy/SSL config)."""
        with patch(_PATCH_ST) as mock_st:
            mock_config = Mock()
            mock_config.debug_auth_handler = Mock()
            mock_st.detect_by_url.return_value = mock_config

            _call_web_auth(mock_app, nuxeo_url)

            call_args = mock_config.debug_auth_handler.call_args[0]
            assert call_args[1] is mock_app.manager

    def test_web_auth_not_frozen_dialog_ui_elements(self, mock_app, nuxeo_url):
        """Test that when no handler is registered, a warning is logged."""
        with patch(_PATCH_ST) as mock_st, patch(
            "nxdrive.drive.gui.application.log"
        ) as mock_log:
            mock_config = Mock()
            mock_config.debug_auth_handler = None
            mock_config.key = "unknown"
            mock_st.detect_by_url.return_value = mock_config

            _call_web_auth(mock_app, nuxeo_url)

            mock_log.warning.assert_called_once()
            assert "No debug_auth_handler" in mock_log.warning.call_args[0][0]
