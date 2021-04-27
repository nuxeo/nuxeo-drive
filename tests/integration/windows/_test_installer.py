import os
import subprocess
from glob import glob
from logging import getLogger

import pytest

from nxdrive.constants import WINDOWS

from ... import env

if not WINDOWS:
    pytestmark = pytest.mark.skip

log = getLogger(__name__)


class Installer:

    launcher = ""
    uninstaller = ""

    def __init__(self, path, *install_opt):
        self.path = path
        self.install_opt = ["/verysilent"] + list(install_opt)
        log.info("Installer path is %r", self.path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.uninstall()

    def install(self, *install_opt):
        log.info("Installing, calling %r %s", self.path, " ".join(install_opt))
        subprocess.Popen([self.path] + list(install_opt))
        self.launcher = ""
        self.uninstaller = ""

    def uninstall(self):
        if not getattr(self, "uninstaller", None):
            return

        log.info("Uninstallation, calling %r /verysilent", self.uninstaller)
        subprocess.Popen([self.uninstaller, "/verysilent"])


@pytest.fixture()
def installer_path():
    """Generate a fresh installer."""
    cmd = ["powershell", ".\\tools\\windows\\deploy_ci_agent.ps1", "-build"]
    log.info("Building the installer: %r", cmd)
    subprocess.Popen(cmd)
    path = glob("dist\\nuxeo-drive-*.exe")[0]
    yield path
    os.remove(path)


def test_installer_arguments(installer_path):
    """
    Test arguments the installer can manage:

    - Mandatory arguments
        TARGETURL: The URL of the Nuxeo server.
        TARGETUSERNAME: The username of the user who will be using Nuxeo Drive.
    - Optional arguments
        TARGETPASSWORD: The password of the user who will be using Nuxeo Drive.

    Arguments __not__ tested:
        TARGETDRIVEFOLDER: The path to the user synchronisation folder that will be created.
        START=auto: Start Nuxeo Drive after the installation.
    """
    with Installer(installer_path) as installer:
        args = [
            f'/TARGETURL="{env.NXDRIVE_TEST_NUXEO_URL}"',
            f'/TARGETUSERNAME="{env.NXDRIVE_TEST_USERNAME}"',
            f'/TARGETPASSWORD="{env.NXDRIVE_TEST_PASSWORD}"',
        ]
        installer.install(args)
