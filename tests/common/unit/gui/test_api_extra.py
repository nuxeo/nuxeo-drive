"""Deterministic unit coverage for the shared GUI API.

The product-specific API tests exercise the main Nuxeo flows.  These tests
concentrate on shared dispatch, cleanup, error, and lightweight delegation
paths without opening a browser, starting Qt's event loop, or using a server.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
import requests

from nxdrive.drive.constants import DirectDownloadStatus, TransferStatus
from nxdrive.drive.exceptions import (
    EncryptedSSLCertificateKey,
    EngineTypeMissing,
    InvalidSSLCertificate,
    MissingClientSSLCertificate,
    RemoteOAuth2Error,
    RootAlreadyBindWithDifferentAccount,
)
from nxdrive.drive.gui import api as api_module
from nxdrive.drive.gui.api import QMLDriveApi
from nxdrive.drive.updater.constants import Login


def server_config(**overrides):
    """Build the complete registry shape consumed by :class:`QMLDriveApi`."""
    values = {
        "key": "TEST",
        "engine_type": "TEST_ENGINE",
        "browser_startup_page": "startup",
        "oauth2_class_path": "tests.oauth.Handler",
        "supports_browser_token_update": True,
        "ssl_login_page": "",
        "password_auth_handler": None,
        "relogin_handler": None,
        "oauth2_password_auth_handler": None,
        "save_auth_callback_params_hook": None,
        "load_auth_callback_params_hook": None,
        "clear_auth_callback_params_hook": None,
        "local_folder_name": "Test Drive",
        "test_server_url_getter": None,
        "is_url_fallback": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.fixture
def api_env():
    """Create an API with explicit mocks for every external boundary."""
    manager = Mock(name="manager")
    manager.engines = {}
    manager.dao = Mock(name="manager_dao")
    manager.proxy = Mock(name="proxy")

    application = Mock(name="application")
    application.manager = manager

    api = QMLDriveApi(application)
    # Instance-level mocks make signal assertions deterministic and prevent
    # callbacks connected by other tests from influencing these tests.
    api.setMessage = Mock(name="setMessage")
    api.openAuthenticationDialog = Mock(name="openAuthenticationDialog")
    api.downloadLocationChanged = Mock(name="downloadLocationChanged")
    api.showReloginPopup = Mock(name="showReloginPopup")
    api.callback_params = {}
    return SimpleNamespace(api=api, manager=manager, application=application)


def test_pending_auth_callback_hooks_are_isolated_and_defensive(api_env):
    api = api_env.api
    saved = Mock()
    loaded = Mock(return_value={"engine": "engine-1"})
    cleared = Mock()
    config = server_config(
        save_auth_callback_params_hook=saved,
        load_auth_callback_params_hook=loaded,
        clear_auth_callback_params_hook=cleared,
    )
    options = SimpleNamespace(server_type="TEST")

    with patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get", return_value=config
    ) as get_config:
        params = {"engine": "engine-1"}
        api._save_pending_auth_callback_params(params)
        assert api._load_pending_auth_callback_params() == params
        api._clear_pending_auth_callback_params()

        saved.assert_called_once_with(api, params)
        loaded.assert_called_once_with(api)
        cleared.assert_called_once_with(api)
        assert get_config.call_args_list == [call("TEST"), call("TEST"), call("TEST")]

        config.load_auth_callback_params_hook = Mock(return_value="not-a-dict")
        assert api._load_pending_auth_callback_params() == {}

        config.save_auth_callback_params_hook = Mock(side_effect=ValueError("bad"))
        config.load_auth_callback_params_hook = Mock(side_effect=ValueError("bad"))
        config.clear_auth_callback_params_hook = Mock(side_effect=ValueError("bad"))
        api._save_pending_auth_callback_params(params)
        assert api._load_pending_auth_callback_params() == {}
        api._clear_pending_auth_callback_params()

        config.save_auth_callback_params_hook = None
        config.load_auth_callback_params_hook = None
        config.clear_auth_callback_params_hook = None
        api._save_pending_auth_callback_params(params)
        assert api._load_pending_auth_callback_params() == {}
        api._clear_pending_auth_callback_params()


def test_server_config_resolution_honors_brand_and_url_detection(api_env):
    api = api_env.api
    branded = server_config(key="ALFRESCO")
    default = server_config(key="NXDRIVE")
    detected = server_config(key="DETECTED")
    fallback = server_config(key="FALLBACK", is_url_fallback=True)

    options = SimpleNamespace(server_type="ALFRESCO")
    with patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(
        api_module.st,
        "get",
        side_effect=lambda key: {
            "ALFRESCO": branded,
            "NXDRIVE": default,
        }[key],
    ), patch.object(
        api_module.st, "detect_by_url"
    ) as detect:
        assert api._resolve_server_config("https://neutral.example") is branded
        detect.assert_not_called()

    options.server_type = "NXDRIVE"
    with patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(api_module.st, "get", return_value=default), patch.object(
        api_module.st, "detect_by_url", return_value=fallback
    ):
        assert api._resolve_server_config("https://unknown.example") is default

    options.server_type = None
    with patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(api_module.st, "detect_by_url", return_value=detected):
        assert api._resolve_server_config("https://known.example") is detected


def test_engine_data_notification_and_updater_delegates(api_env):
    api, manager = api_env.api, api_env.manager
    dao = Mock()
    engine = SimpleNamespace(uid="engine-1", dao=dao, cancel_session=Mock())
    manager.engines = {"engine-1": engine}

    dao.get_last_files_count.return_value = 7
    assert api.get_last_files_count("engine-1") == 7
    dao.get_last_files_count.assert_called_once_with(duration=60)
    assert api.get_last_files_count("missing") == 0

    url = Mock()
    url.toLocalFile.return_value = "relative/file.txt"
    with patch.object(
        api_module, "abspath", return_value="/absolute/file.txt"
    ) as abspath:
        assert api.to_local_file(url) == "/absolute/file.txt"
        abspath.assert_called_once_with("relative/file.txt")

    api.discard_notification("notice")
    manager.notification_service.discard_notification.assert_called_once_with("notice")

    manager.updater.status = "downloading"
    manager.updater.version = "6.0"
    manager.updater.available_version = "6.1"
    assert api.get_update_status() == "downloading"
    assert api.get_update_version() == "6.0"
    assert api.get_available_version() == "6.1"
    api.app_update("6.1")
    manager.updater.update.assert_called_once_with("6.1")

    dao.get_dt_uploads_raw.return_value = [{"id": 1}]
    dao.get_active_sessions_raw.return_value = [{"id": 2}]
    dao.get_completed_sessions_raw.return_value = [{"id": 3}]
    dao.get_active_direct_downloads.return_value = [{"id": 4}]
    dao.get_completed_direct_downloads.return_value = [{"id": 5}]
    dao.get_direct_downloads_for_monitoring.return_value = [{"id": 6}]
    assert api.get_direct_transfer_items(dao) == [{"id": 1}]
    assert api.get_active_sessions_items(dao) == [{"id": 2}]
    assert api.get_completed_sessions_items(dao) == [{"id": 3}]
    assert api.get_active_direct_downloads_items(dao) == [{"id": 4}]
    assert api.get_completed_direct_downloads_items(dao) == [{"id": 5}]
    assert api.get_direct_downloads_for_monitoring(dao) == [{"id": 6}]
    dao.get_dt_uploads_raw.assert_called_once_with(
        limit=api_module.DT_MONITORING_MAX_ITEMS, chunked=True
    )
    dao.get_completed_sessions_raw.assert_called_once_with(limit=20)
    dao.get_completed_direct_downloads.assert_called_once_with(limit=20)
    dao.get_direct_downloads_for_monitoring.assert_called_once_with(limit=50)

    dao.get_count.side_effect = [2, 3]
    assert api.get_active_sessions_count("engine-1") == 2
    assert api.get_completed_sessions_count("engine-1") == 3
    assert str(TransferStatus.ONGOING.value) in dao.get_count.call_args_list[0].args[0]
    assert str(TransferStatus.DONE.value) in dao.get_count.call_args_list[1].args[0]
    assert api.get_active_sessions_count("missing") == 0
    assert api.get_completed_sessions_count("missing") == 0

    api.cancel_session("engine-1", 42)
    engine.cancel_session.assert_called_once_with(42)
    api.cancel_session("missing", 42)


def test_state_lists_metadata_and_feature_export(api_env):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    state_a, state_b = Mock(name="state_a"), Mock(name="state_b")
    dao = Mock()
    dao.get_unsynchronizeds.return_value = [state_a]
    dao.get_errors.return_value = [state_b]
    engine = SimpleNamespace(
        uid="engine-1",
        dao=dao,
        local=Mock(),
        get_conflicts=Mock(return_value=[state_b]),
    )
    engine.local.abspath.return_value = Path("/sync/document.txt")
    manager.engines = {"engine-1": engine}

    with patch.object(
        api,
        "_export_formatted_state",
        side_effect=lambda uid, state: {
            "uid": uid,
            "state": state,
        },
    ):
        assert api.get_unsynchronizeds("engine-1") == [
            {"uid": "engine-1", "state": state_a}
        ]
        assert api.get_conflicts("engine-1") == [{"uid": "engine-1", "state": state_b}]
        assert api.get_errors("engine-1") == [{"uid": "engine-1", "state": state_b}]
        assert api.get_unsynchronizeds("missing") == []
        assert api.get_conflicts("missing") == []
        assert api.get_errors("missing") == []

    api.show_metadata("engine-1", "folder/document.txt")
    application.hide_systray.assert_called_once_with()
    engine.local.abspath.assert_called_once_with(Path("folder/document.txt"))
    application.show_metadata.assert_called_once_with(Path("/sync/document.txt"))
    api.show_metadata("missing", "ignored")

    features = api.get_features_list()
    synchronization = next(row for row in features if row[1] == "synchronization")
    assert synchronization == [
        "Synchronization",
        "synchronization",
        "FEATURE_SYNCHRONIZATION",
    ]


def test_local_remote_and_window_open_helpers(api_env):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    engine = SimpleNamespace(
        uid="engine-1",
        dao=Mock(),
        local=Mock(),
        open_remote=Mock(),
    )
    engine.local.abspath.return_value = Path("/sync/folder/file.txt")
    manager.engines = {"engine-1": engine}

    api.open_direct_transfer("missing")
    application.show_direct_transfer_window.assert_not_called()
    application.reset_mock()

    api.open_server_folders("engine-1")
    application.hide_systray.assert_called_once_with()
    application.show_server_folders.assert_called_once_with(engine, None, None)
    api.open_server_folders("missing")

    assert api.get_hostname_from_url("https://example.test:8443/path") == "example.test"
    assert api.get_hostname_from_url("not a url") == "not a url"

    api.open_remote_server("engine-1")
    engine.open_remote.assert_called_once_with()
    api.open_remote_server("missing")

    api.open_in_explorer("/tmp/file.txt")
    manager.open_local_file.assert_called_with("/tmp/file.txt", select=True)

    manager.open_local_file.reset_mock()
    api.open_local("", "/standalone/file.txt")
    manager.open_local_file.assert_called_once_with(Path("standalone/file.txt"))
    manager.open_local_file.reset_mock()
    api.open_local("engine-1", "/folder/file.txt")
    engine.local.abspath.assert_called_once_with(Path("folder/file.txt"))
    manager.open_local_file.assert_called_once_with(Path("/sync/folder/file.txt"))
    manager.open_local_file.reset_mock()
    api.open_local("missing", "/ignored.txt")
    manager.open_local_file.assert_not_called()

    api.show_conflicts_resolution("engine-1")
    application.show_conflicts_resolution.assert_called_once_with(engine)
    api.show_conflicts_resolution("missing")


def test_download_location_change_and_direct_download_actions(api_env, tmp_path):
    api, manager = api_env.api, api_env.manager
    configured = tmp_path / "configured"
    configured.mkdir()
    options = SimpleNamespace(download_folder=str(configured), set=Mock())

    with patch.object(api_module, "Options", options), patch.object(
        api_module, "access", return_value=True
    ):
        assert api.get_download_location() == str(configured)

    options.download_folder = str(tmp_path / "missing")
    with patch.object(api_module, "Options", options), patch.object(
        api_module.Path, "home", return_value=tmp_path
    ):
        assert api.get_download_location() == str(tmp_path / "Downloads")

    with patch.object(api, "get_download_location", return_value=str(configured)):
        api.open_download_folder()
    manager.open_local_file.assert_called_with(str(configured))

    class FakeFileDialog:
        class Option:
            ShowDirsOnly = 1
            DontResolveSymlinks = 2

        getExistingDirectory = Mock(return_value=str(tmp_path / "chosen"))

    with patch("nxdrive.drive.qt.imports.QFileDialog", FakeFileDialog), patch.object(
        api_module, "Options", options
    ), patch.object(
        api, "get_download_location", return_value=str(configured)
    ), patch.object(
        api_module, "save_config"
    ) as save_config, patch.object(
        api_module.Translator, "get", return_value="Choose"
    ):
        api.change_download_location()
        options.set.assert_called_once_with(
            "download_folder", str(tmp_path / "chosen"), setter="manual"
        )
        save_config.assert_called_once_with(
            {"download_folder": str(tmp_path / "chosen")}
        )
        api.downloadLocationChanged.emit.assert_called_once_with()

        FakeFileDialog.getExistingDirectory.return_value = ""
        options.set.reset_mock()
        api.downloadLocationChanged.emit.reset_mock()
        api.change_download_location()
        options.set.assert_not_called()
        api.downloadLocationChanged.emit.assert_not_called()

    dao = Mock()
    engine = SimpleNamespace(dao=dao)
    manager.engines = {"engine-1": engine}
    api.pause_direct_download("engine-1", 1)
    api.resume_direct_download("engine-1", 2)
    api.cancel_direct_download("engine-1", 3)
    assert dao.update_direct_download_status.call_args_list == [
        call(1, DirectDownloadStatus.PAUSED),
        call(2, DirectDownloadStatus.IN_PROGRESS),
        call(3, DirectDownloadStatus.CANCELLED),
    ]
    manager.engines = {}
    api.pause_direct_download("missing", 1)
    api.resume_direct_download("missing", 2)
    api.cancel_direct_download("missing", 3)


def test_invalid_credentials_and_basic_state_accessors(api_env):
    api, manager = api_env.api, api_env.manager
    invalid = SimpleNamespace(
        uid="invalid", has_invalid_credentials=Mock(return_value=True)
    )
    valid = SimpleNamespace(
        uid="valid", has_invalid_credentials=Mock(return_value=False)
    )
    manager.engines = {"valid": valid, "invalid": invalid}

    assert api.get_invalid_credentials_engine_uid() == "invalid"
    assert api.has_invalid_credentials("invalid") is True
    assert api.has_invalid_credentials("valid") is False
    assert api.has_invalid_credentials("missing") is False
    manager.engines = {"valid": valid}
    assert api.get_invalid_credentials_engine_uid() == ""

    manager.version = "5.4"
    manager.restart_needed = True
    manager.is_paused = False
    options = SimpleNamespace(
        update_site_url="https://updates.test", deletion_behavior="unsync"
    )
    with patch.object(api_module, "Options", options):
        assert api.get_version() == "5.4"
        assert api.get_update_url() == "https://updates.test"
        assert api.get_deletion_behavior() == "unsync"

    api.set_deletion_behavior("delete")
    manager.set_config.assert_called_once_with("deletion_behavior", "delete")
    assert api.restart_needed() is True
    assert api.is_paused() is False
    api.suspend(True)
    api.suspend(False)
    manager.resume.assert_called_once_with()
    manager.suspend.assert_called_once_with()


def test_web_update_token_dispatch_and_success_variants(api_env):
    api, manager, application = api_env.api, api_env.manager, api_env.application

    api.web_update_token("missing")
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")
    api.setMessage.emit.reset_mock()

    password_engine = SimpleNamespace(
        uid="basic",
        type="basic-engine",
        server_url="https://basic.test",
        remote_user="alice",
        remote=SimpleNamespace(auth=object()),
        _web_authentication=False,
    )
    password_config = server_config(
        key="BASIC",
        browser_startup_page="",
        oauth2_class_path=None,
        supports_browser_token_update=False,
    )
    manager.engines = {"basic": password_engine}
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=password_config
    ):
        api.web_update_token("basic")
    application.show_settings.assert_called_once_with("Accounts")
    api.showReloginPopup.emit.assert_called_once_with("basic", "alice")

    oauth_engine = SimpleNamespace(
        uid="oauth",
        type="oauth-engine",
        server_url="https://oauth.test",
        remote_user="bob",
        remote=SimpleNamespace(auth=object()),
        _web_authentication=True,
    )
    oauth_config = server_config(
        key="OAUTH",
        browser_startup_page="",
        oauth2_class_path="tests.oauth.Handler",
        supports_browser_token_update=False,
    )
    manager.engines = {"oauth": oauth_engine}
    auth = Mock()
    auth.connect_url.return_value = "https://idp.test/authorize"
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=oauth_config
    ), patch.object(
        api_module, "get_auth", return_value=auth
    ) as get_auth, patch.object(
        api, "_save_pending_auth_callback_params"
    ) as save:
        api.web_update_token("oauth")
    manager.get_server_login_type.assert_not_called()
    get_auth.assert_called_once_with(
        "https://oauth.test",
        {},
        dao=manager.dao,
        device_id=manager.device_id,
        server_type="OAUTH",
    )
    callback = {"engine": "oauth", "server_url": "https://oauth.test"}
    save.assert_called_once_with(callback)
    application.open_authentication_dialog.assert_called_with(
        "https://idp.test/authorize", callback
    )

    normal_engine = SimpleNamespace(
        uid="normal",
        type="normal-engine",
        server_url="https://nuxeo.test",
        remote_user="carol",
        remote=SimpleNamespace(auth=object()),
        _web_authentication=False,
    )
    normal_config = server_config(key="NXDRIVE")
    manager.engines = {"normal": normal_engine}
    manager.get_server_login_type.reset_mock()
    manager.get_server_login_type.return_value = Login.OLD
    with patch.object(api_module.st, "get_by_engine_type", return_value=normal_config):
        api.web_update_token("normal")
    manager.updater.force_downgrade.assert_called_once_with()

    manager.updater.force_downgrade.reset_mock()
    manager.get_server_login_type.return_value = Login.NEW
    auth.connect_url.return_value = "https://login.test/token"
    frozen_options = SimpleNamespace(is_frozen=True)
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=normal_config
    ), patch.object(
        api_module, "get_auth", return_value=auth
    ) as get_auth, patch.object(
        api_module, "Options", frozen_options
    ), patch.object(
        api, "_save_pending_auth_callback_params"
    ):
        api.web_update_token("normal")
    get_auth.assert_called_once_with(
        "https://nuxeo.test",
        "",
        dao=manager.dao,
        device_id=manager.device_id,
        server_type="NXDRIVE",
    )
    assert application.open_authentication_dialog.call_args.args[0] == (
        "https://login.test/token&updateToken=True"
    )

    class OAuthMarker:
        pass

    normal_engine.remote.auth = OAuthMarker()
    unfrozen_options = SimpleNamespace(is_frozen=False)
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=normal_config
    ), patch.object(api_module, "OAuthenticationBase", OAuthMarker), patch.object(
        api_module, "get_auth", return_value=auth
    ) as get_auth, patch.object(
        api_module, "Options", unfrozen_options
    ), patch.object(
        api, "_save_pending_auth_callback_params"
    ):
        api.web_update_token("normal")
    assert get_auth.call_args.args[1] == {}


def test_web_update_token_reports_unexpected_setup_failure(api_env):
    api, manager = api_env.api, api_env.manager
    engine = SimpleNamespace(
        uid="engine-1",
        type="test-engine",
        server_url="https://server.test",
        remote_user="user",
        remote=SimpleNamespace(auth=object()),
        _web_authentication=False,
    )
    manager.engines = {"engine-1": engine}
    manager.get_server_login_type.return_value = Login.NEW
    config = server_config()
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=config
    ), patch.object(
        api_module, "get_auth", side_effect=RuntimeError("cannot create auth")
    ):
        api.web_update_token("engine-1")
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (MissingClientSSLCertificate("missing"), "MISSING_CLIENT_SSL"),
        (EncryptedSSLCertificateKey("encrypted"), "ENCRYPTED_CLIENT_SSL_KEY"),
    ],
)
def test_ssl_probe_maps_client_certificate_errors(api_env, exception, expected):
    api = api_env.api
    with patch.object(api_module, "test_url", side_effect=exception) as test_url:
        assert api._get_ssl_error_for_server("https://server.test", "login") == expected
    test_url.assert_called_once_with(
        "https://server.test", proxy=api_env.manager.proxy, login_page="login"
    )


def test_ssl_probe_acceptance_persists_and_retries(api_env):
    api, application = api_env.api, api_env.application
    options = SimpleNamespace(ssl_no_verify=False, ca_bundle="/tmp/ca.pem")
    with patch.object(api_module, "Options", options), patch.object(
        api_module, "test_url", side_effect=[InvalidSSLCertificate("bad"), ""]
    ) as test_url, patch.object(api_module, "save_config") as save_config:
        application.accept_unofficial_ssl_cert.return_value = True
        assert api._get_ssl_error_for_server("https://server.test/path", "signin") == ""
    assert test_url.call_count == 2
    application.accept_unofficial_ssl_cert.assert_called_once_with("server.test")
    assert options.ssl_no_verify is True
    save_config.assert_called_once_with(
        {"ssl_no_verify": True, "ca_bundle": "/tmp/ca.pem"}
    )

    application.accept_unofficial_ssl_cert.reset_mock()
    application.accept_unofficial_ssl_cert.return_value = False
    with patch.object(api_module, "Options", options), patch.object(
        api_module, "test_url", side_effect=InvalidSSLCertificate("bad")
    ):
        assert api._get_ssl_error_for_server("server.test") == "CONNECTION_ERROR"
    application.accept_unofficial_ssl_cert.assert_called_once_with("server.test")

    options.ssl_no_verify = False
    with patch.object(api_module, "Options", options), patch.object(
        api_module, "test_url", side_effect=[InvalidSSLCertificate("bad"), ""]
    ), patch.object(api_module, "save_config") as save_config:
        application.accept_unofficial_ssl_cert.return_value = True
        assert api._get_ssl_error("https://server.test") == ""
    save_config.assert_called_once_with(
        {"ssl_no_verify": True, "ca_bundle": "/tmp/ca.pem"}
    )


def test_ssl_probe_success_uses_only_requested_arguments(api_env):
    api = api_env.api
    with patch.object(api_module, "test_url", return_value="") as test_url:
        assert api._get_ssl_error_for_server("https://server.test") == ""
        assert api._get_ssl_error_for_server("https://server.test", "login") == ""
    assert test_url.call_args_list == [
        call("https://server.test", proxy=api_env.manager.proxy),
        call(
            "https://server.test",
            proxy=api_env.manager.proxy,
            login_page="login",
        ),
    ]


def test_default_folders_and_server_url(api_env):
    api = api_env.api
    config = server_config(local_folder_name="Brand Drive")
    options = SimpleNamespace(server_type="TEST")
    expected_folder = str(Path("/brand"))
    with patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get", return_value=config
    ), patch.object(
        api_module, "get_default_local_folder", return_value=Path("/brand")
    ) as default:
        assert api.default_local_folder() == expected_folder
        assert api.default_server_local_folder() == expected_folder
        assert api.default_local_folder_for_server("TEST") == expected_folder
    default.assert_has_calls(
        [call("Brand Drive"), call("Brand Drive"), call("Brand Drive")]
    )

    with patch.object(api_module, "getenv", return_value="https://env.test"):
        assert api.default_server_url_value() == "https://env.test"

    config.test_server_url_getter = Mock(return_value="https://registry.test")
    with patch.object(api_module, "getenv", return_value=""), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(api_module.st, "get", return_value=config):
        assert api.default_server_url_value() == "https://registry.test"
    config.test_server_url_getter.assert_called_once_with()

    config.test_server_url_getter = None
    with patch.object(api_module, "getenv", return_value=""), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(api_module.st, "get", return_value=config):
        assert api.default_server_url_value() == ""


def test_disk_space_calculation_and_formatting(api_env):
    api, manager = api_env.api, api_env.manager
    dao = Mock()
    dao.get_global_size.return_value = 20
    engine = SimpleNamespace(dao=dao)
    manager.engines = {"engine-1": engine}

    with patch.object(api_module, "disk_space", return_value=(80, 20)), patch.object(
        api,
        "_balance_percents",
        return_value={
            "free": 20.0,
            "used_without_sync": 60.0,
            "synced": 20.0,
        },
    ) as balance:
        assert api.get_disk_space_info_to_width("engine-1", "/sync", 100) == [
            20.0,
            60.0,
            20.0,
        ]
    balance.assert_called_once_with(
        {"free": 20.0, "used_without_sync": 60.0, "synced": 20.0}
    )
    assert api.get_disk_space_info_to_width("missing", "/sync", 100) == []

    for values in (
        {"a": 0.0, "b": 5.0, "c": 95.0},
        {"a": 0.0, "b": 12.0, "c": 88.0},
        {"a": 0.0, "b": 30.0, "c": 70.0},
        {"a": 20.0, "b": 30.0, "c": 50.0},
    ):
        balanced = api._balance_percents(values)
        assert sum(balanced.values()) == pytest.approx(sum(values.values()))
        assert min(balanced.values()) >= 10

    with patch.object(api_module, "disk_space", return_value=(80, 20)), patch.object(
        api_module, "sizeof_fmt", side_effect=lambda value, suffix: f"{value}-{suffix}"
    ), patch.object(api_module.Translator, "get", return_value="B"):
        assert api.get_drive_disk_space("engine-1") == "20-B"
        assert api.get_drive_disk_space("missing") == ""
        assert api.get_free_disk_space("/sync") == "20-B"
        assert api.get_used_space_without_synced("engine-1", "/sync") == "60-B"
        assert api.get_used_space_without_synced("missing", "/sync") == ""


def test_bind_server_core_builds_binder_and_dispatches_engine_type(api_env, tmp_path):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    engine = SimpleNamespace(uid="engine-1")
    manager.bind_engine.return_value = engine
    binder = SimpleNamespace(url="https://server.test/root#brand", username="alice")
    config = server_config(engine_type="brand-engine")

    with patch.object(
        api_module, "Binder", return_value=binder
    ) as binder_factory, patch.object(
        api, "_resolve_server_config", return_value=config
    ), patch.object(
        api_module.Feature, "synchronization", True
    ), patch.object(
        api, "filters_dialog"
    ) as filters:
        api._bind_server(
            tmp_path / "sync",
            "https://server.test/root?ignored=1#brand",
            "alice",
            "secret",
            "",
            token={"access_token": "token"},
            check_fs=False,
        )
    binder_factory.assert_called_once_with(
        username="alice",
        password="secret",
        token={"access_token": "token"},
        no_check=False,
        no_fscheck=True,
        url="https://server.test/root#brand",
    )
    manager.bind_engine.assert_called_once_with(
        "brand-engine", tmp_path / "sync", None, binder, starts=False
    )
    assert application.close_settings_too is True
    filters.assert_called_once_with("engine-1")
    api.setMessage.emit.assert_called_once_with("CONNECTION_SUCCESS", "success")

    manager.bind_engine.reset_mock()
    api.setMessage.emit.reset_mock()
    with patch.object(api_module, "Binder", return_value=binder), patch.object(
        api, "_resolve_server_config", return_value=config
    ), patch.object(api_module.Feature, "synchronization", False), patch.object(
        api, "filters_dialog"
    ) as filters:
        api._bind_server(
            tmp_path / "sync",
            "https://server.test/root",
            "alice",
            "secret",
            "Named account",
        )
    manager.bind_engine.assert_called_once_with(
        "brand-engine", tmp_path / "sync", "Named account", binder, starts=True
    )
    filters.assert_not_called()


def test_bind_server_engine_type_error_and_utility_dispatch(api_env, tmp_path):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    with patch.object(
        api, "_bind_server", side_effect=EngineTypeMissing()
    ), patch.object(api_module, "normalized_path", return_value=tmp_path), patch.object(
        api_module.Translator, "get", side_effect=lambda key, **kwargs: key
    ):
        api.bind_server(str(tmp_path), "https://server.test", "alice")
    api.setMessage.emit.assert_called_once_with("CONNECTION_ERROR", "error")
    application._show_window.assert_called_once_with(application.settings_window)

    api.setMessage.emit.reset_mock()
    manager.unbind_engine.reset_mock()
    api.unbind_server("engine-1", True)
    manager.unbind_engine.assert_called_once_with("engine-1", purge=True)

    engine = SimpleNamespace(uid="engine-1")
    manager.engines = {"engine-1": engine}
    api.filters_dialog("engine-1")
    application.show_filters.assert_called_once_with(engine)
    api.filters_dialog("missing")


def test_bind_server_retries_after_confirming_existing_root(api_env, tmp_path):
    api, application = api_env.api, api_env.application
    conflict = RootAlreadyBindWithDifferentAccount("other-user", "https://other.test")
    proceed, cancel = object(), object()
    question = Mock()
    question.addButton.side_effect = [proceed, cancel]
    question.clickedButton.return_value = proceed
    application.question.return_value = question

    with patch.object(
        api, "_bind_server", side_effect=[conflict, None]
    ) as bind, patch.object(
        api_module, "normalized_path", return_value=tmp_path
    ), patch.object(
        api_module.Translator, "get", side_effect=lambda key, **kwargs: key
    ):
        api.bind_server(
            str(tmp_path),
            "https://server.test",
            "alice",
            password="secret",
            name="Account",
            token="token",
        )

    assert bind.call_args_list == [
        call(
            tmp_path,
            "https://server.test",
            "alice",
            "secret",
            "Account",
            token="token",
            check_fs=True,
        ),
        call(
            tmp_path,
            "https://server.test",
            "alice",
            "secret",
            "Account",
            token="token",
            check_fs=False,
        ),
    ]
    question.exec.assert_called_once_with()


def test_password_relogin_and_oauth_password_dispatch(api_env):
    api, manager = api_env.api, api_env.manager
    password_handler = Mock()
    oauth_handler = Mock()
    config = server_config(
        password_auth_handler=password_handler,
        oauth2_password_auth_handler=oauth_handler,
    )
    with patch.object(api, "_resolve_server_config", return_value=config):
        api.password_auth("/sync", "https://server.test", "alice", "secret")
        api.oauth2_password_auth("/sync", "https://server.test", "alice", "secret")
    password_handler.assert_called_once_with(
        api, "/sync", "https://server.test", "alice", "secret"
    )
    oauth_handler.assert_called_once_with(
        api, "/sync", "https://server.test", "alice", "secret"
    )

    config.password_auth_handler = None
    config.oauth2_password_auth_handler = None
    with patch.object(api, "_resolve_server_config", return_value=config), patch.object(
        api, "bind_server"
    ) as bind:
        api.password_auth("/sync", "https://server.test", "alice", "secret")
        api.oauth2_password_auth("/sync", "https://server.test", "alice", "secret")
    bind.assert_called_once_with(
        "/sync", "https://server.test", "alice", password="secret"
    )
    api.setMessage.emit.assert_called_with("CONNECTION_REFUSED", "error")

    api.setMessage.emit.reset_mock()
    api.relogin("missing", "secret")
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")

    engine = SimpleNamespace(type="test-engine")
    manager.engines = {"engine-1": engine}
    browser_config = server_config(supports_browser_token_update=True)
    with patch.object(api_module.st, "get_by_engine_type", return_value=browser_config):
        api.relogin("engine-1", "secret")
    assert api.setMessage.emit.call_count == 2

    api.setMessage.emit.reset_mock()
    no_handler_config = server_config(
        supports_browser_token_update=False, relogin_handler=None
    )
    with patch.object(
        api_module.st, "get_by_engine_type", return_value=no_handler_config
    ):
        api.relogin("engine-1", "secret")
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")

    handler = Mock()
    handler_config = server_config(
        supports_browser_token_update=False, relogin_handler=handler
    )
    api.setMessage.emit.reset_mock()
    with patch.object(api_module.st, "get_by_engine_type", return_value=handler_config):
        api.relogin("engine-1", "secret")
    handler.assert_called_once_with(engine, "secret")
    api.setMessage.emit.assert_not_called()

    handler.side_effect = RuntimeError("rejected")
    with patch.object(api_module.st, "get_by_engine_type", return_value=handler_config):
        api.relogin("engine-1", "wrong")
    api.setMessage.emit.assert_called_once_with("AUTH_EXPIRED", "error")


def test_web_authentication_server_specific_ssl_and_legacy_paths(api_env):
    api, manager = api_env.api, api_env.manager
    manager.check_local_folder_available.return_value = True
    config = server_config(
        key="BRAND",
        engine_type="brand-engine",
        ssl_login_page="/brand-login",
        supports_browser_token_update=True,
    )
    auth = Mock()
    auth.connect_url.return_value = "https://identity.test/authorize"
    manager.get_server_login_type.return_value = Login.OLD
    options = SimpleNamespace(is_frozen=False)

    with patch.object(api, "_resolve_server_config", return_value=config), patch.object(
        api, "_get_ssl_error_for_server", return_value=""
    ) as ssl_probe, patch.object(api_module, "Options", options), patch.object(
        api_module.st, "get_default_key", return_value="NXDRIVE"
    ), patch.object(
        api_module.st, "get_by_engine_type", return_value=config
    ), patch.object(
        api_module, "get_auth", return_value=auth
    ) as get_auth, patch.object(
        api, "_save_pending_auth_callback_params"
    ) as save:
        api.web_authentication("https://server.test", "/sync", True)
    ssl_probe.assert_called_once_with("https://server.test", "/brand-login")
    get_auth.assert_called_once_with(
        "https://server.test",
        "",
        dao=manager.dao,
        device_id=manager.device_id,
        server_type="BRAND",
    )
    callback = {
        "local_folder": "/sync",
        "server_url": "https://server.test",
        "engine_type": "brand-engine",
    }
    save.assert_called_once_with(callback)
    api.openAuthenticationDialog.emit.assert_called_once_with(
        "https://identity.test/authorize", callback
    )

    manager.updater.force_downgrade.reset_mock()
    api.openAuthenticationDialog.emit.reset_mock()
    options.is_frozen = True
    with patch.object(api, "_resolve_server_config", return_value=config), patch.object(
        api, "_get_ssl_error_for_server", return_value=""
    ), patch.object(api_module, "Options", options):
        api.web_authentication("https://server.test", "/sync", True)
    manager.updater.force_downgrade.assert_called_once_with()
    api.openAuthenticationDialog.emit.assert_not_called()

    api.setMessage.emit.reset_mock()
    with patch.object(api, "_resolve_server_config", return_value=config), patch.object(
        api, "_get_ssl_error_for_server", return_value="CERTIFICATE_ERROR"
    ):
        api.web_authentication("https://server.test", "/sync", False)
    api.setMessage.emit.assert_called_once_with("CERTIFICATE_ERROR", "error")


def test_server_ui_and_remote_metadata_capability(api_env):
    api, manager = api_env.api, api_env.manager
    engine = SimpleNamespace(type="test-engine", set_ui=Mock())
    manager.engines = {"engine-1": engine}

    assert api.set_server_ui("engine-1", "compact") is True
    engine.set_ui.assert_called_once_with("compact")
    assert api.set_server_ui("missing", "compact") is False
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")

    with patch.object(
        api_module.st,
        "get_by_engine_type",
        return_value=server_config(supports_browser_token_update=True),
    ):
        assert api.can_open_remote_metadata("engine-1") is True
    with patch.object(
        api_module.st,
        "get_by_engine_type",
        return_value=server_config(supports_browser_token_update=False),
    ):
        assert api.can_open_remote_metadata("engine-1") is False
    assert api.can_open_remote_metadata("missing") is False


def _set_oauth_config(manager):
    values = {
        "tmp_oauth2_url": "https://server.test",
        "tmp_oauth2_code_verifier": "verifier",
        "tmp_oauth2_state": "expected-state",
    }
    manager.get_config.side_effect = values.get


def test_continue_oauth2_flow_missing_handler_and_generic_failure_cleanup(api_env):
    api, manager = api_env.api, api_env.manager
    config = server_config(key="TEST", oauth2_class_path="missing.Handler")
    options = SimpleNamespace(oauth2_openid_configuration_url="")
    _set_oauth_config(manager)

    with patch.object(api_module, "Options", options), patch.object(
        api, "_resolve_server_config", return_value=config
    ), patch.object(api_module._st, "load_class", return_value=None):
        api.continue_oauth2_flow({"state": "expected-state", "code": "code"})
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")
    assert manager.dao.delete_config.call_args_list == [
        call("tmp_oauth2_url"),
        call("tmp_oauth2_code_verifier"),
        call("tmp_oauth2_state"),
    ]

    api.setMessage.emit.reset_mock()
    manager.dao.delete_config.reset_mock()
    _set_oauth_config(manager)
    oauth_class = Mock(side_effect=RuntimeError("broken constructor"))
    with patch.object(api_module, "Options", options), patch.object(
        api, "_resolve_server_config", return_value=config
    ), patch.object(api_module._st, "load_class", return_value=oauth_class):
        api.continue_oauth2_flow({"state": "expected-state", "code": "code"})
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")
    assert manager.dao.delete_config.call_count == 3


def test_continue_oauth2_flow_remote_error_and_precheck_state(api_env):
    api, manager = api_env.api, api_env.manager
    config = server_config()
    options = SimpleNamespace(oauth2_openid_configuration_url="")
    _set_oauth_config(manager)
    auth = Mock()
    auth.get_token.side_effect = RemoteOAuth2Error("token rejected")
    oauth_class = Mock(return_value=auth)
    with patch.object(api_module, "Options", options), patch.object(
        api, "_resolve_server_config", return_value=config
    ), patch.object(api_module._st, "load_class", return_value=oauth_class):
        api.continue_oauth2_flow({"state": "expected-state", "code": "code"})
    api.setMessage.emit.assert_called_once_with("CONNECTION_UNKNOWN", "error")
    assert manager.dao.delete_config.call_count == 3

    api.setMessage.emit.reset_mock()
    manager.dao.delete_config.reset_mock()
    manager.get_config.side_effect = lambda key: None
    api.continue_oauth2_flow({"state": "state", "code": "code"})
    api.setMessage.emit.assert_called_once_with("OAUTH2_MISSING_URL", "error")
    manager.dao.delete_config.assert_not_called()


def test_handle_token_routes_persisted_callbacks_and_always_clears(api_env):
    api = api_env.api
    with patch.object(
        api, "_load_pending_auth_callback_params", return_value={"engine": "engine-1"}
    ) as load, patch.object(
        api, "update_token", return_value="TOKEN_ERROR"
    ) as update, patch.object(
        api, "_clear_pending_auth_callback_params"
    ) as clear:
        api.handle_token("token", "alice")
    load.assert_called_once_with()
    update.assert_called_once_with("token", "alice")
    clear.assert_called_once_with()
    api.setMessage.emit.assert_called_once_with("TOKEN_ERROR", "error")

    api.callback_params = {"local_folder": "/sync"}
    api.setMessage.emit.reset_mock()
    with patch.object(api, "create_account", return_value="") as create, patch.object(
        api, "_clear_pending_auth_callback_params"
    ) as clear:
        api.handle_token({"access_token": "token"}, "bob")
    create.assert_called_once_with({"access_token": "token"}, "bob")
    clear.assert_called_once_with()
    api.setMessage.emit.assert_not_called()

    api.callback_params = {"unexpected": "value"}
    with patch.object(api, "_clear_pending_auth_callback_params") as clear:
        api.handle_token("token", "carol")
    clear.assert_called_once_with()

    api.callback_params = {}
    api.setMessage.emit.reset_mock()
    with patch.object(
        api, "_load_pending_auth_callback_params", return_value={}
    ), patch.object(api, "_clear_pending_auth_callback_params") as clear:
        api.handle_token("", "nobody")
    clear.assert_called_once_with()
    api.setMessage.emit.assert_called_once_with("CONNECTION_REFUSED", "error")


def test_update_token_success_and_error_mapping(api_env):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    engine = SimpleNamespace(
        local_folder=Path("/sync"),
        server_url="https://server.test",
        remote_user="old-user",
        update_token=Mock(),
    )
    manager.engines = {"engine-1": engine}
    api.callback_params = {"engine": "engine-1"}

    assert api.update_token("token", "new-user") == ""
    engine.update_token.assert_called_once_with("token", "new-user")
    application.set_icon_state.assert_called_once_with("idle")
    application.show_settings.assert_called_once_with("Accounts")
    api.setMessage.emit.assert_called_once_with("CONNECTION_SUCCESS", "success")

    manager.engines = {}
    assert api.update_token("ignored", "user") == ""

    manager.engines = {"engine-1": engine}
    refused = requests.ConnectionError("refused")
    refused.errno = 61
    engine.update_token.side_effect = refused
    assert api.update_token("token", "new-user") == "CONNECTION_REFUSED"

    connection_error = requests.ConnectionError("network")
    connection_error.errno = 5
    engine.update_token.side_effect = connection_error
    assert api.update_token("token", "new-user") == "CONNECTION_ERROR"

    engine.update_token.side_effect = RuntimeError("unexpected")
    assert api.update_token("token", "new-user") == "CONNECTION_UNKNOWN"


def test_sync_conflict_and_remote_open_helpers(api_env):
    api, manager = api_env.api, api_env.manager
    engine = SimpleNamespace(
        type="test-engine",
        dao=Mock(),
        resolve_with_local=Mock(),
        resolve_with_remote=Mock(),
        retry_pair=Mock(),
        ignore_pair=Mock(),
        open_edit=Mock(),
        get_metadata_url=Mock(return_value="https://server.test/doc/1"),
        open_remote=Mock(),
    )
    engine.dao.get_syncing_count.return_value = 4
    manager.engines = {"engine-1": engine}

    assert api.get_syncing_count("engine-1") == 4
    assert api.get_syncing_count("missing") == 0
    api.resolve_with_local("engine-1", 1)
    api.resolve_with_remote("engine-1", 2)
    api.retry_pair("engine-1", 3)
    api.ignore_pair("engine-1", 4, "ignored")
    engine.resolve_with_local.assert_called_once_with(1)
    engine.resolve_with_remote.assert_called_once_with(2)
    engine.retry_pair.assert_called_once_with(3)
    engine.ignore_pair.assert_called_once_with(4, "ignored")
    api.resolve_with_local("missing", 1)
    api.resolve_with_remote("missing", 2)
    api.retry_pair("missing", 3)
    api.ignore_pair("missing", 4, "ignored")

    api.open_remote("engine-1", "ref", "name.txt")
    engine.open_edit.assert_called_once_with("ref", "name.txt")
    api.open_remote("missing", "ref", "name.txt")

    api.open_remote_document("engine-1", "ref", "/path/name.txt")
    engine.get_metadata_url.assert_called_with("ref")
    engine.open_remote.assert_called_once_with(url="https://server.test/doc/1")
    assert api.get_remote_document_url("engine-1", "ref") == (
        "https://server.test/doc/1"
    )
    assert api.get_remote_document_url("missing", "ref") == ""

    engine.open_edit.side_effect = OSError("cannot open")
    api.open_remote("engine-1", "ref", "name.txt")
    engine.open_edit.side_effect = None
    engine.get_metadata_url.side_effect = OSError("cannot build URL")
    api.open_remote_document("engine-1", "ref", "/path/name.txt")


def test_text_task_and_pending_task_helpers(api_env):
    api, manager, application = api_env.api, api_env.manager, api_env.application
    assert api.get_text("{'name': 'Drive'}", "name") == "Drive"
    assert api.get_text("not-json", "name") == ""
    with patch.object(api_module.Translator, "get", return_value="ago"):
        assert api.text_red("2 minutes ago") is True
        assert api.text_red("today") is False

    api.open_tasks_window("engine-1")
    api.close_tasks_window()
    application.hide_systray.assert_called_once_with()
    application.show_tasks_window.assert_called_once_with("engine-1")
    application.close_tasks_window.assert_called_once_with()

    engine = SimpleNamespace(
        uid="engine-1",
        remote_user="alice",
        remote=Mock(),
        fetch_pending_task_list=Mock(),
    )
    manager.engines = {"engine-1": engine}
    task = SimpleNamespace(
        id="task-1",
        targetDocumentIds=[{"id": "doc-1"}],
        directive="approve",
        workflowModelName="SerialDocumentReview",
    )
    with patch.object(api, "_fetch_tasks", return_value=[task]) as fetch, patch.object(
        api, "get_document_details", return_value=SimpleNamespace(name="Contract")
    ), patch.object(api_module, "get_task_type", return_value="Approve"):
        assert api.tasks_remaining("engine-1") == 1
        tasks = api.get_Tasks_list("engine-1", True, True)
    assert tasks == [task]
    assert task.name == "Contract"
    assert task.directive == "Approve"
    assert task.workflowModelName == "Serial Document Review"
    assert api.engine_changed is True
    assert api.hide_refresh_button is True
    assert api.last_task_list
    application.show_hide_refresh_button.assert_called_once_with(0)
    assert fetch.call_count == 2
    assert api.tasks_remaining("missing") == 0

    broken = SimpleNamespace(
        id="task-2",
        targetDocumentIds=[],
        directive="review",
        workflowModelName="Review",
    )
    with patch.object(api, "_fetch_tasks", return_value=[broken]), patch.object(
        api_module, "get_task_type", return_value="Review"
    ):
        api.get_Tasks_list("engine-1", False, False)
    assert broken.name == "Unknown Document"
    assert api.hide_refresh_button is False

    assert api.get_username("engine-1") == "alice"
    engine.remote.get_info.return_value = {"name": "Document"}
    assert api.get_document_details("engine-1", "doc-1") == {"name": "Document"}
    engine.remote.get_info.assert_called_once_with("doc-1", fetch_parent_uid=False)
    assert api.get_document_details("missing", "doc-1") == []

    application.fetch_pending_tasks.return_value = [task]
    assert api._fetch_tasks(engine) == [task]
    with patch.object(api, "_fetch_tasks", return_value=[task]):
        api.fetch_pending_tasks(engine)
    engine.fetch_pending_task_list.assert_called_once_with("task-1")
    engine.fetch_pending_task_list.reset_mock()
    with patch.object(api, "_fetch_tasks", return_value=[]):
        api.fetch_pending_tasks(engine)
    engine.fetch_pending_task_list.assert_not_called()

    api.on_clicked_open_task("engine-1", "task-1")
    application.open_task.assert_called_once_with(engine, "task-1")
    api.on_clicked_open_task("missing", "task-1")

    engine.get_task_url = Mock(return_value="https://server.test/task/1")
    engine.open_remote = Mock()
    api.display_pending_task("engine-1", "task-1", "/document")
    engine.get_task_url.assert_called_once_with("task-1")
    engine.open_remote.assert_called_once_with(url="https://server.test/task/1")
    api.display_pending_task("missing", "task-1", "/document")
    engine.get_task_url.side_effect = RuntimeError("cannot build task URL")
    api.display_pending_task("engine-1", "task-1", "/document")

    with patch.object(api_module, "log") as logger:
        api.log_qml("QML message")
    logger.debug.assert_called_once_with("[QML] QML message")
