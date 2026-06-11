"""
Nuxeo-specific Direct Download implementation.

Inherits generic infrastructure from ``nxdrive.drive.direct_download.DirectDownload``
and adds Nuxeo server operations (document fetching, NXQL queries, blob download).
"""

from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from nxdrive.drive.constants import DirectDownloadStatus
from nxdrive.drive.direct_download import DirectDownload as _DirectDownloadBase
from nxdrive.drive.objects import DirectDownload as DirectDownloadRecord
from nxdrive.drive.utils import safe_filename

if TYPE_CHECKING:
    from nxdrive.drive.manager import Manager  # noqa
    from nxdrive.nuxeo.engine.engine import Engine  # noqa

__all__ = ("DirectDownload",)

log = getLogger(__name__)


class DirectDownload(_DirectDownloadBase):
    """
    Nuxeo-specific Direct Download worker.

    Inherits all generic infrastructure from
    ``nxdrive.drive.direct_download.DirectDownload`` and overrides only
    the server-specific operations (NXQL queries, Nuxeo blob download, etc.).
    """

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

    # ------------------------------------------------------------------ Nuxeo-specific download operations

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
            self._download_folder(engine, doc_id, safe_name, batch_folder)
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
    ) -> None:
        """
        Download a folder and all its contents recursively.

        :param engine: The engine to use for API calls
        :param folder_id: The document ID of the folder
        :param folder_name: The name of the folder
        :param parent_path: The local parent path where to create the folder
        :raises RuntimeError: If listing children fails
        """
        # Create the local folder
        folder_path = self._get_unique_path(parent_path / folder_name)
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
        # Calculate the target file path (handle duplicates)
        target_path = self._get_unique_path(target_folder / filename)

        # Build the full download URL
        if download_url.startswith("http"):
            full_url = download_url
        else:
            full_url = server_url.rstrip("/") + "/" + download_url.lstrip("/")

        resp = None
        try:
            # Use the engine's remote client to make the request with streaming
            resp = engine.remote.client.request(
                "GET",
                full_url.replace(engine.remote.client.host, ""),
                ssl_verify=engine.remote.verification_needed,
                stream=True,
            )
            resp.raise_for_status()

            # Try to get total size from Content-Length header
            try:
                total_bytes = int(resp.headers.get("Content-Length", 0))
            except (TypeError, ValueError):
                total_bytes = 0
            bytes_downloaded = 0

            # Write the content to file using streaming to avoid loading all into memory
            with open(target_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
                    if not chunk:
                        continue

                    # Check for cancellation during download
                    if record_uid and self._is_single_download_cancelled(record_uid):
                        log.info(f"Download cancelled for {filename}")
                        raise RuntimeError(f"Download cancelled for {filename}")

                    f.write(chunk)
                    bytes_downloaded += len(chunk)

                    # Update progress
                    if record_uid and total_bytes > 0:
                        self._update_download_progress(
                            record_uid, bytes_downloaded, total_bytes
                        )

        except Exception:
            log.exception(f"Download failed for {filename}")
            raise
        finally:
            if resp is not None:
                resp.close()
