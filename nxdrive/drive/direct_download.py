"""Server-agnostic Direct Download base class.

Provides the generic queue management, batch processing, zip archiving,
database tracking, and folder management.  Server-specific operations
(document fetching, folder traversal, actual HTTP download) are abstract
and must be supplied by a subclass (e.g. ``nuxeo/direct_download.py``).
"""

import os
import shutil
import time
import uuid
import zipfile
from datetime import datetime
from logging import getLogger
from pathlib import Path
from queue import Empty, Queue
from threading import Lock
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from nxdrive.drive.constants import DirectDownloadStatus
from nxdrive.drive.engine.workers import Worker
from nxdrive.drive.objects import DirectDownload as DirectDownloadRecord
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSignal, pyqtSlot
from nxdrive.drive.utils import simplify_url

if TYPE_CHECKING:
    from nxdrive.drive.engine.engine import Engine  # noqa
    from nxdrive.drive.manager import Manager  # noqa

__all__ = ("DirectDownload",)

log = getLogger(__name__)


class DirectDownload(Worker):
    """Server-agnostic Direct Download worker.

    Subclass in each server-type package and override the abstract hooks:
    ``_process_download()``, ``_download_folder()``, ``_get_children()``,
    ``_get_download_url()``, ``_download_file()``, ``_calculate_folder_size()``,
    ``_create_download_record()``.
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

        # Ensure the download folder exists
        self._folder.mkdir(parents=True, exist_ok=True)
        log.info(f"Direct Download folder: {self._folder}")

        # Connect to the manager's directDownload signal
        self._manager.directDownload.connect(self.download)

        self.thread.started.connect(self.run)

    # ------------------------------------------------------------------ properties

    @property
    def download_folder(self) -> Path:
        """Return the download folder path."""
        return self._folder

    @property
    def download_folders(self) -> List[str]:
        """Return the list of all download batch folder names."""
        return self._download_folders.copy()

    # ------------------------------------------------------------------ folder management

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

    # ------------------------------------------------------------------ download slot

    @pyqtSlot(list)
    def download(self, documents: List[Dict[str, str]], /) -> None:
        """
        Handle direct download request for one or more documents.
        All documents from a single URL request are queued together as a batch.

        :param documents: List of document dictionaries containing:
            - server_url: The server URL
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

    # ------------------------------------------------------------------ engine lookup

    def _get_engine(
        self, server_url: str, /, *, user: str = None
    ) -> Optional["Engine"]:
        """
        Find an engine matching the server URL and optionally user.

        :param server_url: The server URL
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

    # ------------------------------------------------------------------ main loop

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

    # ------------------------------------------------------------------ batch processing

    def _process_batch(self, documents: List[Dict[str, str]], /) -> None:
        """
        Process a batch of documents from a single URL request.
        Creates a timestamped folder for this batch.
        Creates database records for each download.

        :param documents: List of document dictionaries to download
        """
        batch_size = len(documents)

        # Create a timestamped folder for this batch
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

            # Create database record for this download with batch_id for grouping
            record_uid = self._create_download_record(
                doc, selected_items=selected_items_str, batch_id=batch_id
            )
            if record_uid:
                download_records.append(record_uid)

            try:
                # Update status to IN_PROGRESS
                if record_uid:
                    self._update_download_status(
                        record_uid, DirectDownloadStatus.IN_PROGRESS
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

    # ------------------------------------------------------------------ zip / destination

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

    # ------------------------------------------------------------------ database operations

    def _create_download_record(
        self,
        doc: Dict[str, str],
        /,
        *,
        selected_items: str = None,
        batch_id: str = None,
    ) -> Optional[int]:
        """Create a database record for a download.  **Must be overridden.**"""
        raise NotImplementedError

    def _calculate_folder_size(self, engine: "Engine", folder_id: str, /) -> tuple:
        """Calculate folder size recursively.  **Must be overridden.**"""
        raise NotImplementedError

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
                                "progress": progress,
                                "bytes_downloaded": bytes_downloaded,
                                "total_bytes": total_bytes,
                            }
                        )
                        return
        except Exception:
            log.exception(f"Failed to update download progress for {uid}")

    # ------------------------------------------------------------------ abstract hooks (override in subclass)

    def _process_download(self, doc: Dict[str, str], batch_folder: Path, /) -> None:
        """Process a single document download.  **Must be overridden.**"""
        raise NotImplementedError

    def _download_folder(
        self,
        engine: "Engine",
        folder_id: str,
        folder_name: str,
        parent_path: Path,
        /,
    ) -> None:
        """Download a folder recursively.  **Must be overridden.**"""
        raise NotImplementedError

    def _get_children(
        self, engine: "Engine", parent_id: str, /
    ) -> List[Dict[str, Any]]:
        """Get children documents of a folder.  **Must be overridden.**"""
        raise NotImplementedError

    def _get_download_url(self, doc: Dict[str, Any], /) -> Optional[str]:
        """Extract download URL from a document.  **Must be overridden.**"""
        raise NotImplementedError

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
        """Download a single file.  **Must be overridden.**"""
        raise NotImplementedError

    # ------------------------------------------------------------------ utilities

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
