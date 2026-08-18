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
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from logging import getLogger
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from nxdrive.drive.constants import APP_NAME, DirectDownloadStatus
from nxdrive.drive.engine.workers import Worker
from nxdrive.drive.objects import DirectDownload as DirectDownloadRecord
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import pyqtSignal, pyqtSlot
from nxdrive.drive.utils import simplify_url

if TYPE_CHECKING:
    from nxdrive.drive.engine.engine import Engine  # noqa
    from nxdrive.drive.manager import Manager  # noqa

__all__ = ("DirectDownload", "DownloadPaused")

log = getLogger(__name__)


# Re-export ``DownloadPaused`` so callers of the Direct-Download layer
# (including the Nuxeo subclass) can grab both the worker class and the
# pause sentinel from a single module.  The exception itself is defined
# alongside the other transfer-lifecycle errors in
# ``nxdrive.drive.exceptions``; it is raised from the chunk loop when
# the user pauses a mid-flight transfer and is caught in
# :meth:`DirectDownload._run_doc`, which releases the executor thread
# so the pool stays healthy while the record waits for a Resume click.
from nxdrive.drive.exceptions import DownloadPaused  # noqa: E402


@dataclass
class _Batch:
    """
    Bookkeeping for a single Direct Download batch running on the
    worker pool. One instance is created per URL click (or per
    resumed group at startup) and lives until every document in the
    batch has been finalized (COMPLETED / FAILED / CANCELLED).

    Access to the mutable counters is protected by ``lock``.
    """

    batch_id: str
    batch_folder: Path
    record_uids: List[int] = field(default_factory=list)
    remaining: int = 0
    total: int = 0
    successful: int = 0
    failed: int = 0
    selected_items_str: str = ""
    finalized: bool = False
    lock: Lock = field(default_factory=Lock)


class DirectDownload(Worker):
    """Server-agnostic Direct Download worker.

    Subclass in each server-type package and override the abstract hooks:
    ``_process_download()``, ``_download_folder()``, ``_get_children()``,
    ``_get_download_url()``, ``_download_file()``, ``_calculate_folder_size()``,
    ``_create_download_record()``.

    Concurrency: documents are dispatched to a bounded thread pool
    (see ``Options.direct_download_max_workers``), so multiple
    documents — potentially from different user-clicked batches — can
    be streamed in parallel. Per-batch finalisation (zip archive,
    move to Downloads, status flip to COMPLETED) fires once every
    document in that batch has settled.
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

    def __init__(
        self,
        manager: "Manager",
        folder: Path,
        /,
        *,
        executor: Optional[Any] = None,
    ) -> None:
        super().__init__("DirectDownload")

        self._manager = manager
        self._folder = folder
        self.lock = Lock()

        self._stop = False

        # List to track all download batch folders (download_<timestamp>)
        # Guarded by ``_folders_lock`` because worker-pool threads may
        # append or remove entries concurrently on batch start/cleanup.
        self._download_folders: List[str] = []
        self._folders_lock = Lock()

        # In-flight batches keyed by ``batch_id`` (== batch folder name).
        # Guarded by ``_batches_lock``.
        self._batches: Dict[str, _Batch] = {}
        self._batches_lock = Lock()

        # Ensure persisted active downloads are requeued only once per app run.
        self._resumed_persisted_downloads = False

        # Ensure the download folder exists
        self._folder.mkdir(parents=True, exist_ok=True)
        log.info(f"Direct Download folder: {self._folder}")

        # Bounded thread pool that streams documents in parallel. Tests
        # can inject a synchronous stand-in through the ``executor``
        # keyword to keep behaviour deterministic.
        if executor is not None:
            self._executor: Any = executor
            self._owns_executor = False
        else:
            max_workers = max(1, int(Options.direct_download_max_workers or 1))
            self._executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="DirectDownload",
            )
            self._owns_executor = True

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
        with self._folders_lock:
            return list(self._download_folders)

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

        with self._folders_lock:
            self._download_folders.append(folder_name)

        return batch_folder

    def check_active_sessions(self) -> bool:
        """Check if any engine still has active direct download sessions."""
        for engine in self._manager.engines.copy().values():
            dao = getattr(engine, "dao", None)
            if not dao:
                continue
            active_downloads = dao.get_active_direct_downloads()
            if active_downloads:
                return True
        return False

    def _can_finalize_batch(self, record_uids: List[int], /) -> bool:
        """Return True when the current batch is safe to archive/finalize."""
        for uid in record_uids:
            record = self._get_download_record(uid)
            if not record:
                continue
            if record.status in (
                DirectDownloadStatus.PENDING,
                DirectDownloadStatus.PAUSED,
                DirectDownloadStatus.CANCELLED,
            ):
                return False
        return True

    def cleanup(self) -> None:
        """
        Clean up the download folder by removing all downloaded files and folders.
        This is similar to how Direct Edit clears its edit folder.
        Also clears the list of download folder names.
        """
        log.info("Cleanup Direct Download folder")

        if not self._folder.exists():
            self._folder.mkdir(parents=True, exist_ok=True)
            with self._folders_lock:
                self._download_folders.clear()
            return

        # Check for active direct download sessions upon application shutdown
        if self._stop:
            if self.check_active_sessions():
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

        with self._folders_lock:
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
                folder_name = batch_folder.name
                with self._folders_lock:
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

        All documents from a single URL request are treated as one
        batch for zip-archive purposes, but are dispatched to the
        worker pool **individually** so multiple documents (and
        multiple batches) can stream in parallel.

        A PENDING database record is inserted **synchronously** for
        every document before the futures are submitted, so the UI
        renders the new download immediately — even while other
        downloads are still in progress.
        """
        if not documents:
            log.warning("No documents to download")
            return

        self._process_batch(documents)

    def resume_persisted_downloads(self) -> None:
        """
        Requeue active downloads stored in databases after an application restart.
        Active records (PENDING / IN_PROGRESS / PAUSED) are grouped by their
        original batch identifier and re-submitted to the worker pool.
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
            self._process_batch(documents)

        if resumed_count:
            log.info(
                f"Resubmitted {resumed_count} persisted direct download(s) in {len(batches)} batch(es)"
            )

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
        """Idle loop.

        With the worker pool now driving downloads, this thread only
        exists to honour pause/resume/stop through ``_interact``. It
        does no work itself.
        """
        while not self._stop:
            try:
                self._interact()
            except Exception:
                # ``_interact`` raises ThreadInterrupt on stop — bail
                # out cleanly instead of spamming the log.
                return
            time.sleep(0.1)


    # ------------------------------------------------------------------ batch processing

    def _process_batch(self, documents: List[Dict[str, str]], /) -> None:
        """
        Turn a list of documents into an in-flight batch and dispatch
        each document as a separate task on the worker pool.

        The pending database rows are inserted **synchronously** here
        (before submission) so the UI shows every requested download
        as soon as the user clicks the link, even while other
        downloads are still running.

        :param documents: List of document dictionaries to download
        """
        if not documents:
            return

        batch_size = len(documents)

        # Reuse the original temp folder when resuming persisted downloads so
        # that already-downloaded files are not fetched again.
        old_batch_folder_name: Optional[str] = documents[0].get("_batch_folder")
        if old_batch_folder_name:
            candidate = self._folder / old_batch_folder_name
            if candidate.is_dir():
                batch_folder = candidate
                with self._folders_lock:
                    if old_batch_folder_name not in self._download_folders:
                        self._download_folders.append(old_batch_folder_name)
            else:
                batch_folder = self._create_batch_folder()
        else:
            batch_folder = self._create_batch_folder()

        # Use doc_id as fallback if filename is None or empty
        selected_item_names = [
            doc.get("filename") or doc.get("doc_id", "unknown") for doc in documents
        ]
        selected_items_str = ", ".join(selected_item_names)

        # Use batch folder name as the batch identifier for grouping
        batch_id = batch_folder.name

        batch = _Batch(
            batch_id=batch_id,
            batch_folder=batch_folder,
            selected_items_str=selected_items_str,
        )

        # Insert / adopt records synchronously so the UI can show every
        # requested download immediately.
        prepared_docs: List[Dict[str, Any]] = []
        for doc in documents:
            existing_record_uid = doc.get("_record_uid")
            if existing_record_uid:
                record_uid = int(existing_record_uid)
            else:
                record_uid = self._insert_pending_record(
                    doc, selected_items=selected_items_str, batch_id=batch_id
                )

            if not record_uid:
                # Failed to persist — still count as a batch member so
                # ``batchCompleted`` totals stay consistent.
                self.downloadError.emit(
                    str(doc.get("filename") or doc.get("doc_id") or "unknown"),
                    "Failed to create download record",
                )
                batch.failed += 1
                continue

            doc["_record_uid"] = record_uid
            batch.record_uids.append(record_uid)
            prepared_docs.append(doc)

        batch.total = len(prepared_docs)
        batch.remaining = len(prepared_docs)

        # Nothing to do — either an empty batch or every insert failed.
        if batch.total == 0:
            self.batchStarting.emit(batch_size)
            self.batchCompleted.emit(batch.successful, batch.failed)
            self._cleanup_batch_folder(batch_folder)
            return

        with self._batches_lock:
            self._batches[batch_id] = batch

        # Announce the batch to the UI before dispatching.
        self.batchStarting.emit(batch_size)

        for doc in prepared_docs:
            self._submit_doc(doc, batch)

    def _submit_doc(self, doc: Dict[str, Any], batch: _Batch, /) -> "Future":
        """Submit one document to the worker pool. Overridable for tests."""
        return self._executor.submit(self._run_doc, doc, batch)

    def _insert_pending_record(
        self,
        doc: Dict[str, str],
        /,
        *,
        selected_items: str = None,
        batch_id: str = None,
    ) -> Optional[int]:
        """
        Insert a minimal PENDING record for *doc* and return its UID.

        The base implementation falls back to the legacy
        :meth:`_create_download_record` hook so subclasses that have
        not yet been migrated keep working. Subclasses should override
        this with a fast, remote-call-free INSERT.
        """
        return self._create_download_record(
            doc, selected_items=selected_items, batch_id=batch_id
        )

    def _enrich_record(
        self,
        record_uid: int,
        doc: Dict[str, str],
        engine: "Engine",
        /,
    ) -> None:
        """
        Populate metadata (sizes, folder counts, folderish flag) on a
        previously-inserted PENDING record. Runs on a worker thread.

        The base class is a no-op; subclasses override to perform the
        remote fetch and folder recursion here so that the GUI slot
        stays fast.
        """
        return None

    def _run_doc(self, doc: Dict[str, Any], batch: _Batch, /) -> None:
        """
        Worker-pool entry point for one document.

        Runs the full per-doc pipeline (pause / cancel gate → status
        flip → enrichment → ``_process_download``) and, on completion,
        tries to finalize the enclosing batch if it was the last one
        out.

        Cancellation, pause, and shutdown are treated as "skipped" and
        do not count towards the batch success / failure totals. In
        particular, pause returns immediately instead of blocking the
        executor thread; the record stays in ``PAUSED`` state and will
        be re-submitted by :meth:`resume_download` when the user clicks
        the Resume button.
        """
        record_uid = int(doc["_record_uid"])
        error_name = doc.get("filename") or doc.get("doc_id") or "unknown"
        outcome = "skipped"

        try:
            if self._stop:
                return

            # Fast, non-blocking pause / cancel checks. Neither one
            # spins on ``time.sleep`` any more; the parallel executor
            # needs its threads back.
            if self._is_paused(record_uid):
                log.info(f"Download {record_uid} is paused, skipping")
                return
            if self._is_single_download_cancelled(record_uid):
                log.info(f"Download {record_uid} cancelled, skipping")
                return

            try:
                self._update_download_status(
                    record_uid, DirectDownloadStatus.IN_PROGRESS
                )
                self._update_download_path(
                    record_uid, str(self._get_download_destination())
                )

                server_url = doc.get("server_url", "")
                engine = self._get_engine(server_url, user=doc.get("user"))
                if engine is not None:
                    try:
                        self._enrich_record(record_uid, doc, engine)
                    except Exception:
                        # Enrichment is best-effort; keep going even if
                        # the remote lookup blew up.
                        log.exception(
                            f"Failed to enrich record {record_uid}; "
                            "continuing with placeholder metadata"
                        )

                self._process_download(doc, batch.batch_folder)
                outcome = "ok"

            except DownloadPaused:
                # Mid-transfer pause. Leave the record in PAUSED state
                # (the DAO was updated when the user clicked pause) and
                # release the worker thread so the pool stays healthy.
                log.info(
                    f"Download {record_uid} paused mid-transfer, "
                    "will resume on user request"
                )

            except Exception as exc:
                outcome = "failed"
                log.exception("Document download failed")
                # Surface the per-doc failure to the UI. Without this,
                # ``_process_download``'s early ``except`` around
                # ``get_info`` is the *only* place ``downloadError``
                # fires, so downstream failures (e.g. a document with
                # no resolvable blob) silently vanish from the user's
                # view.
                self.downloadError.emit(str(error_name), str(exc))
                self._update_download_status(
                    record_uid,
                    DirectDownloadStatus.FAILED,
                    last_error=str(exc),
                )

        finally:
            with batch.lock:
                if outcome == "ok":
                    batch.successful += 1
                elif outcome == "failed":
                    batch.failed += 1
                # "skipped" (stop / pause / cancelled) is intentionally uncounted.
                batch.remaining -= 1
                should_finalize = batch.remaining <= 0 and not batch.finalized
                if should_finalize:
                    batch.finalized = True

            if should_finalize:
                try:
                    self._finalize_batch(batch)
                except Exception:
                    log.exception(
                        f"Failed to finalize batch {batch.batch_id!r}"
                    )

    def _finalize_batch(self, batch: _Batch, /) -> None:
        """
        Archive and finalize a batch once every one of its documents
        has settled. Fires ``batchCompleted`` at the end.

        Only records that made it through the transfer
        (``IN_PROGRESS`` at finalization time) are zipped and marked
        ``COMPLETED``. Paused / cancelled / failed records are left
        alone so a single paused document does not block the rest of
        the batch from moving to Downloads.
        """
        record_uids = list(batch.record_uids)

        finalizable_uids: List[int] = []
        for uid in record_uids:
            record = self._get_download_record(uid)
            if record and record.status == DirectDownloadStatus.IN_PROGRESS:
                finalizable_uids.append(uid)

        archive_path: Optional[Path] = None
        if finalizable_uids:
            archive_path = self._create_zip_archive(batch.batch_folder)
        else:
            # Nothing transferred — just drop the (possibly empty) batch folder.
            self._cleanup_batch_folder(batch.batch_folder)

        for uid in finalizable_uids:
            self._update_download_status(
                uid,
                DirectDownloadStatus.COMPLETED,
                download_path=(
                    str(archive_path) if archive_path else str(batch.batch_folder)
                ),
            )

        if archive_path:
            zip_file_name = archive_path.name
            for uid in finalizable_uids:
                self._update_download_path(uid, str(archive_path), zip_file_name)

        with self._batches_lock:
            self._batches.pop(batch.batch_id, None)

        self.batchCompleted.emit(batch.successful, batch.failed)

    # ------------------------------------------------------------------ resume single record

    def resume_download(self, record_uid: int, /) -> bool:
        """
        Re-submit a paused / interrupted single record to the worker
        pool. Called from the GUI API when the user clicks Resume.

        Returns ``True`` when a task was submitted, ``False`` if the
        record could not be located or the engine went away.
        """
        record: Optional[DirectDownloadRecord] = self._get_download_record(record_uid)
        if record is None:
            log.warning(f"Cannot resume download {record_uid}: record not found")
            return False

        # Reconstruct the doc dictionary. We only need enough to route
        # the download; ``_run_doc`` will re-enrich sizes as needed.
        doc: Dict[str, Any] = {
            "server_url": record.server_url,
            "doc_id": record.doc_uid,
            "filename": record.doc_name,
            "_record_uid": record_uid,
        }

        # Pull the engine's username so ``_get_engine`` can pick the
        # right binder on multi-account setups.
        for engine in self._manager.engines.copy().values():
            if engine.dao is None:
                continue
            candidate = engine.dao.get_direct_download(record_uid)
            if candidate is not None:
                try:
                    doc["user"] = engine.get_binder().username
                except Exception:
                    doc["user"] = ""
                break

        # Reuse the original batch folder when it still exists so any
        # partial data survives the resume. Otherwise start fresh.
        if record.zip_file:
            candidate_folder = self._folder / record.zip_file
            if candidate_folder.is_dir():
                doc["_batch_folder"] = record.zip_file

        self._process_batch([doc])
        return True


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
                    f"Unable to download to {configured_path} because {APP_NAME} does not have access to it. "
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
        """Return True as soon as any download in the batch is cancelled.

        Historically this method also polled while a record was
        ``PAUSED`` — that busy-wait pinned the (single) worker thread
        indefinitely.  With the parallel executor we can no longer
        afford to block: pause is now a cheap non-blocking check
        (see :meth:`_is_paused`) and resume goes through
        :meth:`resume_download`.
        """
        for uid in record_uids:
            record = self._get_download_record(uid)
            if record and record.status == DirectDownloadStatus.CANCELLED:
                return True
        return False

    def _is_single_download_cancelled(self, uid: int, /) -> bool:
        """Return True if this record has been cancelled. Non-blocking."""
        record = self._get_download_record(uid)
        return bool(record and record.status == DirectDownloadStatus.CANCELLED)

    def _is_paused(self, uid: int, /) -> bool:
        """Return True if the record is currently PAUSED. Non-blocking."""
        record = self._get_download_record(uid)
        return bool(record and record.status == DirectDownloadStatus.PAUSED)

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
        emitted_bytes_downloaded: Optional[int] = None,
        emitted_total_bytes: Optional[int] = None,
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
                        signal_bytes_downloaded = (
                            emitted_bytes_downloaded
                            if emitted_bytes_downloaded is not None
                            else bytes_downloaded
                        )
                        signal_total_bytes = (
                            emitted_total_bytes
                            if emitted_total_bytes is not None
                            else total_bytes
                        )
                        signal_progress = (
                            (signal_bytes_downloaded / signal_total_bytes * 100)
                            if signal_total_bytes > 0
                            else 0.0
                        )
                        # Emit progress signal for real-time UI updates
                        self.downloadProgress.emit(
                            {
                                "uid": uid,
                                "doc_name": filename,
                                "progress": signal_progress,
                                "bytes_downloaded": signal_bytes_downloaded,
                                "total_bytes": signal_total_bytes,
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
        record_uid: Optional[int] = None,
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

        # Best-effort shutdown of the worker pool. Any in-flight
        # streaming download bails out via the per-chunk cancellation
        # check in ``_download_file``; anything not yet started is
        # cancelled outright.
        if self._owns_executor:
            try:
                self._executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:
                # ``cancel_futures`` was added in Python 3.9; ignore on
                # older stubs.
                self._executor.shutdown(wait=False)
            except Exception:
                log.exception("Failed to shutdown Direct Download executor")

        super().stop()
