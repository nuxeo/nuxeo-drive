import os
from os.path import join
import tempfile
import shutil

from nose.tools import with_setup
from nose.tools import assert_equal
from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_raises
from nxdrive.controller import Controller

TEST_FOLDER = tempfile.mkdtemp()
TEST_SYNCED_FOLDER = join(TEST_FOLDER, 'local_folder')
TEST_CONFIG_FOLDER = join(TEST_FOLDER, 'config')


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

    def authenticate(self):
        # dummy check
        return (
            (self.user_id == 'myuser' and self.password == 'secretpassword')
            or
            (self.user_id == 'nemo' and self.password == 'secret'))

    def is_valid_root(self, repo, ref_or_path):
        # dummy check
        return repo == 'default'


@with_setup(setup, teardown)
def test_bindings():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)

    # by default no bindings => no status to report
    assert_equal(ctl.status(), ())

    # it is not possible to bind a new root if not a subfolder of a bound
    # local folder
    remote_repo = 'default'
    remote_root = 'dead-beef-cafe-babe'
    local_root = join(TEST_SYNCED_FOLDER, 'Dead Beef')
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

    # Registering a server with a the wrong credentials will also fail
    assert_raises(RuntimeError, ctl.bind_server, TEST_SYNCED_FOLDER + '2',
                  'http://example.com/nuxeo',
                  'myuser', 'wrong password')


    # Registering a root outside of a server-bound folder will also yield an
    # error
    other_root = join(TEST_FOLDER, 'other_root')
    assert_raises(RuntimeError, ctl.bind_root, other_root, remote_repo,
                  remote_root)

    # local folder has not be created
    assert_false(os.path.exists(other_root))

    # Registering twice the same root will also raise an integrity constraint
    # error
    assert_raises(Exception, ctl.bind_root, local_root, remote_repo,
                  remote_root)


def test_binding_deletions():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)

    # it is not possible to bind a new root if not a subfolder of a bound
    # local folder
    remote_repo = 'default'
    remote_root = 'dead-beef-cafe-babe'
    local_root = join(TEST_SYNCED_FOLDER, 'Dead Beef')
    assert_raises(RuntimeError, ctl.bind_root, local_root, remote_repo,
                  remote_root)

    # register a couple of bindings
    ctl.bind_server(TEST_SYNCED_FOLDER, 'http://example.com/nuxeo',
                    'myuser', 'secretpassword')
    folder1 = join(TEST_SYNCED_FOLDER, 'folder1')
    folder2 = join(TEST_SYNCED_FOLDER, 'folder2')
    folder3 = join(TEST_SYNCED_FOLDER, 'folder3')

    ctl.bind_root(folder1, 'default', 'folder1')
    ctl.bind_root(folder2, 'default', 'folder2')
    ctl.bind_root(folder3, 'default', 'folder3')

    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is not None)
    assert_true(ctl.get_root_binding(folder1) is not None)
    assert_true(ctl.get_root_binding(folder2) is not None)
    assert_true(ctl.get_root_binding(folder3) is not None)

    # let's delete a binding manually
    ctl.unbind_root(folder2)
    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is not None)
    assert_true(ctl.get_root_binding(folder1) is not None)
    assert_true(ctl.get_root_binding(folder2) is None)
    assert_true(ctl.get_root_binding(folder3) is not None)

    # let's unbind the whole server folder
    ctl.unbind_server(TEST_SYNCED_FOLDER)
    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is None)
    assert_true(ctl.get_root_binding(folder1) is None)
    assert_true(ctl.get_root_binding(folder2) is None)
    assert_true(ctl.get_root_binding(folder3) is None)
