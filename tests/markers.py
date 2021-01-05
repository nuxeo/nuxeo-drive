"""Collection of pytest markers to ease test filtering."""
import os

import pytest

from nxdrive.constants import LINUX, MAC, WINDOWS

# Skip tests based on data coming from Jenkins (not public)
jenkins_only = pytest.mark.skipif(
    "JENKINS_URL" not in os.environ, reason="Must be ran from Jenkins."
)

# OS specific tests
linux_only = pytest.mark.skipif(not LINUX, reason="GNU/Linux only.")
mac_only = pytest.mark.skipif(not MAC, reason="macOS only.")
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows only.")

not_linux = pytest.mark.skipif(LINUX)
not_mac = pytest.mark.skipif(MAC)
not_windows = pytest.mark.skipif(WINDOWS)
