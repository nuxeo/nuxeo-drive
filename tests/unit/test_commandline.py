# coding: utf-8
from contextlib import suppress
from unittest.mock import patch

import pytest

from nxdrive.commandline import CliHandler
from nxdrive.options import Options
from nxdrive.utils import normalized_path

from ..markers import mac_only, windows_only


def create_ini(env: str = "PROD") -> None:
    with open(Options.nxdrive_home / "config.ini", "w") as f:
        f.writelines(
            f"""
[DEFAULT]
env = {env}

[PROD]
log-level_console = DEBUG
debug = False

[DEV]
log_level-console = ERROR
debug = True
delay = 3
tmp-file-limit = 0.0105
"""
        )


def create_ini_bad():
    with open(Options.nxdrive_home / "config.ini", "w") as f:
        f.writelines(
            """
[DEFAULT]
env = bad

[bad]
log-level-console = DEBUG
 debug = False

delay = 3
"""
        )


@pytest.fixture
def cmd(tmp):
    path = tmp() / "config"
    path.mkdir(parents=True, exist_ok=True)
    Options.nxdrive_home = normalized_path(path)

    yield CliHandler()

    with suppress(FileNotFoundError):
        (Options.nxdrive_home / "config.ini").unlink()


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
def test_default_override(cmd):
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
    create_ini()
    options = cmd.parse_cli([])
    assert options.log_level_console == "DEBUG"
    assert not options.debug

    # config.ini override, but arg specified
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "INFO"
    assert not options.debug

    # other usage section
    create_ini(env="DEV")
    options = cmd.parse_cli([])
    assert options.log_level_console == "ERROR"
    assert options.debug
    assert options.delay == 3
    assert options.tmp_file_limit == 0.0105


@Options.mock()
def test_malformatted_line(cmd):
    create_ini_bad()
    cmd.parse_cli([])
    # The malformed line will display a warning:
    # Unknown logging level ('=', 'DEBUG', 'False', 'debug'), need to be one of ...
    # Callback check for 'log_level_console' denied modification. Value is still 'WARNING'.
    assert Options.log_level_console == "WARNING"


def test_z_last_ensure_options_not_modified():
    assert str(Options) == "Options()"
