"""
Direct Download feature - download documents directly from Nuxeo server.

This module handles the direct download of documents triggered by nxdrive:// protocol URLs.
Downloads are saved to the 'download' folder inside the .nuxeo-drive directory.
Each download batch is stored in a timestamped subfolder (download_<timestamp>).
Supports recursive download of folders and their contents.
"""

import os
import shutil
import zipfile
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from queue import Queue
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
        Format: download_YYYYMMDD_HHMMSS

        :return: Path to the created batch folder
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder_name = f"download_{timestamp}"
        batch_folder = self._folder / folder_name
        batch_folder.mkdir(parents=True, exist_ok=True)

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
                if not self._download_queue.empty():
                    batch = self._download_queue.get_nowait()
                    self._process_batch(batch)
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

        # Create a timestamped folder for this batch
        batch_folder = self._create_batch_folder()

        # Collect selected item names for display
        selected_item_names = [doc.get("filename", "unknown") for doc in documents]
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

                self._process_download(doc, batch_folder)
                successful += 1

                # Update status to COMPLETED
                if record_uid:
                    self._update_download_status(
                        record_uid,
                        DirectDownloadStatus.COMPLETED,
                        download_path=str(batch_folder),
                    )

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

                # TODO: Uncomment to delete the timestamped download folder after copying
                # self._cleanup_batch_folder(batch_folder)

                return target_path

            # Multiple files or folders: create zip archive
            zip_filename = f"{batch_folder.name}.zip"
            zip_path = downloads_folder / zip_filename

            # Handle duplicate zip filenames
            zip_path = self._get_unique_path(zip_path)

            # Create the zip archive
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for file_path in batch_folder.rglob("*"):
                    if file_path.is_file():
                        # Calculate the archive name (relative path from batch folder)
                        arcname = file_path.relative_to(batch_folder)
                        zipf.write(file_path, arcname)

            log.info(
                f"Selected documents downloaded successfully to {downloads_folder}"
            )

            # TODO: Uncomment to delete the timestamped download folder after zipping
            # self._cleanup_batch_folder(batch_folder)

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
        # try:
        #     if batch_folder.exists() and batch_folder.is_dir():
        #         shutil.rmtree(batch_folder, ignore_errors=True)
        #         # Remove from the list of download folders
        #         folder_name = batch_folder.name
        #         if folder_name in self._download_folders:
        #             self._download_folders.remove(folder_name)
        #         log.info(f"Cleaned up batch folder: {batch_folder}")
        # except Exception as exc:
        #     log.info(f"Failed to cleanup batch folder {batch_folder}: {exc}")
        pass

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
            doc_name = doc.get("filename", "unknown")
            doc_size = 0
            is_folder = False
            folder_count = 0
            file_count = 1

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

            # Create the download record
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
                created_at=datetime.now(timezone.utc),
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

            return engine.dao.save_direct_download(record)

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
                        engine.dao.update_direct_download_status(
                            uid, status, last_error=last_error
                        )
                        return
        except Exception:
            log.exception(f"Failed to update download status for {uid}")

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

    def _process_download(self, doc: Dict[str, str], batch_folder: Path, /) -> None:
        """
        Process a single document download. If the document is a folder,
        recursively download all its contents.

        :param doc: Document dictionary with download information
        :param batch_folder: The batch folder to download into
        :raises Exception: If download fails
        """
        filename = doc.get("filename", "unknown")
        server_url = doc.get("server_url", "")
        user = doc.get("user")
        doc_id = doc.get("doc_id", "")
        download_url = doc.get("download_url", "")

        # Emit starting signal
        self.downloadStarting.emit(filename, server_url)

        # Get engine for authentication
        engine = self._get_engine(server_url, user=user)
        if not engine:
            error_msg = f"No engine found for server {server_url}"
            self.downloadError.emit(filename, error_msg)
            raise RuntimeError(error_msg)

        # Fetch document info to check if it's a folder
        try:
            doc_info = engine.remote.fetch(doc_id)
            is_folderish = "Folderish" in doc_info.get("facets", [])
            doc_title = doc_info.get("properties", {}).get("dc:title", filename)
        except Exception:
            log.exception(f"Failed to fetch document info for {doc_id}")
            is_folderish = False
            doc_title = filename

        # Sanitize filename for filesystem safety
        safe_name = safe_filename(doc_title)

        if is_folderish:
            # Handle folder: create folder and download contents recursively
            self._download_folder(engine, doc_id, safe_name, batch_folder)
        else:
            # Handle file: download directly
            self._download_file(
                engine, server_url, download_url, safe_name, batch_folder
            )

        self.downloadCompleted.emit(safe_name, str(batch_folder / safe_name))

    def _download_folder(
        self,
        engine: "Engine",
        folder_id: str,
        folder_name: str,
        parent_path: Path,
        /,
    ) -> None:
        """
        Download a folder and all its contents recursively.

        :param engine: The engine to use for API calls
        :param folder_id: The document ID of the folder
        :param folder_name: The name of the folder
        :param parent_path: The local parent path where to create the folder
        """
        # Create the local folder
        folder_path = self._get_unique_path(parent_path / folder_name)
        folder_path.mkdir(parents=True, exist_ok=True)

        # Query for children documents
        try:
            children = self._get_children(engine, folder_id)
        except Exception:
            log.exception(f"Failed to get children for folder {folder_id}")
            return

        # Process each child
        for child in children:
            child_id = child.get("uid", "")
            child_title = child.get("properties", {}).get("dc:title", "unknown")
            child_is_folderish = "Folderish" in child.get("facets", [])
            safe_child_name = safe_filename(child_title)

            if child_is_folderish:
                # Recursively download subfolder
                self._download_folder(engine, child_id, safe_child_name, folder_path)
            else:
                # Download file
                download_url = self._get_download_url(child)
                if download_url:
                    server_url = engine.server_url
                    self._download_file(
                        engine, server_url, download_url, safe_child_name, folder_path
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
        query = (
            f"SELECT * FROM Document "
            f"WHERE ecm:parentId = '{parent_id}' "
            f"AND ecm:isVersion = 0 "
            f"AND ecm:isTrashed = 0"
        )

        result = engine.remote.query(query, page_size=1000)
        entries = result.get("entries", [])

        # The query result may not include blob properties with length
        # Fetch each document individually to get complete properties
        full_entries = []
        for entry in entries:
            doc_uid = entry.get("uid", "")
            if doc_uid:
                try:
                    # Fetch full document info including blob properties
                    full_doc = engine.remote.fetch(doc_uid)
                    full_entries.append(full_doc)
                except Exception:
                    # Fall back to the query result if fetch fails
                    full_entries.append(entry)
            else:
                full_entries.append(entry)

        return full_entries

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
    ) -> None:
        """
        Download a single file to the target folder.

        :param engine: The engine to use for download
        :param server_url: The server base URL
        :param download_url: The download URL path
        :param filename: The target filename
        :param target_folder: The folder to save the file in
        """
        # Calculate the target file path (handle duplicates)
        target_path = self._get_unique_path(target_folder / filename)

        # Build the full download URL
        if download_url.startswith("http"):
            full_url = download_url
        else:
            full_url = server_url.rstrip("/") + "/" + download_url.lstrip("/")

        try:
            # Use the engine's remote client to make the request
            resp = engine.remote.client.request(
                "GET",
                full_url.replace(engine.remote.client.host, ""),
                ssl_verify=engine.remote.verification_needed,
            )

            # Write the content to file
            with open(target_path, "wb") as f:
                f.write(resp.content)

        except Exception:
            log.exception(f"Download failed for {filename}")
            raise

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
