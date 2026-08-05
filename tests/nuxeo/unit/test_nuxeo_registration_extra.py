"""Tests for nxdrive/nuxeo/registration.py"""

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch


@contextmanager
def _mock_debug_auth_dialog():
    """Provide a fully mocked debug-auth dialog and Nuxeo client."""
    dialog = MagicMock()
    layout = MagicMock()
    username = MagicMock()
    username.text.return_value = "typed-user"
    password = MagicMock()
    password.text.return_value = "typed-password"
    buttons = MagicMock()
    line_edit = MagicMock(side_effect=[username, password])
    nuxeo_cls = MagicMock()
    manager = MagicMock()
    manager.device_id = "device-id"
    manager.proxy.settings.return_value = {"https": "proxy.example"}
    api = MagicMock()

    with patch("nxdrive.drive.qt.imports.QDialog", return_value=dialog), patch(
        "nxdrive.drive.qt.imports.QVBoxLayout", return_value=layout
    ), patch("nxdrive.drive.qt.imports.QLineEdit", line_edit), patch(
        "nxdrive.drive.qt.imports.QDialogButtonBox", return_value=buttons
    ), patch(
        "nuxeo.client.Nuxeo", nuxeo_cls
    ), patch(
        "nxdrive.drive.utils.get_verify", return_value=False
    ), patch(
        "nxdrive.drive.utils.client_certificate", return_value="client-certificate"
    ), patch(
        "nxdrive.drive.metrics.utils.current_os", return_value="Test OS"
    ):
        yield SimpleNamespace(
            api=api,
            buttons=buttons,
            dialog=dialog,
            layout=layout,
            line_edit=line_edit,
            manager=manager,
            nuxeo_cls=nuxeo_cls,
            password=password,
            username=username,
        )


def test_auth_factory_with_dict_token():
    """dict token → OAuthentication."""
    from nxdrive.nuxeo.registration import _nuxeo_auth_factory

    token = {"access_token": "abc", "refresh_token": "def"}
    with patch("nxdrive.nuxeo.auth.oauth2.OAuthentication") as MockOAuth:
        MockOAuth.return_value = "oauth_obj"
        result = _nuxeo_auth_factory("http://host", token, extra="val")
    MockOAuth.assert_called_once_with("http://host", token=token, extra="val")
    assert result == "oauth_obj"


def test_auth_factory_with_str_token():
    """str token → TokenAuthentication."""
    from nxdrive.nuxeo.registration import _nuxeo_auth_factory

    with patch("nxdrive.nuxeo.auth.token.TokenAuthentication") as MockToken:
        MockToken.return_value = "token_obj"
        result = _nuxeo_auth_factory("http://host", "my_token")
    MockToken.assert_called_once_with("http://host", token="my_token")
    assert result == "token_obj"


def test_debug_init():
    """_nuxeo_debug_init sets CHECK_PARAMS."""
    import nuxeo.constants

    from nxdrive.nuxeo.registration import _nuxeo_debug_init

    original = getattr(nuxeo.constants, "CHECK_PARAMS", None)
    try:
        _nuxeo_debug_init()
        assert nuxeo.constants.CHECK_PARAMS is True
    finally:
        if original is not None:
            nuxeo.constants.CHECK_PARAMS = original
        else:
            del nuxeo.constants.CHECK_PARAMS


def test_parse_direct_transfer_remote_path():
    from nxdrive.nuxeo.registration import _nuxeo_parse_direct_transfer_remote_path

    with patch(
        "nxdrive.nuxeo.protocol.parse_direct_transfer_remote_path",
        return_value="/parsed",
    ):
        result = _nuxeo_parse_direct_transfer_remote_path("/some/path")
    assert result == "/parsed"


def test_normalize_download_server_path():
    from nxdrive.nuxeo.registration import _nuxeo_normalize_download_server_path

    with patch(
        "nxdrive.nuxeo.protocol.normalize_download_server_path",
        return_value="normalized",
    ):
        result = _nuxeo_normalize_download_server_path("server.com/nuxeo")
    assert result == "normalized"


def test_normalize_protocol_url():
    from nxdrive.nuxeo.registration import _nuxeo_normalize_protocol_url

    with patch(
        "nxdrive.nuxeo.protocol.normalize_protocol_url", return_value="nxdrive://ok"
    ):
        result = _nuxeo_normalize_protocol_url("nxdrive://something")
    assert result == "nxdrive://ok"


def test_protocol_token_pattern():
    from nxdrive.nuxeo.registration import _nuxeo_protocol_token_pattern

    result = _nuxeo_protocol_token_pattern()
    assert isinstance(result, str)


def test_get_test_server_url_from_env():
    from nxdrive.nuxeo.registration import _nuxeo_get_test_server_url

    with patch.dict("os.environ", {"NXDRIVE_TEST_NUXEO_URL": "http://test:8080/nuxeo"}):
        result = _nuxeo_get_test_server_url()
    assert result == "http://test:8080/nuxeo"


def test_get_test_server_url_default():
    from nxdrive.nuxeo.registration import _nuxeo_get_test_server_url

    with patch.dict("os.environ", {}, clear=True):
        result = _nuxeo_get_test_server_url()
    assert result == ""


def test_save_auth_callback_params():
    from nxdrive.nuxeo.registration import _nuxeo_save_auth_callback_params

    api = MagicMock()
    params = {"code": "xyz"}
    with patch(
        "nxdrive.nuxeo.gui.auth_callback_store.save_auth_callback_params"
    ) as mock_save:
        _nuxeo_save_auth_callback_params(api, params)
    mock_save.assert_called_once_with(api, params)


def test_load_auth_callback_params():
    from nxdrive.nuxeo.registration import _nuxeo_load_auth_callback_params

    api = MagicMock()
    with patch(
        "nxdrive.nuxeo.gui.auth_callback_store.load_auth_callback_params",
        return_value=None,
    ) as mock_load:
        result = _nuxeo_load_auth_callback_params(api)
    mock_load.assert_called_once_with(api)
    assert result is None


def test_clear_auth_callback_params():
    from nxdrive.nuxeo.registration import _nuxeo_clear_auth_callback_params

    api = MagicMock()
    with patch(
        "nxdrive.nuxeo.gui.auth_callback_store.clear_auth_callback_params"
    ) as mock_clear:
        _nuxeo_clear_auth_callback_params(api)
    mock_clear.assert_called_once_with(api)


def test_debug_auth_handler_requests_token_and_dispatches_it():
    from nxdrive.drive.constants import APP_NAME, TOKEN_PERMISSION
    from nxdrive.drive.qt import constants as qt
    from nxdrive.nuxeo.registration import _nuxeo_debug_auth_handler

    with patch.dict(
        "os.environ",
        {
            "NXDRIVE_TEST_USERNAME": "default-user",
            "NXDRIVE_TEST_PASSWORD": "default-password",
        },
        clear=True,
    ), _mock_debug_auth_dialog() as mocked:
        mocked.nuxeo_cls.return_value.client.request_auth_token.return_value = (
            "auth-token"
        )

        _nuxeo_debug_auth_handler(
            "https://server.example/nuxeo", mocked.manager, mocked.api
        )
        accept = mocked.buttons.accepted.connect.call_args.args[0]
        accept()

    mocked.dialog.setWindowTitle.assert_called_once_with("Authentication")
    mocked.dialog.resize.assert_called_once_with(250, 100)
    mocked.line_edit.assert_has_calls(
        [
            call("default-user", parent=mocked.dialog),
            call("default-password", parent=mocked.dialog),
        ]
    )
    mocked.password.setEchoMode.assert_called_once_with(qt.Password)
    mocked.layout.addWidget.assert_has_calls(
        [call(mocked.username), call(mocked.password), call(mocked.buttons)]
    )
    mocked.buttons.setStandardButtons.assert_called_once_with(qt.Cancel | qt.Ok)
    mocked.dialog.setLayout.assert_called_once_with(mocked.layout)
    mocked.dialog.exec.assert_called_once_with()
    mocked.manager.proxy.settings.assert_called_once_with(
        url="https://server.example/nuxeo"
    )
    mocked.nuxeo_cls.assert_called_once_with(
        host="https://server.example/nuxeo",
        auth=("typed-user", "typed-password"),
        proxies={"https": "proxy.example"},
        verify=False,
        cert="client-certificate",
    )
    mocked.nuxeo_cls.return_value.client.request_auth_token.assert_called_once_with(
        "device-id",
        TOKEN_PERMISSION,
        app_name=APP_NAME,
        device="Test OS",
    )
    mocked.api.handle_token.assert_called_once_with("auth-token", "typed-user")
    mocked.dialog.close.assert_called_once_with()


def test_debug_auth_handler_cancel_closes_without_authenticating():
    from nxdrive.nuxeo.registration import _nuxeo_debug_auth_handler

    with _mock_debug_auth_dialog() as mocked:
        _nuxeo_debug_auth_handler(
            "https://server.example/nuxeo", mocked.manager, mocked.api
        )
        reject = mocked.buttons.rejected.connect.call_args.args[0]
        reject()

    mocked.dialog.close.assert_called_once_with()
    mocked.nuxeo_cls.assert_not_called()
    mocked.api.handle_token.assert_not_called()


def test_debug_auth_handler_dispatches_empty_token_on_invalid_credentials():
    from nxdrive.nuxeo.registration import _nuxeo_debug_auth_handler

    logger = MagicMock()
    with _mock_debug_auth_dialog() as mocked, patch(
        "logging.getLogger", return_value=logger
    ):
        mocked.nuxeo_cls.return_value.client.request_auth_token.side_effect = (
            RuntimeError("invalid credentials")
        )

        _nuxeo_debug_auth_handler(
            "https://server.example/nuxeo", mocked.manager, mocked.api
        )
        accept = mocked.buttons.accepted.connect.call_args.args[0]
        accept()

    logger.error.assert_called_once_with("Connection error: invalid credentials")
    mocked.api.handle_token.assert_called_once_with("", "typed-user")
    mocked.dialog.close.assert_called_once_with()
