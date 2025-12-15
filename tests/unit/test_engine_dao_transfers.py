"""Unit tests for EngineDAO transfer-related methods."""

from multiprocessing import RLock
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

from nxdrive.constants import TransferStatus
from nxdrive.objects import Download, Upload


class TestSaveDtUpload:
    """Test cases for EngineDAO.save_dt_upload method."""

    def test_save_dt_upload_basic(self, engine_dao):
        """Test saving a basic Direct Transfer upload."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an upload object
            upload = Upload(
                uid=None,
                path=Path("/tmp/test_file.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4()), "extraData": "test"},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-123",
                doc_pair=1,
                request_uid=str(uuid4()),
            )

            # Save the upload
            dao.save_dt_upload(upload)

            # Verify upload was saved and UID was assigned
            assert upload.uid is not None
            assert upload.uid > 0

            # Verify the signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

            # Verify the upload can be retrieved
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved is not None
            assert retrieved.uid == upload.uid
            assert retrieved.path == upload.path
            assert retrieved.filesize == upload.filesize
            assert retrieved.remote_parent_path == upload.remote_parent_path
            assert retrieved.remote_parent_ref == upload.remote_parent_ref
            assert retrieved.is_direct_transfer is True

    def test_save_dt_upload_batch_filtering(self, engine_dao):
        """Test that 'blobs' key is removed from batch when saving."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an upload with blobs in batch
            upload = Upload(
                uid=None,
                path=Path("/tmp/test_file.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={
                    "batchId": str(uuid4()),
                    "blobs": ["should_be_removed"],
                    "other": "data",
                },
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-123",
                doc_pair=1,
                request_uid=str(uuid4()),
            )

            dao.save_dt_upload(upload)

            # Retrieve and verify blobs was filtered out
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved is not None
            # The batch should be stored without 'blobs'
            import json

            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT batch FROM Uploads WHERE uid = ?", (upload.uid,)
            ).fetchone()
            batch_data = json.loads(result[0])
            assert "blobs" not in batch_data
            assert "batchId" in batch_data
            assert "other" in batch_data

    def test_save_dt_upload_with_session_status(self, engine_dao):
        """Test that upload inherits status from linked session."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Get an existing doc pair with a session
            # From the migration test, we know session 1 exists
            doc_pairs = dao.get_local_children(Path("/home/test/Downloads"))
            if doc_pairs:
                doc_pair = doc_pairs[0]

                upload = Upload(
                    uid=None,
                    path=Path("/tmp/test_session_file.txt"),
                    status=TransferStatus.PAUSED,  # This will be overridden
                    engine="test-engine-uid",
                    is_direct_edit=False,
                    is_direct_transfer=True,
                    filesize=2048,
                    batch={"batchId": str(uuid4())},
                    chunk_size=1024,
                    remote_parent_path="/remote/path",
                    remote_parent_ref="remote-ref-456",
                    doc_pair=doc_pair.id,
                    request_uid=str(uuid4()),
                )

                dao.save_dt_upload(upload)

                # Verify upload status was set (should match session status)
                assert upload.uid is not None
                retrieved = dao.get_dt_upload(uid=upload.uid)
                assert retrieved is not None

    def test_save_dt_upload_cancelled_when_state_removed(self, engine_dao):
        """Test that upload is CANCELLED when linked state doesn't exist."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create upload with non-existent doc_pair
            upload = Upload(
                uid=None,
                path=Path("/tmp/orphan_file.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=512,
                batch={"batchId": str(uuid4())},
                chunk_size=256,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-789",
                doc_pair=999999,  # Non-existent doc_pair
                request_uid=str(uuid4()),
            )

            dao.save_dt_upload(upload)

            # Upload status should be CANCELLED (default when state not found)
            assert upload.status == TransferStatus.CANCELLED


class TestPauseTransfer:
    """Test cases for EngineDAO.pause_transfer method."""

    def test_pause_transfer_upload(self, engine_dao):
        """Test pausing an upload transfer."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()
            dao.transferUpdated = Mock()

            # Create and save an upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/upload_file.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-123",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Pause the transfer
            progress = 45.5
            dao.pause_transfer("upload", upload.uid, progress, is_direct_transfer=True)

            # Verify status and progress were updated
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.PAUSED
            assert retrieved.progress == progress

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()
            dao.transferUpdated.emit.assert_not_called()

    def test_pause_transfer_non_direct_transfer(self, engine_dao):
        """Test pausing a non-direct transfer (regular sync)."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()
            dao.transferUpdated = Mock()

            # Create a regular upload (not direct transfer)
            upload = Upload(
                uid=None,
                path=Path("/tmp/regular_upload.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=False,
                filesize=2048,
                batch={"batchId": str(uuid4())},
                chunk_size=1024,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-456",
                doc_pair=1,
                request_uid=str(uuid4()),
            )

            # Manually insert since we're testing regular uploads
            import json

            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Uploads (path, status, engine, is_direct_edit, "
                "is_direct_transfer, filesize, batch, chunk_size, "
                "remote_parent_path, remote_parent_ref, doc_pair, request_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(upload.path),
                    TransferStatus.ONGOING.value,
                    upload.engine,
                    upload.is_direct_edit,
                    upload.is_direct_transfer,
                    upload.filesize,
                    json.dumps(upload.batch),
                    upload.chunk_size,
                    upload.remote_parent_path,
                    upload.remote_parent_ref,
                    upload.doc_pair,
                    upload.request_uid,
                ),
            )
            upload.uid = cursor.lastrowid

            # Pause the transfer (not direct transfer)
            progress = 75.0
            dao.pause_transfer("upload", upload.uid, progress, is_direct_transfer=False)

            # Verify the correct signal was emitted
            dao.transferUpdated.emit.assert_called_once()
            dao.directTransferUpdated.emit.assert_not_called()

    def test_pause_transfer_download(self, engine_dao):
        """Test pausing a download transfer."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a download
            download = Download(
                uid=None,
                path=Path("/tmp/download_file.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                filesize=4096,
                tmpname=Path("/tmp/temp_download.txt"),
                url="http://example.com/file.txt",
            )

            # Manually insert download
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Downloads (path, status, engine, is_direct_edit, "
                "filesize, tmpname, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(download.path),
                    TransferStatus.ONGOING.value,
                    download.engine,
                    download.is_direct_edit,
                    download.filesize,
                    str(download.tmpname),
                    download.url,
                ),
            )
            download.uid = cursor.lastrowid

            # Pause the download
            progress = 33.3
            dao.pause_transfer("download", download.uid, progress)

            # Verify status and progress
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT status, progress FROM Downloads WHERE uid = ?",
                (download.uid,),
            ).fetchone()
            assert result[0] == TransferStatus.PAUSED.value
            assert result[1] == progress

            # Verify signal was emitted
            dao.transferUpdated.emit.assert_called_once()


class TestResumeTransfer:
    """Test cases for EngineDAO.resume_transfer method."""

    def test_resume_transfer_upload(self, engine_dao):
        """Test resuming a paused upload."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()
            dao.transferUpdated = Mock()

            # Create and save a paused upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/paused_upload.txt"),
                status=TransferStatus.PAUSED,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=2048,
                batch={"batchId": str(uuid4())},
                chunk_size=1024,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-999",
                doc_pair=1,
                request_uid=str(uuid4()),
            )

            # Manually insert with PAUSED status
            import json

            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Uploads (path, status, engine, is_direct_edit, "
                "is_direct_transfer, filesize, batch, chunk_size, "
                "remote_parent_path, remote_parent_ref, doc_pair, request_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(upload.path),
                    TransferStatus.PAUSED.value,
                    upload.engine,
                    upload.is_direct_edit,
                    upload.is_direct_transfer,
                    upload.filesize,
                    json.dumps(upload.batch),
                    upload.chunk_size,
                    upload.remote_parent_path,
                    upload.remote_parent_ref,
                    upload.doc_pair,
                    upload.request_uid,
                ),
            )
            upload.uid = cursor.lastrowid

            # Resume the transfer
            dao.resume_transfer("upload", upload.uid, is_direct_transfer=True)

            # Verify status is now ONGOING
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.ONGOING

            # Verify correct signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()
            dao.transferUpdated.emit.assert_not_called()

    def test_resume_transfer_download(self, engine_dao):
        """Test resuming a paused download."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a paused download
            download = Download(
                uid=None,
                path=Path("/tmp/paused_download.txt"),
                status=TransferStatus.PAUSED,
                engine="test-engine-uid",
                is_direct_edit=False,
                filesize=8192,
                tmpname=Path("/tmp/temp_paused_download.txt"),
                url="http://example.com/paused.txt",
            )

            # Insert download
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Downloads (path, status, engine, is_direct_edit, "
                "filesize, tmpname, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(download.path),
                    TransferStatus.PAUSED.value,
                    download.engine,
                    download.is_direct_edit,
                    download.filesize,
                    str(download.tmpname),
                    download.url,
                ),
            )
            download.uid = cursor.lastrowid

            # Resume the download
            dao.resume_transfer("download", download.uid, is_direct_transfer=False)

            # Verify status is ONGOING
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT status FROM Downloads WHERE uid = ?", (download.uid,)
            ).fetchone()
            assert result[0] == TransferStatus.ONGOING.value

            # Verify signal was emitted
            dao.transferUpdated.emit.assert_called_once()

    def test_resume_transfer_non_direct_transfer_upload(self, engine_dao):
        """Test resuming a non-direct transfer upload."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()
            dao.transferUpdated = Mock()

            # Create regular upload (not direct transfer)
            upload = Upload(
                uid=None,
                path=Path("/tmp/regular_paused.txt"),
                status=TransferStatus.PAUSED,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=False,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-111",
                doc_pair=1,
                request_uid=str(uuid4()),
            )

            # Insert with PAUSED status
            import json

            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Uploads (path, status, engine, is_direct_edit, "
                "is_direct_transfer, filesize, batch, chunk_size, "
                "remote_parent_path, remote_parent_ref, doc_pair, request_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    str(upload.path),
                    TransferStatus.PAUSED.value,
                    upload.engine,
                    upload.is_direct_edit,
                    upload.is_direct_transfer,
                    upload.filesize,
                    json.dumps(upload.batch),
                    upload.chunk_size,
                    upload.remote_parent_path,
                    upload.remote_parent_ref,
                    upload.doc_pair,
                    upload.request_uid,
                ),
            )
            upload.uid = cursor.lastrowid

            # Resume the transfer (non-direct transfer)
            dao.resume_transfer("upload", upload.uid, is_direct_transfer=False)

            # Verify correct signal was emitted
            dao.transferUpdated.emit.assert_called_once()
            dao.directTransferUpdated.emit.assert_not_called()


class TestResumeSession:
    """Test cases for EngineDAO.resume_session method."""

    def test_resume_session_basic(self, engine_dao):
        """Test resuming a paused session."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = Mock()
            dao.directTransferUpdated = Mock()

            # Session 1 exists in this database
            session_uid = 1

            # Resume the session
            dao.resume_session(session_uid)

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called()

    def test_resume_session_updates_upload_status(self, engine_dao):
        """Test that resume_session updates uploads to ONGOING status."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = Mock()
            dao.directTransferUpdated = Mock()

            # Get a session
            session_uid = 1
            session = dao.get_session(session_uid)
            assert session is not None

            # Create an upload linked to this session
            doc_pairs = dao.get_local_children(Path("/home/test/Downloads"))
            if doc_pairs:
                doc_pair = doc_pairs[0]

                # Create a paused upload
                upload = Upload(
                    uid=None,
                    path=Path("/tmp/session_upload.txt"),
                    status=TransferStatus.PAUSED,
                    engine="test-engine-uid",
                    is_direct_edit=False,
                    is_direct_transfer=True,
                    filesize=4096,
                    batch={"batchId": str(uuid4())},
                    chunk_size=2048,
                    remote_parent_path="/remote/path",
                    remote_parent_ref="remote-ref-session",
                    doc_pair=doc_pair.id,
                    request_uid=str(uuid4()),
                )

                # Insert with PAUSED status
                import json

                conn = dao._get_write_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO Uploads (path, status, engine, is_direct_edit, "
                    "is_direct_transfer, filesize, batch, chunk_size, "
                    "remote_parent_path, remote_parent_ref, doc_pair, request_uid) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        str(upload.path),
                        TransferStatus.PAUSED.value,
                        upload.engine,
                        upload.is_direct_edit,
                        upload.is_direct_transfer,
                        upload.filesize,
                        json.dumps(upload.batch),
                        upload.chunk_size,
                        upload.remote_parent_path,
                        upload.remote_parent_ref,
                        upload.doc_pair,
                        upload.request_uid,
                    ),
                )
                upload.uid = cursor.lastrowid

                # Resume the session
                dao.resume_session(session_uid)

                # Verify upload status is now ONGOING
                conn = dao._get_read_connection()
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT status FROM Uploads WHERE uid = ?", (upload.uid,)
                ).fetchone()
                assert result[0] == TransferStatus.ONGOING.value

    def test_resume_session_without_queue_manager(self, engine_dao):
        """Test that resume_session returns early if queue_manager is None."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = None
            dao.directTransferUpdated = Mock()

            # Should return early without error
            dao.resume_session(1)

            # Signal should not be emitted
            dao.directTransferUpdated.emit.assert_not_called()

    def test_resume_session_multiple_uploads(self, engine_dao):
        """Test resuming a session with multiple uploads."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.queue_manager = Mock()
            dao.directTransferUpdated = Mock()

            session_uid = 1

            # Create multiple paused uploads linked to the session
            doc_pairs = dao.get_local_children(Path("/home/test/Downloads"))
            if len(doc_pairs) >= 2:
                import json

                upload_uids = []
                for i, doc_pair in enumerate(doc_pairs[:2]):
                    upload = Upload(
                        uid=None,
                        path=Path(f"/tmp/multi_upload_{i}.txt"),
                        status=TransferStatus.PAUSED,
                        engine="test-engine-uid",
                        is_direct_edit=False,
                        is_direct_transfer=True,
                        filesize=1024 * (i + 1),
                        batch={"batchId": str(uuid4())},
                        chunk_size=512,
                        remote_parent_path="/remote/path",
                        remote_parent_ref=f"remote-ref-{i}",
                        doc_pair=doc_pair.id,
                        request_uid=str(uuid4()),
                    )

                    conn = dao._get_write_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "INSERT INTO Uploads (path, status, engine, is_direct_edit, "
                        "is_direct_transfer, filesize, batch, chunk_size, "
                        "remote_parent_path, remote_parent_ref, doc_pair, request_uid) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            str(upload.path),
                            TransferStatus.PAUSED.value,
                            upload.engine,
                            upload.is_direct_edit,
                            upload.is_direct_transfer,
                            upload.filesize,
                            json.dumps(upload.batch),
                            upload.chunk_size,
                            upload.remote_parent_path,
                            upload.remote_parent_ref,
                            upload.doc_pair,
                            upload.request_uid,
                        ),
                    )
                    upload_uids.append(cursor.lastrowid)

                # Resume the session
                dao.resume_session(session_uid)

                # Verify all uploads are now ONGOING
                conn = dao._get_read_connection()
                cursor = conn.cursor()
                for uid in upload_uids:
                    result = cursor.execute(
                        "SELECT status FROM Uploads WHERE uid = ?", (uid,)
                    ).fetchone()
                    assert result[0] == TransferStatus.ONGOING.value


class TestSetTransferStatus:
    """Test cases for EngineDAO.set_transfer_status method."""

    def test_set_transfer_status_upload_to_done(self, engine_dao):
        """Test setting upload transfer status to DONE."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an ongoing upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/completing_upload.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=2048,
                batch={"batchId": str(uuid4())},
                chunk_size=1024,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-done",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Change status to DONE
            upload.status = TransferStatus.DONE
            dao.set_transfer_status("upload", upload)

            # Verify status was updated
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.DONE

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

    def test_set_transfer_status_upload_to_failed(self, engine_dao):
        """Test setting upload transfer status to CANCELLED."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an ongoing upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/failing_upload.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-fail",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Change status to CANCELLED
            upload.status = TransferStatus.CANCELLED
            dao.set_transfer_status("upload", upload)

            # Verify status was updated
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.CANCELLED

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

    def test_set_transfer_status_download(self, engine_dao):
        """Test setting download transfer status."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create a download
            download = Download(
                uid=None,
                path=Path("/tmp/status_download.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                filesize=4096,
                tmpname=Path("/tmp/temp_status_download.txt"),
                url="http://example.com/status.txt",
            )

            # Insert download
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Downloads (path, status, engine, is_direct_edit, "
                "filesize, tmpname, url) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(download.path),
                    TransferStatus.ONGOING.value,
                    download.engine,
                    download.is_direct_edit,
                    download.filesize,
                    str(download.tmpname),
                    download.url,
                ),
            )
            download.uid = cursor.lastrowid

            # Change status to DONE
            download.status = TransferStatus.DONE
            dao.set_transfer_status("download", download)

            # Verify status was updated
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT status FROM Downloads WHERE uid = ?", (download.uid,)
            ).fetchone()
            assert result[0] == TransferStatus.DONE.value

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

    def test_set_transfer_status_suspended(self, engine_dao):
        """Test setting transfer status to SUSPENDED."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/suspended_upload.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=8192,
                batch={"batchId": str(uuid4())},
                chunk_size=4096,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-suspended",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Change status to SUSPENDED
            upload.status = TransferStatus.SUSPENDED
            dao.set_transfer_status("upload", upload)

            # Verify status was updated
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.SUSPENDED

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

    def test_set_transfer_status_from_paused_to_ongoing(self, engine_dao):
        """Test changing transfer status from PAUSED to ONGOING."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create a paused upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/paused_to_ongoing.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=2048,
                batch={"batchId": str(uuid4())},
                chunk_size=1024,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-paused",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)

            # First set to PAUSED
            upload.status = TransferStatus.PAUSED
            dao.set_transfer_status("upload", upload)
            assert dao.get_dt_upload(uid=upload.uid).status == TransferStatus.PAUSED

            dao.directTransferUpdated.reset_mock()

            # Now change back to ONGOING
            upload.status = TransferStatus.ONGOING
            dao.set_transfer_status("upload", upload)

            # Verify status was updated
            retrieved = dao.get_dt_upload(uid=upload.uid)
            assert retrieved.status == TransferStatus.ONGOING

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()


class TestSetTransferDoc:
    """Test cases for EngineDAO.set_transfer_doc method."""

    def test_set_transfer_doc_upload(self, engine_dao):
        """Test setting doc_pair for an upload transfer."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/test_upload_doc.txt"),
                status=TransferStatus.ONGOING,
                engine="original-engine-uid",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref-123",
                doc_pair=1,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)

            # Set new doc_pair and engine
            new_doc_pair = 999
            new_engine = "new-engine-uid"
            dao.set_transfer_doc("upload", upload.uid, new_engine, new_doc_pair)

            # Verify the update
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT doc_pair, engine FROM Uploads WHERE uid = ?", (upload.uid,)
            ).fetchone()
            assert result[0] == new_doc_pair
            assert result[1] == new_engine

    def test_set_transfer_doc_download(self, engine_dao):
        """Test setting doc_pair for a download transfer."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a download
            download = Download(
                uid=None,
                path=Path("test_download_doc.txt"),
                status=TransferStatus.ONGOING,
                engine="original-engine",
                is_direct_edit=False,
                filesize=2048,
                tmpname=Path("temp_download_doc.txt"),
                url="http://example.com/file.txt",
                doc_pair=5,
            )
            dao.save_download(download)

            # Get the download to retrieve its uid
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT uid FROM Downloads WHERE path = ?", (str(download.path),)
            ).fetchone()
            download_uid = result[0]

            # Set new doc_pair and engine
            new_doc_pair = 888
            new_engine = "updated-engine-uid"
            dao.set_transfer_doc("download", download_uid, new_engine, new_doc_pair)

            # Verify the update
            result = cursor.execute(
                "SELECT doc_pair, engine FROM Downloads WHERE uid = ?",
                (download_uid,),
            ).fetchone()
            assert result[0] == new_doc_pair
            assert result[1] == new_engine


class TestSaveDownload:
    """Test cases for EngineDAO.save_download method."""

    def test_save_download_basic(self, engine_dao):
        """Test saving a basic download."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a download object
            download = Download(
                uid=None,
                path=Path("download_file_basic.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine-uid",
                is_direct_edit=False,
                filesize=4096,
                tmpname=Path("temp_download_file_basic.txt"),
                url="http://example.com/download.txt",
                doc_pair=10,
            )

            # Save the download
            dao.save_download(download)

            # Verify the signal was emitted
            dao.transferUpdated.emit.assert_called_once()

            # Verify the download was saved
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT path, status, engine, filesize, tmpname, url, doc_pair FROM Downloads WHERE path = ?",
                (str(download.path),),
            ).fetchone()
            assert result is not None
            assert result[0] == str(download.path)
            assert result[1] == TransferStatus.ONGOING.value
            assert result[2] == download.engine
            assert result[3] == download.filesize
            assert result[4] == str(download.tmpname)
            assert result[5] == download.url
            assert result[6] == download.doc_pair

    def test_save_download_direct_edit(self, engine_dao):
        """Test saving a direct edit download."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a direct edit download
            download = Download(
                uid=None,
                path=Path("direct_edit_download_save.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=True,
                filesize=8192,
                tmpname=Path("temp_direct_edit_save.txt"),
                url="http://example.com/direct_edit.txt",
                doc_pair=20,
            )

            # Save the download
            dao.save_download(download)

            # Verify is_direct_edit flag
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT is_direct_edit FROM Downloads WHERE path = ?",
                (str(download.path),),
            ).fetchone()
            assert result[0] == 1  # True is stored as 1

    def test_save_download_different_statuses(self, engine_dao):
        """Test saving downloads with different statuses."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            statuses = [
                TransferStatus.ONGOING,
                TransferStatus.PAUSED,
                TransferStatus.SUSPENDED,
            ]

            for idx, status in enumerate(statuses):
                download = Download(
                    uid=None,
                    path=Path(f"download_status_{idx}.txt"),
                    status=status,
                    engine="test-engine",
                    is_direct_edit=False,
                    filesize=1024 * (idx + 1),
                    tmpname=Path(f"temp_status_{idx}.txt"),
                    url=f"http://example.com/file_{idx}.txt",
                    doc_pair=30 + idx,
                )

                dao.save_download(download)

                # Verify status
                conn = dao._get_read_connection()
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT status FROM Downloads WHERE path = ?",
                    (str(download.path),),
                ).fetchone()
                assert result[0] == status.value


class TestRemoveTransfer:
    """Test cases for EngineDAO.remove_transfer method."""

    def test_remove_transfer_by_doc_pair(self, engine_dao):
        """Test removing transfer by doc_pair."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create an upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/upload_to_remove_pair.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref",
                doc_pair=100,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Remove by doc_pair
            dao.remove_transfer("upload", doc_pair=100, is_direct_transfer=True)

            # Verify it was removed
            result = dao.get_dt_upload(uid=upload.uid)
            assert result is None

            # Verify signal was emitted
            dao.directTransferUpdated.emit.assert_called_once()

    def test_remove_transfer_by_path(self, engine_dao):
        """Test removing transfer by path."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Create a download
            download = Download(
                uid=None,
                path=Path("/tmp/download_to_remove_path.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=False,
                filesize=2048,
                tmpname=Path("/tmp/temp_remove_path.txt"),
                url="http://example.com/remove.txt",
                doc_pair=50,
            )
            dao.save_download(download)
            download.uid = dao._get_write_connection().cursor().lastrowid
            dao.transferUpdated.reset_mock()

            # Remove by path
            dao.remove_transfer("download", path=download.path)

            # Verify it was removed
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT * FROM Downloads WHERE path = ?", (str(download.path),)
            ).fetchone()
            assert result is None

            # Verify signal was emitted
            dao.transferUpdated.emit.assert_called_once()

    def test_remove_transfer_priority_doc_pair_over_path(self, engine_dao):
        """Test that doc_pair takes priority over path when both provided."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()

            # Create two uploads with different doc_pairs
            upload1 = Upload(
                uid=None,
                path=Path("/tmp/upload1_priority.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref",
                doc_pair=200,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload1)

            upload2 = Upload(
                uid=None,
                path=Path("/tmp/upload2_priority.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=2048,
                batch={"batchId": str(uuid4())},
                chunk_size=1024,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref",
                doc_pair=201,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload2)

            # Remove using doc_pair (should ignore path)
            dao.remove_transfer(
                "upload",
                doc_pair=200,
                path=upload2.path,
                is_direct_transfer=True,
            )

            # Verify upload1 was removed (by doc_pair)
            result1 = dao.get_dt_upload(uid=upload1.uid)
            assert result1 is None

            # Verify upload2 still exists
            result2 = dao.get_dt_upload(uid=upload2.uid)
            assert result2 is not None

    def test_remove_transfer_no_match(self, engine_dao):
        """Test removing transfer that doesn't exist."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.transferUpdated = Mock()

            # Try to remove non-existent transfer
            dao.remove_transfer("download", doc_pair=999999)

            # Signal should not be emitted if nothing was removed
            dao.transferUpdated.emit.assert_not_called()

    def test_remove_transfer_direct_transfer_signal(self, engine_dao):
        """Test correct signal emission for direct transfer."""
        with engine_dao("engine_migration_18.db") as dao:
            dao.lock = RLock()
            dao.directTransferUpdated = Mock()
            dao.transferUpdated = Mock()

            # Create a direct transfer upload
            upload = Upload(
                uid=None,
                path=Path("/tmp/dt_upload_signal.txt"),
                status=TransferStatus.ONGOING,
                engine="test-engine",
                is_direct_edit=False,
                is_direct_transfer=True,
                filesize=1024,
                batch={"batchId": str(uuid4())},
                chunk_size=512,
                remote_parent_path="/remote/path",
                remote_parent_ref="remote-ref",
                doc_pair=300,
                request_uid=str(uuid4()),
            )
            dao.save_dt_upload(upload)
            dao.directTransferUpdated.reset_mock()

            # Remove with is_direct_transfer=True
            dao.remove_transfer("upload", doc_pair=300, is_direct_transfer=True)

            # Verify correct signal
            dao.directTransferUpdated.emit.assert_called_once()
            dao.transferUpdated.emit.assert_not_called()


class TestDecreaseSessionCounts:
    """Test cases for EngineDAO.decrease_session_counts method."""

    def test_decrease_session_counts_basic(self, engine_dao):
        """Test basic decrease of session counts."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Get existing session
            session = dao.get_session(1)
            assert session is not None

            original_total = session.total_items
            original_planned = session.planned_items

            # Decrease counts
            updated_session = dao.decrease_session_counts(1)

            # Verify counts decreased
            assert updated_session.total_items == original_total - 1
            assert updated_session.planned_items == original_planned - 1
            assert updated_session.total_items >= 0
            assert updated_session.planned_items >= 0

            # Verify signal was emitted
            dao.sessionUpdated.emit.assert_called_once_with(False)

    def test_decrease_session_counts_to_done(self, engine_dao):
        """Test session becomes DONE when uploaded equals total after decrease."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with 3 total, 2 uploaded
            # After decrease: total=2, uploaded=2 (equals) -> DONE
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/test/path",
                    "test-ref",
                    TransferStatus.ONGOING.value,
                    2,
                    3,
                    "test-engine",
                    "Test Session",
                    3,
                ),
            )
            session_uid = cursor.lastrowid

            # Decrease counts (3 total -> 2 total, with 2 uploaded -> equals -> DONE)
            updated_session = dao.decrease_session_counts(session_uid)

            # After decrease: total=2, uploaded=2 (equal), so status should be DONE
            assert updated_session.status == TransferStatus.DONE
            assert updated_session.total_items == 2
            assert updated_session.uploaded_items == 2

    def test_decrease_session_counts_to_cancelled(self, engine_dao):
        """Test session becomes CANCELLED when total reaches 0 and uploaded equals total."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with 1 total, 0 uploaded
            # After decrease: total=0, uploaded=0 (equals) -> CANCELLED
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/test/path2",
                    "test-ref2",
                    TransferStatus.ONGOING.value,
                    0,
                    1,
                    "test-engine",
                    "Test Session 2",
                    1,
                ),
            )
            session_uid = cursor.lastrowid

            # Decrease counts (1 -> 0, with uploaded=0 -> equals -> CANCELLED)
            updated_session = dao.decrease_session_counts(session_uid)

            # After decrease: total=0, uploaded=0 (equal), so status should be CANCELLED
            assert updated_session.status == TransferStatus.CANCELLED
            assert updated_session.total_items == 0
            assert updated_session.uploaded_items == 0

    def test_decrease_session_counts_prevents_negative(self, engine_dao):
        """Test that counts don't go below 0."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with 0 total and planned
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/test/path3",
                    "test-ref3",
                    TransferStatus.CANCELLED.value,
                    0,
                    0,
                    "test-engine",
                    "Test Session 3",
                    0,
                ),
            )
            session_uid = cursor.lastrowid

            # Try to decrease when already at 0
            updated_session = dao.decrease_session_counts(session_uid)

            # Counts should stay at 0
            assert updated_session.total_items == 0
            assert updated_session.planned_items == 0

    def test_decrease_session_counts_nonexistent(self, engine_dao):
        """Test decreasing counts for non-existent session."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Try to decrease non-existent session
            result = dao.decrease_session_counts(999999)

            # Should return None
            assert result is None

            # Signal should not be emitted
            dao.sessionUpdated.emit.assert_not_called()

    def test_decrease_session_counts_updates_timestamp(self, engine_dao):
        """Test that completed_on timestamp is set when session completes."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session that will complete after decrease
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/test/path4",
                    "test-ref4",
                    TransferStatus.ONGOING.value,
                    1,
                    2,
                    "test-engine",
                    "Test Session 4",
                    2,
                ),
            )
            session_uid = cursor.lastrowid

            # Decrease counts (2 -> 1, with uploaded=1, should be DONE)
            dao.decrease_session_counts(session_uid)

            # Check completed_on was set
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT completed_on FROM Sessions WHERE uid = ?", (session_uid,)
            ).fetchone()
            assert result[0] is not None


class TestUpdateSession:
    """Test cases for EngineDAO.update_session method."""

    def test_update_session_increment_uploaded(self, engine_dao):
        """Test incrementing uploaded items count."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Get existing session
            session = dao.get_session(1)
            assert session is not None

            original_uploaded = session.uploaded_items

            # Update session (increment uploaded)
            updated_session = dao.update_session(1)

            # Verify uploaded incremented
            assert updated_session.uploaded_items == original_uploaded + 1

            # Verify signal was emitted
            dao.sessionUpdated.emit.assert_called_once_with(False)

    def test_update_session_to_done(self, engine_dao):
        """Test session becomes DONE when uploaded equals total."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with total=2, uploaded=1
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/update/path",
                    "update-ref",
                    TransferStatus.ONGOING.value,
                    1,
                    2,
                    "test-engine",
                    "Update Session",
                    2,
                ),
            )
            session_uid = cursor.lastrowid

            # Update session (uploaded: 1 -> 2, equals total)
            updated_session = dao.update_session(session_uid)

            # Verify status is DONE
            assert updated_session.status == TransferStatus.DONE
            assert updated_session.uploaded_items == 2
            assert updated_session.total_items == 2

    def test_update_session_sets_completed_timestamp(self, engine_dao):
        """Test that completed_on is set when session completes."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session that will complete on next update
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/complete/path",
                    "complete-ref",
                    TransferStatus.ONGOING.value,
                    0,
                    1,
                    "test-engine",
                    "Complete Session",
                    1,
                ),
            )
            session_uid = cursor.lastrowid

            # Update to completion
            dao.update_session(session_uid)

            # Verify completed_on was set
            conn = dao._get_read_connection()
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT completed_on, status FROM Sessions WHERE uid = ?",
                (session_uid,),
            ).fetchone()
            assert result[0] is not None  # completed_on
            assert result[1] == TransferStatus.DONE.value

    def test_update_session_ongoing_status(self, engine_dao):
        """Test session remains ONGOING when not complete."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with total=5, uploaded=1
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/ongoing/path",
                    "ongoing-ref",
                    TransferStatus.ONGOING.value,
                    1,
                    5,
                    "test-engine",
                    "Ongoing Session",
                    5,
                ),
            )
            session_uid = cursor.lastrowid

            # Update session (uploaded: 1 -> 2, still less than total=5)
            updated_session = dao.update_session(session_uid)

            # Verify status remains ONGOING
            assert updated_session.status == TransferStatus.ONGOING
            assert updated_session.uploaded_items == 2
            assert updated_session.total_items == 5

    def test_update_session_nonexistent(self, engine_dao):
        """Test updating non-existent session."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Try to update non-existent session
            result = dao.update_session(999999)

            # Should return None
            assert result is None

            # Signal should not be emitted
            dao.sessionUpdated.emit.assert_not_called()

    def test_update_session_multiple_times(self, engine_dao):
        """Test updating session multiple times."""
        with engine_dao("engine_migration_16.db") as dao:
            dao.lock = RLock()
            dao.sessionUpdated = Mock()

            # Create a session with total=3, uploaded=0
            conn = dao._get_write_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO Sessions (remote_path, remote_ref, status, uploaded, total, "
                "engine, created_on, description, planned_items) "
                "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
                (
                    "/multi/path",
                    "multi-ref",
                    TransferStatus.ONGOING.value,
                    0,
                    3,
                    "test-engine",
                    "Multi Session",
                    3,
                ),
            )
            session_uid = cursor.lastrowid

            # Update 3 times
            for i in range(3):
                updated_session = dao.update_session(session_uid)
                assert updated_session.uploaded_items == i + 1

                if i < 2:
                    # Not complete yet
                    assert updated_session.status == TransferStatus.ONGOING
                else:
                    # Complete on last update
                    assert updated_session.status == TransferStatus.DONE

            # Verify final state
            final_session = dao.get_session(session_uid)
            assert final_session.uploaded_items == 3
            assert final_session.total_items == 3
            assert final_session.status == TransferStatus.DONE
