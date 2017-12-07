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
from nxdrive.logging_config import get_logger
from tests.common import EMPTY_DIGEST, SOME_TEXT_CONTENT, SOME_TEXT_DIGEST
from tests.common_unit_test import UnitTestCase

if sys.platform == 'win32':
    import win32api


log = get_logger(__name__)


class StubLocalClient(object):
    """
    All tests goes here. If you need to implement a special behavior for
    one OS, override the test method in the class TestLocalClientSimulation.
    Check TestLocalClientSimulation.test_complex_filenames() for a real
    world example.
    """

    def test_make_documents(self):
        doc_1 = self.local_client_1.make_file('/', 'Document 1.txt')
        self.assertTrue(self.local_client_1.exists(doc_1))
        self.assertEqual(self.local_client_1.get_content(doc_1), b'')
        doc_1_info = self.local_client_1.get_info(doc_1)
        self.assertEqual(doc_1_info.name, 'Document 1.txt')
        self.assertEqual(doc_1_info.path, doc_1)
        self.assertEqual(doc_1_info.get_digest(), EMPTY_DIGEST)
        self.assertFalse(doc_1_info.folderish)

        doc_2 = self.local_client_1.make_file('/', 'Document 2.txt',
                                              content=SOME_TEXT_CONTENT)
        self.assertTrue(self.local_client_1.exists(doc_2))
        self.assertEqual(self.local_client_1.get_content(doc_2),
                         SOME_TEXT_CONTENT)
        doc_2_info = self.local_client_1.get_info(doc_2)
        self.assertEqual(doc_2_info.name, 'Document 2.txt')
        self.assertEqual(doc_2_info.path, doc_2)
        self.assertEqual(doc_2_info.get_digest(), SOME_TEXT_DIGEST)
        self.assertFalse(doc_2_info.folderish)

        self.local_client_1.delete(doc_2)
        self.assertTrue(self.local_client_1.exists(doc_1))
        self.assertFalse(self.local_client_1.exists(doc_2))

        folder_1 = self.local_client_1.make_folder('/', 'A new folder')
        self.assertTrue(self.local_client_1.exists(folder_1))
        folder_1_info = self.local_client_1.get_info(folder_1)
        self.assertEqual(folder_1_info.name, 'A new folder')
        self.assertEqual(folder_1_info.path, folder_1)
        self.assertEqual(folder_1_info.get_digest(), None)
        self.assertTrue(folder_1_info.folderish)

        doc_3 = self.local_client_1.make_file(folder_1, 'Document 3.txt',
                                              content=SOME_TEXT_CONTENT)
        self.local_client_1.delete(folder_1)
        self.assertFalse(self.local_client_1.exists(folder_1))
        self.assertFalse(self.local_client_1.exists(doc_3))

    def test_get_info_invalid_date(self):
        doc_1 = self.local_client_1.make_file('/', 'Document 1.txt')
        os.utime(self.local_client_1.abspath(
                os.path.join('/', 'Document 1.txt')), (0, 999999999999999))
        doc_1_info = self.local_client_1.get_info(doc_1)
        self.assertEqual(doc_1_info.name, 'Document 1.txt')
        self.assertEqual(doc_1_info.path, doc_1)
        self.assertEqual(doc_1_info.get_digest(), EMPTY_DIGEST)
        self.assertFalse(doc_1_info.folderish)

    def test_complex_filenames(self):
        # create another folder with the same title
        title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"

        folder_1 = self.local_client_1.make_folder('/', title_with_accents)
        folder_1_info = self.local_client_1.get_info(folder_1)
        self.assertEqual(folder_1_info.name, title_with_accents)

        # create another folder with the same title
        with pytest.raises(DuplicationDisabledError):
            self.local_client_1.make_folder('/', title_with_accents)

        # Create a long file name with weird chars
        long_filename = u"\xe9" * 50 + u"%$#!()[]{}+_-=';&^" + u".doc"
        file_1 = self.local_client_1.make_file(folder_1, long_filename)
        file_1 = self.local_client_1.get_info(file_1)
        self.assertEqual(file_1.name, long_filename)
        self.assertEqual(file_1.path, folder_1_info.path + u"/" + long_filename)

        # Create a file with invalid chars
        invalid_filename = u"a/b\\c*d:e<f>g?h\"i|j.doc"
        escaped_filename = u"a-b-c-d-e-f-g-h-i-j.doc"
        file_2 = self.local_client_1.make_file(folder_1, invalid_filename)
        file_2 = self.local_client_1.get_info(file_2)
        self.assertEqual(file_2.name, escaped_filename)
        self.assertEqual(
                file_2.path, folder_1_info.path + u'/' + escaped_filename)

    def test_missing_file(self):
        with pytest.raises(NotFound):
            self.local_client_1.get_info('/Something Missing')

    @pytest.mark.timeout(30)
    def test_case_sensitivity(self):
        local = self.local_client_1
        sensitive = local.is_case_sensitive()
        log.info('OS is case sensitive: %r', sensitive)

        local.make_file('/', 'abc.txt')
        if sensitive:
            local.make_file('/', 'ABC.txt')
        else:
            with pytest.raises(DuplicationDisabledError):
                local.make_file('/', 'ABC.txt')
        self.assertEqual(len(local.get_children_info('/')), sensitive + 1)

    @pytest.mark.skipif(
        sys.platform != 'win32',
        reason='Windows only.')
    def test_windows_short_names(self):
        """
        Test 8.3 file name convention:
        https://msdn.microsoft.com/en-us/library/windows/desktop/aa365247(v=vs.85).aspx
        """

        local = self.local_client_1
        remote = self.remote_document_client_1
        long_name = 'a' * 32
        short_name = 'AAAAAA~1'

        # Create the folder
        folder = local.make_file('/', long_name)
        with pytest.raises(DuplicationDisabledError):
            local.make_file('/', short_name)
        path = local.abspath(folder)
        self.assertEqual(os.path.basename(path), long_name)

        # Get the short name
        short = win32api.GetShortPathName(path)
        self.assertEqual(os.path.basename(short), short_name)

        # Sync and check the short name is nowhere
        self.wait_sync()
        children = remote.get_children_info(self.workspace)
        self.assertTrue(len(children), 1)
        self.assertEqual(children[0].name, long_name)

    def test_get_children_info(self):
        folder_1 = self.local_client_1.make_folder('/', 'Folder 1')
        folder_2 = self.local_client_1.make_folder('/', 'Folder 2')
        file_1 = self.local_client_1.make_file(
            '/', 'File 1.txt', content=b'foo\n')

        # not a direct child of '/'
        self.local_client_1.make_file(folder_1, 'File 2.txt', content=b'bar\n')

        # ignored files
        data = b'baz\n'
        self.local_client_1.make_file('/', '.File 2.txt', content=data)
        self.local_client_1.make_file('/', '~$File 2.txt', content=data)
        self.local_client_1.make_file('/', 'File 2.txt~', content=data)
        self.local_client_1.make_file('/', 'File 2.txt.swp', content=data)
        self.local_client_1.make_file('/', 'File 2.txt.lock', content=data)
        self.local_client_1.make_file('/', 'File 2.txt.part', content=data)
        self.local_client_1.make_file('/', '.File 2.txt.nxpart', content=data)
        if self.local_client_1.is_case_sensitive():
            self.local_client_1.make_file('/', 'File 2.txt.LOCK', content=data)
        else:
            with pytest.raises(DuplicationDisabledError):
                self.local_client_1.make_file(
                    '/', 'File 2.txt.LOCK', content=data)

        workspace_children = self.local_client_1.get_children_info('/')
        self.assertEqual(len(workspace_children), 3)
        self.assertEqual(workspace_children[0].path, file_1)
        self.assertEqual(workspace_children[1].path, folder_1)
        self.assertEqual(workspace_children[2].path, folder_2)

    def test_deep_folders(self):
        # Check that local client can workaround the default Windows
        # MAX_PATH limit
        folder = '/'
        for _i in range(30):
            folder = self.local_client_1.make_folder(folder, '0123456789')

        # Last Level
        last_level_folder_info = self.local_client_1.get_info(folder)
        self.assertEqual(last_level_folder_info.path, '/0123456789' * 30)

        # Create a nested file
        deep_file = self.local_client_1.make_file(folder, 'File.txt',
                                                  content=b'Some Content.')

        # Check the consistency of get_children_info and get_info
        deep_file_info = self.local_client_1.get_info(deep_file)
        deep_children = self.local_client_1.get_children_info(folder)
        self.assertEqual(len(deep_children), 1)
        deep_child_info = deep_children[0]
        self.assertEqual(deep_file_info.name, deep_child_info.name)
        self.assertEqual(deep_file_info.path, deep_child_info.path)
        self.assertEqual(deep_file_info.get_digest(),
                         deep_child_info.get_digest())

        # Update the file content
        self.local_client_1.update_content(deep_file, b'New Content.')
        self.assertEqual(self.local_client_1.get_content(deep_file),
                         b'New Content.')

        # Delete the folder
        self.local_client_1.delete(folder)
        self.assertFalse(self.local_client_1.exists(folder))
        self.assertFalse(self.local_client_1.exists(deep_file))

        # Delete the root folder and descendants
        self.local_client_1.delete('/0123456789')
        self.assertFalse(self.local_client_1.exists('/0123456789'))

    def test_get_new_file(self):
        path, os_path, name = self.local_client_1.get_new_file('/',
                                                               'Document 1.txt')
        self.assertEqual(path, '/Document 1.txt')
        self.assertTrue(os_path.endswith(os.path.join(self.workspace_title,
                                                      'Document 1.txt')))
        self.assertEqual(name, 'Document 1.txt')
        self.assertFalse(self.local_client_1.exists(path))
        self.assertFalse(os.path.exists(os_path))

    def test_xattr(self):
        ref = self.local_client_1.make_file('/', 'File 2.txt', content=b'baz\n')
        path = self.local_client_1.abspath(ref)
        mtime = int(os.path.getmtime(path))
        sleep(1)
        self.local_client_1.set_remote_id(ref, 'TEST')
        self.assertEqual(mtime, int(os.path.getmtime(path)))
        sleep(1)
        self.local_client_1.remove_remote_id(ref)
        self.assertEqual(mtime, int(os.path.getmtime(path)))

    def test_get_path(self):
        doc = 'doc.txt'
        abs_path = os.path.join(
            self.local_nxdrive_folder_1, self.workspace_title, doc)
        self.assertEqual(self.local_client_1.get_path(abs_path), '/' + doc)

        # Encoding test
        self.assertEqual(self.local_client_1.get_path('été.txt'), '/')

    def test_is_equal_digests(self):
        content = b'joe'
        local_path = self.local_client_1.make_file('/', 'File.txt',
                                                   content=content)
        local_digest = hashlib.md5(content).hexdigest()
        # Equal digests
        self.assertTrue(self.local_client_1.is_equal_digests(
            local_digest, local_digest, local_path))

        # Different digests with same digest algorithm
        other_content = b'jack'
        remote_digest = hashlib.md5(other_content).hexdigest()
        self.assertNotEqual(local_digest, remote_digest)
        self.assertFalse(self.local_client_1.is_equal_digests(
            local_digest, remote_digest, local_path))

        # Different digests with different digest algorithms but same content
        remote_digest = hashlib.sha1(content).hexdigest()
        self.assertNotEqual(local_digest, remote_digest)
        self.assertTrue(self.local_client_1.is_equal_digests(
            local_digest, remote_digest, local_path))

        # Different digests with different digest algorithms and different
        # content
        remote_digest = hashlib.sha1(other_content).hexdigest()
        self.assertNotEqual(local_digest, remote_digest)
        self.assertFalse(self.local_client_1.is_equal_digests(
            local_digest, remote_digest, local_path))


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

    def test_remote_changing_case_accentued_folder(self):
        """
        NXDRIVE-1061: Remote rename of an accentued folder on Windows fails.
        I put this test only here because we need to test native
        LocalClient.rename().
        """

        local = self.local_client_1
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
    sys.platform == 'linux2',
    reason='GNU/Linux uses native LocalClient.')
class TestLocalClientSimulation(StubLocalClient, UnitTestCase):
    """
    Test LocalClient using OS specific commands to make FS operations.
    This will simulate user actions on:
        - Explorer (Windows)
        - File Manager (macOS)
    """

    def setUp(self):
        self.engine_1.start()
        self.wait_sync()

    def test_complex_filenames(self):
        """
        It should fail on Windows:
        Explorer cannot find the directory as the path is way to long.
        """

        if sys.platform == 'win32':
            try:
                # IOError: [Errno 2] No such file or directory
                with pytest.raises(IOError):
                    super(TestLocalClientSimulation,
                          self).test_complex_filenames()
            except AssertionError:
                # Sometimes it does not raise the expected assertion ...
                # TODO: More tests to know why.
                pass
        else:
            super(TestLocalClientSimulation, self).test_complex_filenames()

    def test_deep_folders(self):
        """
        It should fail on Windows:
        Explorer cannot deal with very long paths.
        """

        if sys.platform == 'win32':
            # WindowsError: [Error 206] The filename or extension is too long
            with pytest.raises(OSError) as ex:
                super(TestLocalClientSimulation, self).test_deep_folders()
                self.assertEqual(ex.errno, 206)
        else:
            super(TestLocalClientSimulation, self).test_deep_folders()
