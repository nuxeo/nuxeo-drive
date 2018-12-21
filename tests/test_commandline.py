# coding: utf-8
import os
import tempfile
import unittest
from contextlib import suppress

import pytest

from nxdrive.commandline import CliHandler
from nxdrive.options import Options
from nxdrive.osi import AbstractOSIntegration
from .common import clean_dir


class FakeOSIntegration(AbstractOSIntegration):
    def get_system_configuration(self):
        return {"log_level_console": "SYSTEM_TEST"}


def getOSIntegration(manager):
    return FakeOSIntegration(None)


class TestCommandLine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = os.path.join(os.environ.get("WORKSPACE", ""), "tmp")
        self.addCleanup(clean_dir, self.tmpdir)
        os.makedirs(self.tmpdir, exist_ok=True)

        self.cmd = CliHandler()
        self.addCleanup(self.clean_ini)

    def create_ini(self, filename="config.ini", env="PROD"):
        with open(filename, "w+") as inifile:
            inifile.writelines(
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

    def create_ini_bad(self, filename="config.ini"):
        with open(filename, "w+") as inifile:
            inifile.writelines(
                """
[DEFAULT]
env = bad

[bad]
log-level-console = TRACE
 debug = False

delay = 3
"""
            )

    def clean_ini(self, filename="config.ini"):
        with suppress(OSError):
            os.remove(filename)

    def test_redact_payload(self):
        payload = b"nxdrive://token/12345678-acbd-1234-cdef-1234567890ab/user/Administrator@127.0.0.1"
        assert self.cmd.redact_payload(payload) == b"<REDACTED>"
        assert self.cmd.redact_payload(b"payload") == b"payload"

    @Options.mock()
    def test_update_site_url(self):
        Options.nxdrive_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        argv = ["console", "--update-site-url", "DEBUG_TEST"]
        options = self.cmd.parse_cli([])
        assert options.update_site_url == Options.update_site_url

        # Normal arg
        options = self.cmd.parse_cli(argv)
        assert options.update_site_url == "DEBUG_TEST"

    @Options.mock()
    def test_system_default(self):
        Options.nxdrive_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        original = AbstractOSIntegration.get
        AbstractOSIntegration.get = staticmethod(getOSIntegration)
        try:
            self.clean_ini()
            argv = ["console", "--log-level-console", "WARNING"]
            # Default value
            options = self.cmd.parse_cli([])
            assert options.log_level_console == "SYSTEM_TEST"

            # Normal arg
            options = self.cmd.parse_cli(argv)
            assert options.log_level_console == "WARNING"
        finally:
            AbstractOSIntegration.get = staticmethod(original)

    @Options.mock()
    def test_default_override(self):
        Options.nxdrive_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        self.clean_ini()
        argv = ["console", "--log-level-console=WARNING"]

        # Default value
        options = self.cmd.parse_cli([])
        assert options.log_level_console == "INFO"

        # Normal arg
        options = self.cmd.parse_cli(argv)
        assert options.log_level_console == "WARNING"

        # config.ini override
        self.create_ini()
        options = self.cmd.parse_cli([])
        assert options.log_level_console == "TRACE"
        self.clean_ini()

        # config.ini override, but arg specified
        options = self.cmd.parse_cli(argv)
        assert options.log_level_console == "WARNING"

        # other usage section
        self.create_ini(env="DEV")
        options = self.cmd.parse_cli([])
        assert options.log_level_console == "ERROR"
        self.clean_ini()

    @Options.mock()
    def test_malformatted_line(self):
        Options.nxdrive_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        self.clean_ini()

        # config.ini override
        self.create_ini_bad()
        with pytest.raises(TypeError):
            self.cmd.parse_cli([])
        self.clean_ini()
