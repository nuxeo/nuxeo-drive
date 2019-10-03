# coding: utf-8
import time
from logging import getLogger
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch
from urllib.error import URLError

import pytest
from nuxeo.exceptions import Forbidden
from nxdrive.exceptions import DocumentAlreadyLocked, NotFound, ThreadInterrupt
from nxdrive.objects import NuxeoDocumentInfo
from nxdrive.utils import parse_protocol_url, safe_os_filename

from . import LocalTest, make_tmp_file
from .common import OneUserTest, TwoUsersTest
from ..utils import random_png

log = getLogger(__name__)


def direct_edit_is_starting(*args, **kwargs):
    log.info("DirectEdit is starting: args=%r, kwargs=%r", args, kwargs)


def open_local_file(*args, **kwargs):
    log.info("Opening local file: args=%r, kwargs=%r", args, kwargs)


class DirectEditSetup:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        # Test setup
        self.direct_edit = self.manager_1.direct_edit
        self.direct_edit.directEditUploadCompleted.connect(self.app.sync_completed)
        self.direct_edit.directEditStarting.connect(direct_edit_is_starting)
        self.direct_edit.start()

        self.remote = self.remote_document_client_1
        self.local = LocalTest(self.nxdrive_conf_folder_1 / "edit")

        # Fix needed only for tests: as Engine.suspend_engine() is used as callback
        # for Remote.upload_callback, and it first checks if the Engine is started.
        # This is not the case, but we need to simulate that in order the make tests
        # pass.
        self.engine_1._stopped = False

        yield

        # Test teardown
        self.direct_edit._stop_watchdog()
        self.direct_edit.stop()
        with pytest.raises(ThreadInterrupt):
            self.direct_edit.stop_client()


class TestDirectEdit(OneUserTest, DirectEditSetup):
    def _direct_edit_update(
        self,
        doc_id: str,
        filename: str,
        content: bytes,
        xpath: str = "file:content",
        url: str = None,
    ):
        # Download file
        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            if url:
                info = parse_protocol_url(url)
                self.direct_edit.edit(
                    info["server_url"],
                    info["doc_id"],
                    user=info["user"],
                    download_url=info["download_url"],
                )
            else:
                self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            local_path = Path(f"{doc_id}_{safe_os_filename(xpath)}/{filename}")
            assert self.local.exists(local_path)
            self.wait_sync(fail_if_timeout=False)
            self.local.delete_final(local_path)

            # Update file content
            self.local.update_content(local_path, content)
            self.wait_sync()
            doc_info = self.remote.get_info(doc_id)
            assert self.remote.get_blob(doc_info, xpath=xpath) == content

            # Update file content twice
            content += b" updated"
            self.local.update_content(local_path, content)
            self.wait_sync()
            doc_info = self.remote.get_info(doc_id)
            assert self.remote.get_blob(doc_info, xpath=xpath) == content

    def test_attachments(self):
        main_filename = "mainfile.txt"
        attachment_filename = "attachment.txt"

        doc_id = self.remote.make_file("/", main_filename, content=b"Initial content.")
        file_path = make_tmp_file(self.upload_tmp_dir, "Attachment content")
        self.remote.upload(
            file_path,
            command="Blob.AttachOnDocument",
            filename=attachment_filename,
            document=self.remote.check_ref(doc_id),
            xpath="files:files",
        )
        scheme, host = self.nuxeo_url.split("://")
        attachment_xpath = "files:files/0/file"
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{attachment_filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/{attachment_xpath}/{attachment_filename}"
        )
        self._direct_edit_update(doc_id, main_filename, b"Main test")
        self._direct_edit_update(
            doc_id,
            attachment_filename,
            b"Attachment test",
            xpath=attachment_xpath,
            url=url,
        )

    def test_no_xpath(self):
        filename = "test_file.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Initial content.")
        content = b"Initial content."
        xpath = "file:content"

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            local_path = Path(f"{doc_id}_{safe_os_filename(xpath)}/{filename}")
            assert self.local.exists(local_path)
            self.wait_sync(fail_if_timeout=False)
            self.local.set_remote_id(local_path.parent, b"", name="nxdirecteditxpath")

            # Update file content
            self.local.update_content(local_path, content)
            self.wait_sync()
            doc_info = self.remote.get_info(doc_id)
            assert self.remote.get_blob(doc_info, xpath=xpath) == content

            # Update file content twice
            content += b" updated"
            self.local.update_content(local_path, content)
            self.wait_sync()
            doc_info = self.remote.get_info(doc_id)
            assert self.remote.get_blob(doc_info, xpath=xpath) == content

    def test_cleanup(self):
        filename = "Mode op\xe9ratoire.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")
        local_path = f"/{doc_id}_file-content/{filename}"

        # Download file
        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert self.local.exists(local_path)
            self.wait_sync(timeout=2, fail_if_timeout=False)
            self.direct_edit.stop()

            # Update file content
            self.local.update_content(local_path, b"Test")
            # Create empty folder (NXDRIVE-598)
            self.local.make_folder("/", "emptyfolder")

            # Verify the cleanup dont delete document
            self.direct_edit._cleanup()
            assert self.local.exists(local_path)
            assert self.remote.get_blob(self.remote.get_info(doc_id)) != b"Test"

            # Verify it reupload it
            self.direct_edit.start()
            self.wait_sync(timeout=2, fail_if_timeout=False)
            assert self.local.exists(local_path)
            assert self.remote.get_blob(self.remote.get_info(doc_id)) == b"Test"

            # Verify it is cleanup if sync
            self.direct_edit.stop()
            self.direct_edit._cleanup()
            assert not self.local.exists(local_path)

    def test_cleanup_document_not_found(self):
        """If a file does not exist on the server, it should be deleted locally."""

        def extract_edit_info(ref: Path):
            raise NotFound()

        filename = "Mode op\xe9ratoire.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")
        local_path = f"/{doc_id}_file-content/{filename}"

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert self.local.exists(local_path)
            self.wait_sync(timeout=2, fail_if_timeout=False)
            self.direct_edit.stop()

            # Simulate a deletion of the file on the server
            with patch.object(
                self.direct_edit, "_extract_edit_info", extract_edit_info
            ):
                # Verify the cleanup does delete the file
                self.direct_edit._cleanup()
                assert not self.local.exists(local_path)

            # Verify nothing more is done after a restart
            self.direct_edit.start()
            self.wait_sync(timeout=2, fail_if_timeout=False)
            assert not self.local.exists(local_path)

    def test_filename_encoding(self):
        filename = "Mode op\xe9ratoire.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")
        self._direct_edit_update(doc_id, filename, b"Test")

    def test_forbidden_edit(self):
        """
        A user may lost its rights to edit a file (or even access to the document).
        In that case, a notification is shown and the DirectEdit is stopped early.
        """
        filename = "secret-file.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Initial content.")

        def forbidden_signal(self, *args, **kwargs):
            nonlocal received
            received = True

        received = False
        self.direct_edit.directEditForbidden.connect(forbidden_signal)

        bad_remote = self.get_bad_remote()
        bad_remote.make_server_call_raise(Forbidden(message="Mock"))

        with patch.object(
            self.manager_1, "open_local_file", new=open_local_file
        ), patch.object(self.engine_1, "remote", new=bad_remote):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert received

    def test_forbidden_upload(self):
        """
        A user may lost its rights to edit a file (or even access to the document).
        In that case, a notification is shown and the document is remove dfrom the upload queue.
        """
        filename = "secret-file2.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Initial content.")
        local_path = f"/{doc_id}_file-content/{filename}"

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            self.wait_sync(timeout=2, fail_if_timeout=False)

            # Simulate server error
            bad_remote = self.get_bad_remote()
            bad_remote.make_upload_raise(Forbidden(message="Mock"))

            with patch.object(self.engine_1, "remote", new=bad_remote):
                # Update file content
                self.local.update_content(local_path, b"Updated")
                time.sleep(5)

                # The file should _not_ be updated on the server
                assert (
                    self.remote.get_blob(self.remote.get_info(doc_id))
                    == b"Initial content."
                )

    def test_direct_edit_version(self):
        from nuxeo.models import BufferBlob

        filename = "versionedfile.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Initial content.")

        self.remote.execute(
            command="Document.CreateVersion",
            input_obj=f"doc:{doc_id}",
            increment="Major",
        )
        blob = BufferBlob(data="Updated content.", name=filename, mimetype="text/plain")
        batch = self.remote.uploads.batch()
        batch.upload(blob)
        self.remote.execute(
            command="Blob.AttachOnDocument", document=doc_id, input_obj=batch.get(0)
        )
        self.remote.execute(
            command="Document.CreateVersion",
            input_obj=f"doc:{doc_id}",
            increment="Major",
        )
        versions = self.remote.execute(
            command="Document.GetVersions", input_obj=f"doc:{doc_id}"
        )
        entries = versions["entries"]
        assert len(entries) == 2

        version_to_edit = None
        for entry in entries:
            if entry.get("properties").get("uid:major_version") == 1:
                version_to_edit = entry

        assert version_to_edit
        doc_id = version_to_edit["uid"]

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            assert not self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            local_path = Path(f"/{doc_id}_file-content/{filename}")
            assert not self.local.exists(local_path)

    def test_network_loss(self):
        """ Updates should be sent when the network is up again. """
        filename = "networkless file.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Initial content.")

        # Download file
        local_path = f"/{doc_id}_file-content/{filename}"

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            self.wait_sync(timeout=2, fail_if_timeout=False)

            # Simulate server error
            bad_remote = self.get_bad_remote()
            error = URLError(
                "[Errno 10051] (Mock) socket operation was attempted to an unreachable network"
            )
            bad_remote.make_upload_raise(error)

            with patch.object(self.engine_1, "remote", new=bad_remote):
                # Update file content
                self.local.update_content(local_path, b"Updated")
                time.sleep(5)
                self.local.update_content(local_path, b"Updated twice")
                time.sleep(5)
                # The file should not be updated on the server
                assert (
                    self.remote.get_blob(self.remote.get_info(doc_id))
                    == b"Initial content."
                )

            # Check the file is reuploaded when the network come again
            # timout=30 to ensure the file is removed from the blacklist (which have a 30 sec delay)
            self.wait_sync(timeout=30, fail_if_timeout=False)
            assert (
                self.remote.get_blob(self.remote.get_info(doc_id)) == b"Updated twice"
            )

    def test_note_edit(self):
        remote = self.remote_1
        info = remote.get_filesystem_root_info()
        workspace_id = remote.get_fs_children(info.uid)[0].uid
        content = "Content of file 1 Avec des accents h\xe9h\xe9.".encode("utf-8")
        file_id = remote.make_file(
            workspace_id, "Mode op\xe9ratoire.txt", content=content
        ).uid
        doc_id = file_id.split("#")[-1]
        self._direct_edit_update(
            doc_id, "Mode op\xe9ratoire.txt", b"Atol de PomPom Gali", xpath="note:note"
        )

    def test_edit_document_with_folderish_facet(self):
        """ Ensure we can DirectEdit documents that have the Folderish facet. """

        filename = "picture-as-folder.png"
        content = random_png(size=42)
        doc_id = self.remote.make_file(
            "/", filename, content=content, doc_type="Picture"
        )

        # Add the Folderish facet
        self.remote.execute(
            command="Document.AddFacet", input_obj=doc_id, facet="Folderish"
        )

        content_updated = random_png(size=24)
        self._direct_edit_update(doc_id, filename, content_updated)

    def test_permission_readonly(self):
        """Opening a read-only document is prohibited."""

        from_dict_orig = NuxeoDocumentInfo.from_dict

        def from_dict(doc: Dict[str, Any], parent_uid: str = None) -> NuxeoDocumentInfo:
            info = from_dict_orig(doc)
            # Remove the Write permission to trigger the read-only signal
            info.permissions.remove("Write")
            return info

        def readonly_signal(self, *args, **kwargs):
            nonlocal received
            received = True

        received = False
        self.direct_edit.directEditReadonly.connect(readonly_signal)
        doc_id = self.remote.make_file("/", "RO file.txt", content=b"content")

        with patch.object(NuxeoDocumentInfo, "from_dict", new=from_dict):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert received

    def test_self_locked_file(self):
        filename = "Mode operatoire.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")
        self.remote.lock(doc_id)
        self._direct_edit_update(doc_id, filename, b"Test")

    def test_url_with_spaces(self):
        scheme, host = self.nuxeo_url.split("://")
        filename = "My file with spaces.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")

        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        self._direct_edit_update(doc_id, filename, b"Test", url=url)

    def test_url_with_accents(self):
        scheme, host = self.nuxeo_url.split("://")
        filename = "éèáä.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")

        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        self._direct_edit_update(doc_id, filename, b"Test", url=url)

    def test_multiple_editions_on_unsynced_document(self):
        """Direct Edit'ing a file that is not synced must work everytime.
        Before NXDRIVE-1824, only the 1st time was working, then any try
        to Direct Edit the document was failing.
        """

        filename = "multiplication des pains.txt"
        uid = self.remote.make_file("/", filename, content=b"Plein de pains.")
        scheme, host = self.nuxeo_url.split("://")
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{uid}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{uid}"
            f"/file:content/{filename}"
        )

        # Filter the root to remove local data
        ws_path = f"/{self.engine_1.dao.get_state_from_local('/').remote_ref}"
        self.engine_1.add_filter(ws_path)
        self.wait_sync()
        assert not self.local.get_children_info("/")

        # Edit several times the document, it must work
        self._direct_edit_update(uid, filename, b"Pain 1", url=url)
        self._direct_edit_update(uid, filename, b"Pain 2", url=url)
        self._direct_edit_update(uid, filename, b"Pain 3")
        self._direct_edit_update(uid, filename, b"Pain 4")

    def test_double_lock_same_user(self):
        filename = "Mode opératoire¹.txt"
        uid = self.remote.make_file("/", filename, content=b"Some content.")

        # First time: OK
        assert self.direct_edit._lock(self.remote, uid)

        # Second time: OK
        assert self.direct_edit._lock(self.remote, uid)


class TestDirectEditLock(TwoUsersTest, DirectEditSetup):
    def test_locked_file(self):
        def locked_file_signal(self, *args, **kwargs):
            nonlocal received
            received = True

        received = False
        filename = "Mode operatoire.txt"
        doc_id = self.remote.make_file("/", filename, content=b"Some content.")
        self.remote_document_client_2.lock(doc_id)
        self.direct_edit.directEditLocked.connect(locked_file_signal)
        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        assert received

    def test_double_lock_different_user(self):
        filename = "Mode opératoire².txt"
        uid = self.remote.make_file("/", filename, content=b"Some content.")

        # Lock the document with user 1
        assert self.direct_edit._lock(self.remote, uid)

        # Try to lock with user 2, it must fail
        with pytest.raises(DocumentAlreadyLocked) as exc:
            self.direct_edit._lock(self.remote_2, uid)
        assert str(exc.value) == f"Document already locked by {self.user_1!r}"
