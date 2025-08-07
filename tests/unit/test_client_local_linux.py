"""
For file nxdrive/client/local/linux.py
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from nxdrive.constants import LINUX, MAC


@pytest.mark.skipif(MAC, reason="Cannot run on MacOS")
@patch("subprocess.check_output")
@patch("pathlib.Path.is_file")
def test_has_folder_icon(mock_is_file, mock_subprocess_check_output):
    # Test case cannot run on MacOS because of missing imports
    from nxdrive.client.local.linux import LocalClient

    lc_obj = LocalClient(Path())
    mock_is_file.return_value = True
    mock_subprocess_check_output.return_value = "metadata::emblems: [emblem-nuxeo]"
    output = lc_obj.has_folder_icon(Path())
    assert output is True


@pytest.mark.skipif(not LINUX, reason="GNU/Linux only.")
def test_remove_remote_id_impl():
    # Test case must run only on Linux
    from nxdrive.client.local.linux import LocalClient

    # Test success
    assert LocalClient.remove_remote_id_impl(Path()) is None
    # Test exception
