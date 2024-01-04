import subprocess
from unittest.mock import Mock

import pytest

from ..markers import linux_only


@linux_only
@pytest.fixture
def localclient(tmp_path):
    from nxdrive.client.local.linux import LocalClient

    localclient = LocalClient
    localclient.shared_icons = tmp_path
    return localclient


@linux_only
def test_has_folder_icon(localclient, tmp_path, monkeypatch):
    file = localclient.shared_icons / "emblem-nuxeo.svg"
    file.write_bytes(b"baz\n")
    localclient.abspath = Mock(return_value=tmp_path)
    subprocess.check_output = Mock(return_value="metadata::emblems:")
    assert not localclient.has_folder_icon(localclient, tmp_path)

    # Test the exception handling
    def mock_check_output(*args, **kwargs):
        raise Exception

    monkeypatch.setattr(subprocess, "check_output", mock_check_output)

    with pytest.raises(Exception):
        assert localclient.has_folder_icon(localclient, tmp_path)
