import os
import tempfile
import hashlib
from nose import with_setup
from nose.tools import assert_true
from nose.tools import assert_false
from nose.tools import assert_equal
from nose.tools import assert_not_equal
from nose.tools import assert_raises

from nxdrive.client import LocalClient
from nxdrive.client import NotFound
from nxdrive.tests.common import EMPTY_DIGEST
from nxdrive.tests.common import SOME_TEXT_CONTENT
from nxdrive.tests.common import SOME_TEXT_DIGEST
from nxdrive.tests.common import clean_dir


LOCAL_TEST_FOLDER = None
TEST_WORKSPACE = None
lcclient = None


def setup_temp_folder():
    global lcclient, LOCAL_TEST_FOLDER, TEST_WORKSPACE
    build_workspace = os.environ.get('WORKSPACE')
    tmpdir = None
    if build_workspace is not None:
        tmpdir = os.path.join(build_workspace, "tmp")
        if not os.path.isdir(tmpdir):
            os.makedirs(tmpdir)
    LOCAL_TEST_FOLDER = tempfile.mkdtemp(u'-nuxeo-drive-tests', dir=tmpdir)
    lcclient = LocalClient(LOCAL_TEST_FOLDER)
    TEST_WORKSPACE = lcclient.make_folder(u'/', u'Some Workspace')


def teardown_temp_folder():
    clean_dir(LOCAL_TEST_FOLDER)


with_temp_folder = with_setup(setup_temp_folder, teardown_temp_folder)


@with_temp_folder
def test_make_documents():
    doc_1 = lcclient.make_file(TEST_WORKSPACE, u'Document 1.txt')
    assert_true(lcclient.exists(doc_1))
    assert_equal(lcclient.get_content(doc_1), b"")
    doc_1_info = lcclient.get_info(doc_1)
    assert_equal(doc_1_info.name, u'Document 1.txt')
    assert_equal(doc_1_info.path, doc_1)
    assert_equal(doc_1_info.get_digest(), EMPTY_DIGEST)
    assert_equal(doc_1_info.folderish, False)

    doc_2 = lcclient.make_file(TEST_WORKSPACE, u'Document 2.txt',
                              content=SOME_TEXT_CONTENT)
    assert_true(lcclient.exists(doc_2))
    assert_equal(lcclient.get_content(doc_2), SOME_TEXT_CONTENT)
    doc_2_info = lcclient.get_info(doc_2)
    assert_equal(doc_2_info.name, u'Document 2.txt')
    assert_equal(doc_2_info.path, doc_2)
    assert_equal(doc_2_info.get_digest(), SOME_TEXT_DIGEST)
    assert_equal(doc_2_info.folderish, False)

    lcclient.delete(doc_2)
    assert_true(lcclient.exists(doc_1))
    assert_false(lcclient.exists(doc_2))

    folder_1 = lcclient.make_folder(TEST_WORKSPACE, u'A new folder')
    assert_true(lcclient.exists(folder_1))
    folder_1_info = lcclient.get_info(folder_1)
    assert_equal(folder_1_info.name, u'A new folder')
    assert_equal(folder_1_info.path, folder_1)
    assert_equal(folder_1_info.get_digest(), None)
    assert_equal(folder_1_info.folderish, True)

    doc_3 = lcclient.make_file(folder_1, u'Document 3.txt',
                               content=SOME_TEXT_CONTENT)
    lcclient.delete(folder_1)
    assert_false(lcclient.exists(folder_1))
    assert_false(lcclient.exists(doc_3))


@with_temp_folder
def test_complex_filenames():
    # create another folder with the same title
    title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
    folder_1 = lcclient.make_folder(TEST_WORKSPACE, title_with_accents)
    folder_1_info = lcclient.get_info(folder_1)
    assert_equal(folder_1_info.name, title_with_accents)

    # create another folder with the same title
    title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
    folder_2 = lcclient.make_folder(TEST_WORKSPACE, title_with_accents)
    folder_2_info = lcclient.get_info(folder_2)
    assert_equal(folder_2_info.name, title_with_accents + u"__1")
    assert_not_equal(folder_1, folder_2)

    title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
    folder_3 = lcclient.make_folder(TEST_WORKSPACE, title_with_accents)
    folder_3_info = lcclient.get_info(folder_3)
    assert_equal(folder_3_info.name, title_with_accents + u"__2")
    assert_not_equal(folder_1, folder_3)

    # Create a long file name with weird chars
    long_filename = u"\xe9" * 50 + u"%$#!()[]{}+_-=';&^" + u".doc"
    file_1 = lcclient.make_file(folder_1, long_filename)
    file_1 = lcclient.get_info(file_1)
    assert_equal(file_1.name, long_filename)
    assert_equal(file_1.path, folder_1_info.path + u"/" + long_filename)

    # Create a file with invalid chars
    invalid_filename = u"a/b\\c*d:e<f>g?h\"i|j.doc"
    escaped_filename = u"a-b-c-d-e-f-g-h-i-j.doc"
    file_2 = lcclient.make_file(folder_1, invalid_filename)
    file_2 = lcclient.get_info(file_2)
    assert_equal(file_2.name, escaped_filename)
    assert_equal(file_2.path, folder_1_info.path + u'/' + escaped_filename)


@with_temp_folder
def test_missing_file():
    assert_raises(NotFound, lcclient.get_info, u'/Something Missing')


@with_temp_folder
def test_get_children_info():
    folder_1 = lcclient.make_folder(TEST_WORKSPACE, u'Folder 1')
    folder_2 = lcclient.make_folder(TEST_WORKSPACE, u'Folder 2')
    file_1 = lcclient.make_file(TEST_WORKSPACE, u'File 1.txt',
                                content=b"foo\n")

    # not a direct child of TEST_WORKSPACE
    lcclient.make_file(folder_1, u'File 2.txt', content=b"bar\n")

    # ignored files
    lcclient.make_file(TEST_WORKSPACE, u'.File 2.txt', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'~$File 2.txt', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'File 2.txt~', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'File 2.txt.swp', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'File 2.txt.lock', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'File 2.txt.LOCK', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'File 2.txt.part', content=b"baz\n")
    lcclient.make_file(TEST_WORKSPACE, u'.File 2.txt.nxpart', content=b"baz\n")

    workspace_children = lcclient.get_children_info(TEST_WORKSPACE)
    assert_equal(len(workspace_children), 3)
    assert_equal(workspace_children[0].path, file_1)
    assert_equal(workspace_children[1].path, folder_1)
    assert_equal(workspace_children[2].path, folder_2)


@with_temp_folder
def test_deep_folders():
    # Check that local client can workaround the default windows MAX_PATH limit
    folder = '/'
    for _i in range(30):
        folder = lcclient.make_folder(folder, u'0123456789')

    # Last Level
    last_level_folder_info = lcclient.get_info(folder)
    assert_equal(last_level_folder_info.path, u'/0123456789' * 30)

    # Create a nested file
    deep_file = lcclient.make_file(folder, u'File.txt',
        content=b"Some Content.")

    # Check the consistency of  get_children_info and get_info
    deep_file_info = lcclient.get_info(deep_file)
    deep_children = lcclient.get_children_info(folder)
    assert_equal(len(deep_children), 1)
    deep_child_info = deep_children[0]
    assert_equal(deep_file_info.name, deep_child_info.name)
    assert_equal(deep_file_info.path, deep_child_info.path)
    assert_equal(deep_file_info.get_digest(), deep_child_info.get_digest())

    # Update the file content
    lcclient.update_content(deep_file, b"New Content.")
    assert_equal(lcclient.get_content(deep_file), b"New Content.")

    # Delete the folder
    lcclient.delete(folder)
    assert_false(lcclient.exists(folder))
    assert_false(lcclient.exists(deep_file))

    # Delete the root folder and descendants
    lcclient.delete(u'/0123456789')
    assert_false(lcclient.exists(u'/0123456789'))


@with_temp_folder
def test_get_new_file():
    path, os_path, name = lcclient.get_new_file(TEST_WORKSPACE,
                                                u'Document 1.txt')
    assert_equal(path, '/Some Workspace/Document 1.txt')
    assert_true(os_path.endswith(
                    os.path.join('-nuxeo-drive-tests', 'Some Workspace',
                        'Document 1.txt')))
    assert_equal(name, 'Document 1.txt')
    assert_false(lcclient.exists(path))
    assert_false(os.path.exists(os_path))


@with_temp_folder
def test_xattr():
    ref = lcclient.make_file(TEST_WORKSPACE, u'File 2.txt', content=b"baz\n")
    path = lcclient._abspath(ref)
    mtime = int(os.path.getmtime(path))
    from time import sleep
    sleep(1)
    lcclient.set_remote_id(ref, 'TEST')
    assert_true(mtime == int(os.path.getmtime(path)))
    sleep(1)
    lcclient.remove_remote_id(ref)
    assert_true(mtime == int(os.path.getmtime(path)))


@with_temp_folder
def test_get_path():
    abs_path = os.path.join(
                        LOCAL_TEST_FOLDER, 'Some Workspace', 'Test doc.txt')
    assert_equal(lcclient.get_path(abs_path), '/Some Workspace/Test doc.txt')


@with_temp_folder
def test_is_equal_digests():
    content = b"joe"
    local_path = lcclient.make_file(TEST_WORKSPACE, u'File.txt', content=content)
    local_digest = hashlib.md5(content).hexdigest()
    # Equal digests
    assert_true(lcclient.is_equal_digests(local_digest, local_digest, local_path))
    # Different digests with same digest algorithm
    other_content = b"jack"
    remote_digest = hashlib.md5(other_content).hexdigest()
    assert_not_equal(local_digest, remote_digest)
    assert_false(lcclient.is_equal_digests(local_digest, remote_digest, local_path))
    # Different digests with different digest algorithms but same content
    remote_digest = hashlib.sha1(content).hexdigest()
    assert_not_equal(local_digest, remote_digest)
    assert_true(lcclient.is_equal_digests(local_digest, remote_digest, local_path))
    # Different digests with different digest algorithms and different content
    remote_digest = hashlib.sha1(other_content).hexdigest()
    assert_not_equal(local_digest, remote_digest)
    assert_false(lcclient.is_equal_digests(local_digest, remote_digest, local_path))
