import hashlib
import os
import shutil
import tempfile
import time
import urllib2
import socket
import httplib
from nose import with_setup
from nose import SkipTest
from nose.tools import assert_equal

from nxdrive.client import NuxeoClient
from nxdrive.client import LocalClient
from nxdrive.controller import Controller


TEST_WORKSPACE_PATH = '/default-domain/workspaces/test-nxdrive'
TEST_WORKSPACE_TITLE = 'Nuxeo Drive Tests'
TEST_WORKSPACE = None

EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = "Some text content."
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()

NUXEO_URL = None
USER = None
PASSWORD = None
LOCAL_TEST_FOLDER = None
LOCAL_NXDRIVE_FOLDER = None
LOCAL_NXDRIVE_CONF_FOLDER = None

remote_client = None
ctl = None


def setup_integration_env():
    global NUXEO_URL, USER, PASSWORD
    global remote_client, lcclient, TEST_WORKSPACE, LOCAL_TEST_FOLDER
    global LOCAL_NXDRIVE_FOLDER, LOCAL_NXDRIVE_CONF_FOLDER
    global ctl

    # Check the Nuxeo server test environment
    NUXEO_URL = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
    USER = os.environ.get('NXDRIVE_TEST_USER')
    PASSWORD = os.environ.get('NXDRIVE_TEST_PASSWORD')
    if None in (NUXEO_URL, USER, PASSWORD):
        raise SkipTest("No integration server configuration found in "
                       "environment.")

    parent_path = os.path.dirname(TEST_WORKSPACE_PATH)
    workspace_name = os.path.basename(TEST_WORKSPACE_PATH)
    root_remote_client = NuxeoClient(NUXEO_URL, USER, 'test-device',
                                     PASSWORD, base_folder='/')
    TEST_WORKSPACE = root_remote_client.create(
        parent_path, 'Workspace', name=workspace_name,
        properties={'dc:title': TEST_WORKSPACE_TITLE})[u'uid']

    # Client to be use to create remote test documents and folders
    remote_client = NuxeoClient(NUXEO_URL, USER, 'test-device',
                                PASSWORD, base_folder=TEST_WORKSPACE)

    # Check the local filesystem test environment
    LOCAL_TEST_FOLDER = tempfile.mkdtemp('-nuxeo-drive-tests')

    LOCAL_NXDRIVE_FOLDER = os.path.join(
        LOCAL_TEST_FOLDER, 'Nuxeo Drive')
    os.mkdir(LOCAL_NXDRIVE_FOLDER)

    LOCAL_NXDRIVE_CONF_FOLDER = os.path.join(
        LOCAL_TEST_FOLDER, 'nuxeo-drive-conf')
    os.mkdir(LOCAL_NXDRIVE_CONF_FOLDER)

    ctl = Controller(LOCAL_NXDRIVE_CONF_FOLDER)


def teardown_integration_env():
    if ctl is not None:
        ctl.dispose()

    if remote_client is not None and remote_client.exists(TEST_WORKSPACE):
        remote_client.delete(TEST_WORKSPACE, use_trash=False)

    if os.path.exists(LOCAL_TEST_FOLDER):
        shutil.rmtree(LOCAL_TEST_FOLDER)


with_integration_env = with_setup(
    setup_integration_env, teardown_integration_env)


def make_server_tree():
    # create some folders on the server
    folder_1 = remote_client.make_folder(TEST_WORKSPACE, 'Folder 1')
    folder_1_1 = remote_client.make_folder(folder_1, 'Folder 1.1')
    folder_1_2 = remote_client.make_folder(folder_1, 'Folder 1.2')
    folder_2 = remote_client.make_folder(TEST_WORKSPACE, 'Folder 2')

    # create some files on the server
    remote_client.make_file(folder_2, 'Duplicated File.txt',
                            content="Some content.")
    remote_client.make_file(folder_2, 'Duplicated File.txt',
                            content="Other content.")

    remote_client.make_file(folder_1, 'File 1.txt', content="aaa")
    remote_client.make_file(folder_1_1, 'File 2.txt', content="bbb")
    remote_client.make_file(folder_1_2, 'File 3.txt', content="ccc")
    remote_client.make_file(folder_2, 'File 4.txt', content="ddd")
    remote_client.make_file(TEST_WORKSPACE, 'File 5.txt', content="eee")


@with_integration_env
def test_binding_initialization_and_first_sync():
    # Create some documents in a Nuxeo workspace and bind this server to a
    # Nuxeo Drive local folder
    make_server_tree()
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)
    syn = ctl.synchronizer

    # The binding operation creates a new local folder with the Workspace name
    # and reproduce the server side structure with folders and empty documents.
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)
    local = LocalClient(expected_folder)
    level_0 = local.get_children_info('/')

    def size(info):
        return os.stat(info.filepath).st_size

    assert_equal(len(level_0), 3)
    assert_equal(level_0[0].name, 'File 5.txt')
    assert_equal(size(level_0[0]), 0)
    assert_equal(level_0[1].name, 'Folder 1')
    assert_equal(level_0[2].name, 'Folder 2')

    level_1 = local.get_children_info(level_0[1].path)
    assert_equal(len(level_1), 3)
    assert_equal(level_1[0].name, 'File 1.txt')
    assert_equal(size(level_1[0]), 0)
    assert_equal(level_1[1].name, 'Folder 1.1')
    assert_equal(level_1[2].name, 'Folder 1.2')

    level_2 = local.get_children_info(level_0[2].path)
    assert_equal(len(level_2), 3)
    assert_equal(level_2[0].name, 'Duplicated File.txt')
    assert_equal(size(level_2[0]), 0)
    assert_equal(level_2[1].name, 'Duplicated File__1.txt')  # deduped name
    assert_equal(size(level_2[1]), 0)
    assert_equal(level_2[2].name, 'File 4.txt')
    assert_equal(size(level_2[2]), 0)

    # Check the aggregate states information from the controller
    states = ctl.children_states(expected_folder)
    expected_states = [
        (u'/File 5.txt', 'remotely_modified'),
        (u'/Folder 1', 'children_modified'),
        (u'/Folder 2', 'children_modified'),
    ]
    assert_equal(states, expected_states)

    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.txt', 'remotely_modified'),
        (u'/Folder 1/Folder 1.1', 'children_modified'),
        (u'/Folder 1/Folder 1.2', 'children_modified'),
    ]
    assert_equal(states, expected_states)

    states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
    expected_states = [
        (u'/Folder 1/Folder 1.1/File 2.txt', 'remotely_modified'),
    ]
    assert_equal(states, expected_states)

    # Check the list of files and folders with synchronization pending
    pending = ctl.list_pending()
    assert_equal(len(pending), 7)
    assert_equal(pending[0].path, '/File 5.txt')
    assert_equal(pending[1].path, '/Folder 1/File 1.txt')
    assert_equal(pending[2].path, '/Folder 1/Folder 1.1/File 2.txt')
    assert_equal(pending[3].path, '/Folder 1/Folder 1.2/File 3.txt')
    assert_equal(pending[4].path, '/Folder 2/Duplicated File.txt')
    assert_equal(pending[5].path, '/Folder 2/Duplicated File__1.txt')
    assert_equal(pending[6].path, '/Folder 2/File 4.txt')

    # It is also possible to restrict the list of pending document to a
    # specific root
    assert_equal(len(ctl.list_pending(local_root=expected_folder)), 7)

    # It is also possible to restrict the number of pending tasks
    pending = ctl.list_pending(limit=2)
    assert_equal(len(pending), 2)

    # Synchronize the first 2 documents:
    assert_equal(syn.synchronize(limit=2), 2)
    pending = ctl.list_pending()
    assert_equal(len(pending), 5)
    assert_equal(pending[0].path, '/Folder 1/Folder 1.1/File 2.txt')
    assert_equal(pending[1].path, '/Folder 1/Folder 1.2/File 3.txt')
    assert_equal(pending[2].path, '/Folder 2/Duplicated File.txt')
    assert_equal(pending[3].path, '/Folder 2/Duplicated File__1.txt')
    assert_equal(pending[4].path, '/Folder 2/File 4.txt')

    states = ctl.children_states(expected_folder)
    expected_states = [
        (u'/File 5.txt', 'synchronized'),
        (u'/Folder 1', 'children_modified'),
        (u'/Folder 2', 'children_modified'),
    ]
    # The actual content of the file has been updated
    assert_equal(local.get_content('/File 5.txt'), "eee")

    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.txt', 'synchronized'),
        (u'/Folder 1/Folder 1.1', 'children_modified'),
        (u'/Folder 1/Folder 1.2', 'children_modified'),
    ]
    assert_equal(states, expected_states)

    # synchronize everything else
    assert_equal(syn.synchronize(), 5)
    assert_equal(ctl.list_pending(), [])
    states = ctl.children_states(expected_folder)
    expected_states = [
        (u'/File 5.txt', 'synchronized'),
        (u'/Folder 1', 'synchronized'),
        (u'/Folder 2', 'synchronized'),
    ]
    assert_equal(states, expected_states)

    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.txt', 'synchronized'),
        (u'/Folder 1/Folder 1.1', 'synchronized'),
        (u'/Folder 1/Folder 1.2', 'synchronized'),
    ]
    assert_equal(states, expected_states)
    assert_equal(local.get_content('/Folder 1/File 1.txt'), "aaa")
    assert_equal(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbb")
    assert_equal(local.get_content('/Folder 1/Folder 1.2/File 3.txt'), "ccc")
    assert_equal(local.get_content('/Folder 2/File 4.txt'), "ddd")
    assert_equal(local.get_content('/Folder 2/Duplicated File.txt'),
                 "Some content.")
    assert_equal(local.get_content('/Folder 2/Duplicated File__1.txt'),
                 "Other content.")

    # Nothing else left to synchronize
    assert_equal(ctl.list_pending(), [])
    assert_equal(syn.synchronize(), 0)
    assert_equal(ctl.list_pending(), [])

    # Unbind root and resynchronize: smoke test
    ctl.unbind_root(expected_folder)
    assert_equal(ctl.list_pending(), [])
    assert_equal(syn.synchronize(), 0)
    assert_equal(ctl.list_pending(), [])


@with_integration_env
def test_binding_synchronization_empty_start():
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)
    syn = ctl.synchronizer
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)

    # Nothing to synchronize by default
    assert_equal(ctl.list_pending(), [])
    assert_equal(syn.synchronize(), 0)

    # Let's create some document on the server
    make_server_tree()

    # By default nothing is detected
    assert_equal(ctl.list_pending(), [])
    #assert_equal(ctl.children_states(expected_folder), [])

    # Let's scan manually
    session = ctl.get_session()
    syn.scan_remote(expected_folder, session)

    # Changes on the remote server have been detected...
    assert_equal(len(ctl.list_pending()), 11)

    # ...but nothing is yet visible locally as those files don't exist there
    # yet.
    #assert_equal(ctl.children_states(expected_folder), [])

    # Let's perform the synchronization
    assert_equal(syn.synchronize(limit=100), 11)

    # We should now be fully synchronized
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/File 5.txt', u'synchronized'),
        (u'/Folder 1', u'synchronized'),
        (u'/Folder 2', u'synchronized'),
    ])
    local = LocalClient(expected_folder)
    assert_equal(local.get_content('/Folder 1/File 1.txt'), "aaa")
    assert_equal(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbb")
    assert_equal(local.get_content('/Folder 1/Folder 1.2/File 3.txt'), "ccc")
    assert_equal(local.get_content('/Folder 2/File 4.txt'), "ddd")
    assert_equal(local.get_content('/Folder 2/Duplicated File.txt'),
                 "Some content.")
    assert_equal(local.get_content('/Folder 2/Duplicated File__1.txt'),
                 "Other content.")

    # Wait a bit for file time stamps to increase enough: on most OS the file
    # modification time resolution is 1s
    time.sleep(1.0)

    # Let do some local and remote changes concurrently
    local.delete('/File 5.txt')
    local.update_content('/Folder 1/File 1.txt', 'aaaa')
    remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', 'bbbb')
    remote_client.delete('/Folder 2')
    f3 = remote_client.make_folder(TEST_WORKSPACE, 'Folder 3')
    remote_client.make_file(f3, 'File 6.txt', content='ffff')
    local.make_folder('/', 'Folder 4')

    # Rescan
    syn.scan_local(expected_folder, session)
    syn.scan_remote(expected_folder, session)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/File 5.txt', u'locally_deleted'),
        (u'/Folder 1', u'children_modified'),
        (u'/Folder 2', u'children_modified'),  # what do we want for this?
        # Folder 3 is not yet visible has not sync has happen to give it a
        # local path yet
        (u'/Folder 4', u'unknown'),
    ])
    # It is possible to fetch the full children states of the root though:
    full_states = ctl.children_states(expected_folder, full_states=True)
    assert_equal(len(full_states), 5)
    assert_equal(full_states[0][0].remote_name, 'Folder 3')
    assert_equal(full_states[0][1], 'children_modified')

    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.txt', 'locally_modified'),
        (u'/Folder 1/Folder 1.1', 'children_modified'),
        (u'/Folder 1/Folder 1.2', 'synchronized'),
    ]
    assert_equal(states, expected_states)
    states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
    expected_states = [
        (u'/Folder 1/Folder 1.1/File 2.txt', u'remotely_modified'),
    ]
    assert_equal(states, expected_states)
    states = ctl.children_states(expected_folder + '/Folder 2')
    expected_states = [
        (u'/Folder 2/Duplicated File.txt', u'remotely_deleted'),
        (u'/Folder 2/Duplicated File__1.txt', u'remotely_deleted'),
        (u'/Folder 2/File 4.txt', u'remotely_deleted'),
    ]
    assert_equal(states, expected_states)

    # Perform synchronization
    assert_equal(syn.synchronize(limit=100), 10)

    # We should now be fully synchronized again
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/Folder 1', 'synchronized'),
        (u'/Folder 3', 'synchronized'),
        (u'/Folder 4', 'synchronized'),
    ])
    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.txt', 'synchronized'),
        (u'/Folder 1/Folder 1.1', 'synchronized'),
        (u'/Folder 1/Folder 1.2', 'synchronized'),
    ]
    assert_equal(states, expected_states)
    assert_equal(local.get_content('/Folder 1/File 1.txt'), "aaaa")
    assert_equal(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "bbbb")
    assert_equal(local.get_content('/Folder 3/File 6.txt'), "ffff")
    assert_equal(remote_client.get_content('/Folder 1/File 1.txt'),
                 "aaaa")
    assert_equal(remote_client.get_content('/Folder 1/Folder 1.1/File 2.txt'),
                 "bbbb")
    assert_equal(remote_client.get_content('/Folder 3/File 6.txt'),
                 "ffff")

    # Rescan: no change to detect we should reach a fixpoint
    syn.scan_local(expected_folder, session)
    syn.scan_remote(expected_folder, session)
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/Folder 1', 'synchronized'),
        (u'/Folder 3', 'synchronized'),
        (u'/Folder 4', 'synchronized'),
    ])

    # Send some binary data that is not valid in utf-8 or ascii (to test the
    # HTTP / Multipart transform layer).
    time.sleep(1.0)
    local.update_content('/Folder 1/File 1.txt', "\x80")
    remote_client.update_content('/Folder 1/Folder 1.1/File 2.txt', '\x80')
    syn.scan_local(expected_folder, session)
    syn.scan_remote(expected_folder, session)
    assert_equal(syn.synchronize(limit=100), 2)
    assert_equal(remote_client.get_content('/Folder 1/File 1.txt'), "\x80")
    assert_equal(local.get_content('/Folder 1/Folder 1.1/File 2.txt'), "\x80")


@with_integration_env
def test_synchronization_modification_on_created_file():
    # Regression test: a file is created locally, then modification is detected
    # before first upload
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)
    syn = ctl.synchronizer
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)
    assert_equal(ctl.list_pending(), [])

    # Let's create some document on the client and the server
    local = LocalClient(expected_folder)
    local.make_folder('/', 'Folder')
    local.make_file('/Folder', 'File.txt', content='Some content.')

    # First local scan (assuming the network is offline):
    syn.scan_local(expected_folder)
    assert_equal(len(ctl.list_pending()), 2)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/Folder', 'children_modified'),
    ])
    assert_equal(ctl.children_states(expected_folder + '/Folder'), [
        (u'/Folder/File.txt', u'unknown'),
    ])

    # Wait a bit for file time stamps to increase enough: on most OS the file
    # modification time resolution is 1s
    time.sleep(1.0)

    # Let's modify it offline and rescan locally
    local.update_content('/Folder/File.txt', content='Some content.')
    syn.scan_local(expected_folder)
    assert_equal(len(ctl.list_pending()), 2)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/Folder', u'children_modified'),
    ])
    assert_equal(ctl.children_states(expected_folder + '/Folder'), [
        (u'/Folder/File.txt', u'locally_modified'),
    ])

    # Assume the computer is back online, the synchronization should occur as if
    # the document was just created and not trigger an update
    syn.loop(full_local_scan=True, full_remote_scan=True, delay=0.010,
             max_loops=1, fault_tolerant=False)
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/Folder', u'synchronized'),
    ])
    assert_equal(ctl.children_states(expected_folder + '/Folder'), [
        (u'/Folder/File.txt', u'synchronized'),
    ])


@with_integration_env
def test_synchronization_loop():
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)
    syn = ctl.synchronizer
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)

    assert_equal(ctl.list_pending(), [])
    assert_equal(syn.synchronize(), 0)

    # Let's create some document on the client and the server
    local = LocalClient(expected_folder)
    local.make_folder('/', 'Folder 3')
    make_server_tree()

    # Run the full synchronization loop a limited amount of times
    syn.loop(full_local_scan=True, full_remote_scan=True, delay=0.010,
             max_loops=3, fault_tolerant=False)

    # All is synchronized
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/File 5.txt', u'synchronized'),
        (u'/Folder 1', u'synchronized'),
        (u'/Folder 2', u'synchronized'),
        (u'/Folder 3', u'synchronized'),
    ])


@with_integration_env
def test_synchronization_offline():
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)
    syn = ctl.synchronizer
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)

    assert_equal(ctl.list_pending(), [])
    assert_equal(syn.synchronize(), 0)

    # Let's create some document on the client and the server
    local = LocalClient(expected_folder)
    local.make_folder('/', 'Folder 3')
    make_server_tree()

    # Find various ways to similate network or server failure
    errors = [
        urllib2.URLError('Test error'),
        socket.error('Test error'),
        httplib.HTTPException('Test error'),
    ]
    for error in errors:
        ctl.make_remote_raise(error)
        # Synchronization does not occur but does not fail either
        syn.loop(full_local_scan=True, full_remote_scan=True, delay=0,
                 max_loops=1, fault_tolerant=False)
        # Only the local change has been detected
        assert_equal(len(ctl.list_pending()), 1)

    # Reenable network
    ctl.make_remote_raise(None)
    syn.loop(full_local_scan=True, full_remote_scan=True, delay=0,
             max_loops=1, fault_tolerant=False)

    # All is synchronized
    assert_equal(len(ctl.list_pending()), 0)
    assert_equal(ctl.children_states(expected_folder), [
        (u'/File 5.txt', u'synchronized'),
        (u'/Folder 1', u'synchronized'),
        (u'/Folder 2', u'synchronized'),
        (u'/Folder 3', u'synchronized'),
    ])
