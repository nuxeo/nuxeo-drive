# coding: utf-8
from unittest.mock import patch

import pytest

from nxdrive.commandline import CliHandler
from nxdrive.options import Options
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import normalized_path


def create_ini(env: str = "PROD") -> None:
    with open(Options.nxdrive_home / "config.ini", "w") as f:
        f.writelines(
            f"""
[DEFAULT]
env = {env}

[PROD]
log-level_console = TRACE
debug = False

[DEV]
log_level-console = ERROR
delay = 3
"""
        )


def create_ini_bad():
    with open(Options.nxdrive_home / "config.ini", "w") as f:
        f.writelines(
            """
[DEFAULT]
env = bad

[bad]
log-level-console = TRACE
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
def test_system_default(cmd):
    def get_conf(_):
        return {"log_level_console": "TRACE"}

    argv = ["console", "--log-level-console", "WARNING"]

    with patch.object(AbstractOSIntegration, "get_system_configuration", new=get_conf):
        # Default value
        options = cmd.parse_cli([])
        assert options.log_level_console == "TRACE"

        # Normal arg
        options = cmd.parse_cli(argv)
        assert options.log_level_console == "WARNING"


@Options.mock()
def test_default_override(cmd):
    argv = ["console", "--log-level-console=WARNING"]

    # Default value
    options = cmd.parse_cli([])
    assert options.log_level_console == "INFO"

    # Normal arg
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "WARNING"

    # config.ini override
    create_ini()
    options = cmd.parse_cli([])
    assert options.log_level_console == "TRACE"

    # config.ini override, but arg specified
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "WARNING"

    # other usage section
    create_ini(env="DEV")
    options = cmd.parse_cli([])
    assert options.log_level_console == "ERROR"


@Options.mock()
def test_malformatted_line(cmd):
    create_ini_bad()
    with pytest.raises(TypeError):
        cmd.parse_cli([])


def test_z_last_ensure_options_not_modified():
    assert str(Options) == "Options()"
