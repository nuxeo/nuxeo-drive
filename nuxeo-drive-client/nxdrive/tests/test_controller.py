import os
from datetime import datetime
from os.path import join
import tempfile
import shutil

from nose.tools import with_setup
from nose.tools import assert_equal
from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_raises
from nxdrive.controller import Controller
from nxdrive.client import NuxeoDocumentInfo
from nxdrive.client import NotFound
from nxdrive.client import Unauthorized

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

    def __init__(self, server_url, user_id, password, repository='default',
                 base_folder=None):
        self.server_url = server_url
        self.user_id = user_id
        self.password = password
        self.base_folder = base_folder
        self.repository = repository

        if user_id != 'username' or password != 'secret':
            raise Unauthorized(server_url, user_id)

        self.possible_roots = {
            'dead-beef-cafe-babe':
            NuxeoDocumentInfo(
                base_folder, 'The Root',
                'dead-beef-cafe-babe', 'cafe-beef-dead-babe',
                True, datetime.utcnow(), None),
            'folder_1-nuxeo-ref':
            NuxeoDocumentInfo(
                base_folder, 'Folder 1',
                'folder_1-nuxeo-ref', 'cafe-beef-dead-babe',
                True, datetime.utcnow(), None),
            'folder_2-nuxeo-ref':
            NuxeoDocumentInfo(
                base_folder, 'Folder 2',
                'folder_2-nuxeo-ref', 'cafe-beef-dead-babe',
                True, datetime.utcnow(), None),
            'folder_3-nuxeo-ref':
            NuxeoDocumentInfo(
                base_folder, 'Folder 3',
                'folder_3-nuxeo-ref', 'cafe-beef-dead-babe',
                True, datetime.utcnow(), None),
        }

    def get_info(self, ref):
        root_info = self.possible_roots.get(ref)
        if root_info is None:
            raise NotFound(ref + ' not found')
        return root_info

    def check_writable(self, ref):
        return ref in ['/']

    def get_children_info(self, ref):
        # TODO: implement me!
        return []


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
                    'username', 'secret')
    ctl.bind_root(local_root, remote_repo, remote_root)

    # The local Dead Beef folder has been created if missing
    assert_true(os.path.exists(local_root))

    # Registering an other server on the same root will yield an error
    assert_raises(RuntimeError, ctl.bind_server, TEST_SYNCED_FOLDER,
                  'http://somewhere.else.info', 'username', 'secret')

    # Registering a server with a the wrong credentials will also fail
    assert_raises(Unauthorized, ctl.bind_server, TEST_SYNCED_FOLDER + '2',
                  'http://example.com/nuxeo',
                  'username', 'wrong password')

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
                    'username', 'secret')
    folder_1 = join(TEST_SYNCED_FOLDER, 'folder_1')
    folder_2 = join(TEST_SYNCED_FOLDER, 'folder_2')
    folder_3 = join(TEST_SYNCED_FOLDER, 'folder_3')

    ctl.bind_root(folder_1, 'default', 'folder_1-nuxeo-ref')
    ctl.bind_root(folder_2, 'default', 'folder_2-nuxeo-ref')
    ctl.bind_root(folder_3, 'default', 'folder_3-nuxeo-ref')

    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is not None)
    assert_true(ctl.get_root_binding(folder_1) is not None)
    assert_true(ctl.get_root_binding(folder_2) is not None)
    assert_true(ctl.get_root_binding(folder_3) is not None)

    # let's delete a binding manually
    ctl.unbind_root(folder_2)
    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is not None)
    assert_true(ctl.get_root_binding(folder_1) is not None)
    assert_true(ctl.get_root_binding(folder_2) is None)
    assert_true(ctl.get_root_binding(folder_3) is not None)

    # check that you cannot unbind the same root twice
    assert_raises(RuntimeError, ctl.unbind_root, folder_2)
    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is not None)
    assert_true(ctl.get_root_binding(folder_1) is not None)
    assert_true(ctl.get_root_binding(folder_2) is None)
    assert_true(ctl.get_root_binding(folder_3) is not None)

    # let's unbind the whole server folder
    ctl.unbind_server(TEST_SYNCED_FOLDER)
    assert_true(ctl.get_server_binding(TEST_SYNCED_FOLDER) is None)
    assert_true(ctl.get_root_binding(folder_1) is None)
    assert_true(ctl.get_root_binding(folder_2) is None)
    assert_true(ctl.get_root_binding(folder_3) is None)

    # check that you cannot unbind the same server twice
    assert_raises(RuntimeError, ctl.unbind_server, TEST_SYNCED_FOLDER)

    # check that you cannot unbind non bound roots and servers
    assert_raises(RuntimeError, ctl.unbind_root, folder_2 + '-bis')
    assert_raises(RuntimeError, ctl.unbind_server, TEST_SYNCED_FOLDER + '-bis')
