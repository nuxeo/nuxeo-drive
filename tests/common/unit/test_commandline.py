from pathlib import Path
from unittest.mock import patch

import pytest

from nxdrive.drive.commandline import DEFAULTSECT, CliHandler
from nxdrive.drive.options import Options
from nxdrive.drive.utils import normalized_path

from ...markers import mac_only, windows_only


def create_ini(
    default_section: str = DEFAULTSECT, env: str = "PROD", encoding: str = "utf-8"
) -> Path:
    path = Options.nxdrive_home / "config.ini"
    with open(path, "w", encoding=encoding) as f:
        f.writelines(
            f"""
[{default_section}]
env = {env}

[PROD]
log-level_console = DEBUG
debug = False
empty-value=

[Inception]
nxdrive_home = {str(Options.nxdrive_home / "drive_home")}
force-locale = en

[DEV]
log_level-console = ERROR
debug = True
delay = 3
tmp-file-limit = 0.0105

[BAD]
log-level-console = DEBUG
 debug = False
delay = 3
"""
        )

    if env != "Inception":
        return path

    # Also add a config file in the new nxdrive_home to ensure it will be parsed as expected
    path = Options.nxdrive_home / "drive_home" / "config.ini"
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding=encoding) as f:
        f.writelines(
            """
[DEFAULT]
env = français

[français]
force-locale = fr
"""
        )

    return path


@pytest.fixture
def cmd(tmp):
    path = tmp() / "config"
    path.mkdir(parents=True, exist_ok=True)
    Options.set("nxdrive_home", normalized_path(path), setter="local")
    Options.server_type = "NUXEO"

    yield CliHandler()


@pytest.fixture
def config():
    path_list = []

    def _config(**kwargs):
        path_list.append(create_ini(**kwargs))

    yield _config

    for path in path_list:
        path.unlink(missing_ok=True)


def test_redact_payload(cmd):
    payload = b"nxdrive://token/12345678-acbd-1234-cdef-1234567890ab/user/Administrator@127.0.0.1"
    assert cmd.redact_payload(payload) == b"<REDACTED>"
    assert cmd.redact_payload(b"payload") == b"payload"


@Options.mock()
def test_update_site_url(cmd):
    argv = ["console", "--update-site-url", "DEBUG_TEST"]
    options = cmd.parse_cli([])
    assert options.update_site_url == Options.update_site_url

    # Normal arg
    options = cmd.parse_cli(argv)
    assert options.update_site_url == "DEBUG_TEST"


@Options.mock()
@pytest.mark.parametrize("encoding", ["utf-16", "utf-8-sig"])
def test_bad_encoding_utf_16(encoding, cmd, config):
    config(encoding=encoding)
    cmd.parse_cli([])


@Options.mock()
def test_defaults(cmd):
    argv = ["console", "--log-level-console", "WARNING"]

    # Default value
    options = cmd.parse_cli([])
    assert options.log_level_console == "WARNING"

    # Normal arg
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "WARNING"


def get_conf(_):
    return {"log_level_console": "DEBUG"}


@Options.mock()
@windows_only
def test_system_default_windows(cmd):
    from nxdrive.drive.osi.windows.windows import WindowsIntegration

    with patch.object(WindowsIntegration, "get_system_configuration", new=get_conf):
        options = cmd.parse_cli([])
        assert options.log_level_console == "DEBUG"


@Options.mock()
@mac_only
def test_system_default_mac(cmd):
    from nxdrive.drive.osi.darwin.darwin import DarwinIntegration

    with patch.object(DarwinIntegration, "get_system_configuration", new=get_conf):
        options = cmd.parse_cli([])
        assert options.log_level_console == "DEBUG"


@Options.mock()
def test_default_override(cmd, config):
    argv = ["console", "--log-level-console=INFO"]

    # Default value
    options = cmd.parse_cli([])
    assert options.log_level_console == "WARNING"
    assert not options.debug

    # Normal arg
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "INFO"
    assert not options.debug

    # config.ini override
    config()
    options = cmd.parse_cli([])
    assert options.log_level_console == "DEBUG"
    assert not options.debug

    # config.ini override, but arg specified
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "INFO"
    assert not options.debug

    # other usage section
    config(env="DEV")
    options = cmd.parse_cli([])
    assert options.log_level_console == "ERROR"
    assert options.debug
    assert options.delay == 3
    assert options.tmp_file_limit == 0.0105


@Options.mock()
def test_default_override_from_alternate_nxdrive_home(cmd, config):
    expected_nxdrive_home = str(Options.nxdrive_home / "drive_home")
    config(env="Inception")
    args = cmd.load_config()
    assert args["nxdrive_home"] == expected_nxdrive_home
    assert args["force_locale"] == "fr"


def test_confg_file_no_default_section(cmd, config):
    config(default_section="default")
    args = cmd.load_config()
    assert not args


@Options.mock()
def test_malformatted_line(cmd, config):
    config(env="BAD")
    cmd.parse_cli([])
    # The malformed line will display a warning:
    # Unknown logging level ('=', 'DEBUG', 'False', 'debug'), need to be one of ...
    # Callback check for 'log_level_console' denied modification. Value is still 'WARNING'.
    assert Options.log_level_console == "WARNING"


def test_launch(cmd):
    obj_cli = cmd
    obj_cli.manager = obj_cli.get_manager()
    with patch("nxdrive.drive.utils.PidLockFile.lock") as mock_lock:
        Options.protocol_url = "dummy_url"
        mock_lock.return_value = 100
        assert obj_cli.launch(None, console=False) == 0
        Options.protocol_url = ""
        assert obj_cli.launch(None, console=False) == 0

    with patch("nxdrive.drive.utils.PidLockFile.lock") as mock_lock:
        mock_lock.return_value = ""
        with patch("nxdrive.drive.utils.PidLockFile.unlock") as mock_unlock:
            mock_unlock.return_value = ""
            with patch("nxdrive.drive.commandline.CliHandler._get_application"):
                assert obj_cli.launch(None, console=False)


@windows_only
def test_clipboard_signal_block(cmd):
    from nxdrive.drive.gui.application import Application

    obj_cli = cmd
    obj_cli.manager = obj_cli.get_manager()
    # Test Windows clipboard blocking signals
    with patch("nxdrive.drive.utils.PidLockFile.lock") as mock_lock, patch(
        "nxdrive.drive.commandline.CliHandler._get_application"
    ) as mock_application, patch(
        "nxdrive.drive.gui.application.Application.exec"
    ) as mock_exec, patch(
        "nxdrive.drive.gui.application.Application.show_metrics_acceptance"
    ) as mock_show_metrics:
        mock_lock.return_value = ""
        mock_application.return_value = Application(obj_cli.manager)
        mock_show_metrics.return_value = None
        mock_exec.return_value = 0

        assert obj_cli.launch(None, console=False) == 0


def test_send_to_running_instance(cmd):
    obj_cli = cmd
    obj_cli.manager = obj_cli.get_manager()
    mock_payload = bytes()
    with patch(
        "PySide6.QtNetwork.QLocalSocket.waitForConnected"
    ) as mock_wait_connected:
        mock_wait_connected.return_value = True
        assert obj_cli._send_to_running_instance(mock_payload, 100) is True


# ─── Additional Commandline Tests ────────────────────────────────────────────


def test_load_supported_server_keys(cmd):
    """Test _load_supported_server_keys returns a list of keys."""
    keys = cmd._load_supported_server_keys()
    assert isinstance(keys, list)
    assert len(keys) > 0
    # Keys should be uppercase
    for key in keys:
        assert key == key.upper()


def test_get_version(cmd):
    """Test get_version returns a version string."""
    version = cmd.get_version()
    assert version
    # Should be a semantic version like X.Y.Z
    parts = version.split(".")
    assert len(parts) >= 2


def test_is_fresh_install(cmd):
    """Test _is_fresh_install detects no home dir."""
    with patch("pathlib.Path.is_dir", return_value=False):
        assert cmd._is_fresh_install() is True


def test_is_not_fresh_install(cmd):
    """Test _is_fresh_install when home dir exists."""
    with patch("pathlib.Path.is_dir", return_value=True):
        assert cmd._is_fresh_install() is False


def test_restore_server_type_found(cmd):
    """Test _restore_server_type sets Options.server_type.

    ``_restore_server_type`` mutates module-level global state
    (``Feature`` in ``nxdrive.drive.feature`` and ``Options.server_type``)
    via ``apply_server_type_restrictions``. We snapshot and restore it so
    the test does not leak defaults into unrelated tests such as
    ``test_feature.py::TestFeatureDefaults``.
    """
    from nxdrive.drive.feature import DisabledFeatures, Feature

    saved_feature = dict(vars(Feature))
    saved_disabled = list(DisabledFeatures)
    saved_server_type = Options.server_type
    try:
        with patch("pathlib.Path.is_dir", return_value=True):
            cmd._restore_server_type()
        # After restore, server_type should be set
        assert Options.server_type is not None
    finally:
        # Undo the global mutations performed by
        # apply_server_type_restrictions to avoid polluting later tests.
        for k, v in saved_feature.items():
            setattr(Feature, k, v)
        DisabledFeatures[:] = saved_disabled
        Options.server_type = saved_server_type


def test_restore_server_type_not_found(cmd):
    """Test _restore_server_type when no home dir exists.

    Same global-state hygiene as ``test_restore_server_type_found``.
    """
    from nxdrive.drive.feature import DisabledFeatures, Feature

    saved_feature = dict(vars(Feature))
    saved_disabled = list(DisabledFeatures)
    saved_server_type = Options.server_type
    try:
        with patch("pathlib.Path.is_dir", return_value=False):
            cmd._restore_server_type()
        # Should remain unchanged (no match)
        assert Options.server_type == saved_server_type
    finally:
        for k, v in saved_feature.items():
            setattr(Feature, k, v)
        DisabledFeatures[:] = saved_disabled
        Options.server_type = saved_server_type


def test_make_cli_parser(cmd):
    """Test make_cli_parser creates a valid parser."""
    parser = cmd.make_cli_parser(add_subparsers=True)
    assert parser is not None
    # Should have subcommands
    parser.parse_args(["--version"])
    # --version triggers SystemExit


def test_make_cli_parser_no_subparsers(cmd):
    """Test make_cli_parser without subparsers."""
    parser = cmd.make_cli_parser(add_subparsers=False)
    assert parser is not None


def test_parse_cli_defaults(cmd):
    """Test parse_cli with no arguments returns console command."""
    ns = cmd.parse_cli(["console"])
    assert ns.command == "console"


def test_parse_cli_bind_server(cmd):
    """Test parse_cli with bind-server command."""
    ns = cmd.parse_cli(
        [
            "bind-server",
            "--password",
            "secret",
            "--local-folder",
            "/tmp/test",
            "user",
            "http://localhost:8080/nuxeo",
        ]
    )
    assert ns.command == "bind_server"
    assert ns.username == "user"
    assert ns.server_url == "http://localhost:8080/nuxeo"


def test_parse_cli_clean_folder(cmd):
    """Test parse_cli with clean-folder command."""
    ns = cmd.parse_cli(["clean-folder", "--local-folder", "/tmp/test"])
    assert ns.command == "clean_folder"


def test_redact_payload_with_token(cmd):
    """Test redact_payload masks token values."""
    payload = b"nxdrive://token/abc123secret"
    result = cmd.redact_payload(payload)
    assert b"abc123secret" not in result
    assert result == b"<REDACTED>"


def test_redact_payload_no_token(cmd):
    """Test redact_payload does not mask non-token payloads."""
    payload = b"nxdrive://edit/something"
    result = cmd.redact_payload(payload)
    assert result == payload
