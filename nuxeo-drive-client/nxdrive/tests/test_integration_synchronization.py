import os
import hashlib
import shutil
import tempfile
from nose import with_setup
from nose import SkipTest
from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_equal
from nose.tools import assert_not_equal
from nose.tools import assert_raises

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

lcclient = None
nxclient = None


def setup_integration_env():
    global NUXEO_URL, USER, PASSWORD
    global nxclient, lcclient, TEST_WORKSPACE, LOCAL_TEST_FOLDER
    global LOCAL_NXDRIVE_FOLDER, LOCAL_NXDRIVE_CONF_FOLDER

    # Check the Nuxeo server test environment
    NUXEO_URL = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
    USER = os.environ.get('NXDRIVE_TEST_USER')
    PASSWORD = os.environ.get('NXDRIVE_TEST_PASSWORD')
    if None in (NUXEO_URL, USER, PASSWORD):
        raise SkipTest("No integration server configuration found in "
                       "environment.")

    parent_path = os.path.dirname(TEST_WORKSPACE_PATH)
    workspace_name = os.path.basename(TEST_WORKSPACE_PATH)
    root_nxclient = NuxeoClient(NUXEO_URL, USER, PASSWORD)
    TEST_WORKSPACE = root_nxclient.create(
        parent_path, 'Workspace', name=workspace_name,
        properties={'dc:title': TEST_WORKSPACE_TITLE})[u'uid']

    # Client to be use to create remote test documents and folders
    nxclient = NuxeoClient(NUXEO_URL, USER, PASSWORD,
                           base_folder=TEST_WORKSPACE)

    # Check the local filesystem test environment
    LOCAL_TEST_FOLDER = tempfile.mkdtemp('-nuxeo-drive-tests')

    LOCAL_NXDRIVE_FOLDER = os.path.join(
        LOCAL_TEST_FOLDER, 'Nuxeo Drive')
    os.mkdir(LOCAL_NXDRIVE_FOLDER)

    LOCAL_NXDRIVE_CONF_FOLDER = os.path.join(
        LOCAL_TEST_FOLDER, 'nuxeo-drive-conf')
    os.mkdir(LOCAL_NXDRIVE_CONF_FOLDER)

    # Local client to use to create local test files and folders
    lcclient = LocalClient(LOCAL_NXDRIVE_CONF_FOLDER)


def teardown_integration_env():
    if nxclient is not None and nxclient.exists(TEST_WORKSPACE):
        nxclient.delete(TEST_WORKSPACE)

    if os.path.exists(LOCAL_TEST_FOLDER):
        shutil.rmtree(LOCAL_TEST_FOLDER)


with_integration_env = with_setup(
    setup_integration_env, teardown_integration_env)


def make_server_tree():
    # create some folders on the server
    folder_1 = nxclient.make_folder(TEST_WORKSPACE, 'Folder 1')
    folder_1_1 = nxclient.make_folder(folder_1, 'Folder 1.1')
    folder_1_2 = nxclient.make_folder(folder_1, 'Folder 1.2')
    folder_2 = nxclient.make_folder(TEST_WORKSPACE, 'Folder 2')

    # create some files on the server
    nxclient.make_file(folder_2, 'Duplicated File.txt',
                               content="Some content.")
    nxclient.make_file(folder_2, 'Duplicated File.txt',
                               content="Other content.")

    nxclient.make_file(folder_1, 'File 1.doc', content="aaa")
    nxclient.make_file(folder_1_1, 'File 2.doc', content="bbb")
    nxclient.make_file(folder_1_2, 'File 3.doc', content="ccc")
    nxclient.make_file(folder_2, 'File 4.doc', content="ddd")
    nxclient.make_file(TEST_WORKSPACE, 'File 5.doc', content="eee")


@with_integration_env
def test_binding_initialization():
    # Create some documents in a Nuxeo workspace and bind this server to a
    # Nuxeo Drive local folder
    make_server_tree()
    ctl = Controller(LOCAL_NXDRIVE_CONF_FOLDER)
    ctl.bind_server(LOCAL_NXDRIVE_FOLDER, NUXEO_URL, USER, PASSWORD)
    ctl.bind_root(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE)

    # The binding operation creates a new local folder with the Workspace name
    # and reproduce the server side structure with folders and empty documents.
    expected_folder = os.path.join(LOCAL_NXDRIVE_FOLDER, TEST_WORKSPACE_TITLE)
    local = LocalClient(expected_folder)
    level_0 = local.get_children_info('/')

    def size(info):
        return os.stat(info.filepath).st_size

    assert_equal(len(level_0), 3)
    assert_equal(level_0[0].name, 'File 5.doc')
    assert_equal(size(level_0[0]), 0)
    assert_equal(level_0[1].name, 'Folder 1')
    assert_equal(level_0[2].name, 'Folder 2')

    level_1 = local.get_children_info(level_0[1].path)
    assert_equal(len(level_1), 3)
    assert_equal(level_1[0].name, 'File 1.doc')
    assert_equal(size(level_1[0]), 0)
    assert_equal(level_1[1].name, 'Folder 1.1')
    assert_equal(level_1[2].name, 'Folder 1.2')

    level_2 = local.get_children_info(level_0[2].path)
    assert_equal(len(level_2), 3)
    assert_equal(level_2[0].name, 'Duplicated File.txt')
    assert_equal(size(level_2[0]), 0)
    assert_equal(level_2[1].name, 'Duplicated File__1.txt')  # deduped name
    assert_equal(size(level_2[1]), 0)
    assert_equal(level_2[2].name, 'File 4.doc')
    assert_equal(size(level_2[2]), 0)

    # Check the aggregate states information from the controller
    states = ctl.children_states(expected_folder)
    expected_states = [
        (u'/File 5.doc', 'remotely_modified'),
        (u'/Folder 1', 'children_modified'),
        (u'/Folder 2', 'children_modified'),
    ]
    assert_equal(states, expected_states)

    states = ctl.children_states(expected_folder + '/Folder 1')
    expected_states = [
        (u'/Folder 1/File 1.doc', 'remotely_modified'),
        (u'/Folder 1/Folder 1.1', 'children_modified'),
        (u'/Folder 1/Folder 1.2', 'children_modified'),
    ]
    assert_equal(states, expected_states)

    states = ctl.children_states(expected_folder + '/Folder 1/Folder 1.1')
    expected_states = [
        (u'/Folder 1/Folder 1.1/File 2.doc', 'remotely_modified'),
    ]
    assert_equal(states, expected_states)

    # Check the list of files and folders with synchronization pending
    pending = ctl.list_pending()
    assert_equal(len(pending), 7)
    assert_equal(pending[0].path, '/File 5.doc')
    assert_equal(pending[1].path, '/Folder 1/File 1.doc')
    assert_equal(pending[2].path, '/Folder 1/Folder 1.1/File 2.doc')
    assert_equal(pending[3].path, '/Folder 1/Folder 1.2/File 3.doc')
    assert_equal(pending[4].path, '/Folder 2/Duplicated File.txt')
    assert_equal(pending[5].path, '/Folder 2/Duplicated File__1.txt')
    assert_equal(pending[6].path, '/Folder 2/File 4.doc')

    # It is also possible to restrict the number of pending tasks
    pending = ctl.list_pending(limit=2)
    assert_equal(len(pending), 2)
