import os
import tempfile
import shutil

from nose.tools import assert_equal
from nose.tools import assert_raises
from nxdrive.controller import Controller

test_folder = tempfile.mkdtemp()
test_synced_folder = None
test_config_folder = None


def setup_module():
    global test_folder, test_synced_folder, test_config_folder
    test_synced_folder = os.path.join(test_folder, 'local_folder')
    test_config_folder = os.path.join(test_folder, 'config')
    os.makedirs(test_synced_folder)
    os.makedirs(test_config_folder)


def teardown_module():
    global test_folder
    shutil.rmtree(test_folder)


class FakeNuxeoClient(object):
    """Fake / mock client that does not require a real nuxeo instance"""

    def __init__(self, server_url, user_id, password):
        self.server_url = server_url
        self.user_id = user_id
        self.password = password

    def is_valid_root(self, ref_or_path):
        return ref_or_path == 'dead-beef-cafe-babe'


def test_bindings():
    ctl = Controller(test_config_folder, nuxeo_client_factory=FakeNuxeoClient,
                     echo=True)

    # by default no bindings => no status to report
    assert_equal(ctl.status(), ())

    # it is not possible to bind a new root if not a subfolder of a bound
    # local folder
    remote_root = 'dead-beef-cafe-babe'
    local_root = os.path.join(test_synced_folder, 'Dead Beef')
    assert_raises(RuntimeError, ctl.bind_root, local_root, remote_root)

    # register a new server binding
    ctl.bind_server(test_synced_folder,
                    'http://example.com/nuxeo',
                    'myuser', 'secretpassword')
    ctl.bind_root(local_root, remote_root)

    # the new binding has created a new home
    assert_equal(len(ctl.status()), 1)
