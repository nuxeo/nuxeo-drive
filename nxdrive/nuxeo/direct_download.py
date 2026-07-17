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
from nxdrive.drive.options import Options  # backward compatibility for tests
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

    def _get_download_destination(self) -> Path:
        """Backward-compatible destination resolution for patched tests."""
        import os

        user_downloads = Path.home() / "Downloads"

        configured_folder = Options.download_folder
        if configured_folder:
            configured_path = Path(configured_folder)
            if configured_path.exists() and os.access(configured_path, os.W_OK):
                return configured_path

        if not user_downloads.exists():
            user_downloads.mkdir(parents=True, exist_ok=True)

        return user_downloads

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
            record.total_bytes = doc_size
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
                    file_size = 0
                    if file_content and isinstance(file_content, dict):
                        # length is returned as string, convert to int
                        file_size = int(file_content.get("length", 0) or 0)
                    if file_size <= 0:
                        child_id = child.get("uid", "")
                        if child_id:
                            try:
                                child_info = engine.remote.get_info(child_id)
                                blob = (
                                    child_info.get_blob("file:content")
                                    if child_info
                                    else None
                                )
                                if blob:
                                    file_size = int(getattr(blob, "size", 0) or 0)
                            except Exception:
                                log.debug(
                                    f"Could not fetch blob size fallback for {child_id}",
                                    exc_info=True,
                                )
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

            # Get download URL if not provided (for simplified URL format).
            # Try each xpath in order of likelihood; prefer ``blob.data``
            # (a fully-formed ``nxfile`` URL with ``changeToken``) so the
            # server-issued version pin is preserved. Reconstruct the
            # path from ``blob.name`` only when ``data`` is absent
            # (older Nuxeo responses). Notes are excluded here because
            # their ``blob.data`` is the note *content* rather than a
            # URL — they are inline documents and cannot be streamed
            # over HTTP via this path.
            if not download_url and not is_folderish:
                for xpath in (
                    "file:content",
                    "files:files/0/file",
                    "picture:views/0/content",
                ):
                    blob = doc_info.get_blob(xpath)
                    if blob:
                        download_url = blob.data or (
                            f"nxfile/default/{doc_id}/{xpath}/{blob.name}"
                        )
                        break

            # Note documents keep their content inline in ``note:note``
            # rather than as a downloadable blob. Detect and route them
            # to the Note-specific write path below.
            is_note = (
                not download_url
                and not is_folderish
                and doc_info.doc_type == "Note"
                and bool(doc_info.properties.get("note:note"))
            )

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
        elif is_note:
            # Handle Note: write the inline text content directly to disk.
            self._download_note(
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

        # Try common content xpaths in order. ``data`` holds the full
        # ``nxfile`` URL (with ``changeToken``) when the property is
        # populated.
        for xpath in ("file:content", "files:files/0/file", "picture:views/0/content"):
            container = props
            value: Any = None
            for part in xpath.split("/"):
                key: Any = int(part) if part.isnumeric() else part
                if isinstance(container, dict):
                    value = container.get(key)
                elif isinstance(container, list):
                    try:
                        value = container[key]
                    except (IndexError, TypeError):
                        value = None
                else:
                    value = None
                if value is None:
                    break
                container = value
            if isinstance(value, dict):
                data = value.get("data")
                if data:
                    return data

        # Notes are inline: their content lives in ``note:note`` and is
        # not an HTTP-streamable blob — caller must handle separately.
        if doc.get("type") == "Note":
            if props.get("note:note"):
                return None

        return None

    def _download_note(
        self,
        engine: "Engine",
        doc_id: str,
        filename: str,
        target_folder: Path,
        /,
        *,
        record_uid: Optional[int] = None,
    ) -> None:
        """
        Write a Nuxeo Note document's inline content to disk.

        Notes do not expose a downloadable blob under ``file:content``;
        their text lives in ``properties["note:note"]``. The remote
        client's :meth:`NuxeoRemote.get_note` fetches the doc, decodes
        the URL-encoded body, and writes UTF-8 bytes to *file_out*.

        :param engine: The engine to use for API calls
        :param doc_id: The document ID of the Note
        :param filename: The target filename (uses the doc title with
            any user-provided extension preserved)
        :param target_folder: The batch folder to write into
        :param record_uid: Optional DB record UID for progress tracking
        """
        target_path = target_folder / filename

        # ``get_note(file_out=...)`` writes the note bytes directly and
        # returns them. If the note is empty we still create an empty
        # file so the batch finalizer sees a member for this record.
        content = engine.remote.get_note(doc_id, file_out=target_path)
        if not target_path.exists():
            target_path.write_bytes(content or b"")

        if record_uid:
            size = target_path.stat().st_size
            self._update_download_progress(record_uid, size, size)

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
        # Defensive guard: ``_process_download`` and ``_download_folder``
        # can hand us ``None`` when a document has no resolvable blob
        # under any of the known xpaths (empty ``File`` doc, Note,
        # unsupported doc-type, etc.). Fail fast with a clear message
        # so ``_process_batch``'s per-doc ``except`` records ``FAILED``
        # with a useful reason and emits ``downloadError`` to the UI.
        if not download_url:
            raise RuntimeError(f"No downloadable content found for {filename!r}")

        expected_path = target_folder / filename
        target_path = expected_path

        existing_size = expected_path.stat().st_size if expected_path.exists() else 0
        persisted_total_bytes = 0
        folder_total_bytes = 0
        is_folder_record = False
        folder_progress_offset = 0
        if record_uid:
            record = self._get_download_record(record_uid)
            if record:
                persisted_total_bytes = int(record.total_bytes or 0)
                folder_total_bytes = persisted_total_bytes
                is_folder_record = bool(record.is_folder)
                if is_folder_record:
                    folder_progress_offset = max(
                        0, int(record.bytes_downloaded or 0) - existing_size
                    )

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
                        reported_bytes_downloaded = bytes_downloaded
                        reported_total_bytes = total_bytes
                        if is_folder_record and folder_total_bytes > 0:
                            reported_bytes_downloaded = (
                                folder_progress_offset + bytes_downloaded
                            )
                            reported_total_bytes = folder_total_bytes
                        self._update_download_progress(
                            record_uid,
                            reported_bytes_downloaded,
                            reported_total_bytes,
                            filename=filename,
                            emitted_bytes_downloaded=bytes_downloaded,
                            emitted_total_bytes=total_bytes,
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
