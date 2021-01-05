import hashlib
import operator
from pathlib import Path
from shutil import copyfile
from tempfile import mkdtemp

import pytest

from nxdrive.exceptions import NotFound

from . import LocalTest, make_tmp_file
from .common import FS_ITEM_ID_PREFIX, OneUserTest, TwoUsersTest


class TestRemoteFileSystemClient(OneUserTest):
    def setUp(self):
        # Bind the test workspace as sync root for user 1
        remote_doc = self.remote_document_client_1
        remote = self.remote_1
        remote_doc.register_as_root(self.workspace)

        # Fetch the id of the workspace folder item
        info = remote.get_filesystem_root_info()
        self.workspace_id = remote.get_fs_children(info.uid)[0].uid

    #
    # Test the API common with the local client API
    #

    def test_get_fs_info(self):
        remote = self.remote_1

        # Check file info
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        info = remote.get_fs_info(fs_item_id)
        assert info is not None
        assert info.name == "Document 1.txt"
        assert info.uid == fs_item_id
        assert info.parent_uid == self.workspace_id
        assert not info.folderish
        if info.last_contributor:
            assert info.last_contributor == self.user_1
        digest_algorithm = info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of doc 1.")
        assert info.digest == digest
        file_uid = fs_item_id.rsplit("#", 1)[1]
        # NXP-17827: nxbigile has been replace to nxfile, keep handling both
        url = f"/default/{file_uid}/blobholder:0/Document%201.txt"
        cond = info.download_url in (f"nxbigfile{url}", f"nxfile{url}")
        assert cond

        # Check folder info
        fs_item_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        info = remote.get_fs_info(fs_item_id)
        assert info is not None
        assert info.name == "Folder 1"
        assert info.uid == fs_item_id
        assert info.parent_uid == self.workspace_id
        assert info.folderish
        if info.last_contributor:
            assert info.last_contributor == self.user_1
        assert info.digest_algorithm is None
        assert info.digest is None
        assert info.download_url is None

        # Check non existing file info
        fs_item_id = FS_ITEM_ID_PREFIX + "fakeId"
        with pytest.raises(NotFound):
            remote.get_fs_info(fs_item_id)

    def test_get_content(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Check file with content
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.get_content(fs_item_id) == b"Content of doc 1."

        # Check file without content
        doc_uid = remote_doc.make_file_with_no_blob(self.workspace, "Document 2.txt")
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        with pytest.raises(NotFound):
            remote.get_content(fs_item_id)

    def test_stream_content(self):
        remote = self.remote_1

        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        file_path = self.local_test_folder_1 / "Document 1.txt"
        file_out = Path(mkdtemp()) / file_path.name
        tmp_file = remote.stream_content(
            fs_item_id, file_path, file_out, engine_uid=self.engine_1.uid
        )
        assert tmp_file.exists()
        assert tmp_file.name == "Document 1.txt"
        assert tmp_file.read_bytes() == b"Content of doc 1."

    def test_get_fs_children(self):
        remote = self.remote_1

        # Create documents
        folder_1_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        folder_2_id = remote.make_folder(self.workspace_id, "Folder 2").uid
        file_1_id = remote.make_file(
            self.workspace_id, "File 1", content=b"Content of file 1."
        ).uid
        file_2_id = remote.make_file(
            folder_1_id, "File 2", content=b"Content of file 2."
        ).uid

        # Check workspace children
        workspace_children = remote.get_fs_children(self.workspace_id)
        assert workspace_children is not None
        assert len(workspace_children) == 3
        assert workspace_children[0].uid == folder_1_id
        assert workspace_children[0].name == "Folder 1"
        assert workspace_children[0].folderish
        assert workspace_children[1].uid == folder_2_id
        assert workspace_children[1].name == "Folder 2"
        assert workspace_children[1].folderish
        assert workspace_children[2].uid == file_1_id
        assert workspace_children[2].name == "File 1"
        assert not workspace_children[2].folderish

        # Check folder_1 children
        folder_1_children = remote.get_fs_children(folder_1_id)
        assert folder_1_children is not None
        assert len(folder_1_children) == 1
        assert folder_1_children[0].uid == file_2_id
        assert folder_1_children[0].name == "File 2"

    def test_scroll_descendants(self):
        remote = self.remote_1

        # Create documents
        folder_1 = remote.make_folder(self.workspace_id, "Folder 1").uid
        folder_2 = remote.make_folder(self.workspace_id, "Folder 2").uid
        file_1 = remote.make_file(
            self.workspace_id, "File 1.txt", content=b"Content of file 1."
        ).uid
        file_2 = remote.make_file(
            folder_1, "File 2.txt", content=b"Content of file 2."
        ).uid

        # Wait for ES completion
        self.wait()

        # Check workspace descendants in one breath, ordered by remote path
        scroll_res = remote.scroll_descendants(self.workspace_id, None)
        assert isinstance(scroll_res, dict)
        assert "scroll_id" in scroll_res
        descendants = sorted(scroll_res["descendants"], key=operator.attrgetter("name"))
        assert len(descendants) == 4

        # File 1.txt
        assert descendants[0].uid == file_1
        assert descendants[0].name == "File 1.txt"
        assert not descendants[0].folderish
        # File 2.txt
        assert descendants[1].name == "File 2.txt"
        assert not descendants[1].folderish
        assert descendants[1].uid == file_2
        # Folder 1
        assert descendants[2].uid == folder_1
        assert descendants[2].name == "Folder 1"
        assert descendants[2].folderish
        # Folder 2
        assert descendants[3].uid == folder_2
        assert descendants[3].name == "Folder 2"
        assert descendants[3].folderish

        # Check workspace descendants in several steps, ordered by remote path
        descendants = []
        scroll_id = None
        while True:
            scroll_res = remote.scroll_descendants(
                self.workspace_id, scroll_id, batch_size=2
            )
            assert isinstance(scroll_res, dict)
            scroll_id = scroll_res["scroll_id"]
            partial_descendants = scroll_res["descendants"]
            if not partial_descendants:
                break
            descendants.extend(partial_descendants)
        descendants = sorted(descendants, key=operator.attrgetter("name"))
        assert len(descendants) == 4

        # File 1.txt
        assert descendants[0].uid == file_1
        assert descendants[0].name == "File 1.txt"
        assert not descendants[0].folderish
        # File 2.txt
        assert descendants[1].name == "File 2.txt"
        assert not descendants[1].folderish
        assert descendants[1].uid == file_2
        # Folder 1
        assert descendants[2].uid == folder_1
        assert descendants[2].name == "Folder 1"
        assert descendants[2].folderish
        # Folder 2
        assert descendants[3].uid == folder_2
        assert descendants[3].name == "Folder 2"
        assert descendants[3].folderish

    def test_make_folder(self):
        remote = self.remote_1

        fs_item_info = remote.make_folder(self.workspace_id, "My new folder")
        assert fs_item_info is not None
        assert fs_item_info.name == "My new folder"
        assert fs_item_info.folderish
        assert fs_item_info.digest_algorithm is None
        assert fs_item_info.digest is None
        assert fs_item_info.download_url is None

    def test_make_file(self):
        remote = self.remote_1

        # Check File document creation
        fs_item_info = remote.make_file(
            self.workspace_id, "My new file.odt", content=b"Content of my new file."
        )
        assert fs_item_info is not None
        assert fs_item_info.name == "My new file.odt"
        assert not fs_item_info.folderish
        digest_algorithm = fs_item_info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of my new file.")
        assert fs_item_info.digest == digest

        # Check Note document creation
        fs_item_info = remote.make_file(
            self.workspace_id, "My new note.txt", content=b"Content of my new note."
        )
        assert fs_item_info is not None
        assert fs_item_info.name == "My new note.txt"
        assert not fs_item_info.folderish
        digest_algorithm = fs_item_info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of my new note.")
        assert fs_item_info.digest == digest

    def test_make_file_custom_encoding(self):
        remote = self.remote_1

        # Create content encoded in utf-8 and cp1252
        unicode_content = "\xe9"  # e acute
        utf8_encoded = unicode_content.encode("utf-8")
        utf8_digest = hashlib.md5(utf8_encoded).hexdigest()
        cp1252_encoded = unicode_content.encode("cp1252")

        # Make files with this content
        utf8_fs_id = remote.make_file(
            self.workspace_id, "My utf-8 file.txt", content=utf8_encoded
        ).uid
        cp1252_fs_id = remote.make_file(
            self.workspace_id, "My cp1252 file.txt", content=cp1252_encoded
        ).uid

        # Check content
        utf8_content = remote.get_content(utf8_fs_id)
        assert utf8_content == utf8_encoded
        cp1252_content = remote.get_content(cp1252_fs_id)
        assert cp1252_content == utf8_encoded

        # Check digest
        utf8_info = remote.get_fs_info(utf8_fs_id)
        assert utf8_info.digest == utf8_digest
        cp1252_info = remote.get_fs_info(cp1252_fs_id)
        assert cp1252_info.digest == utf8_digest

    def test_update_content(self):
        remote = self.remote_1

        # Create file
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid

        # Check file update
        remote.update_content(fs_item_id, b"Updated content of doc 1.")
        assert remote.get_content(fs_item_id) == b"Updated content of doc 1."

    def test_delete(self):
        remote = self.remote_1

        # Create file
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.fs_exists(fs_item_id)

        # Delete file
        remote.delete(fs_item_id)
        assert not remote.fs_exists(fs_item_id)

    def test_exists(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Check existing file system item
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.fs_exists(fs_item_id)

        # Check non existing file system item (non existing document)
        fs_item_id = FS_ITEM_ID_PREFIX + "fakeId"
        assert not remote.fs_exists(fs_item_id)

        # Check non existing file system item (document without content)
        doc_uid = remote_doc.make_file_with_no_blob(self.workspace, "Document 2.txt")
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        assert not remote.fs_exists(fs_item_id)

    #
    # Test the API specific to the remote file system client
    #

    def test_get_fs_item(self):
        remote = self.remote_1

        # Check file item
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        fs_item = remote.get_fs_item(fs_item_id)
        assert fs_item is not None
        assert fs_item["name"] == "Document 1.txt"
        assert fs_item["id"] == fs_item_id
        assert not fs_item["folder"]

        # Check file item using parent id
        fs_item = remote.get_fs_item(fs_item_id, parent_fs_item_id=self.workspace_id)
        assert fs_item is not None
        assert fs_item["name"] == "Document 1.txt"
        assert fs_item["id"] == fs_item_id
        assert fs_item["parentId"] == self.workspace_id

        # Check folder item
        fs_item_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        fs_item = remote.get_fs_item(fs_item_id)
        assert fs_item is not None
        assert fs_item["name"] == "Folder 1"
        assert fs_item["id"] == fs_item_id
        assert fs_item["folder"]

        # Check non existing file system item
        fs_item_id = FS_ITEM_ID_PREFIX + "fakeId"
        assert remote.get_fs_item(fs_item_id) is None

    def test_streaming_upload(self):
        remote = self.remote_1

        # Create a document by streaming a text file
        file_path = make_tmp_file(remote.upload_tmp_dir, b"Some content.")
        try:
            fs_item_info = remote.stream_file(
                self.workspace_id, file_path, filename="My streamed file.txt"
            )
        finally:
            file_path.unlink()
        fs_item_id = fs_item_info.uid
        assert fs_item_info.name == "My streamed file.txt"
        assert remote.get_content(fs_item_id) == b"Some content."

        # Update a document by streaming a new text file
        file_path = make_tmp_file(remote.upload_tmp_dir, b"Other content.")
        try:
            fs_item_info = remote.stream_update(
                fs_item_id, file_path, filename="My updated file.txt"
            )
        finally:
            file_path.unlink()
        assert fs_item_info.uid == fs_item_id
        assert fs_item_info.name == "My updated file.txt"
        assert remote.get_content(fs_item_id) == b"Other content."

        # Create a document by streaming a binary file
        file_path = self.upload_tmp_dir / "testFile.pdf"
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        local_client = LocalTest(self.upload_tmp_dir)
        assert fs_item_info.name == "testFile.pdf"
        assert (
            fs_item_info.digest == local_client.get_info("/testFile.pdf").get_digest()
        )

    def test_mime_type_doc_type_association(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Upload a PDF file, should create a File document
        file_path = self.upload_tmp_dir / "testFile.pdf"
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        doc_type = remote_doc.get_info(doc_uid).doc_type
        assert doc_type == "File"

        # Upload a JPG file, should create a Picture document
        file_path = self.upload_tmp_dir / "cat.jpg"
        copyfile(self.location / "resources" / "files" / "cat.jpg", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        doc_type = remote_doc.get_info(doc_uid).doc_type
        assert doc_type == "Picture"

    def test_unregister_nested_roots(self):
        # Check that registering a parent folder of an existing root
        # automatically unregister sub folders to avoid synchronization
        # inconsistencies
        remote = self.remote_document_client_1

        # By default no root is synchronized
        remote.unregister_as_root(self.workspace)
        self.wait()
        assert not remote.get_roots()

        folder = remote.make_folder(self.workspace, "Folder")
        sub_folder_1 = remote.make_folder(folder, "Sub Folder 1")
        sub_folder_2 = remote.make_folder(folder, "Sub Folder 2")

        # Register the sub folders as roots
        remote.register_as_root(sub_folder_1)
        remote.register_as_root(sub_folder_2)
        assert len(remote.get_roots()) == 2

        # Register the parent folder as root
        remote.register_as_root(folder)
        roots = remote.get_roots()
        assert len(roots) == 1
        assert roots[0].uid == folder

        # Unregister the parent folder
        remote.unregister_as_root(folder)
        assert not remote.get_roots()

    def test_lock_unlock(self):
        remote = self.remote_document_client_1
        doc_id = remote.make_file(
            self.workspace, "TestLocking.txt", content=b"File content"
        )

        status = remote.is_locked(doc_id)
        assert not status
        remote.lock(doc_id)
        assert remote.is_locked(doc_id)

        remote.unlock(doc_id)
        assert not remote.is_locked(doc_id)

    @staticmethod
    def _get_digest(algorithm: str, content: bytes) -> str:
        hasher = getattr(hashlib, algorithm)
        if hasher is None:
            raise RuntimeError(f"Unknown digest algorithm: {algorithm}")
        return hasher(content).hexdigest()


class TestRemoteFileSystemClient2(TwoUsersTest):
    def setUp(self):
        # Bind the test workspace as sync root for user 1
        remote_doc = self.remote_document_client_1
        remote = self.remote_1
        remote_doc.register_as_root(self.workspace)

        # Fetch the id of the workspace folder item
        info = remote.get_filesystem_root_info()
        self.workspace_id = remote.get_fs_children(info.uid)[0].uid

    def test_modification_flags_locked_document(self):
        remote = self.remote_1
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid

        # Check flags for a document that isn't locked
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        assert info.lock_owner is None
        assert info.lock_created is None

        # Check flags for a document locked by the current user
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        remote.lock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        lock_info_available = remote.get_fs_item(fs_item_id).get("lockInfo") is not None
        if lock_info_available:
            assert info.lock_owner == self.user_1
            assert info.lock_created is not None
        remote.unlock(doc_uid)

        # Check flags for a document locked by another user
        self.remote_2.lock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert not info.can_rename
        assert not info.can_update
        assert not info.can_delete
        if lock_info_available:
            assert info.lock_owner == self.user_2
            assert info.lock_created is not None

        # Check flags for a document unlocked by another user
        self.remote_2.unlock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        assert info.lock_owner is None
        assert info.lock_created is None
