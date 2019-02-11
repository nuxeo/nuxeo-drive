# coding: utf-8
import os
from contextlib import suppress
from unittest.mock import patch

import pytest

from nxdrive.commandline import CliHandler
from nxdrive.options import Options
from nxdrive.osi import AbstractOSIntegration
from nxdrive.utils import normalized_path


def create_ini(env: str = "PROD") -> None:
    with open("config.ini", "w+") as f:
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
    with open("config.ini", "w+") as f:
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


def clean_ini():
    with suppress(OSError):
        os.remove("config.ini")


@pytest.fixture
def cmd():
    yield CliHandler()


@pytest.fixture
def home(tempdir):
    path = tempdir() / "config"
    path.mkdir(parents=True, exist_ok=True)
    Options.nxdrive_home = normalized_path(path)


def test_redact_payload(cmd):
    payload = b"nxdrive://token/12345678-acbd-1234-cdef-1234567890ab/user/Administrator@127.0.0.1"
    assert cmd.redact_payload(payload) == b"<REDACTED>"
    assert cmd.redact_payload(b"payload") == b"payload"


@Options.mock()
def test_update_site_url(home, cmd):
    argv = ["console", "--update-site-url", "DEBUG_TEST"]
    options = cmd.parse_cli([])
    assert options.update_site_url == Options.update_site_url

    # Normal arg
    options = cmd.parse_cli(argv)
    assert options.update_site_url == "DEBUG_TEST"


@Options.mock()
def test_system_default(home, cmd):
    def get_conf(_):
        return {"log_level_console": "SYSTEM_TEST"}

    clean_ini()
    argv = ["console", "--log-level-console", "WARNING"]

    with patch.object(AbstractOSIntegration, "get_system_configuration", new=get_conf):
        # Default value
        options = cmd.parse_cli([])
        assert options.log_level_console == "SYSTEM_TEST"

        # Normal arg
        options = cmd.parse_cli(argv)
        assert options.log_level_console == "WARNING"


@Options.mock()
def test_default_override(home, cmd):
    clean_ini()
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
    clean_ini()

    # config.ini override, but arg specified
    options = cmd.parse_cli(argv)
    assert options.log_level_console == "WARNING"

    # other usage section
    create_ini(env="DEV")
    options = cmd.parse_cli([])
    assert options.log_level_console == "ERROR"
    clean_ini()


@Options.mock()
def test_malformatted_line(home, cmd):
    clean_ini()

    # config.ini override
    create_ini_bad()
    with pytest.raises(TypeError):
        cmd.parse_cli([])
    clean_ini()
