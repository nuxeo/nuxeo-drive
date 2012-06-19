import os
import hashlib
from nose import with_setup
from nose import SkipTest
from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_equal
from nose.tools import assert_not_equal
from nose.tools import assert_raises

from nxdrive.client import NuxeoClient
from nxdrive.client import Unauthorized
from nxdrive.client import NotFound


TEST_WORKSPACE = '/default-domain/workspaces/test-nxdrive'

EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = "Some text content."
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()


nxclient = None


def setup_integration_server():
    global nxclient
    NUXEO_URL = os.environ.get('NXDRIVE_TEST_NUXEO_URL')
    USER = os.environ.get('NXDRIVE_TEST_USER')
    PASSWORD = os.environ.get('NXDRIVE_TEST_PASSWORD')
    if None in (NUXEO_URL, USER, PASSWORD):
        raise SkipTest("No integration server configuration found in "
                       "environment.")
    nxclient = NuxeoClient(NUXEO_URL, USER, PASSWORD)

    parent_path = os.path.dirname(TEST_WORKSPACE)
    workspace_name = os.path.basename(TEST_WORKSPACE)
    nxclient.create(parent_path, 'Workspace', name=workspace_name,
                    properties={'dc:title': 'Nuxeo Drive Tests'})


def teardown_integration_server():
    if nxclient is not None and nxclient.exists(TEST_WORKSPACE):
        nxclient.delete(TEST_WORKSPACE)


with_integration_server = with_setup(
    setup_integration_server, teardown_integration_server)


@with_integration_server
def test_authentication_failure():
    assert_raises(
        Unauthorized,
        NuxeoClient, nxclient.server_url, 'someone else', 'bad password')


@with_integration_server
def test_make_documents():
    doc_1 = nxclient.make_file(TEST_WORKSPACE, 'Document 1.txt')
    assert_true(nxclient.exists(doc_1))
    assert_equal(nxclient.get_content(doc_1), "")
    doc_1_info = nxclient.get_info(doc_1)
    assert_equal(doc_1_info.name, 'Document 1.txt')
    assert_equal(doc_1_info.uid, doc_1)
    assert_equal(doc_1_info.get_digest(), EMPTY_DIGEST)
    assert_equal(doc_1_info.folderish, False)

    doc_2 = nxclient.make_file(TEST_WORKSPACE, 'Document 2.txt',
                              content=SOME_TEXT_CONTENT)
    assert_true(nxclient.exists(doc_2))
    assert_equal(nxclient.get_content(doc_2), SOME_TEXT_CONTENT)
    doc_2_info = nxclient.get_info(doc_2)
    assert_equal(doc_2_info.name, 'Document 2.txt')
    assert_equal(doc_2_info.uid, doc_2)
    assert_equal(doc_2_info.get_digest(), SOME_TEXT_DIGEST)
    assert_equal(doc_2_info.folderish, False)

    nxclient.delete(doc_2)
    assert_true(nxclient.exists(doc_1))
    assert_false(nxclient.exists(doc_2))

    folder_1 = nxclient.make_folder(TEST_WORKSPACE, 'A new folder')
    assert_true(nxclient.exists(folder_1))
    folder_1_info = nxclient.get_info(folder_1)
    assert_equal(folder_1_info.name, 'A new folder')
    assert_equal(folder_1_info.uid, folder_1)
    assert_equal(folder_1_info.get_digest(), None)
    assert_equal(folder_1_info.folderish, True)

    doc_3 = nxclient.make_file(folder_1, 'Document 3.txt',
                               content=SOME_TEXT_CONTENT)
    nxclient.delete(folder_1)
    assert_false(nxclient.exists(folder_1))
    assert_false(nxclient.exists(doc_3))


@with_integration_server
def test_complex_filenames():
    # create another folder with the same title
    title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
    folder_1 = nxclient.make_folder(TEST_WORKSPACE, title_with_accents)
    folder_1_info = nxclient.get_info(folder_1)
    assert_equal(folder_1_info.name, title_with_accents)

    # create another folder with the same title
    title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
    folder_2 = nxclient.make_folder(TEST_WORKSPACE, title_with_accents)
    folder_2_info = nxclient.get_info(folder_2)
    assert_equal(folder_2_info.name, title_with_accents)
    assert_not_equal(folder_1, folder_2)

    # Create a file
    # TODO: handle sanitization of the '/' character in local name
    long_filename = u"\xe9" * 50 + u"%$#!*()[]{}+_-=';:&^" + ".doc"
    file_1 = nxclient.make_file(folder_1, long_filename)
    file_1 = nxclient.get_info(file_1)
    assert_equal(file_1.name, long_filename)


@with_integration_server
def test_missing_document():
    assert_raises(NotFound, nxclient.get_info, '/Something Missing')
