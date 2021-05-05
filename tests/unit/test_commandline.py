from pathlib import Path
from unittest.mock import patch

import pytest

from nxdrive.commandline import DEFAULTSECT, CliHandler
from nxdrive.options import Options
from nxdrive.utils import normalized_path

from ..markers import mac_only, windows_only


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
    from nxdrive.osi.windows.windows import WindowsIntegration

    with patch.object(WindowsIntegration, "get_system_configuration", new=get_conf):
        options = cmd.parse_cli([])
        assert options.log_level_console == "DEBUG"


@Options.mock()
@mac_only
def test_system_default_mac(cmd):
    from nxdrive.osi.darwin.darwin import DarwinIntegration

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
