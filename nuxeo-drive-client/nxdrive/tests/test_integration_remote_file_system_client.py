from nxdrive.client import NotFound
from nxdrive.tests.common import IntegrationTestCase
import hashlib


DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX = 'defaultFileSystemItemFactory/default/'

class TestIntegrationRemoteFileSystemClient(IntegrationTestCase):

    #
    # Test the API common with the local client API
    #

    def test_get_info(self):
        remote_document_client = self.remote_document_client_1
        remote_file_system_client = self.remote_file_system_client_1

        # Check file info
        file_uid = remote_document_client.make_file(self.workspace,
            'Document 1.txt', content="Content of doc 1.")
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + file_uid
        info = remote_file_system_client.get_info(fs_item_id)
        self.assertIsNotNone(info)
        self.assertEquals(info.name, 'Document 1.txt')
        self.assertEquals(info.uid, fs_item_id)
        self.assertEquals(info.parent_uid,
            DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + self.workspace)
        self.assertFalse(info.folderish)
        digest_algorithm = info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of doc 1.")
        self.assertEquals(info.digest, digest)
        self.assertEquals(info.download_url,
            'nxbigfile/default/' + file_uid + '/blobholder:0/Document%201.txt')

        # Check folder info
        folder_uid = remote_document_client.make_folder(self.workspace,
            'Folder 1')
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + folder_uid
        info = remote_file_system_client.get_info(fs_item_id)
        self.assertIsNotNone(info)
        self.assertEquals(info.name, 'Folder 1')
        self.assertEquals(info.uid, fs_item_id)
        self.assertEquals(info.parent_uid,
            DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + self.workspace)
        self.assertTrue(info.folderish)
        self.assertIsNone(info.digest_algorithm)
        self.assertIsNone(info.digest)
        self.assertIsNone(info.download_url)

        # Check non existing file info
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + 'fakeId'
        self.assertRaises(NotFound,
            remote_file_system_client.get_info, fs_item_id)
        self.assertIsNone(
            remote_file_system_client.get_info(fs_item_id,
                raise_if_missing=False))

    def test_get_content(self):
        remote_document_client = self.remote_document_client_1
        remote_file_system_client = self.remote_file_system_client_1

        # Check file with content
        doc_uid = remote_document_client.make_file(self.workspace,
            'Document 1.txt', content="Content of doc 1.")
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + doc_uid
        self.assertEquals(remote_file_system_client.get_content(fs_item_id),
            "Content of doc 1.")

        # Check file without content
        doc_uid = remote_document_client.make_file(self.workspace,
            'Document 2.txt')
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + doc_uid
        self.assertRaises(NotFound,
            remote_file_system_client.get_content, fs_item_id)

    def test_get_children_info(self):
        # TODO
        pass

    def test_make_folder(self):
        remote_file_system_client = self.remote_file_system_client_1

        parent_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + self.workspace
        fs_item_id = remote_file_system_client.make_folder(parent_id,
            'My new folder')
        self.assertIsNotNone(fs_item_id)
        info = remote_file_system_client.get_info(fs_item_id)
        self.assertIsNotNone(info)
        self.assertEquals(info.name, 'My new folder')
        self.assertTrue(info.folderish)
        self.assertIsNone(info.digest_algorithm)
        self.assertIsNone(info.digest)
        self.assertIsNone(info.download_url)

    def test_make_file(self):
        remote_file_system_client = self.remote_file_system_client_1

        # Check File document creation
        parent_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + self.workspace
        fs_item_id = remote_file_system_client.make_file(parent_id,
            'My new file.odt', "Content of my new file.")
        self.assertIsNotNone(fs_item_id)
        info = remote_file_system_client.get_info(fs_item_id)
        self.assertIsNotNone(info)
        self.assertEquals(info.name, 'My new file.odt')
        self.assertFalse(info.folderish)
        digest_algorithm = info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of my new file.")
        self.assertEquals(info.digest, digest)

        # Check Note document creation
        fs_item_id = remote_file_system_client.make_file(parent_id,
            'My new note.txt', "Content of my new note.")
        self.assertIsNotNone(fs_item_id)
        info = remote_file_system_client.get_info(fs_item_id)
        self.assertIsNotNone(info)
        self.assertEquals(info.name, 'My new note.txt')
        self.assertFalse(info.folderish)
        digest_algorithm = info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of my new note.")
        self.assertEquals(info.digest, digest)

    def test_make_file_custom_encoding(self):
        remote_file_system_client = self.remote_file_system_client_1

        # Create content encoded in utf-8 and cp1252
        unicode_content = u'\xe9' # e acute
        utf8_encoded = unicode_content.encode('utf-8')
        utf8_digest = hashlib.md5(utf8_encoded).hexdigest()
        cp1252_encoded = unicode_content.encode('cp1252')

        # Make files with this content
        parent_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + self.workspace
        utf8_fs_id = remote_file_system_client.make_file(parent_id,
            'My utf-8 file.txt', utf8_encoded)
        cp1252_fs_id = remote_file_system_client.make_file(parent_id,
            'My cp1252 file.txt', cp1252_encoded)

        # Check content
        utf8_content = remote_file_system_client.get_content(utf8_fs_id)
        self.assertEqual(utf8_content, utf8_encoded)
        cp1252_content = remote_file_system_client.get_content(cp1252_fs_id)
        self.assertEqual(cp1252_content, utf8_encoded)

        # Check digest
        utf8_info = remote_file_system_client.get_info(utf8_fs_id)
        self.assertEqual(utf8_info.digest, utf8_digest)
        cp1252_info = remote_file_system_client.get_info(cp1252_fs_id)
        self.assertEqual(cp1252_info.digest, utf8_digest)

    def test_update_content(self):
        #TODO
        pass

    def test_delete(self):
        # TODO
        pass

    def test_exists(self):
        remote_document_client = self.remote_document_client_1
        remote_file_system_client = self.remote_file_system_client_1

        # Check existing file system item
        doc_uid = remote_document_client.make_file(self.workspace,
            'Document 1.txt', content="Content of doc 1.")
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + doc_uid
        self.assertTrue(remote_file_system_client.exists(fs_item_id))

        # Check non existing file system item (non existing document)
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + 'fakeId'
        self.assertFalse(remote_file_system_client.exists(fs_item_id))

        # Check non existing file system item (document without content)
        doc_uid = remote_document_client.make_file(self.workspace,
            'Document 2.txt')
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + doc_uid
        self.assertFalse(remote_file_system_client.exists(fs_item_id))

    # TODO: probably to be replaced by test_can_rename, test_can_update,
    # test_can_delete, test_can_create_child
    def test_check_writable(self):
        # TODO
        pass

    #
    # Test the API specific to the remote file system client
    #

    def test_get_fs_item(self):
        remote_document_client = self.remote_document_client_1
        remote_file_system_client = self.remote_file_system_client_1

        # Check file item
        file_uid = remote_document_client.make_file(self.workspace,
            'Document 1.txt', content="Content of doc 1.")
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + file_uid
        fs_item = remote_file_system_client.get_fs_item(fs_item_id)
        self.assertIsNotNone(fs_item)
        self.assertEquals(fs_item['name'], 'Document 1.txt')
        self.assertEquals(fs_item['id'], fs_item_id)
        self.assertFalse(fs_item['folder'])

        # Check folder item
        folder_uid = remote_document_client.make_folder(self.workspace,
            'Folder 1')
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + folder_uid
        fs_item = remote_file_system_client.get_fs_item(fs_item_id)
        self.assertIsNotNone(fs_item)
        self.assertEquals(fs_item['name'], 'Folder 1')
        self.assertEquals(fs_item['id'], fs_item_id)
        self.assertTrue(fs_item['folder'])

        # Check non existing file system item
        fs_item_id = DEFAULT_FILE_SYSTEM_ITEM_ID_PREFIX + 'fakeId'
        self.assertIsNone(remote_file_system_client.get_fs_item(fs_item_id))

    def _get_digest(self, digest_algorithm, content):
        hasher = getattr(hashlib, digest_algorithm)
        if hasher is None:
            raise RuntimeError('Unknown digest algorithm: %s' % digest_algorithm)
        return hasher(content).hexdigest()
