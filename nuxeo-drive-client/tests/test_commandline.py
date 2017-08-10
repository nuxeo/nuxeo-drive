# coding: utf-8
import os
import tempfile
import unittest

from nxdrive.commandline import CliHandler
from nxdrive.osi import AbstractOSIntegration
from tests.common import clean_dir


class FakeOSIntegration(AbstractOSIntegration):
    def get_system_configuration(self):
        args = dict()
        args["log_level_console"] = "SYSTEM_TEST"
        return args


def getOSIntegration(manager):
    return FakeOSIntegration(None)


class CommandLineTestCase(unittest.TestCase):
    def setUp(self):
        self.cmd = CliHandler()
        self.build_workspace = os.environ.get('WORKSPACE')
        self.tmpdir = None
        if self.build_workspace is not None:
            self.tmpdir = os.path.join(self.build_workspace, "tmp")
            if not os.path.isdir(self.tmpdir):
                os.makedirs(self.tmpdir)

    def create_ini(self, filename='config.ini', env='PROD'):
        with open(filename, 'w+') as inifile:
            inifile.writelines(['[DEFAULT]\n',
                            'env=' + env + '\n',
                            '[PROD]\n',
                            'log-level-console=TRACE\n',
                            '[DEV]\n',
                            'log-level-console=ERROR\n'])

    def clean_ini(self, filename='config.ini'):
        if os.path.exists(filename):
            os.remove(filename)

    def test_update_site_url(self):
        argv = ["ndrive", "console", "--update-site-url", "DEBUG_TEST"]
        options = self.cmd.parse_cli([])
        self.assertEqual(options.update_site_url,
                         "http://community.nuxeo.com/static/drive/",
                         "The official default")
        # Normal arg
        options = self.cmd.parse_cli(argv)
        self.assertEqual(options.update_site_url, "DEBUG_TEST",
                            "Should be debug test")

    def test_system_default(self):
        original = AbstractOSIntegration.get
        AbstractOSIntegration.get = staticmethod(getOSIntegration)
        self.cmd.default_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        try:
            self.clean_ini()
            argv = ["ndrive", "console", "--log-level-console", "WARNING"]
            # Default value
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, "SYSTEM_TEST",
                                "The system default is SYSTEM_TEST")
            # Normal arg
            options = self.cmd.parse_cli(argv)
            self.assertEqual(options.log_level_console, 'WARNING',
                             'Should be WARNING')
        finally:
            clean_dir(self.cmd.default_home)
            AbstractOSIntegration.get = staticmethod(original)

    def test_default_override(self):
        self.cmd.default_home = tempfile.mkdtemp("config", dir=self.tmpdir)
        try:
            self.clean_ini()
            argv = ["ndrive", "console", "--log-level-console", "WARNING"]
            # Default value
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, "INFO",
                                "The official default is INFO")
            # Normal arg
            options = self.cmd.parse_cli(argv)
            self.assertEqual(options.log_level_console, 'WARNING',
                             'Should be WARNING')
            # config.ini override
            self.create_ini()
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, 'TRACE',
                                "The config.ini shoud link to PROD")
            # config.ini override, but arg specified
            options = self.cmd.parse_cli(argv)
            self.assertEqual(options.log_level_console, 'WARNING',
                             'Should be WARNING')
            # other usage section
            self.create_ini(env='DEV')
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, 'ERROR',
                                "The config.ini shoud link to DEV")
            # user config.ini override
            conf = os.path.join(self.cmd.default_home, 'config.ini')
            self.create_ini(conf, "PROD")
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, 'TRACE',
                                "The config.ini shoud link to PROD")
            self.clean_ini(conf)
            options = self.cmd.parse_cli([])
            self.assertEqual(options.log_level_console, 'ERROR',
                                "The config.ini shoud link to DEV")
            self.clean_ini()
        finally:
            clean_dir(self.cmd.default_home)
