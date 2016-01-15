import os
from shutil import copyfile
from time import sleep
from nxdrive.client import NuxeoClient
from nxdrive.client import Unauthorized
from nxdrive.client import NotFound
from nxdrive.client import LocalClient
from nxdrive.tests.common import SOME_TEXT_CONTENT
from nxdrive.tests.common import SOME_TEXT_DIGEST
from nxdrive.tests.common import IntegrationTestCase
from nose import SkipTest


def wait_for_deletion(client, doc, retries_left=10, delay=0.300,
                      use_trash=True):
    if retries_left <= 0:
        raise ValueError("Document was not deleted before client timeout")
    if not client.exists(doc, use_trash=use_trash):
        # OK: the document has been deleted
        return
    # Wait a bit for the sub-folder deletion asynchronous listener to do its
    # job and then retry
    sleep(delay)
    wait_for_deletion(client, doc, retries_left=retries_left - 1,
                      use_trash=use_trash)


class TestRemoteDocumentClient(IntegrationTestCase):

    def test_authentication_failure(self):
        self.assertRaises(Unauthorized, NuxeoClient,
                      self.remote_document_client_1.server_url,
                      'someone else', 'test-device', self.version,
                      password='bad password')
        self.assertRaises(Unauthorized, NuxeoClient,
                      self.remote_document_client_1.server_url,
                      'someone else', 'test-device', self.version,
                      token='some-bad-token')

    def test_make_token(self):
        remote_client = self.remote_document_client_1
        token = remote_client.request_token()
        if token is None:
            raise SkipTest('nuxeo-platform-login-token is not deployed')
        self.assertTrue(len(token) > 5)
        self.assertEquals(remote_client.auth[0], 'X-Authentication-Token')
        self.assertEquals(remote_client.auth[1], token)

        # Requesting token is an idempotent operation
        token2 = remote_client.request_token()
        self.assertEquals(token, token2)

        # It's possible to create a new client using the same token
        remote_client2 = NuxeoClient(
            remote_client.server_url, remote_client.user_id,
            remote_client.device_id, remote_client.client_version,
            token=token, base_folder=self.workspace)

        token3 = remote_client.request_token()
        self.assertEquals(token, token3)

        # Register a root with client 2 and see it with client one
        folder_1 = remote_client2.make_folder('/', 'Folder 1')
        remote_client2.register_as_root(folder_1)

        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].name, 'Folder 1')

        # The root can also been seen with a new client connected using
        # password based auth
        remote_client3 = NuxeoClient(
            remote_client.server_url, remote_client.user_id,
            remote_client.device_id, remote_client.client_version,
            password=self.password_1, base_folder=None)
        roots = remote_client3.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].name, 'Folder 1')

        # Another device using the same user credentials will get a different
        # token
        remote_client4 = NuxeoClient(
            remote_client.server_url, remote_client.user_id,
            'other-test-device', remote_client.client_version,
            password=self.password_1, base_folder=None)
        token4 = remote_client4.request_token()
        self.assertNotEquals(token, token4)

        # A client can revoke a token explicitly and thus lose credentials
        remote_client4.revoke_token()
        self.assertRaises(IOError, remote_client4.get_roots)

    def test_make_documents(self):
        remote_client = self.remote_document_client_1
        doc_1 = remote_client.make_file(self.workspace, 'Document 1.txt')
        self.assertTrue(remote_client.exists(doc_1))
        self.assertEquals(remote_client.get_content(doc_1), "")
        doc_1_info = remote_client.get_info(doc_1)
        self.assertEquals(doc_1_info.name, 'Document 1.txt')
        self.assertEquals(doc_1_info.uid, doc_1)
        self.assertIsNone(doc_1_info.digest_algorithm)
        self.assertIsNone(doc_1_info.get_digest())
        self.assertEquals(doc_1_info.folderish, False)

        doc_2 = remote_client.make_file(self.workspace, 'Document 2.txt',
                                  content=SOME_TEXT_CONTENT)

        self.assertTrue(remote_client.exists(doc_2))
        self.assertEquals(remote_client.get_content(doc_2),
                          SOME_TEXT_CONTENT)
        doc_2_info = remote_client.get_info(doc_2)
        self.assertEquals(doc_2_info.name, 'Document 2.txt')
        self.assertEquals(doc_2_info.uid, doc_2)
        self.assertEquals(doc_2_info.digest_algorithm, 'md5')
        self.assertEquals(doc_2_info.get_digest(), SOME_TEXT_DIGEST)
        self.assertEquals(doc_2_info.folderish, False)

        remote_client.delete(doc_2)
        self.assertTrue(remote_client.exists(doc_1))
        self.assertFalse(remote_client.exists(doc_2))
        self.assertRaises(NotFound, remote_client.get_info, doc_2)

        # the document has been put in the trash by default
        self.assertTrue(remote_client.exists(doc_2, use_trash=False)
                        is not None)

        # the document is now physically deleted (by calling delete
        # a second time: the 'delete' transition will no longer be available
        # hence physical deletion is used as a fallback)
        remote_client.delete(doc_2, use_trash=False)
        self.assertFalse(remote_client.exists(doc_2, use_trash=False))
        self.assertRaises(NotFound, remote_client.get_info, doc_2,
                          use_trash=False)

        # Test folder deletion (with trash)
        folder_1 = remote_client.make_folder(self.workspace, 'A new folder')
        self.assertTrue(remote_client.exists(folder_1))
        folder_1_info = remote_client.get_info(folder_1)
        self.assertEquals(folder_1_info.name, 'A new folder')
        self.assertEquals(folder_1_info.uid, folder_1)
        self.assertIsNone(folder_1_info.digest_algorithm)
        self.assertIsNone(folder_1_info.get_digest())
        self.assertEquals(folder_1_info.folderish, True)

        doc_3 = remote_client.make_file(folder_1, 'Document 3.txt',
                                   content=SOME_TEXT_CONTENT)
        remote_client.delete(folder_1)
        self.assertFalse(remote_client.exists(folder_1))
        wait_for_deletion(remote_client, doc_3)

        self.assertFalse(remote_client.exists(doc_3))

        # Test folder deletion (without trash)
        folder_1 = remote_client.make_folder(self.workspace, 'A new folder')
        self.assertTrue(remote_client.exists(folder_1))
        folder_1_info = remote_client.get_info(folder_1)
        self.assertEquals(folder_1_info.name, 'A new folder')
        self.assertEquals(folder_1_info.uid, folder_1)
        self.assertIsNone(folder_1_info.digest_algorithm)
        self.assertIsNone(folder_1_info.get_digest())
        self.assertEquals(folder_1_info.folderish, True)

        doc_3 = remote_client.make_file(folder_1, 'Document 3.txt',
                                   content=SOME_TEXT_CONTENT)
        remote_client.delete(folder_1, use_trash=False)
        self.assertFalse(remote_client.exists(folder_1, use_trash=False))
        wait_for_deletion(remote_client, doc_3, use_trash=False)

    def test_complex_filenames(self):
        remote_client = self.remote_document_client_1
        # create another folder with the same title
        title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
        folder_1 = remote_client.make_folder(self.workspace,
                                             title_with_accents)
        folder_1_info = remote_client.get_info(folder_1)
        self.assertEquals(folder_1_info.name, title_with_accents)

        # create another folder with the same title
        title_with_accents = u"\xc7a c'est l'\xe9t\xe9 !"
        folder_2 = remote_client.make_folder(self.workspace,
                                             title_with_accents)
        folder_2_info = remote_client.get_info(folder_2)
        self.assertEquals(folder_2_info.name, title_with_accents)
        self.assertNotEquals(folder_1, folder_2)

        # Create a file
        # TODO: handle sanitization of the '/' character in local name
        long_filename = u"\xe9" * 50 + u"%$#!*()[]{}+_-=';:&^" + ".doc"
        file_1 = remote_client.make_file(folder_1, long_filename)
        file_1 = remote_client.get_info(file_1)
        self.assertEquals(file_1.name, long_filename)

    def test_missing_document(self):
        remote_client = self.remote_document_client_1
        self.assertRaises(NotFound, remote_client.get_info,
                      '/Something Missing')

    def test_get_children_info(self):
        remote_client = self.remote_document_client_1
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')
        file_1 = remote_client.make_file(self.workspace, 'File 1.txt',
                                              content="foo\n")

        # not a direct child of self.workspace
        remote_client.make_file(folder_1, 'File 2.txt', content="bar\n")

        # ignored files
        remote_client.make_file(self.workspace,
                                     '.File 2.txt', content="baz\n")
        remote_client.make_file(self.workspace,
                                     '~$File 2.txt', content="baz\n")
        remote_client.make_file(self.workspace,
                                     'File 2.txt~', content="baz\n")
        remote_client.make_file(self.workspace,
                                     'File 2.txt.swp', content="baz\n")
        remote_client.make_file(self.workspace,
                                     'File 2.txt.lock', content="baz\n")
        remote_client.make_file(self.workspace,
                                     'File 2.txt.LOCK', content="baz\n")
        remote_client.make_file(self.workspace,
                                     'File 2.txt.part', content="baz\n")

        workspace_children = remote_client.get_children_info(self.workspace)
        self.assertEquals(len(workspace_children), 3)
        self.assertEquals(workspace_children[0].uid, file_1)
        self.assertEquals(workspace_children[0].name, 'File 1.txt')
        self.assertEquals(workspace_children[1].uid, folder_1)
        self.assertEquals(workspace_children[1].name, 'Folder 1')
        self.assertEquals(workspace_children[2].uid, folder_2)
        self.assertEquals(workspace_children[2].name, 'Folder 2')

    def test_get_synchronization_roots_from_server(self):
        remote_client = self.remote_document_client_1
        # Check that the list of repositories can be introspected
        self.assertEquals(remote_client.get_repository_names(), ['default'])

        # By default no root is synchronized
        self.assertEquals(remote_client.get_roots(), [])

        # Register one root explicitly
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')
        folder_3 = remote_client.make_folder(self.workspace, 'Folder 3')
        remote_client.register_as_root(folder_1)

        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].name, 'Folder 1')

        # registetration is idem-potent
        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].name, 'Folder 1')

        remote_client.register_as_root(folder_2)
        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 2)
        self.assertEquals(roots[0].name, 'Folder 1')
        self.assertEquals(roots[1].name, 'Folder 2')

        remote_client.unregister_as_root(folder_1)
        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].name, 'Folder 2')

        # register new roots in another order
        remote_client.register_as_root(folder_3)
        remote_client.register_as_root(folder_1)
        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 3)
        self.assertEquals(roots[0].name, 'Folder 1')
        self.assertEquals(roots[1].name, 'Folder 2')
        self.assertEquals(roots[2].name, 'Folder 3')

        remote_client.delete(folder_1, use_trash=True)
        remote_client.delete(folder_3, use_trash=False)
        remote_client.unregister_as_root(folder_2)
        self.assertEquals(remote_client.get_roots(), [])

    def test_unregister_nested_roots(self):
        # Check that registering a parent folder of an existing root
        # automatically unregister sub folders to avoid synchronization
        # inconsistencies
        remote_client = self.remote_document_client_1
        # Check that the list of repositories can be introspected
        self.assertEquals(remote_client.get_repository_names(), ['default'])

        # By default no root is synchronized
        self.assertEquals(remote_client.get_roots(), [])
        folder = remote_client.make_folder(self.workspace, 'Folder')
        sub_folder_1 = remote_client.make_folder(folder, 'Sub Folder 1')
        sub_folder_2 = remote_client.make_folder(folder, 'Sub Folder 2')

        # Register the sub folders as roots
        remote_client.register_as_root(sub_folder_1)
        remote_client.register_as_root(sub_folder_2)
        self.assertEquals(len(remote_client.get_roots()), 2)

        # Register the parent folder as root
        remote_client.register_as_root(folder)
        roots = remote_client.get_roots()
        self.assertEquals(len(roots), 1)
        self.assertEquals(roots[0].uid, folder)

        # Unregister the parent folder
        remote_client.unregister_as_root(folder)
        self.assertEquals(len(remote_client.get_roots()), 0)

    def test_streaming_upload(self):
        remote_client = self.remote_document_client_1

        # Create a document by streaming a text file
        file_path = remote_client.make_tmp_file("Some content.")
        try:
            doc_ref = remote_client.stream_file(self.workspace, 'Streamed text file', file_path,
                                                filename='My streamed file.txt')
        finally:
            os.remove(file_path)
        self.assertEquals(remote_client.get_info(doc_ref).name,
                          'Streamed text file')
        self.assertEquals(remote_client.get_content(doc_ref), "Some content.")

        # Update a document by streaming a new text file
        file_path = remote_client.make_tmp_file("Other content.")
        try:
            remote_client.stream_update(doc_ref, file_path, filename='My updated file.txt')
        finally:
            os.remove(file_path)
        self.assertEquals(remote_client.get_content(doc_ref), "Other content.")

        # Create a document by streaming a binary file
        file_path = os.path.join(self.upload_tmp_dir, 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        doc_ref = remote_client.stream_file(self.workspace,
                                  'Streamed binary file', file_path)
        local_client = LocalClient(self.upload_tmp_dir)
        doc_info = remote_client.get_info(doc_ref)
        self.assertEquals(doc_info.name, 'Streamed binary file')
        self.assertEquals(doc_info.digest_algorithm, 'md5')
        self.assertEquals(doc_info.digest,
                          local_client.get_info('/testFile.pdf').get_digest())

    def test_bad_mime_type(self):
        remote_client = self.remote_document_client_1

        # Create a document by streaming a binary file
        file_path = os.path.join(self.upload_tmp_dir, 'testFile.pdf')
        copyfile('nxdrive/tests/resources/testFile.pdf', file_path)
        doc_ref = remote_client.stream_file(self.workspace,
                                  'Streamed binary file',
                                  file_path, mime_type='pdf')
        local_client = LocalClient(self.upload_tmp_dir)
        doc_info = remote_client.get_info(doc_ref)
        self.assertEquals(doc_info.name, 'Streamed binary file')
        print doc_info.digest_algorithm
        self.assertEquals(doc_info.digest,
                          local_client.get_info('/testFile.pdf').get_digest(digest_func=doc_info.digest_algorithm))

    def test_versioning(self):
        remote_client = self.remote_document_client_1
        doc = remote_client.make_file(self.workspace,
                                      'Document to version.txt',
                                      content="Initial content.")

        # Create version 1.0
        remote_client.create_version(doc, 'Major')
        versions = remote_client.get_versions(doc)
        self.assertEqual(len(versions), 1)
        version_1 = versions[0]
        version_1_uid = version_1[0]
        version_1_label = version_1[1]
        version_1_info = remote_client.get_info(version_1_uid,
                                                include_versions=True)
        self.assertEquals(version_1_info.name, 'Document to version.txt')
        self.assertEquals(version_1_label, '1.0')
        self.assertEquals(remote_client.get_content(version_1_uid),
                          "Initial content.")

        # Update doc and create version 1.1
        remote_client.update_content(doc, "Updated content.")
        remote_client.create_version(doc, 'Minor')
        versions = remote_client.get_versions(doc)
        self.assertEqual(len(versions), 2)
        version_2 = versions[1]
        version_2_uid = version_2[0]
        version_2_label = version_2[1]
        self.assertEquals(version_2_label, '1.1')
        self.assertEquals(remote_client.get_content(version_2_uid),
                          "Updated content.")

        # Update doc and restore it to version 1.0
        remote_client.update_content(doc, "Twice updated content.")
        self.assertEquals(remote_client.get_content(doc),
                          "Twice updated content.")
        remote_client.restore_version(version_1_uid)
        self.assertEquals(remote_client.get_content(doc),
                          "Initial content.")

        # Restore doc to version 1.1
        remote_client.restore_version(version_2_uid)
        self.assertEquals(remote_client.get_content(doc),
                          "Updated content.")

    def test_get_update_info(self):
        remote_client = self.remote_document_client_1
        update_info = remote_client.get_update_info()
        self.assertIsNotNone(update_info.get('serverVersion'))
        self.assertIsNotNone(update_info.get('updateSiteURL'))

    def test_lock_unlock(self):
        remote = self.remote_document_client_1
        doc_id = remote.make_file(self.workspace, 'TestLocking.txt', 'File content')
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))
        remote.lock(doc_id)
        self.assertTrue(self.remote_restapi_client_1.is_locked(doc_id))
        remote.unlock(doc_id)
        self.assertFalse(self.remote_restapi_client_1.is_locked(doc_id))
