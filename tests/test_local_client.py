# coding: utf-8
"""
Test LocalClient with native FS operations and specific OS ones.
See win_local_client.py and mac_local_client.py for more informations.

See NXDRIVE-742.
"""
import hashlib
import os
import sys
from time import sleep

import pytest

from nxdrive.client import LocalClient, NotFound
from nxdrive.client.common import DuplicationDisabledError
from .common import UnitTestCase

if sys.platform == 'win32':
    import win32api


EMPTY_DIGEST = hashlib.md5().hexdigest()
SOME_TEXT_CONTENT = b'Some text content.'
SOME_TEXT_DIGEST = hashlib.md5(SOME_TEXT_CONTENT).hexdigest()


class StubLocalClient(object):
    """
    All tests goes here. If you need to implement a special behavior for
    one OS, override the test method in the class TestLocalClientSimulation.
    Check TestLocalClientSimulation.test_complex_filenames() for a real
    world example.
    """

    def test_make_documents(self):
        local = self.local_1
        doc_1 = local.make_file('/', 'Document 1.txt')
        assert local.exists(doc_1)
        assert not local.get_content(doc_1)
        doc_1_info = local.get_info(doc_1)
        assert doc_1_info.name == 'Document 1.txt'
        assert doc_1_info.path == doc_1
        assert doc_1_info.get_digest() == EMPTY_DIGEST
        assert not doc_1_info.folderish

        doc_2 = local.make_file(
            '/', 'Document 2.txt', content=SOME_TEXT_CONTENT)
        assert local.exists(doc_2)
        assert local.get_content(doc_2) ==  SOME_TEXT_CONTENT
        doc_2_info = local.get_info(doc_2)
        assert doc_2_info.name == 'Document 2.txt'
        assert doc_2_info.path == doc_2
        assert doc_2_info.get_digest() == SOME_TEXT_DIGEST
        assert not doc_2_info.folderish

        local.delete(doc_2)
        assert local.exists(doc_1)
        assert not local.exists(doc_2)

        folder_1 = local.make_folder('/', 'A new folder')
        assert local.exists(folder_1)
        folder_1_info = local.get_info(folder_1)
        assert folder_1_info.name == 'A new folder'
        assert folder_1_info.path == folder_1
        assert not folder_1_info.get_digest()
        assert folder_1_info.folderish

        doc_3 = local.make_file(
            folder_1, 'Document 3.txt', content=SOME_TEXT_CONTENT)
        local.delete(folder_1)
        assert not local.exists(folder_1)
        assert not local.exists(doc_3)

    def test_get_info_invalid_date(self):
        local = self.local_1
        doc_1 = local.make_file('/', 'Document 1.txt')
        os.utime(local.abspath(
                os.path.join('/', 'Document 1.txt')), (0, 999999999999999))
        doc_1_info = local.get_info(doc_1)
        assert doc_1_info.name == 'Document 1.txt'
        assert doc_1_info.path == doc_1
        assert doc_1_info.get_digest() == EMPTY_DIGEST
        assert not doc_1_info.folderish

    def test_complex_filenames(self):
        local = self.local_1
        # create another folder with the same title
        title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"

        folder_1 = local.make_folder('/', title_with_accents)
        folder_1_info = local.get_info(folder_1)
        assert folder_1_info.name == title_with_accents

        # create another folder with the same title
        with pytest.raises(DuplicationDisabledError):
            local.make_folder('/', title_with_accents)

        # Create a long file name with weird chars
        long_filename = u"\xe9" * 50 + u"%$#!()[]{}+_-=';&^" + u".doc"
        file_1 = local.make_file(folder_1, long_filename)
        file_1 = local.get_info(file_1)
        assert file_1.name == long_filename
        assert file_1.path == folder_1_info.path + u"/" + long_filename

        # Create a file with invalid chars
        invalid_filename = u"a/b\\c*d:e<f>g?h\"i|j.doc"
        escaped_filename = u"a-b-c-d-e-f-g-h-i-j.doc"
        file_2 = local.make_file(folder_1, invalid_filename)
        file_2 = local.get_info(file_2)
        assert file_2.name == escaped_filename
        assert file_2.path == folder_1_info.path + u'/' + escaped_filename

    @pytest.mark.xfail(True, raises=NotFound, reason='Must fail.')
    def test_missing_file(self):
        local = self.local_1
        local.get_info('/Something Missing')

    @pytest.mark.timeout(30)
    def test_case_sensitivity(self):
        local = self.local_1
        sensitive = local.is_case_sensitive()

        local.make_file('/', 'abc.txt')
        if sensitive:
            local.make_file('/', 'ABC.txt')
        else:
            with pytest.raises(DuplicationDisabledError):
                local.make_file('/', 'ABC.txt')
        assert len(local.get_children_info('/')) == sensitive + 1

    @pytest.mark.skipif(sys.platform != 'win32', reason='Windows only.')
    def test_windows_short_names(self):
        """
        Test 8.3 file name convention:
        https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247(v=vs.85).aspx
        """

        local = self.local_1
        remote = self.remote_document_client_1
        long_name = 'a' * 32
        short_name = 'AAAAAA~1'

        # Create the folder
        folder = local.make_file('/', long_name)
        with pytest.raises(DuplicationDisabledError):
            local.make_file('/', short_name)
        path = local.abspath(folder)
        assert os.path.basename(path) == long_name

        # Get the short name
        short = win32api.GetShortPathName(path)
        assert os.path.basename(short) == short_name

        # Sync and check the short name is nowhere
        self.wait_sync()
        children = remote.get_children_info(self.workspace)
        assert len(children) == 1
        assert children[0].name == long_name

    def test_get_children_info(self):
        local = self.local_1
        folder_1 = local.make_folder('/', 'Folder 1')
        folder_2 = local.make_folder('/', 'Folder 2')
        file_1 = local.make_file(
            '/', 'File 1.txt', content=b'foo\n')

        # not a direct child of '/'
        local.make_file(folder_1, 'File 2.txt', content=b'bar\n')

        # ignored files
        data = b'baz\n'
        local.make_file('/', '.File 2.txt', content=data)
        local.make_file('/', '~$File 2.txt', content=data)
        local.make_file('/', 'File 2.txt~', content=data)
        local.make_file('/', 'File 2.txt.swp', content=data)
        local.make_file('/', 'File 2.txt.lock', content=data)
        local.make_file('/', 'File 2.txt.part', content=data)
        local.make_file('/', '.File 2.txt.nxpart', content=data)
        if local.is_case_sensitive():
            local.make_file('/', 'File 2.txt.LOCK', content=data)
        else:
            with pytest.raises(DuplicationDisabledError):
                local.make_file(
                    '/', 'File 2.txt.LOCK', content=data)

        workspace_children = local.get_children_info('/')
        assert len(workspace_children) == 3
        assert workspace_children[0].path == file_1
        assert workspace_children[1].path == folder_1
        assert workspace_children[2].path == folder_2

    def test_deep_folders(self):
        # Check that local client can workaround the default Windows
        # MAX_PATH limit
        local = self.local_1
        folder = '/'
        for _i in range(30):
            folder = local.make_folder(folder, '0123456789')

        # Last Level
        last_level_folder_info = local.get_info(folder)
        assert last_level_folder_info.path == '/0123456789' * 30

        # Create a nested file
        deep_file = local.make_file(
            folder, 'File.txt', content=b'Some Content.')

        # Check the consistency of get_children_info and get_info
        deep_file_info = local.get_info(deep_file)
        deep_children = local.get_children_info(folder)
        assert len(deep_children) == 1
        deep_child_info = deep_children[0]
        assert deep_file_info.name == deep_child_info.name
        assert deep_file_info.path == deep_child_info.path
        assert deep_file_info.get_digest() == deep_child_info.get_digest()

        # Update the file content
        local.update_content(deep_file, b'New Content.')
        assert local.get_content(deep_file) == b'New Content.'

        # Delete the folder
        local.delete(folder)
        assert not local.exists(folder)
        assert not local.exists(deep_file)

        # Delete the root folder and descendants
        local.delete('/0123456789')
        assert not local.exists('/0123456789')

    def test_get_new_file(self):
        local = self.local_1
        path, os_path, name = local.get_new_file(
            '/', 'Document 1.txt')
        assert path == '/Document 1.txt'
        assert os_path.endswith(os.path.join(self.workspace_title,
                                             'Document 1.txt'))
        assert name == 'Document 1.txt'
        assert not local.exists(path)
        assert not os.path.exists(os_path)

    def test_xattr(self):
        local = self.local_1
        ref = local.make_file('/', 'File 2.txt',
                                            content=b'baz\n')
        path = local.abspath(ref)
        mtime = int(os.path.getmtime(path))
        sleep(1)
        local.set_remote_id(ref, 'TEST')
        assert mtime == int(os.path.getmtime(path))
        sleep(1)
        local.remove_remote_id(ref)
        assert mtime == int(os.path.getmtime(path))

    def test_get_path(self):
        local = self.local_1
        doc = 'doc.txt'
        abs_path = os.path.join(
            self.local_nxdrive_folder_1, self.workspace_title, doc)
        assert local.get_path(abs_path) == '/' + doc

        # Encoding test
        assert local.get_path('été.txt') == '/'

    def test_is_equal_digests(self):
        local = self.local_1
        content = b'joe'
        local_path = local.make_file('/', 'File.txt',
                                                   content=content)
        local_digest = hashlib.md5(content).hexdigest()
        # Equal digests
        assert local.is_equal_digests(
            local_digest, local_digest, local_path)

        # Different digests with same digest algorithm
        other_content = b'jack'
        remote_digest = hashlib.md5(other_content).hexdigest()
        assert local_digest != remote_digest
        assert not local.is_equal_digests(
            local_digest, remote_digest, local_path)

        # Different digests with different digest algorithms but same content
        remote_digest = hashlib.sha1(content).hexdigest()
        assert local_digest != remote_digest
        assert local.is_equal_digests(
            local_digest, remote_digest, local_path)

        # Different digests with different digest algorithms and different
        # content
        remote_digest = hashlib.sha1(other_content).hexdigest()
        assert local_digest != remote_digest
        assert not local.is_equal_digests(
            local_digest, remote_digest, local_path)


class TestLocalClientNative(StubLocalClient, UnitTestCase):
    """
    Test LocalClient using native python commands to make FS operations.
    This will simulate Drive actions.
    """

    def setUp(self):
        self.engine_1.start()
        self.wait_sync()

    def get_local_client(self, path):
        return LocalClient(path)

    @pytest.mark.xfail(
        sys.platform == 'win32', raises=OSError,
        reason='Explorer cannot deal with very long paths')
    def test_deep_folders(self):
        """
        It should fail on Windows:
            WindowsError: [Error 206] The filename or extension is too long
        Explorer cannot deal with very long paths.
        """

        super(TestLocalClientNative, self).test_deep_folders()

    def test_remote_changing_case_accentued_folder(self):
        """
        NXDRIVE-1061: Remote rename of an accentued folder on Windows fails.
        I put this test only here because we need to test native
        LocalClient.rename().
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Step 1: remotely create an accentued folder
        root = remote.make_folder('/', u'Projet Hémodialyse')
        folder = remote.make_folder(root, u'Pièces graphiques')

        self.wait_sync(wait_for_async=True)
        assert local.exists(u'/Projet Hémodialyse')
        assert local.exists(u'/Projet Hémodialyse/Pièces graphiques')

        # Step 2: remotely change the case of the subfolder
        remote.update(folder, properties={'dc:title': u'Pièces Graphiques'})

        self.wait_sync(wait_for_async=True)
        children = local.get_children_info(u'/Projet Hémodialyse')
        assert len(children) == 1
        assert children[0].name == u'Pièces Graphiques'


@pytest.mark.skipif(
    sys.platform == 'linux2', reason='GNU/Linux uses native LocalClient.')
class TestLocalClientSimulation(StubLocalClient, UnitTestCase):
    """
    Test LocalClient using OS-specific commands to make FS operations.
    This will simulate user actions on:
        - Explorer (Windows)
        - File Manager (macOS)
    """

    def setUp(self):
        self.engine_1.start()
        self.wait_sync()

    @pytest.mark.xfail(
        sys.platform == 'win32', raises=IOError,
        reason='Explorer cannot find the directory as the path is way to long')
    def test_complex_filenames(self):
        """
        It should fail on Windows: IOError: [Errno 2] No such file or directory
        Explorer cannot find the directory as the path is way to long.
        """

        super(TestLocalClientSimulation, self).test_complex_filenames()

    @pytest.mark.xfail(
        sys.platform == 'win32', raises=OSError,
        reason='Explorer cannot deal with very long paths')
    def test_deep_folders(self):
        """
        It should fail on Windows:
            WindowsError: [Error 206] The filename or extension is too long
        Explorer cannot deal with very long paths.
        """

        super(TestLocalClientSimulation, self).test_deep_folders()
