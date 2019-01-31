# coding: utf-8
"""Collection of pytest markers to ease test filtering."""

import os

import pytest

from nxdrive.constants import MAC, WINDOWS


# Skip tests based on data coming from Jenkins (not public)
jenkins_only = pytest.mark.skipif(
    "JENKINS_URL" not in os.environ, reason="Must be ran from Jenkins."
)

# Skip tests that must be run on macOS only
mac_only = pytest.mark.skipif(not MAC, reason="macOS only.")

# Skip tests that must be run on Windows only
windows_only = pytest.mark.skipif(not WINDOWS, reason="Windows only.")

# Skip tests that must __not__ be run on Windows
not_windows = pytest.mark.skipif(WINDOWS)
