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
from nxdrive.client import LocalClient

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
        return True

    def get_children_info(self, ref):
        return []


@with_setup(setup, teardown)
def test_bindings():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)

    # by default no bindings => cannot ask for a status
    assert_raises(NotFound, ctl.children_states, TEST_SYNCED_FOLDER)

    # it is not possible to bind a new root if the local folder is not bound to
    # the server
    remote_repo = 'default'
    remote_root = 'dead-beef-cafe-babe'
    expected_local_root = join(TEST_SYNCED_FOLDER, 'The Root')

    assert_raises(RuntimeError, ctl.bind_root, TEST_SYNCED_FOLDER,
                  remote_root, repository=remote_repo)

    # register a new server binding
    ctl.bind_server(TEST_SYNCED_FOLDER, 'http://example.com/nuxeo',
                    'username', 'secret')
    # TODO: implement me: children states of the server folder
    #assert_equal(ctl.children_states(TEST_SYNCED_FOLDER), [])

    ctl.bind_root(TEST_SYNCED_FOLDER, remote_root, repository=remote_repo)

    # The local root folder has been created
    assert_true(os.path.exists(expected_local_root))
    assert_equal(ctl.children_states(expected_local_root), [])

    # Registering twice the same root will also raise an integrity constraint
    # error
    assert_raises(Exception, ctl.bind_root, TEST_SYNCED_FOLDER, remote_root,
                  repository=remote_root)

    # Registering an other server on the same root will yield an error
    assert_raises(RuntimeError, ctl.bind_server, TEST_SYNCED_FOLDER,
                  'http://somewhere.else.info', 'username', 'secret')

    # Registering a server with a the wrong credentials will also fail
    assert_raises(Unauthorized, ctl.bind_server, TEST_SYNCED_FOLDER + '2',
                  'http://example.com/nuxeo',
                  'username', 'wrong password')

    # Registering a root outside in an unbound toplevel folder will fail
    other_folder = join(TEST_FOLDER, 'other_folder')
    assert_raises(RuntimeError, ctl.bind_root, other_folder, remote_root,
                  repository=remote_repo)

    # local folder has not be created
    assert_false(os.path.exists(other_folder))


@with_setup(setup, teardown)
def test_local_scan():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)
    ctl.bind_server(TEST_SYNCED_FOLDER, 'http://example.com/nuxeo',
                    'username', 'secret')
    ctl.bind_root(TEST_SYNCED_FOLDER, 'folder_1-nuxeo-ref')
    ctl.bind_root(TEST_SYNCED_FOLDER, 'folder_2-nuxeo-ref')
    root_1 = join(TEST_SYNCED_FOLDER, 'Folder 1')
    root_2 = join(TEST_SYNCED_FOLDER, 'Folder 2')

    client_1 = LocalClient(root_1)
    client_2 = LocalClient(root_2)

    # Folder are registered but empty for now
    assert_equal(ctl.children_states(root_1), [])
    assert_equal(ctl.children_states(root_2), [])

    # Put some content under the first root
    client_1.make_file('/', 'File 1.txt',
                       content="Initial 'File 1.txt' content")
    folder_3 = client_1.make_folder('/', 'Folder 3')
    client_1.make_file(folder_3, 'File 2.txt',
                       content="Initial 'File 2.txt' content")

    # The states have not been updated
    assert_equal(ctl.children_states(root_1), [])
    assert_equal(ctl.children_states(root_2), [])

    # Scanning the other root will not updated the first root states.
    session = ctl.get_session()
    ctl._scan_local(root_2, session)
    assert_equal(ctl.children_states(root_1), [])

    # Scanning root_1 will find the changes
    ctl._scan_local(root_1, session)
    assert_equal(ctl.children_states(root_1), [
        (u'/File 1.txt', u'unknown'),
        (u'/Folder 3', 'children_modified'),
    ])
    folder_3_abs = os.path.join(root_1, 'Folder 3')
    assert_equal(ctl.children_states(folder_3_abs), [
        (u'/Folder 3/File 2.txt', u'unknown'),
    ])

    # Let's do some changes
    client_1.delete('/File 1.txt')
    client_1.make_folder('/Folder 3', 'Folder 3.1')
    client_1.make_file('/Folder 3', 'File 3.txt',
                      content="Initial 'File 3.txt' content")
    client_1.update_content('/Folder 3/File 2.txt',
                            "Updated content for 'File 2.txt'")

    # If we don't do a rescan, the controller is not aware of the changes
    assert_equal(ctl.children_states(root_1), [
        (u'/File 1.txt', u'unknown'),
        (u'/Folder 3', 'children_modified'),
    ])
    folder_3_abs = os.path.join(root_1, 'Folder 3')
    assert_equal(ctl.children_states(folder_3_abs), [
        (u'/Folder 3/File 2.txt', u'unknown'),
    ])

    # Let's scan again
    ctl._scan_local(root_1, session)
    assert_equal(ctl.children_states(root_1), [
        (u'/Folder 3', 'children_modified'),
    ])
    assert_equal(ctl.children_states(folder_3_abs), [
        (u'/Folder 3/File 2.txt', u'unknown'),
        (u'/Folder 3/File 3.txt', u'unknown'),
        (u'/Folder 3/Folder 3.1', u'unknown')
    ])


@with_setup(setup, teardown)
def test_binding_deletions():
    ctl = Controller(TEST_CONFIG_FOLDER, nuxeo_client_factory=FakeNuxeoClient)

    # register a couple of bindings
    ctl.bind_server(TEST_SYNCED_FOLDER, 'http://example.com/nuxeo',
                    'username', 'secret')

    ctl.bind_root(TEST_SYNCED_FOLDER, 'folder_1-nuxeo-ref')
    ctl.bind_root(TEST_SYNCED_FOLDER, 'folder_2-nuxeo-ref')
    ctl.bind_root(TEST_SYNCED_FOLDER, 'folder_3-nuxeo-ref')

    # Expected created local folders
    folder_1 = join(TEST_SYNCED_FOLDER, 'Folder 1')
    folder_2 = join(TEST_SYNCED_FOLDER, 'Folder 2')
    folder_3 = join(TEST_SYNCED_FOLDER, 'Folder 3')

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
