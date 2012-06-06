import os
import tempfile
import shutil

from nose.tools import with_setup
from nose.tools import assert_equal
from nose.tools import assert_true
from nose.tools import assert_raises
from nxdrive.controller import Controller

TEST_FOLDER = tempfile.mkdtemp()
TEST_SYNCED_FOLDER = os.path.join(TEST_FOLDER, 'local_folder')
TEST_CONFIG_FOLDER = os.path.join(TEST_FOLDER, 'config')


def setup():
    if os.path.exists(TEST_FOLDER):
        shutil.rmtree(TEST_FOLDER)
    os.makedirs(TEST_FOLDER)
    os.makedirs(TEST_SYNCED_FOLDER)
    os.makedirs(TEST_CONFIG_FOLDER)


def teardown():
    if os.path.exists(TEST_FOLDER):
        shutil.rmtree(TEST_FOLDER)


class FakeNuxeoClient(object):
    """Fake / mock client that does not require a real nuxeo instance"""

    def __init__(self, server_url, user_id, password):
        self.server_url = server_url
        self.user_id = user_id
        self.password = password

    def is_valid_root(self, repo, ref_or_path):
        return repo == 'default' and ref_or_path == 'dead-beef-cafe-babe'


@with_setup(setup, teardown)
def test_bindings():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)

    # by default no bindings => no status to report
    assert_equal(ctl.status(), ())

    # it is not possible to bind a new root if not a subfolder of a bound
    # local folder
    remote_repo = 'default'
    remote_root = 'dead-beef-cafe-babe'
    local_root = os.path.join(TEST_SYNCED_FOLDER, 'Dead Beef')
    assert_raises(RuntimeError, ctl.bind_root, local_root, remote_repo,
                  remote_root)

    # register a new server binding
    ctl.bind_server(TEST_SYNCED_FOLDER,
                    'http://example.com/nuxeo',
                    'myuser', 'secretpassword')
    ctl.bind_root(local_root, remote_repo, remote_root)

    # The local Dead Beef folder has been created if missing
    assert_true(os.path.exists(local_root))

    # Registering an other server on the same root will yield an error
    assert_raises(RuntimeError, ctl.bind_server, TEST_SYNCED_FOLDER,
                  'http://somewhere.else.info', 'nemo', 'secret')

    # Registering an other root on the same folder will also yield an error
    other_root = os.path.join(TEST_FOLDER, 'other_root')
    assert_raises(RuntimeError, ctl.bind_root, other_root, remote_repo,
                  remote_root)

    # Registering a root outside of a server-bound folder will also yield an
    # error
    assert_raises(Exception, ctl.bind_root, local_root, remote_repo,
                  remote_root)
