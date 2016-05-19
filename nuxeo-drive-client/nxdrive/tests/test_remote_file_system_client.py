from nxdrive.client import NotFound
from nxdrive.client import LocalClient
from nxdrive.tests.common import FS_ITEM_ID_PREFIX
from nxdrive.tests.common import IntegrationTestCase
from nxdrive.client.base_automation_client import CorruptedFile
from shutil import copyfile
import hashlib
from threading import current_thread
import os


class TestRemoteFileSystemClient(IntegrationTestCase):

    def setUp(self):
        super(TestRemoteFileSystemClient, self).setUp()
        # Bind the test workspace as sync root for user 1
        remote_document_client = self.remote_document_client_1
        remote_fs_client = self.remote_file_system_client_1
        remote_document_client.register_as_root(self.workspace)

        # Fetch the id of the workspace folder item
        toplevel_folder_info = remote_fs_client.get_filesystem_root_info()
        self.workspace_id = remote_fs_client.get_children_info(
            toplevel_folder_info.uid)[0].uid

    #
    # Test the API common with the local client API
    #

    def test_get_info(self):
        remote_client = self.remote_file_system_client_1

        # Check file info
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        info = remote_client.get_info(fs_item_id)
        self.assertTrue(info is not None)
        self.assertEquals(info.name, 'Document 1.txt')
        self.assertEquals(info.uid, fs_item_id)
        self.assertEquals(info.parent_uid,
            self.workspace_id)
        self.assertFalse(info.folderish)
        if info.last_contributor:
            self.assertEquals(info.last_contributor, self.user_1)
        digest_algorithm = info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of doc 1.")
        self.assertEquals(info.digest, digest)
        file_uid = fs_item_id.rsplit("#", 1)[1]
        # NXP-17827: nxbigile has been replace to nxfile, keep handling both
        cond = (info.download_url == 'nxbigfile/default/' + file_uid + '/blobholder:0/Document%201.txt'
                or info.download_url == 'nxfile/default/' + file_uid + '/blobholder:0/Document%201.txt')
        self.assertTrue(cond)

        # Check folder info
        fs_item_id = remote_client.make_folder(self.workspace_id,
            'Folder 1').uid
        info = remote_client.get_info(fs_item_id)
        self.assertTrue(info is not None)
        self.assertEquals(info.name, 'Folder 1')
        self.assertEquals(info.uid, fs_item_id)
        self.assertEquals(info.parent_uid,
            self.workspace_id)
        self.assertTrue(info.folderish)
        if info.last_contributor:
            self.assertEquals(info.last_contributor, self.user_1)
        self.assertTrue(info.digest_algorithm is None)
        self.assertTrue(info.digest is None)
        self.assertTrue(info.download_url is None)

        # Check non existing file info
        fs_item_id = FS_ITEM_ID_PREFIX + 'fakeId'
        self.assertRaises(NotFound,
            remote_client.get_info, fs_item_id)
        self.assertTrue(
            remote_client.get_info(fs_item_id,
                raise_if_missing=False) is None)

    def test_get_content(self):
        remote_client = self.remote_file_system_client_1

        # Check file with content
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        self.assertEquals(remote_client.get_content(fs_item_id),
            "Content of doc 1.")

        # Check file without content
        doc_uid = self.remote_document_client_1.make_file(self.workspace,
            'Document 2.txt')
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        self.assertRaises(NotFound,
            remote_client.get_content, fs_item_id)

    def test_wrong_hash(self):
        remote_client = self.remote_file_system_client_1
        hash_method =  None
        # Check file with content
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        # Monkey patch the get_info to change hash
        def get_info(fs_item_id, parent_fs_item_id=None,
                 raise_if_missing=True):
            fs_item = remote_client.get_fs_item(fs_item_id,
                                   parent_fs_item_id=parent_fs_item_id)
            fs_item['digest']='aaaaa'
            if hash_method is not None:
                fs_item['digestAlgorithm'] = hash_method.lower()
            if fs_item is None:
                if raise_if_missing:
                    raise NotFound("Could not find '%s' on '%s'" % (
                        fs_item_id, self.server_url))
                return None
            return remote_client.file_to_info(fs_item)

        remote_client.get_info = get_info
        self.assertRaises(CorruptedFile, remote_client.get_content, fs_item_id)
        file_path = os.path.join(self.local_test_folder_1, 'Document 1.txt')
        self.assertRaises(CorruptedFile, remote_client.stream_content, fs_item_id, file_path)
        hash_method = 'not_hash'
        self.assertRaises(ValueError, remote_client.get_content, fs_item_id)

    def test_stream_content(self):
        remote_client = self.remote_file_system_client_1

        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        file_path = os.path.join(self.local_test_folder_1, 'Document 1.txt')
        tmp_file = remote_client.stream_content(fs_item_id, file_path)
        self.assertTrue(os.path.exists(tmp_file))
        self.assertEquals(os.path.basename(tmp_file), '.Document 1.txt' + str(current_thread().ident)+ '.nxpart')
        self.assertEqual(open(tmp_file, 'rb').read(), "Content of doc 1.")

    def test_get_children_info(self):
        remote_client = self.remote_file_system_client_1

        # Create documents
        folder_1_id = remote_client.make_folder(self.workspace_id,
            'Folder 1').uid
        folder_2_id = remote_client.make_folder(self.workspace_id,
            'Folder 2').uid
        file_1_id = remote_client.make_file(self.workspace_id,
            'File 1', "Content of file 1.").uid
        file_2_id = remote_client.make_file(folder_1_id,
            'File 2', "Content of file 2.").uid

        # Check workspace children
        workspace_children = remote_client.get_children_info(self.workspace_id)
        self.assertTrue(workspace_children is not None)
        self.assertEquals(len(workspace_children), 3)
        self.assertEquals(workspace_children[0].uid, folder_1_id)
        self.assertEquals(workspace_children[0].name, 'Folder 1')
        self.assertTrue(workspace_children[0].folderish)
        self.assertEquals(workspace_children[1].uid, folder_2_id)
        self.assertEquals(workspace_children[1].name, 'Folder 2')
        self.assertTrue(workspace_children[1].folderish)
        self.assertEquals(workspace_children[2].uid, file_1_id)
        # the .txt name is added by the server to the title of Note
        # documents
        self.assertEquals(workspace_children[2].name, 'File 1.txt')
        self.assertFalse(workspace_children[2].folderish)

        # Check folder_1 children
        folder_1_children = remote_client.get_children_info(folder_1_id)
        self.assertTrue(folder_1_children is not None)
        self.assertEquals(len(folder_1_children), 1)
        self.assertEquals(folder_1_children[0].uid, file_2_id)
        self.assertEquals(folder_1_children[0].name, 'File 2.txt')

    def test_scroll_descendants(self):
        remote_client = self.remote_file_system_client_1

        # Create documents
        folder_1_id = remote_client.make_folder(self.workspace_id, 'Folder 1').uid
        folder_2_id = remote_client.make_folder(self.workspace_id, 'Folder 2').uid
        file_1_id = remote_client.make_file(self.workspace_id, 'File 1', "Content of file 1.").uid
        file_2_id = remote_client.make_file(folder_1_id, 'File 2', "Content of file 2.").uid

        # Wait for ES completion
        self.wait()

        # Check workspace descendants in one breath, ordered by remote path
        scroll_res = remote_client.scroll_descendants(self.workspace_id, None)
        self.assertIsNotNone(scroll_res)
        self.assertIsNotNone(scroll_res.get('scroll_id'))
        descendants = scroll_res.get('descendants')
        self.assertIsNotNone(descendants)
        self.assertEquals(len(descendants), 4)
        self.assertEquals(descendants[0].uid, file_1_id)
        self.assertEquals(descendants[0].name, 'File 1.txt')
        self.assertFalse(descendants[0].folderish)
        self.assertEquals(descendants[1].uid, folder_1_id)
        self.assertEquals(descendants[1].name, 'Folder 1')
        self.assertTrue(descendants[1].folderish)
        self.assertEquals(descendants[2].uid, file_2_id)
        self.assertEquals(descendants[2].name, 'File 2.txt')
        self.assertFalse(descendants[2].folderish)
        self.assertEquals(descendants[3].uid, folder_2_id)
        self.assertEquals(descendants[3].name, 'Folder 2')
        self.assertTrue(descendants[3].folderish)

        # Check workspace descendants in several steps, ordered by remote path
        descendants = []
        scroll_id = None
        while True:
            scroll_res = remote_client.scroll_descendants(self.workspace_id, scroll_id=scroll_id, batch_size=2)
            self.assertIsNotNone(scroll_res)
            scroll_id = scroll_res.get('scroll_id')
            self.assertIsNotNone(scroll_id)
            partial_descendants = scroll_res.get('descendants')
            self.assertIsNotNone(partial_descendants)
            if not partial_descendants:
                break
            descendants.extend(partial_descendants)
        self.assertEquals(len(descendants), 4)
        self.assertEquals(descendants[0].uid, file_1_id)
        self.assertEquals(descendants[0].name, 'File 1.txt')
        self.assertFalse(descendants[0].folderish)
        self.assertEquals(descendants[1].uid, folder_1_id)
        self.assertEquals(descendants[1].name, 'Folder 1')
        self.assertTrue(descendants[1].folderish)
        self.assertEquals(descendants[2].uid, file_2_id)
        self.assertEquals(descendants[2].name, 'File 2.txt')
        self.assertFalse(descendants[2].folderish)
        self.assertEquals(descendants[3].uid, folder_2_id)
        self.assertEquals(descendants[3].name, 'Folder 2')
        self.assertTrue(descendants[3].folderish)

    def test_make_folder(self):
        remote_client = self.remote_file_system_client_1

        fs_item_info = remote_client.make_folder(self.workspace_id,
            'My new folder')
        self.assertTrue(fs_item_info is not None)
        self.assertEquals(fs_item_info.name, 'My new folder')
        self.assertTrue(fs_item_info.folderish)
        self.assertTrue(fs_item_info.digest_algorithm is None)
        self.assertTrue(fs_item_info.digest is None)
        self.assertTrue(fs_item_info.download_url is None)

    def test_make_file(self):
        remote_client = self.remote_file_system_client_1

        # Check File document creation
        fs_item_info = remote_client.make_file(self.workspace_id,
            'My new file.odt', "Content of my new file.")
        self.assertTrue(fs_item_info is not None)
        self.assertEquals(fs_item_info.name, 'My new file.odt')
        self.assertFalse(fs_item_info.folderish)
        digest_algorithm = fs_item_info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of my new file.")
        self.assertEquals(fs_item_info.digest, digest)

        # Check Note document creation
        fs_item_info = remote_client.make_file(self.workspace_id,
            'My new note.txt', "Content of my new note.")
        self.assertTrue(fs_item_info is not None)
        self.assertEquals(fs_item_info.name, 'My new note.txt')
        self.assertFalse(fs_item_info.folderish)
        digest_algorithm = fs_item_info.digest_algorithm
        self.assertEquals(digest_algorithm, 'md5')
        digest = self._get_digest(digest_algorithm, "Content of my new note.")
        self.assertEquals(fs_item_info.digest, digest)

    def test_make_file_custom_encoding(self):
        remote_client = self.remote_file_system_client_1

        # Create content encoded in utf-8 and cp1252
        unicode_content = u'\xe9'  # e acute
        utf8_encoded = unicode_content.encode('utf-8')
        utf8_digest = hashlib.md5(utf8_encoded).hexdigest()
        cp1252_encoded = unicode_content.encode('cp1252')

        # Make files with this content
        utf8_fs_id = remote_client.make_file(self.workspace_id,
            'My utf-8 file.txt', utf8_encoded).uid
        cp1252_fs_id = remote_client.make_file(self.workspace_id,
            'My cp1252 file.txt', cp1252_encoded).uid

        # Check content
        utf8_content = remote_client.get_content(utf8_fs_id)
        self.assertEqual(utf8_content, utf8_encoded)
        cp1252_content = remote_client.get_content(cp1252_fs_id)
        self.assertEqual(cp1252_content, utf8_encoded)

        # Check digest
        utf8_info = remote_client.get_info(utf8_fs_id)
        self.assertEqual(utf8_info.digest, utf8_digest)
        cp1252_info = remote_client.get_info(cp1252_fs_id)
        self.assertEqual(cp1252_info.digest, utf8_digest)

    def test_update_content(self):
        remote_client = self.remote_file_system_client_1

        # Create file
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid

        # Check file update
        remote_client.update_content(
            fs_item_id, "Updated content of doc 1.")
        self.assertEquals(remote_client.get_content(fs_item_id),
            "Updated content of doc 1.")

    def test_delete(self):
        remote_client = self.remote_file_system_client_1

        # Create file
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        self.assertTrue(remote_client.exists(fs_item_id))

        # Delete file
        remote_client.delete(fs_item_id)
        self.assertFalse(remote_client.exists(fs_item_id))

    def test_exists(self):
        remote_client = self.remote_file_system_client_1

        # Check existing file system item
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        self.assertTrue(remote_client.exists(fs_item_id))

        # Check non existing file system item (non existing document)
        fs_item_id = FS_ITEM_ID_PREFIX + 'fakeId'
        self.assertFalse(remote_client.exists(fs_item_id))

        # Check non existing file system item (document without content)
        doc_uid = self.remote_document_client_1.make_file(self.workspace,
            'Document 2.txt')
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        self.assertFalse(remote_client.exists(fs_item_id))

    # TODO
    def test_check_writable(self):
        pass

    #
    # Test the API specific to the remote file system client
    #

    def test_get_fs_item(self):
        remote_client = self.remote_file_system_client_1

        # Check file item
        fs_item_id = remote_client.make_file(self.workspace_id,
            'Document 1.txt', "Content of doc 1.").uid
        fs_item = remote_client.get_fs_item(fs_item_id)
        self.assertTrue(fs_item is not None)
        self.assertEquals(fs_item['name'], 'Document 1.txt')
        self.assertEquals(fs_item['id'], fs_item_id)
        self.assertFalse(fs_item['folder'])

        # Check file item using parent id
        fs_item = remote_client.get_fs_item(fs_item_id,
                                        parent_fs_item_id=self.workspace_id)
        self.assertTrue(fs_item is not None)
        self.assertEquals(fs_item['name'], 'Document 1.txt')
        self.assertEquals(fs_item['id'], fs_item_id)
        self.assertEquals(fs_item['parentId'], self.workspace_id)

        # Check folder item
        fs_item_id = remote_client.make_folder(self.workspace_id,
            'Folder 1').uid
        fs_item = remote_client.get_fs_item(fs_item_id)
        self.assertTrue(fs_item is not None)
        self.assertEquals(fs_item['name'], 'Folder 1')
        self.assertEquals(fs_item['id'], fs_item_id)
        self.assertTrue(fs_item['folder'])

        # Check non existing file system item
        fs_item_id = FS_ITEM_ID_PREFIX + 'fakeId'
        self.assertTrue(remote_client.get_fs_item(fs_item_id)
                        is None)

    def test_get_top_level_children(self):
        remote_document_client = self.remote_document_client_1
        remote_file_system_client = self.remote_file_system_client_1

        # The workspace is registered as a sync root in the setup
        children = remote_file_system_client.get_top_level_children()
        self.assertEquals(len(children), 1)
        self.assertEquals(children[0]['name'], self.workspace_title)

        # Create 2 remote folders inside the workspace sync root
        fs_item_1_id = remote_file_system_client.make_folder(
            self.workspace_id, 'Folder 1').uid
        fs_item_2_id = remote_file_system_client.make_folder(
            self.workspace_id, 'Folder 2').uid
        folder_1_uid = fs_item_1_id.rsplit("#", 1)[1]
        folder_2_uid = fs_item_2_id.rsplit("#", 1)[1]

        # Unregister the workspace
        remote_document_client.unregister_as_root(self.workspace)
        children = remote_file_system_client.get_top_level_children()
        self.assertEquals(children, [])

        # Register the sub folders as new roots
        remote_document_client.register_as_root(folder_1_uid)
        remote_document_client.register_as_root(folder_2_uid)
        children = remote_file_system_client.get_top_level_children()
        self.assertEquals(len(children), 2)

        # Unregister one sync root
        remote_document_client.unregister_as_root(folder_1_uid)
        children = remote_file_system_client.get_top_level_children()
        self.assertEquals(len(children), 1)

    def test_conflicted_item_name(self):
        remote_file_system_client = self.remote_file_system_client_1
        new_name = remote_file_system_client.conflicted_name("My File.doc")
        self.assertTrue(new_name.startswith(
            "My File (" + self.user_1 + " - "))
        self.assertTrue(new_name.endswith(").doc"))

    def test_streaming_upload(self):
        remote_client = self.remote_file_system_client_1

        # Create a document by streaming a text file
        file_path = remote_client.make_tmp_file("Some content.")
        try:
            fs_item_info = remote_client.stream_file(self.workspace_id, file_path, filename='My streamed file.txt')
        finally:
            os.remove(file_path)
        fs_item_id = fs_item_info.uid
        self.assertEquals(fs_item_info.name,
                        'My streamed file.txt')
        self.assertEquals(remote_client.get_content(fs_item_id),
                          "Some content.")

        # Update a document by streaming a new text file
        file_path = remote_client.make_tmp_file("Other content.")
        try:
            fs_item_info = remote_client.stream_update(fs_item_id, file_path, filename='My updated file.txt')
        finally:
            os.remove(file_path)
        self.assertEqual(fs_item_info.uid, fs_item_id)
        self.assertEquals(fs_item_info.name,
                        'My updated file.txt')
        self.assertEquals(remote_client.get_content(fs_item_id),
                          "Other content.")

        # Create a document by streaming a binary file
        file_path = os.path.join(self.upload_tmp_dir, 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        fs_item_info = remote_client.stream_file(self.workspace_id, file_path)
        local_client = LocalClient(self.upload_tmp_dir)
        self.assertEquals(fs_item_info.name, 'testFile.pdf')
        self.assertEquals(fs_item_info.digest,
                          local_client.get_info('/testFile.pdf').get_digest())

    def test_bad_mime_type(self):
        remote_client = self.remote_file_system_client_1

        # Create a document by streaming a binary file
        file_path = os.path.join(self.upload_tmp_dir, 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        fs_item_info = remote_client.stream_file(self.workspace_id, file_path,
                                               mime_type='pdf')
        local_client = LocalClient(self.upload_tmp_dir)
        self.assertEquals(fs_item_info.name, 'testFile.pdf')
        self.assertEquals(fs_item_info.digest,
                          local_client.get_info('/testFile.pdf').get_digest())

    def test_mime_type_doc_type_association(self):

        # Upload a PDF file, should create a File document
        file_path = os.path.join(self.upload_tmp_dir, 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        fs_item_info = self.remote_file_system_client_1.stream_file(
                                            self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit('#', 1)[1]
        doc_type = self.remote_document_client_1.get_info(doc_uid).doc_type
        self.assertEquals(doc_type, 'File')

        # Upload a JPG file, should create a Picture document
        file_path = os.path.join(self.upload_tmp_dir, 'cat.jpg')
        copyfile('nxdrive/tests/resources/cat.jpg', file_path)
        fs_item_info = self.remote_file_system_client_1.stream_file(
                                            self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit('#', 1)[1]
        doc_type = self.remote_document_client_1.get_info(doc_uid).doc_type
        self.assertEquals(doc_type, 'Picture')

    def test_modification_flags_locked_document(self):
        remote = self.remote_file_system_client_1
        fs_item_id = remote.make_file(self.workspace_id, 'Document 1.txt', "Content of doc 1.").uid

        # Check flags for a document that isn't locked
        info = remote.get_info(fs_item_id)
        self.assertTrue(info.can_rename)
        self.assertTrue(info.can_update)
        self.assertTrue(info.can_delete)
        self.assertIsNone(info.lock_owner)
        self.assertIsNone(info.lock_created)

        # Check flags for a document locked by the current user
        doc_uid = fs_item_id.rsplit('#', 1)[1]
        self.remote_document_client_1.lock(doc_uid)
        info = remote.get_info(fs_item_id)
        self.assertTrue(info.can_rename)
        self.assertTrue(info.can_update)
        self.assertTrue(info.can_delete)
        lock_info_available = remote.get_fs_item(fs_item_id).get('lockInfo') is not None
        if lock_info_available:
            self.assertEquals(info.lock_owner, self.user_1)
            self.assertIsNotNone(info.lock_created)
        self.remote_document_client_1.unlock(doc_uid)

        # Check flags for a document locked by another user
        self.remote_document_client_2.lock(doc_uid)
        info = remote.get_info(fs_item_id)
        self.assertFalse(info.can_rename)
        self.assertFalse(info.can_update)
        self.assertFalse(info.can_delete)
        if lock_info_available:
            self.assertEquals(info.lock_owner, self.user_2)
            self.assertIsNotNone(info.lock_created)

        # Check flags for a document unlocked by another user
        self.remote_document_client_2.unlock(doc_uid)
        info = remote.get_info(fs_item_id)
        self.assertTrue(info.can_rename)
        self.assertTrue(info.can_update)
        self.assertTrue(info.can_delete)
        self.assertIsNone(info.lock_owner)
        self.assertIsNone(info.lock_created)

    def _get_digest(self, digest_algorithm, content):
        hasher = getattr(hashlib, digest_algorithm)
        if hasher is None:
            raise RuntimeError('Unknown digest algorithm: %s'
                % digest_algorithm)
        return hasher(content).hexdigest()
