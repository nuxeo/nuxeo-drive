import time
from logging import ERROR, getLogger
from pathlib import Path
from typing import Any, Dict
from unittest.mock import patch
from urllib.error import URLError
from uuid import uuid4

import pytest
from nuxeo.exceptions import Forbidden, HTTPError

from nxdrive.constants import FILE_BUFFER_SIZE, WINDOWS
from nxdrive.direct_edit import DirectEdit
from nxdrive.exceptions import DocumentAlreadyLocked, NotFound, ThreadInterrupt
from nxdrive.objects import Blob, NuxeoDocumentInfo
from nxdrive.options import Options
from nxdrive.utils import normalized_path, parse_protocol_url, safe_filename

from .. import ensure_no_exception, env
from ..utils import random_png
from . import LocalTest, make_tmp_file
from .common import OneUserNoSync, OneUserTest, TwoUsersTest

log = getLogger(__name__)

# File size to trigger chunk downloads
DOWNLOAD_CHUNK_FILE_SIZE = int(Options.tmp_file_limit * 1024 * 1024) * 2


def direct_edit_is_starting(*args, **kwargs):
    log.info("Direct Edit is starting: args=%r, kwargs=%r", args, kwargs)


def open_local_file(*args, **kwargs):
    log.info("Opening local file: args=%r, kwargs=%r", args, kwargs)


class DirectEditSetup:
    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        # Test setup
        self.direct_edit: DirectEdit = self.manager_1.direct_edit
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
            self.direct_edit.stop_client(None)


class MixinTests(DirectEditSetup):
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
                    info["user"],
                    info["download_url"],
                )
            else:
                self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            local_path = Path(f"{doc_id}_{safe_filename(xpath)}/{filename}")
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

        doc_id = self.remote.make_file_with_blob(
            "/", main_filename, b"Initial content."
        )
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
        doc_id = self.remote.make_file_with_no_blob("/", filename)
        self.remote.attach_blob(doc_id, b"Initial content.", filename)
        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            xpath = "file:content"

            local_path = Path(f"{doc_id}_{safe_filename(xpath)}/{filename}")
            assert self.local.exists(local_path)
            self.wait_sync(fail_if_timeout=False)
            self.local.set_remote_id(local_path.parent, b"", name="nxdirecteditxpath")

            content = b"Initial content."
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
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")
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

            # Verify the cleanup don't delete document
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
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")
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
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")
        self._direct_edit_update(doc_id, filename, b"Test")

    def test_forbidden_edit(self):
        """
        A user may lost its rights to edit a file (or even access to the document).
        In that case, a notification is shown and the Direct Edit is stopped early.
        """
        filename = "secret-file.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")

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
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")
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

    def test_direct_edit_proxy(self):
        """
        Trying to Direct Edit a proxy is not allowed.
        In that case, the file edition must be aborted an a notification must be shown.
        """
        filename = "proxy-test.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Plein de clics.")
        folder_uid = self.remote.make_folder("/", "proxy_folder")
        folder_info = self.remote.get_info(folder_uid)
        proxy_file = self.remote.create_proxy(doc_id, folder_info.path)

        assert proxy_file["isProxy"] is True

        assert not self.direct_edit._prepare_edit(self.nuxeo_url, proxy_file["uid"])
        local_path = Path(f"/{doc_id}_file-content/{filename}")
        assert not self.local.exists(local_path)

    def test_direct_edit_413_error(self):
        """
        When uploading changes to a proxy, an HTTPError 413 is raised.
        The upload must be skipped and the error caught.
        """

        def upload(*_, **__):
            """Mocked remote.upload method that raises a HTTPError 413"""
            raise HTTPError(
                status=413, message="Mock'ed Client Error: Request Entity Too Large"
            )

        filename = "error-413-test.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial")

        with patch.object(
            self.engine_1.remote, "upload", new=upload
        ), ensure_no_exception():
            with pytest.raises(AssertionError) as exc:
                self._direct_edit_update(doc_id, filename, b"New")
            # The update must have failed
            assert "assert b'Initial' == b'New'" in str(exc.value)
        # And the error queue should still be be empty, the bad upload has beend discarded
        assert self.direct_edit._error_queue.empty()

    def test_direct_edit_502_error(self):
        """
        When uploading changes to a proxy, an HTTPError 502 is raised.
        The upload must be postponed and the error caught.
        """
        count = 0
        original_upload = self.engine_1.remote.upload

        def upload(*args, **kwargs):
            """Mocked remote.upload method that raises a HTTPError 502"""
            nonlocal count

            count += 1
            if count < 3:
                raise HTTPError(status=502, message="Mock'ed Client Error: Bad Gateway")
            return original_upload(*args, **kwargs)

        filename = "error-502-test.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial")

        with patch.object(
            self.engine_1.remote, "upload", new=upload
        ), ensure_no_exception():
            self._direct_edit_update(doc_id, filename, b"New")

        # And the error queue should still be be empty, the bad upload has beend discarded
        assert self.direct_edit._error_queue.empty()

        expected = "because server is unavailable"
        assert any(expected in str(log) for log in self._caplog.records)

    def test_direct_edit_max_error(self):
        """
        When uploading changes to the server, recurrent errors can happen.
        The upload must be retried maximum *Options.max_errors* times before being dropped.
        """
        filename = "error.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")
        local_path = f"/{doc_id}_file-content/{filename}"

        with patch.object(self.manager_1, "open_local_file", new=open_local_file):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            self.wait_sync(timeout=2, fail_if_timeout=False)

        # Simulate server error
        bad_remote = self.get_bad_remote()
        bad_remote.make_upload_raise(
            HTTPError(status=404, message="Mock'ed Client Error: Not Found")
        )

        with patch.object(self.engine_1, "remote", new=bad_remote):
            # Update file content
            self.local.update_content(local_path, b"Updated")
            self.wait_sync(timeout=30)

        # The file should _not_ be updated on the server
        content = self.remote.get_blob(self.remote.get_info(doc_id))
        assert content == b"Initial content."

        # There must be no error has the upload has been dropped.
        assert self.direct_edit._error_queue.empty()

        # Upload errors dict must be empty
        assert not self.direct_edit._upload_errors

    def test_orphan_should_unlock(self):
        """
        NXDRIVE-2129: Unlocking of previously edited file when the app crashed in-between.
        Step 1/3 (mimic the previous edition):
            - create the remote file
            - the file is locally downloaded
            - the file is remotely locked by the previous Direct Edit
            - the file is still present locally
        Step 2/3:
            - Drive restart and try to cleanup previous session files
            - the list of all locked files is retrieved
            - call to _autolock_orphans() to process the list of locked files
            - _autolock_orphans() should fill the lock queue with 'unlock_orphan'
            - call to _handle_lock_queue() to process the lock_queue
        Step 3/3: The file is still present locally and has not been unlocked
        Expected behaviour: The file has been cleaned locally and unlocked locally/remotely
        """

        def orphan_unlocked(path: Path) -> None:
            """
            Mocked autolock.orphan_unlocked method.
            Path is normalized before because safe_long_path() is not used yet in the database.
            """
            self.direct_edit._manager.dao.unlock_path(normalized_path(path))

        # STEP 1
        filename = "orphan-test.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")
        local_path = Path(f"{doc_id}_file-content/{filename}")
        edit_local_path = self.direct_edit._folder / local_path

        # File is locked remotely
        self.remote.lock(doc_id)

        # Download file
        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        assert self.local.exists(local_path)
        self.wait_sync(timeout=2, fail_if_timeout=False)

        # File is locked locally
        self.direct_edit._manager.dao.lock_path(edit_local_path, 42, doc_id)

        assert self.remote.is_locked(doc_id)

        # STEP 2
        # Drive restart and try to cleanup files
        self.direct_edit._cleanup()
        # Orphans download should not be cleaned by _cleanup
        assert self.local.exists(local_path)

        with ensure_no_exception():
            # Mimic autolocker._poll()
            self.direct_edit._autolock_orphans([edit_local_path])

        # Ensure that lock queue has been filled with an unlock_orphan item
        assert not self.direct_edit._lock_queue.empty()
        item = self.direct_edit._lock_queue.get_nowait()
        assert item == (local_path, "unlock_orphan")

        # Re-put elem in lock_queue after check
        self.direct_edit._lock_queue.put(item)

        with patch.object(
            self.direct_edit.autolock, "orphan_unlocked", new=orphan_unlocked
        ), ensure_no_exception():
            self.direct_edit._handle_lock_queue()
            # lock queue should be empty after call to _handle_lock_queue()
            assert self.direct_edit._lock_queue.empty()

        # STEP 3

        # The file has been unlocked locally and remotely
        assert not self.remote.is_locked(doc_id)
        assert not self.direct_edit._manager.dao.get_locked_paths()

    def test_forbidden_lock_in_lock_queue(self):
        filename = "file.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")
        local_path = Path(f"{doc_id}_file-content/{filename}")

        def lock(_):
            msg = (
                "(Mock'ed) Failed to invoke operation: Document.Lock, Failed "
                "to invoke operation Document.Lock, Privilege 'WriteProperties' "
                "is not granted to 'USER'"
            )
            raise Forbidden(message=msg)

        def forbidden_signal(self, *args, **kwargs):
            nonlocal received
            received = True

        received = False
        self.direct_edit.directEditLockError.connect(forbidden_signal)

        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)

        # Ensure that lock queue is filled with an lock item
        assert self.direct_edit._lock_queue.empty()
        self.direct_edit._lock_queue.put((local_path, "lock"))
        assert not self.direct_edit._lock_queue.empty()

        with patch.object(
            self.manager_1, "open_local_file", new=open_local_file
        ), patch.object(self.engine_1.remote, "lock", new=lock), ensure_no_exception():
            # self.direct_edit.use_autolock = True
            self.direct_edit._handle_lock_queue()
            assert received

        # The lock queue should be empty after now
        assert self.direct_edit._lock_queue.empty()

        # Ensure there zere no handled exception
        assert not any(log.levelno >= ERROR for log in self._caplog.records)

    def test_unlock_in_lock_queue_error_503(self):
        filename = "file.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")
        local_path = Path(f"{doc_id}_file-content/{filename}")

        def unlock(*args, **kwargs):
            msg = "(Mock'ed) <html><body><b>Http/1.1 Service Unavailable</b></body> </html>"
            raise HTTPError(status=503, message=msg)

        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)

        # Ensure that lock queue is filled with an lock item
        assert self.direct_edit._lock_queue.empty()
        self.direct_edit._lock_queue.put((local_path, "unlock"))
        assert not self.direct_edit._lock_queue.empty()

        with patch.object(
            self.manager_1, "open_local_file", new=open_local_file
        ), patch.object(
            self.engine_1.remote, "unlock", new=unlock
        ), ensure_no_exception():
            self.direct_edit._handle_lock_queue()

        # The unlock queue should not be empty as the file is in error
        assert not self.direct_edit._lock_queue.empty()

        # Ensure there zere no handled exception
        assert not any(log.levelno >= ERROR for log in self._caplog.records)

        # Retry the unlock
        with ensure_no_exception():
            self.direct_edit._handle_lock_queue()

        # The unlock queue should be empty after now
        assert self.direct_edit._lock_queue.empty()

    def test_direct_edit_version(self):
        from nuxeo.models import BufferBlob

        filename = "versionedfile.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")

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
        """Updates should be sent when the network is up again."""
        filename = "networkless file.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Initial content.")

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
            self.wait_sync(timeout=12, fail_if_timeout=False)
            assert (
                self.remote.get_blob(self.remote.get_info(doc_id)) == b"Updated twice"
            )

    def test_note_edit(self):
        filename = "Mode op\xe9ratoire.txt"
        content = "Content of file 1 Avec des accents h\xe9h\xe9.".encode("utf-8")
        # make_file() will make use of the FileManager and thus creating a Note
        doc_id = self.remote.make_file("/", filename, content=content)
        self._direct_edit_update(
            doc_id, filename, b"Atol de PomPom Gali", xpath="note:note"
        )

    def test_edit_document_with_folderish_facet(self):
        """Ensure we can Direct Edit documents that have the Folderish facet."""

        filename = "picture-as-folder.png"
        content = random_png(size=42)
        # make_file() will make use of the FileManager and thus creating a Picture document
        doc_id = self.remote.make_file("/", filename, content=content)

        # Add the Folderish facet
        self.remote.execute(
            command="Document.AddFacet", input_obj=doc_id, facet="Folderish"
        )

        # Ensure the doc type is Picture and has the Folderish facet
        info = self.remote.get_info(doc_id)
        assert info.doc_type == "Picture"
        assert info.folderish

        content_updated = random_png(size=24)
        self._direct_edit_update(doc_id, filename, content_updated)

    def test_blob_without_digest(self):
        """It should be possible to edit a document having a blob without digest.
        It is the case when using a third-party provider like Amazon S3 with accelerate endpoint.
        """

        from_dict_orig = Blob.from_dict

        def from_dict(blob: Dict[str, Any]) -> Blob:
            # Alter digest stuff
            blob["digest"] = None
            blob["digestAlgorithm"] = None
            return from_dict_orig(blob)

        filename = "picture-digestless.png"
        content = random_png(size=42)
        # make_file() will make use of the FileManager and thus creating a Picture document
        doc_id = self.remote.make_file("/", filename, content=content)

        scheme, host = self.nuxeo_url.split("://")
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        content_updated = random_png(size=24)
        with patch.object(Blob, "from_dict", new=from_dict), ensure_no_exception():
            self._direct_edit_update(doc_id, filename, content_updated, url=url)

    def test_blob_with_non_standard_digest(self):
        """It should be possible to edit a document having a blob with a non-standard digest.
        It is the case when using a third-party provider (S3, LiveProxy, ... ).
        """

        from_dict_orig = Blob.from_dict

        def from_dict(blob: Dict[str, Any]) -> Blob:
            # Alter digest stuff
            blob["digest"] += "-2"
            blob.pop("digestAlgorithm", None)
            return from_dict_orig(blob)

        filename = "picture-with-non-standard-digest.png"
        content = random_png(size=42)
        # make_file() will make use of the FileManager and thus creating a Picture document
        doc_id = self.remote.make_file("/", filename, content=content)

        scheme, host = self.nuxeo_url.split("://")
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        content_updated = random_png(size=24)
        with patch.object(Blob, "from_dict", new=from_dict), ensure_no_exception():
            self._direct_edit_update(doc_id, filename, content_updated, url=url)

    @pytest.mark.xfail(reason="NXDRIVE-2496")
    def test_blob_with_non_standard_digest_and_standard_algo(self):
        """It should be possible to edit a document having a blob with a non-standard digest
        but with a standard algorithm.
        """

        from_dict_orig = Blob.from_dict

        def from_dict(blob: Dict[str, Any]) -> Blob:
            # Alter digest stuff
            blob["digest"] += "-2"
            return from_dict_orig(blob)

        filename = "picture-with-non-standard-digest.png"
        content = random_png(size=42)
        # make_file() will make use of the FileManager and thus creating a Picture document
        doc_id = self.remote.make_file("/", filename, content=content)

        scheme, host = self.nuxeo_url.split("://")
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        content_updated = random_png(size=24)
        with patch.object(Blob, "from_dict", new=from_dict), ensure_no_exception():
            self._direct_edit_update(doc_id, filename, content_updated, url=url)

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
        filename = "RO file.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"content")

        with patch.object(NuxeoDocumentInfo, "from_dict", new=from_dict):
            self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert received

    def test_corrupted_download_ok_if_retried(self):
        """Test corrupted downloads that finally works."""

        # Create the test file
        filename = "download corrupted.txt"
        doc_id = self.remote.make_file_with_blob(
            "/", filename, b"0" * DOWNLOAD_CHUNK_FILE_SIZE
        )
        url = f"nxfile/default/{doc_id}/file:content/{filename}"
        tmp_file = self.direct_edit._get_tmp_file(doc_id, filename)

        # Start Direct Edit'ing the document
        try_count = 0

        def callback(_):
            """Make the download callback to alter the temporary file before the first downloaded chunk."""
            nonlocal try_count
            try_count += 1
            if try_count < 2:
                tmp_file.write_bytes(b"1")

        original_request = self.engine_1.remote.client.request

        def request(*args, **kwargs):
            """We need to inspect headers to catch if "Range" is defined.
            If that header is set, it means that a download is resumed, and it should not as
            a corrupted download must be restarted from ground.
            """
            headers = kwargs.get("headers", {})
            assert "Range" not in headers
            return original_request(*args, **kwargs)

        # Retry the download, it should throw a CorruptedFile error and start the download from the ground
        with patch.object(self.engine_1.remote.client, "request", new=request):
            file = self.direct_edit._prepare_edit(
                self.nuxeo_url, doc_id, download_url=url, callback=callback
            )
            assert try_count > 2
            assert isinstance(file, Path)
            assert file.is_file()

    def test_corrupted_download_complete_failure(self):
        """Test corrupted downloads that never works."""

        # Create the test file
        filename = "download corrupted.txt"
        doc_id = self.remote.make_file_with_blob(
            "/", filename, b"0" * DOWNLOAD_CHUNK_FILE_SIZE
        )
        url = f"nxfile/default/{doc_id}/file:content/{filename}"
        tmp_file = self.direct_edit._get_tmp_file(doc_id, filename)

        # Start Direct Edit'ing the document

        def callback(_):
            """Make the download callback to alter the temporary file before each downloaded chunk."""
            tmp_file.write_bytes(b"1")

        # The download will be retried several times without success
        file = self.direct_edit._prepare_edit(
            self.nuxeo_url, doc_id, download_url=url, callback=callback
        )
        assert not file

    @Options.mock()
    def test_corrupted_download_but_no_integrity_check(self):
        """Test corrupted downloads that finally works because there is not integrity check."""

        # Create the test file
        filename = "download corrupted but it's OK.txt"
        doc_id = self.remote.make_file_with_blob(
            "/", filename, b"0" * DOWNLOAD_CHUNK_FILE_SIZE
        )

        Options.disabled_file_integrity_check = True
        original_request = self.engine_1.remote.client.request

        def request(*args, **kwargs):
            """We need to inspect headers to catch if "Range" is defined.
            If that header is set, it means that a download is resumed, and it should not as
            a corrupted download must be restarted from ground.
            """
            headers = kwargs.get("headers", {})
            assert "Range" not in headers
            return original_request(*args, **kwargs)

        def callback(_):
            """Make the download raise a CorruptedFile error."""
            nonlocal try_count
            try_count += 1
            if try_count < 2:
                tmp_file.write_bytes(b"1")

        # Start Direct Edit'ing the document
        try_count = 0
        tmp_file = self.direct_edit._get_tmp_file(doc_id, filename)
        with patch.object(self.engine_1.remote.client, "request", new=request):
            url = f"nxfile/default/{doc_id}/file:content/{filename}"
            file = self.direct_edit._prepare_edit(
                self.nuxeo_url, doc_id, download_url=url, callback=callback
            )
            assert isinstance(file, Path)
            assert file.is_file()

            expected = "disabled_file_integrity_check is True, skipping"
            assert any(expected in str(log) for log in self._caplog.records)

    def test_resumed_download(self):
        """Test a download that failed for some reason. The next edition will resume the download.
        We do not want that: a fresh download should be made every time.
        """

        def request(*args, **kwargs):
            """We need to inspect headers to catch if "Range" is defined.
            If that header is set, it means that a download is resumed, and it should not.
            """
            headers = kwargs.get("headers", {})
            assert "Range" not in headers
            return request_orig(*args, **kwargs)

        request_orig = self.engine_1.remote.client.request

        # Create the test file
        filename = "download resumed.txt"
        doc_id = self.remote.make_file_with_blob(
            "/", filename, b"0" * DOWNLOAD_CHUNK_FILE_SIZE
        )

        # Simulate a partially downloaded file
        tmp_path = self.direct_edit._get_tmp_file(doc_id, filename)
        tmp_path.write_bytes(b"0" * FILE_BUFFER_SIZE)

        # Start Direct Edit'ing the document
        with patch.object(self.engine_1.remote.client, "request", new=request):
            url = f"nxfile/default/{doc_id}/file:content/{filename}"
            file = self.direct_edit._prepare_edit(
                self.nuxeo_url, doc_id, download_url=url
            )
            assert isinstance(file, Path)
            assert file.is_file()

    def test_self_locked_file(self):
        filename = "Mode operatoire.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")
        self.remote.lock(doc_id)
        self._direct_edit_update(doc_id, filename, b"Test")

    def test_url_with_spaces(self):
        scheme, host = self.nuxeo_url.split("://")
        filename = "My file with spaces.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")

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
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")

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

    def test_double_lock_same_user(self):
        filename = "Mode opératoire¹.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")

        # First time: OK
        assert self.direct_edit._lock(self.remote, doc_id)

        # Second time: OK
        assert self.direct_edit._lock(self.remote, doc_id)


class TestDirectEdit(OneUserTest, MixinTests):
    """Direct Edit in "normal" mode, i.e.: when synchronization features are enabled."""

    def test_synced_file(self):
        """Test the fact that instead of downloading the file, we get it from the local sync folder."""
        filename = "M'ode opératoire ツ .txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists(f"/{filename}")

        def download(*_, **__):
            """
            Patch Remote.download() and Remote.get_blob()
            to be able to check that nothing will
            be downloaded as local data is already there.
            """
            assert 0, "No download should be done!"

        with patch.object(self.engine_1.remote, "download", new=download), patch.object(
            self.engine_1.remote, "get_blob", new=download
        ), ensure_no_exception():
            path = self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert isinstance(path, Path)

        assert not list(self.engine_1.dao.get_downloads())

    @pytest.mark.skipif(not WINDOWS, reason="Windows only")
    def test_sync_folder_different_partitions(self):
        """Ensure we can rename a file between different partitions."""
        second_partoche = Path(env.SECOND_PARTITION)
        if not second_partoche.is_dir():
            self.app.quit()
            pytest.skip(f"There is no such {second_partoche!r} partition.")

        local_folder = second_partoche / str(uuid4())
        local_folder.mkdir()

        with patch.object(self.engine_1, "download_dir", new=local_folder):
            # Ensure folders are on different partitions
            assert self.manager_1.home.drive != self.engine_1.download_dir.drive

            filename = "M'ode opératoire ツ .txt"
            doc_id = self.remote.make_file_with_blob("/", filename, b"Some content.")

            # Here we should not end on such error:
            # OSError: [WinError 17] The system cannot move the file to a different disk drive
            path = self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
            assert isinstance(path, Path)

            self._direct_edit_update(doc_id, filename, b"Test different partitions")

    def test_multiple_editions_on_unsynced_document(self):
        """Direct Edit'ing a file that is not synced must work every time.
        Before NXDRIVE-1824, only the 1st time was working, then any try
        to Direct Edit the document was failing.
        """

        filename = "multiplication des pains.txt"
        doc_id = self.remote.make_file_with_blob("/", filename, b"Plein de pains.")
        scheme, host = self.nuxeo_url.split("://")
        url = (
            f"nxdrive://edit/{scheme}/{host}"
            f"/user/{self.user_1}"
            "/repo/default"
            f"/nxdocid/{doc_id}"
            f"/filename/{filename}"
            f"/downloadUrl/nxfile/default/{doc_id}"
            f"/file:content/{filename}"
        )

        # Filter the root to remove local data
        ws_path = f"/{self.engine_1.dao.get_state_from_local(Path('/')).remote_ref}"
        self.engine_1.add_filter(ws_path)
        self.wait_sync()
        assert not self.local.get_children_info("/")

        # Edit several times the document, it must work
        self._direct_edit_update(doc_id, filename, b"Pain 1", url=url)
        self._direct_edit_update(doc_id, filename, b"Pain 2", url=url)
        self._direct_edit_update(doc_id, filename, b"Pain 3")
        self._direct_edit_update(doc_id, filename, b"Pain 4")


class TestDirectEditNoSync(OneUserNoSync, MixinTests):
    """Direct Edit should work when synchronization features are not enabled."""

    pass


class TestDirectEditLock(TwoUsersTest, DirectEditSetup):
    def test_locked_file(self):
        def locked_file_signal(self, *args, **kwargs):
            nonlocal received
            received = True

        received = False
        filename = "Mode operatoire.txt"
        doc_id = self.remote.make_file_with_no_blob("/", filename)
        self.remote_document_client_2.lock(doc_id)
        self.direct_edit.directEditLocked.connect(locked_file_signal)
        self.direct_edit._prepare_edit(self.nuxeo_url, doc_id)
        assert received

    def test_double_lock_different_user(self):
        filename = "Mode opératoire².txt"
        doc_id = self.remote.make_file_with_no_blob("/", filename)

        # Lock the document with user 1
        assert self.direct_edit._lock(self.remote, doc_id)

        # Try to lock with user 2, it must fail
        with pytest.raises(DocumentAlreadyLocked) as exc:
            self.direct_edit._lock(self.remote_2, doc_id)
        assert str(exc.value) == f"Document already locked by {self.user_1!r}"

    def test_unlock_different_user(self):
        filename = "test_unlock_different_user.txt"
        doc_id = self.remote.make_file_with_no_blob("/", filename)

        # Lock the document with user 1
        assert self.direct_edit._lock(self.remote, doc_id)

        with ensure_no_exception():
            # Try to unlock with user 2, should return True for purge
            assert self.direct_edit._unlock(self.remote_2, doc_id, "ref")

    def test_unlock_different_user_error_500(self):
        filename = "test_unlock_different_user.txt"
        doc_id = self.remote.make_file_with_no_blob("/", filename)

        def unlock(*_, **__):
            """
            Patch Remote.unlock() so that it raises
            a specific HTTPError.
            """
            err = f"(Mock'ed) Document already locked by {self.user_1}"
            raise HTTPError(status=500, message=err)

        with patch.object(self.remote_2, "unlock", new=unlock), ensure_no_exception():
            # Try to unlock with user 2, should return True for purge
            assert self.direct_edit._unlock(self.remote_2, doc_id, "ref")
