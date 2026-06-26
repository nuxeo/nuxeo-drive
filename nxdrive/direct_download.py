"""
Direct Download feature - download documents directly from Nuxeo server.

This module handles the direct download of documents triggered by nxdrive:// protocol URLs.
Downloads are saved to the 'download' folder inside the .nuxeo-drive directory.
Each download batch is stored in a timestamped subfolder (download_<timestamp>).
Supports recursive download of folders and their contents.
"""

import os
import shutil
import time
import uuid
import zipfile
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .constants import DirectDownloadStatus
from .engine.workers import Worker
from .objects import DirectDownload as DirectDownloadRecord
from .options import Options
from .qt.imports import pyqtSignal, pyqtSlot
from .utils import safe_filename, simplify_url

if TYPE_CHECKING:
    from .engine.engine import Engine  # noqa
    from .manager import Manager  # noqa

__all__ = ("DirectDownload",)

log = getLogger(__name__)


class DirectDownload(Worker):
    """
    Worker class to handle direct downloads from Nuxeo server.

    This class follows the same architecture as DirectEdit.
    Downloads are saved to ~/.nuxeo-drive/download/ folder.

    Multiple documents from a single URL request are queued together
    as a batch and processed sequentially.
    """

    # Signals for download events
    downloadStarting = pyqtSignal(str, str)  # filename, server_url
    downloadCompleted = pyqtSignal(str, str)  # filename, file_path
    downloadError = pyqtSignal(str, str)  # filename, error message
    downloadProgress = pyqtSignal(
        dict
    )  # Progress update: {uid, progress, bytes_downloaded}
    batchStarting = pyqtSignal(int)  # number of documents in batch
    batchCompleted = pyqtSignal(int, int)  # successful count, failed count

    def __init__(self, manager: "Manager", folder: Path, /) -> None:
        super().__init__("DirectDownload")

        self._manager = manager
        self._folder = folder
        self.lock = Lock()

        # Queue holds batches of documents (List[Dict]) from single URL requests
        self._download_queue: Queue = Queue()
        self._stop = False

        # List to track all download batch folders (download_<timestamp>)
        self._download_folders: List[str] = []

        # Global variable to hold engine
        self.global_engine: Optional["Engine"] = None

        # Ensure persisted active downloads are requeued only once per app run.
        self._resumed_persisted_downloads = False

        # Ensure the download folder exists
        self._folder.mkdir(parents=True, exist_ok=True)
        log.info(f"Direct Download folder: {self._folder}")

        # Connect to the manager's directDownload signal
        self._manager.directDownload.connect(self.download)

        self.thread.started.connect(self.run)

    @property
    def download_folder(self) -> Path:
        """Return the download folder path."""
        return self._folder

    @property
    def download_folders(self) -> List[str]:
        """Return the list of all download batch folder names."""
        return self._download_folders.copy()

    def _create_batch_folder(self) -> Path:
        """
        Create a new timestamped folder for a download batch.
        Format: download_YYYYMMDD_HHMMSS_ffffff_UUID

        :return: Path to the created batch folder
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        unique_id = uuid.uuid4().hex[:8]
        folder_name = f"download_{timestamp}_{unique_id}"
        batch_folder = self._folder / folder_name
        batch_folder.mkdir(parents=True, exist_ok=False)

        # Add to the list of download folders
        self._download_folders.append(folder_name)

        return batch_folder

    def cleanup(self) -> None:
        """
        Clean up the download folder by removing all downloaded files and folders.
        This is similar to how Direct Edit clears its edit folder.
        Also clears the list of download folder names.
        """
        log.info("Cleanup Direct Download folder")

        if not self._folder.exists():
            self._folder.mkdir(parents=True, exist_ok=True)
            self._download_folders.clear()
            return

        # Check for active direct download sessions upon application shutdown
        if self._stop:
            if self.global_engine and self.global_engine.dao:
                active_downloads = self.global_engine.dao.get_active_direct_downloads()
                if len(active_downloads) > 0:
                    log.info("Active downloads detected, skipping cleanup")
                    return  # Skip cleanup if there are active downloads

        # Remove all contents of the download folder
        for item in self._folder.iterdir():
            try:
                if item.is_dir():
                    log.debug(f"Removing folder: {item}")
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    log.debug(f"Removing file: {item}")
                    item.unlink(missing_ok=True)
            except Exception:
                log.exception(f"Error removing {item}")

        # Clear the list of download folders
        self._download_folders.clear()

        log.info("Direct Download folder cleaned up")

    @pyqtSlot(list)
    def download(self, documents: List[Dict[str, str]], /) -> None:
        """
        Handle direct download request for one or more documents.
        All documents from a single URL request are queued together as a batch.

        :param documents: List of document dictionaries containing:
            - server_url: The Nuxeo server URL
            - user: The username
            - repo: The repository name
            - doc_id: The document ID
            - filename: The filename
            - download_url: The download URL path
        """
        if not documents:
            log.warning("No documents to download")
            return

        # Queue the entire batch as a single entry
        self._download_queue.put(documents)

    def resume_persisted_downloads(self) -> None:
        """
        Requeue active downloads stored in databases after an application restart.
        Active records (PENDING / IN_PROGRESS / PAUSED) are grouped by their
        original batch identifier and pushed back into the in-memory queue.
        Existing records are reused to preserve history, status and progress.
        """
        if self._resumed_persisted_downloads:
            return

        self._resumed_persisted_downloads = True

        batches: Dict[str, List[Dict[str, Any]]] = {}
        resumed_count = 0

        for engine in self._manager.engines.copy().values():
            if not engine.dao:
                continue

            try:
                user = engine.get_binder().username
            except Exception:
                user = ""

            for record in engine.dao.get_direct_downloads():
                if record.status not in (
                    DirectDownloadStatus.PENDING,
                    DirectDownloadStatus.IN_PROGRESS,
                    DirectDownloadStatus.PAUSED,
                ):
                    continue

                if record.uid is None:
                    continue

                # After a restart, an in-progress transfer must be restarted.
                if record.status == DirectDownloadStatus.IN_PROGRESS:
                    engine.dao.update_direct_download_status(
                        record.uid, DirectDownloadStatus.PENDING
                    )

                # Group single-item downloads by UID to avoid merging unrelated rows.
                batch_key = record.zip_file or f"single:{record.uid}"
                batches.setdefault(batch_key, []).append(
                    {
                        "server_url": record.server_url,
                        "user": user,
                        "doc_id": record.doc_uid,
                        "filename": record.doc_name,
                        "_record_uid": record.uid,
                        # Carry the original temp folder name so _process_batch
                        # can reuse it instead of creating a fresh one.
                        "_batch_folder": record.zip_file,
                    }
                )
                resumed_count += 1

        for documents in batches.values():
            self._download_queue.put(documents)

        if resumed_count:
            log.info(
                f"Requeued {resumed_count} persisted direct download(s) in {len(batches)} batch(es)"
            )

    def _get_engine(
        self, server_url: str, /, *, user: str = None
    ) -> Optional["Engine"]:
        """
        Find an engine matching the server URL and optionally user.

        :param server_url: The Nuxeo server URL
        :param user: Optional username to match
        :return: Matching Engine or None
        """
        if not server_url:
            return None

        url = simplify_url(server_url)

        # First pass: exact match
        for engine in self._manager.engines.copy().values():
            bind = engine.get_binder()
            engine_url = simplify_url(bind.server_url.rstrip("/"))
            if engine_url == url and (not user or user == bind.username):
                return engine

        # Second pass: case-insensitive user match
        if user:
            user_lower = user.lower()
            for engine in self._manager.engines.copy().values():
                bind = engine.get_binder()
                engine_url = simplify_url(bind.server_url)
                if engine_url == url and user_lower == bind.username.lower():
                    return engine

        return None

    def _execute(self) -> None:
        """Main execution loop for the worker thread."""
        while not self._stop:
            self._interact()

            # Process queued download batches
            try:
                batch = self._download_queue.get(timeout=1.0)
                self._process_batch(batch)
            except Empty:
                continue
            except Exception:
                log.exception("Error processing download queue")

    def _process_batch(self, documents: List[Dict[str, str]], /) -> None:
        """
        Process a batch of documents from a single URL request.
        Creates a timestamped folder for this batch.
        Creates database records for each download.

        :param documents: List of document dictionaries to download
        """
        batch_size = len(documents)

        # Reuse the original temp folder when resuming persisted downloads so
        # that already-downloaded files are not fetched again.
        old_batch_folder_name: Optional[str] = (
            documents[0].get("_batch_folder") if documents else None
        )
        if old_batch_folder_name:
            candidate = self._folder / old_batch_folder_name
            if candidate.is_dir():
                batch_folder = candidate
                if old_batch_folder_name not in self._download_folders:
                    self._download_folders.append(old_batch_folder_name)
            else:
                batch_folder = self._create_batch_folder()
        else:
            batch_folder = self._create_batch_folder()

        # Collect selected item names for display
        # Use doc_id as fallback if filename is None or empty
        selected_item_names = [
            doc.get("filename") or doc.get("doc_id", "unknown") for doc in documents
        ]
        selected_items_str = ", ".join(selected_item_names)

        # Emit batch starting signal
        self.batchStarting.emit(batch_size)

        successful = 0
        failed = 0

        # Track database record UIDs for this batch
        download_records: List[int] = []

        # Use batch folder name as the batch identifier for grouping
        batch_id = batch_folder.name

        for doc in documents:
            # Check if batch was cancelled before starting each doc
            if self._is_download_cancelled(download_records):
                log.info("Batch cancelled, stopping further downloads")
                break

            # Reuse persisted database record on restart; else create a new one.
            existing_record_uid = doc.get("_record_uid")
            if existing_record_uid:
                record_uid = int(existing_record_uid)
            else:
                # Create database record for this download with batch_id for grouping
                record_uid = self._create_download_record(
                    doc, selected_items=selected_items_str, batch_id=batch_id
                )

            if record_uid:
                download_records.append(record_uid)

                # Respect paused/cancelled state for persisted records.
                if self._is_single_download_cancelled(record_uid):
                    log.info(f"Download {record_uid} cancelled, skipping")
                    continue

            try:
                # Update status to IN_PROGRESS
                if record_uid:
                    self._update_download_status(
                        record_uid, DirectDownloadStatus.IN_PROGRESS
                    )
                    self._update_download_path(
                        record_uid, str(self._get_download_destination())
                    )

                doc["_record_uid"] = record_uid
                self._process_download(doc, batch_folder)
                successful += 1

            except Exception as exc:
                log.exception("Document download failed")
                failed += 1

                # Update status to FAILED
                if record_uid:
                    self._update_download_status(
                        record_uid, DirectDownloadStatus.FAILED, last_error=str(exc)
                    )

        # Create zip file of the batch folder in user's Downloads folder
        archive_path = self._create_zip_archive(batch_folder)

        # Mark successful downloads as COMPLETED only after archive is created
        for record_uid in download_records:
            record = self._get_download_record(record_uid)
            if record and record.status in (
                DirectDownloadStatus.IN_PROGRESS,
                DirectDownloadStatus.PENDING,
                DirectDownloadStatus.PAUSED,
            ):
                self._update_download_status(
                    record_uid,
                    DirectDownloadStatus.COMPLETED,
                    download_path=(
                        str(archive_path) if archive_path else str(batch_folder)
                    ),
                )

        # Update download paths and zip_file name to the final archive location
        if archive_path:
            zip_file_name = archive_path.name if archive_path else None
            for record_uid in download_records:
                self._update_download_path(record_uid, str(archive_path), zip_file_name)

        # Emit batch completed signal
        self.batchCompleted.emit(successful, failed)

    def _create_zip_archive(self, batch_folder: Path, /) -> Optional[Path]:
        """
        Create a zip archive of the batch folder in the user's Downloads folder.
        If only a single file exists in the batch folder, copy it directly instead.

        :param batch_folder: The batch folder to archive
        :return: Path to the created zip file or copied file, or None if failed
        """
        try:
            # Determine the target download folder
            downloads_folder = self._get_download_destination()

            # Get all files in the batch folder (including in subdirectories)
            all_files = list(batch_folder.rglob("*"))
            files_only = [f for f in all_files if f.is_file()]
            dirs_only = [f for f in all_files if f.is_dir()]

            # Check if it's a single file with no subdirectories
            if len(files_only) == 1 and len(dirs_only) == 0:
                # Single file case: copy file directly to Downloads folder
                source_file = files_only[0]
                target_path = downloads_folder / source_file.name

                # Handle duplicate filenames
                target_path = self._get_unique_path(target_path)

                # Copy the file
                shutil.copy2(str(source_file), str(target_path))

                log.info(
                    f"{source_file.name} downloaded successfully to {downloads_folder}"
                )

                self._cleanup_batch_folder(batch_folder)

                return target_path

            # Multiple files or folders: create zip archive
            zip_filename = f"{batch_folder.name}.zip"
            zip_path = downloads_folder / zip_filename

            # Handle duplicate zip filenames
            zip_path = self._get_unique_path(zip_path)

            # Collect files to archive
            archive_files = [f for f in batch_folder.rglob("*") if f.is_file()]

            if not archive_files:
                log.warning("No files to archive - all downloads may have failed")
                self._cleanup_batch_folder(batch_folder)
                return None

            # Create the zip archive
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in archive_files:
                    # Calculate the archive name (relative path from batch folder)
                    arcname = file_path.relative_to(batch_folder)
                    zipf.write(file_path, arcname)

            log.info(
                f"Selected documents downloaded successfully to {downloads_folder}"
            )

            self._cleanup_batch_folder(batch_folder)

            return zip_path

        except Exception as exc:
            log.info(f"Failed to download: {exc}")
            return None

    def _get_download_destination(self) -> Path:
        """
        Get the download destination folder.

        Checks if a custom download_folder is configured in Options and accessible.
        Falls back to user's Downloads folder if not configured or not accessible.

        :return: Path to the download destination folder
        """
        user_downloads = Path.home() / "Downloads"

        # Check if custom download folder is configured
        configured_folder = Options.download_folder
        if configured_folder:
            configured_path = Path(configured_folder)

            # Check if the configured folder exists and is writable
            if configured_path.exists() and os.access(configured_path, os.W_OK):
                return configured_path
            else:
                log.info(
                    f"Unable to download to {configured_path} because Nuxeo Drive does not have access to it. "
                    f"Downloading to {user_downloads}"
                )

        # Fall back to user's Downloads folder
        if not user_downloads.exists():
            user_downloads.mkdir(parents=True, exist_ok=True)

        return user_downloads

    def _cleanup_batch_folder(self, batch_folder: Path, /) -> None:
        """
        Delete the timestamped batch folder after creating the zip archive.

        :param batch_folder: The batch folder to delete
        """
        try:
            if batch_folder.exists() and batch_folder.is_dir():
                shutil.rmtree(batch_folder, ignore_errors=True)
                # Remove from the list of download folders
                folder_name = batch_folder.name
                if folder_name in self._download_folders:
                    self._download_folders.remove(folder_name)
                log.info(f"Cleaned up batch folder: {batch_folder}")
        except Exception as exc:
            log.warning(f"Failed to cleanup batch folder {batch_folder}: {exc}")

    # =========================================================================
    # Database Operations
    # =========================================================================

    def _create_download_record(
        self,
        doc: Dict[str, str],
        /,
        *,
        selected_items: str = None,
        batch_id: str = None,
    ) -> Optional[int]:
        """
        Create a database record for a download.

        :param doc: Document dictionary with download information
        :param selected_items: Comma-separated list of selected file/folder names
        :param batch_id: Batch identifier for grouping downloads (e.g., batch folder name)
        :return: The UID of the created record, or None if failed
        """
        try:
            server_url = doc.get("server_url", "")
            user = doc.get("user")
            engine = self._get_engine(server_url, user=user)

            if not engine or not engine.dao:
                log.warning("No engine or DAO available for download record")
                return None

            # Fetch document info for additional details
            doc_id = doc.get("doc_id", "")
            doc_name = doc.get("filename") or doc_id or "unknown"
            doc_size = 0
            is_folder = False
            folder_count = 0
            file_count = 1

            # Creating a record instantly with PENDING status
            record = DirectDownloadRecord(
                uid=None,
                doc_uid=doc_id,
                doc_name=doc_name,
                doc_size=doc_size,
                download_path=None,
                server_url=server_url,
                status=DirectDownloadStatus.PENDING,
                bytes_downloaded=0,
                total_bytes=doc_size,
                progress_percent=0.0,
                created_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
                started_at=None,
                completed_at=None,
                is_folder=is_folder,
                folder_count=folder_count,
                file_count=file_count,
                retry_count=0,
                last_error=None,
                engine=engine.uid,
                zip_file=batch_id,  # Use batch_id for grouping downloads
                selected_items=selected_items,
            )
            uid = engine.dao.save_direct_download(record)

            try:
                doc_info = engine.remote.fetch(doc_id)
                is_folder = "Folderish" in doc_info.get("facets", [])
                doc_name = doc_info.get("properties", {}).get("dc:title", doc_name)

                if is_folder:
                    # For folders, calculate total size, folder count and file count recursively
                    # folder_count includes the main folder itself (add 1)
                    doc_size, subfolder_count, file_count = self._calculate_folder_size(
                        engine, doc_id
                    )
                    folder_count = subfolder_count + 1  # Include the main folder itself
                else:
                    # Get file size from properties
                    props = doc_info.get("properties", {})
                    file_content = props.get("file:content")
                    if file_content and isinstance(file_content, dict):
                        # length is returned as string, convert to int
                        doc_size = int(file_content.get("length", 0) or 0)
                    folder_count = 0
                    file_count = 1
            except Exception as e:
                log.exception(f"Could not fetch doc info for {doc_id}: {e}")

            # Update the record with the fetched details
            record.doc_name = doc_name
            record.doc_size = doc_size
            record.is_folder = is_folder
            record.folder_count = folder_count
            record.file_count = file_count
            engine.dao.update_direct_download(record)

            return uid

        except Exception:
            log.exception("Failed to create download record")
            return None

    def _calculate_folder_size(
        self, engine: "Engine", folder_id: str, /
    ) -> tuple[int, int, int]:
        """
        Calculate the total size of all files in a folder recursively.

        :param engine: The engine to use for API calls
        :param folder_id: The document ID of the folder
        :return: Tuple of (total_size_bytes, folder_count, file_count)
        """
        total_size = 0
        folder_count = 0
        file_count = 0

        try:
            children = self._get_children(engine, folder_id)

            for child in children:
                child_is_folderish = "Folderish" in child.get("facets", [])

                if child_is_folderish:
                    # Count this subfolder
                    folder_count += 1
                    # Recursively calculate subfolder size
                    child_id = child.get("uid", "")
                    (
                        subfolder_size,
                        subfolder_folders,
                        subfolder_files,
                    ) = self._calculate_folder_size(engine, child_id)
                    total_size += subfolder_size
                    folder_count += subfolder_folders
                    file_count += subfolder_files
                else:
                    # Add file size
                    props = child.get("properties", {})
                    file_content = props.get("file:content")
                    if file_content and isinstance(file_content, dict):
                        # length is returned as string, convert to int
                        file_size = int(file_content.get("length", 0) or 0)
                        total_size += file_size
                    file_count += 1

        except Exception:
            log.exception(f"Failed to calculate folder size for {folder_id}")

        return total_size, folder_count, file_count

    def _update_download_status(
        self,
        uid: int,
        status: DirectDownloadStatus,
        /,
        *,
        download_path: Optional[str] = None,
        last_error: Optional[str] = None,
    ) -> None:
        """
        Update the status of a download record.

        :param uid: The UID of the download record
        :param status: The new status
        :param download_path: Optional download path to update
        :param last_error: Optional error message (for FAILED status)
        """
        try:
            # Find the engine that has this download
            for engine in self._manager.engines.copy().values():
                if engine.dao:
                    record = engine.dao.get_direct_download(uid)
                    if record:
                        if download_path:
                            record.download_path = download_path
                            engine.dao.update_direct_download(record)
                        engine.dao.update_direct_download_status(
                            uid, status, last_error=last_error
                        )
                        return
        except Exception:
            log.exception(f"Failed to update download status for {uid}")

    def _get_download_record(self, uid: int, /) -> Optional[DirectDownloadRecord]:
        """Get a download record by UID from any engine."""
        try:
            for engine in self._manager.engines.copy().values():
                if engine.dao:
                    record = engine.dao.get_direct_download(uid)
                    if record:
                        return record
        except Exception:
            log.exception(f"Failed to get download record for {uid}")
        return None

    def _is_download_cancelled(self, record_uids: List[int], /) -> bool:
        """Check if any download in the batch has been cancelled or paused.
        If paused, wait until resumed or cancelled."""
        for uid in record_uids:
            record = self._get_download_record(uid)
            if not record:
                continue
            if record.status == DirectDownloadStatus.CANCELLED:
                return True
            # If paused, wait until resumed or cancelled
            while record and record.status == DirectDownloadStatus.PAUSED:
                if self._stop:
                    return True
                time.sleep(1.0)
                record = self._get_download_record(uid)
                if record and record.status == DirectDownloadStatus.CANCELLED:
                    return True
        return False

    def _is_single_download_cancelled(self, uid: int, /) -> bool:
        """Check if a single download has been cancelled or paused.
        If paused, wait until resumed or cancelled."""
        record = self._get_download_record(uid)
        if not record:
            return False
        # If paused, wait until resumed or cancelled
        while record and record.status == DirectDownloadStatus.PAUSED:
            if self._stop:
                return True
            time.sleep(1.0)
            record = self._get_download_record(uid)
        return bool(record and record.status == DirectDownloadStatus.CANCELLED)

    def _update_download_path(
        self, uid: int, download_path: str, zip_file: str = None, /
    ) -> None:
        """
        Update the download path and zip file name of a record.

        :param uid: The UID of the download record
        :param download_path: The final download path
        :param zip_file: The name of the zip file (if any)
        """
        try:
            for engine in self._manager.engines.copy().values():
                if engine.dao:
                    record = engine.dao.get_direct_download(uid)
                    if record:
                        record.download_path = download_path
                        # Only overwrite zip_file when explicitly provided;
                        # otherwise the original batch-folder name is lost and
                        # restart-resume cannot locate the old temp folder.
                        if zip_file is not None:
                            record.zip_file = zip_file
                        engine.dao.update_direct_download(record)
                        return
        except Exception:
            log.exception(f"Failed to update download path for {uid}")

    def _update_download_progress(
        self,
        uid: int,
        bytes_downloaded: int,
        total_bytes: int,
        /,
        filename: Optional[str] = None,
    ) -> None:
        """
        Update the progress of a download.

        :param uid: The UID of the download record
        :param bytes_downloaded: Bytes downloaded so far
        :param total_bytes: Total bytes to download
        """
        try:
            progress = (
                (bytes_downloaded / total_bytes * 100) if total_bytes > 0 else 0.0
            )

            for engine in self._manager.engines.copy().values():
                if engine.dao:
                    record = engine.dao.get_direct_download(uid)
                    if record:
                        engine.dao.update_direct_download_progress(
                            uid, bytes_downloaded, total_bytes, progress
                        )
                        # Emit progress signal for real-time UI updates
                        self.downloadProgress.emit(
                            {
                                "uid": uid,
                                "doc_name": filename,
                                "progress": progress,
                                "bytes_downloaded": bytes_downloaded,
                                "total_bytes": total_bytes,
                            }
                        )
                        return
        except Exception:
            log.exception(f"Failed to update download progress for {uid}")

    def _process_download(self, doc: Dict[str, str], batch_folder: Path, /) -> None:
        """
        Process a single document download. If the document is a folder,
        recursively download all its contents.

        :param doc: Document dictionary with download information
        :param batch_folder: The batch folder to download into
        :raises Exception: If download fails
        """
        server_url = doc.get("server_url", "")
        user = doc.get("user")
        doc_id = doc.get("doc_id", "")

        # Get filename and download_url from dict (may be None for simplified URL format)
        filename = doc.get("filename")
        download_url = doc.get("download_url")

        # Get engine for authentication
        engine = self._get_engine(server_url, user=user)
        self.global_engine = engine
        if not engine:
            error_msg = f"No engine found for server {server_url}"
            self.downloadError.emit(filename or doc_id, error_msg)
            raise RuntimeError(error_msg)

        # Fetch document info to get filename and check if it's a folder
        try:
            doc_info = engine.remote.get_info(doc_id)
            if not doc_info:
                raise RuntimeError(f"Document {doc_id} not found")

            is_folderish = doc_info.folderish
            doc_title = doc_info.name

            # Get download URL if not provided (for simplified URL format)
            if not download_url and not is_folderish:
                # Construct download URL from document info
                blob = doc_info.get_blob("file:content")
                if blob:
                    # Build the download URL path
                    download_url = f"nxfile/default/{doc_id}/file:content/{blob.name}"

            # Use fetched filename if not provided
            if not filename:
                filename = doc_title

        except Exception as e:
            log.exception(f"Failed to fetch document info for {doc_id}")
            error_msg = f"Failed to get document information: {e}"
            self.downloadError.emit(filename or doc_id, error_msg)
            raise RuntimeError(error_msg)

        # Emit starting signal
        self.downloadStarting.emit(filename, server_url)

        # Sanitize the resolved output name for filesystem safety.
        # Preserve the explicit filename from the protocol URL when provided,
        # and fall back to the repository document title otherwise.
        safe_name = safe_filename(filename or doc_title)

        if is_folderish:
            # Handle folder: create folder and download contents recursively
            self._download_folder(
                engine,
                doc_id,
                safe_name,
                batch_folder,
                record_uid=doc.get("_record_uid"),
            )
        else:
            # Handle file: download directly
            self._download_file(
                engine,
                server_url,
                download_url,
                safe_name,
                batch_folder,
                record_uid=doc.get("_record_uid"),
            )

        self.downloadCompleted.emit(safe_name, str(batch_folder / safe_name))

    def _download_folder(
        self,
        engine: "Engine",
        folder_id: str,
        folder_name: str,
        parent_path: Path,
        /,
        record_uid: Optional[int] = None,
    ) -> None:
        """
        Download a folder and all its contents recursively.

        :param engine: The engine to use for API calls
        :param folder_id: The document ID of the folder
        :param folder_name: The name of the folder
        :param parent_path: The local parent path where to create the folder
        :raises RuntimeError: If listing children fails
        """
        # Reuse the existing folder when resuming an interrupted run so that
        # already-downloaded children are not fetched again.  Only generate a
        # deduplicated name when the folder does not yet exist.
        expected_path = parent_path / folder_name
        if expected_path.exists():
            folder_path = expected_path
        else:
            folder_path = self._get_unique_path(expected_path)
            folder_path.mkdir(parents=True, exist_ok=True)

        # Query for children documents
        children = self._get_children(engine, folder_id)

        # Process each child
        for child in children:
            child_id = child.get("uid", "")
            child_title = child.get("properties", {}).get("dc:title", "unknown")
            child_is_folderish = "Folderish" in child.get("facets", [])
            safe_child_name = safe_filename(child_title)

            if child_is_folderish:
                # Recursively download subfolder
                self._download_folder(
                    engine,
                    child_id,
                    safe_child_name,
                    folder_path,
                    record_uid=record_uid,
                )
            else:
                # Download file
                download_url = self._get_download_url(child)
                if download_url:
                    server_url = engine.server_url
                    self._download_file(
                        engine,
                        server_url,
                        download_url,
                        safe_child_name,
                        folder_path,
                        record_uid=record_uid,
                    )

    def _get_children(
        self, engine: "Engine", parent_id: str, /
    ) -> List[Dict[str, Any]]:
        """
        Get all children documents of a folder with full properties including blob info.

        :param engine: The engine to use for API calls
        :param parent_id: The document ID of the parent folder
        :return: List of child documents with full properties
        """
        # Use NXQL query to get children UIDs first
        # parent_id is a Nuxeo UUID validated upstream, safe for interpolation
        query = (
            f"SELECT * FROM Document "
            f"WHERE ecm:parentId = '{parent_id}' "
            f"AND ecm:isVersion = 0 "
            f"AND ecm:isTrashed = 0"
        )

        children: List[Dict[str, Any]] = []
        page = 0
        page_size = 1000

        while True:
            result = engine.remote.execute(
                command="Document.Query",
                query=query,
                pageSize=page_size,
                currentPageIndex=page,
            )
            entries = result.get("entries", [])

            if not entries:
                break

            children.extend(entries)

            # If we got fewer results than the page size, we've reached the end
            if len(entries) < page_size:
                break

            page += 1

        return children

    def _get_download_url(self, doc: Dict[str, Any], /) -> Optional[str]:
        """
        Extract the download URL from a document.

        :param doc: Document dictionary from API
        :return: Download URL path or None
        """
        props = doc.get("properties", {})

        # Try file:content first (most common)
        file_content = props.get("file:content")
        if file_content and isinstance(file_content, dict):
            data = file_content.get("data")
            if data:
                return data

        # Try note:note for Note documents
        if doc.get("type") == "Note":
            note = props.get("note:note")
            if note:
                # Notes are inline, we'll handle them differently
                return None

        return None

    def _download_file(
        self,
        engine: "Engine",
        server_url: str,
        download_url: str,
        filename: str,
        target_folder: Path,
        /,
        *,
        record_uid: Optional[int] = None,
    ) -> None:
        """
        Download a single file to the target folder.

        :param engine: The engine to use for download
        :param server_url: The server base URL
        :param download_url: The download URL path
        :param filename: The target filename
        :param target_folder: The folder to save the file in
        :param record_uid: Optional DB record UID for progress tracking
        """
        expected_path = target_folder / filename
        target_path = expected_path

        existing_size = expected_path.stat().st_size if expected_path.exists() else 0
        persisted_total_bytes = 0
        is_folder_record = False
        if record_uid:
            record = self._get_download_record(record_uid)
            if record:
                persisted_total_bytes = int(record.total_bytes or 0)
                is_folder_record = bool(record.is_folder)

        # For folder downloads, persisted total_bytes tracks the whole folder batch,
        # not each child file. Do not use it for per-file completion checks.
        if is_folder_record:
            persisted_total_bytes = 0

        # Only skip when we are sure the file is already complete.
        # A mere file presence can be an interrupted partial download.
        if expected_path.exists() and persisted_total_bytes > 0:
            if existing_size >= persisted_total_bytes:
                log.debug(
                    f"File already complete from previous run, skipping: {filename}"
                )
                return
        elif expected_path.exists() and persisted_total_bytes == 0 and not record_uid:
            # Fresh (non-resumed) duplicate request: keep previous behavior by avoiding overwrite.
            log.debug(f"File already present from previous run, skipping: {filename}")
            return

        # Build the full download URL
        if download_url.startswith("http"):
            full_url = download_url
        else:
            full_url = server_url.rstrip("/") + "/" + download_url.lstrip("/")

        resp = None
        try:
            headers = None
            file_mode = "wb"

            # Resume interrupted files when possible.
            if existing_size > 0:
                headers = {"Range": f"bytes={existing_size}-"}
                file_mode = "ab"

            # Use the engine's remote client to make the request with streaming
            resp = engine.remote.client.request(
                "GET",
                full_url.replace(engine.remote.client.host, ""),
                ssl_verify=engine.remote.verification_needed,
                stream=True,
                headers=headers,
            )

            # Resuming from EOF can return 416 (Range Not Satisfiable), which means
            # the local file is already complete for this child.
            if existing_size > 0 and getattr(resp, "status_code", None) == 416:
                log.debug(
                    f"File already complete from previous run (range EOF), skipping: {filename}"
                )
                return

            resp.raise_for_status()

            # If server ignored Range and returned full payload, restart from scratch.
            if existing_size > 0 and getattr(resp, "status_code", None) != 206:
                file_mode = "wb"
                existing_size = 0

            # Try to get total size from Content-Length header
            try:
                content_length = int(resp.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                content_length = 0

            if existing_size > 0 and getattr(resp, "status_code", None) == 206:
                total_bytes = existing_size + content_length
            elif persisted_total_bytes > 0:
                total_bytes = persisted_total_bytes
            else:
                total_bytes = content_length

            bytes_downloaded = existing_size

            # Write the content to file using streaming to avoid loading all into memory
            with open(target_path, file_mode) as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue

                    # Check for cancellation during download
                    if record_uid and self._is_single_download_cancelled(record_uid):
                        if self._stop:
                            return
                        log.info(f"Download cancelled for {filename}")
                        raise RuntimeError(f"Download cancelled for {filename}")

                    f.write(chunk)
                    bytes_downloaded += len(chunk)

                    # Update progress
                    if record_uid and total_bytes > 0:
                        self._update_download_progress(
                            record_uid, bytes_downloaded, total_bytes, filename=filename
                        )

        except RuntimeError as e:
            if not str(e).startswith("Download cancelled"):
                raise
        except Exception:
            log.exception(f"Download failed for {filename}")
            raise
        finally:
            if resp is not None:
                resp.close()

    def _get_unique_path(self, path: Path, /) -> Path:
        """
        Get a unique file path, adding (1), (2), etc. if file exists.

        :param path: Original file path
        :return: Unique file path
        """
        if not path.exists():
            return path

        counter = 1
        stem = path.stem
        suffix = path.suffix
        parent = path.parent

        while path.exists():
            path = parent / f"{stem} ({counter}){suffix}"
            counter += 1

        return path

    def stop(self) -> None:
        """Stop the worker."""
        self._stop = True
        super().stop()
