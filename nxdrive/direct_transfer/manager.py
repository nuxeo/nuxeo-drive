# coding: utf-8
"""
The Direct Transfer feature.

What: the transfers manager.

For now, transfers are done in sequence as it eases the implementation.
For better performances, one should really use Nuxeo Drive.
"""
from collections import deque
from datetime import datetime
from logging import getLogger
from operator import attrgetter
from pathlib import Path
from typing import TYPE_CHECKING, Callable, List, Optional, Set

from PyQt5.QtCore import QCoreApplication

from ..constants import CONNECTION_ERROR, TransferStatus
from ..state import State
from ..utils import get_tree_list
from . import uploader
from .models import DATABASE, MODELS, Session, Transfer
from .runner import Runner

if TYPE_CHECKING:
    from nuxeo.handlers.default import Uploader  # noqa
    from nuxeo.models import Document  # noqa

    from .client.remote_client import Remote  # noqa


log = getLogger(__name__)


class DirectTransferManager:
    """Direct Transfer manager.
    This is the core of the feature, separated from Nuxeo Drive.
    It is used to create a new Direct Transfer, keep track of the progression,
    pause/resume transfers and it is connected to a (beautiful) custom QML component.
    """

    def __init__(
        self,
        db: str,
        engine_uid: str,
        remote: "Remote",
        chunk_callback: Callable[["Uploader"], None] = lambda *_: None,
        done_callback: Callable[[bool, int], None] = lambda *_: None,
        dupe_callback: Callable[[Path, "Document"], None] = lambda *_: None,
    ) -> None:
        """
        *chunk_callback* is triggered when a chunk is successfully uploaded.
        *done_callback* is triggered when an upload was successfully done.
        *dupe_callback* is triggered when a given upload would generate a duplicate on the server.
        """
        self.db = db
        self.engine_uid = engine_uid
        self.remote = remote
        self.chunk_callback = chunk_callback
        self.done_callback = done_callback
        self.dupe_callback = dupe_callback

        self.is_started = False
        self.reinit()

    def reinit(self) -> None:
        """(Re)Initialize the database connection, refetch session and associated transfers."""
        # Init the database
        self.init_db(self.db)

        # Retrieve the session or create a new one
        self.session, _ = Session.get_or_create(finished=None)

        # Retrieve associated transfers
        transfers = Transfer.get_or_none(Transfer.session == self.session.id) or []
        if not isinstance(transfers, list):
            # 1 record in the database
            transfers = [transfers]
        self.transfers: List[Transfer] = transfers

        # The thread-safe queue
        self._iterator: deque = deque()

        # Inject new methods
        self.inject()

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}<uid={self.engine_uid!r}"
            f", db={self.db!r}"
            f", paths={len(self.transfers)}"
            f", completed={self.is_completed!r}"
            f", started={self.is_started!r}"
            f", progress={self.progress:.1f}"
            f", size={self.size}"
            f", uploaded={self.uploaded}"
            f", priority={self.priority}"
            ">"
        )

    def __iter__(self) -> "DirectTransferManager":
        """The whole class is an iterator.
        It is used to io iterate over transfers to handle:

            >>> for transfer in self:
            ...     upload(transfer)

        """
        self._iterator.clear()
        self._iterator.extend(self.partitions)

        return self

    def __next__(self) -> Transfer:
        """Get the next transfer to handle. See __iter__()."""
        try:
            return self._iterator.popleft()  # type: ignore
        except IndexError:
            raise StopIteration()

    @property
    def is_completed(self) -> bool:
        """Return True when all transfers are done."""
        return not self.uploading and self.progress >= 100.0

    @property
    def partitions(self) -> List[Transfer]:
        """Return a list of paths to upload, sorted by remote path > file type > local path."""
        return sorted(
            self.transfers, key=attrgetter("remote_path", "is_file", "local_path")
        )

    @property
    def priority(self) -> int:
        """Session priority."""
        priority: int = self.session.priority
        return priority

    @property
    def progress(self) -> float:
        """Overall progression."""
        if not self.has_transfers_to_handle():
            # All transfers are either done or aborted
            return 100.0

        return self.uploaded * 100.0 / self.size

    @property
    def size(self) -> int:
        """Overall files size to upload."""
        return sum(
            transfer.file_size
            for transfer in self.transfers
            if transfer.status is not TransferStatus.ABORTED
        )

    @property
    def uploaded(self) -> int:
        """Overall uploaded size."""
        return sum(
            transfer.uploaded_size
            for transfer in self.transfers
            if transfer.status is not TransferStatus.ABORTED
        )

    @property
    def uploading(self) -> List[Transfer]:
        """Get the transfers being uploaded."""
        return [
            transfer
            for transfer in self.transfers
            if transfer.status is TransferStatus.ONGOING
        ]

    def add(self, local_path: Path, remote_path: str) -> Optional[Transfer]:
        """Plan the *local_path* upload to the given *remote_path*.
        Return the Transfer item.
        """
        if self.already_added(local_path):
            log.debug(f"{local_path!r} is already part of the upload list")
            return None

        try:
            is_file = local_path.is_file()
            size = local_path.stat().st_size
        except OSError:
            log.warning(f"Skipping errored {local_path!r}", exc_info=True)
            return None
        else:
            # Folders have no size
            if not is_file:
                size = 0

        transfer: Transfer = Transfer.create(
            session=self.session.id,
            local_path=local_path,
            remote_path=remote_path,
            is_file=is_file,
            file_size=size,
        )
        log.debug(
            f"Added {local_path!r} to the upload list of session {self.session.id}"
        )
        self.transfers.append(transfer)
        return transfer

    def add_all(self, local_paths: Set[Path], remote_path: str) -> None:
        """Recursively plan *local_paths* upload to the given *remote_path*."""
        for local_path in sorted(local_paths):
            if local_path.is_file():
                self.add(local_path, remote_path)
            elif local_path.is_dir():
                tree = get_tree_list(local_path, remote_path)
                for computed_remote_path, path in sorted(tree):
                    self.add(path, computed_remote_path)

    def already_added(self, local_path: Path) -> bool:
        """Return True if a given *local_path* is already planned for upload."""
        return any(transfer.local_path == local_path for transfer in self.transfers)

    def cancel(self, file: Path) -> None:
        """Cancel the transfer of the given local *file*.
        This method is used when a duplicate creation would happen but
        the user asked to cancel the upload.
        """
        for transfer in self.transfers:
            if transfer.local_path != file:
                continue

            log.info(f"Transfer of {file!r} cancelled (user choice)")
            transfer.status = TransferStatus.ABORTED  # type: ignore
            transfer.save()
            self.requeue(transfer)

    def decrease_priority(self, session: Session) -> None:
        """Decrease the *session* priority."""
        session.priority -= 1
        if session.priority < 0:
            session.priority = 0
        session.save()

    def has_transfers_to_handle(self) -> bool:
        """Check if transfers are all either completed or aborted."""
        return any(
            transfer.status not in (TransferStatus.DONE, TransferStatus.ABORTED)
            for transfer in self.transfers
        )

    def increase_priority(self, session: Session) -> None:
        """Increase the *session* priority."""
        session.priority += 1
        session.save()

    def init_db(self, db: str) -> None:
        """Initialize the database."""
        DATABASE.init(db)
        DATABASE.connect()
        DATABASE.create_tables(MODELS)
        log.debug(f"Initialized database {db!r}")

    def inject(self) -> None:
        """Inject new methods into the Remote client."""
        self.remote.dt_upload = uploader.dt_upload
        self.remote.dt_do_upload = uploader.dt_do_upload
        self.remote.dt_link_blob_to_doc = uploader.dt_link_blob_to_doc
        self.remote.dt_upload_chunks = uploader.dt_upload_chunks

    def replace_blob(self, file: Path, doc_uid: str) -> None:
        """Replace the document's blob on the server.
        This method is used when a duplicate creation would happen and
        the user asked to replace the attached blob.
        """
        for transfer in self.transfers:
            if transfer.local_path != file:
                continue

            log.info(
                "Replacing the document's attached file "
                f"(UID is {doc_uid!r}) for {file!r} (user choice)"
            )
            transfer.replace_blob = True
            transfer.save()
            self.requeue(transfer)

    def requeue(self, transfer: Transfer) -> None:
        """Repush the given *transfer* into the queue, at the beginning."""
        self._iterator.appendleft(transfer)
        log.debug(f"Re-queued {transfer.local_path!r}")
        if not self.is_started:
            self.start()

    def reset(self) -> None:
        """Reset data and start a new transfers session."""
        if self.is_started:
            log.warning("Cannot reset as there are ongoing transfers.")
            return

        if not self.session.started:
            log.warning("Cannot reset unstarted session transfers.")
            return

        if self.session.status is not TransferStatus.DONE:
            self.session.finished = datetime.now()
            self.session.status = TransferStatus.ABORTED
            self.session.save()

        self._iterator.clear()
        self.transfers = []
        self.session = Session.create()

    def reset_error(self, transfer: Transfer) -> None:
        """Reset the error of a given *transfer*."""
        transfer.error_count = 0
        transfer.save()

    def should_stop(self) -> bool:
        """Method calls before uploading any local path to let the possibility to abort the session."""
        # .stop() has been called
        return not self.is_started

    def start(self) -> None:
        """Start transfers."""
        msg = f"Direct Transfer session {self.session.id}"

        if self.is_started:
            log.warning(f"{msg} already running ... ")
            return

        if self.session.status is TransferStatus.DONE:
            log.info(f"{msg} already completed.")
            return

        log.info(f"{msg} starting ...")

        if not self.session.started:
            self.session.started = datetime.now()
            self.session.save()

        self.is_started = True
        try:
            for transfer in self:
                if self.should_stop():
                    break

                if transfer.status in (TransferStatus.DONE, TransferStatus.ABORTED):
                    # That means the local path was either:
                    # - already processed
                    # - cancelled
                    # - locally removed
                    continue

                if transfer.error_count >= 3:
                    continue

                self.upload(transfer)
        finally:
            self.is_started = False

        if not self.is_completed:
            log.info(f"{msg} ended (progression: {self.progress}%).")
            return

        self.session.finished = datetime.now()
        self.session.status = TransferStatus.DONE
        self.session.save()
        elapsed = self.session.finished - self.session.started
        log.info(f"{msg} finished in {elapsed}!")

    def shutdown(self) -> None:
        """Stop everything."""
        log.debug("Shutting down the Direct Transfer manager ...")
        self.stop()
        if not DATABASE.is_closed():
            DATABASE.close()

    def stop(self) -> None:
        """Stop transfers."""
        if not self.is_started:
            return

        log.info(f"Direct Transfer session {self.session.id} stopping ...")

        self.is_started = False
        for transfer in self.transfers:
            if transfer.status is not TransferStatus.ONGOING:
                continue

            transfer.status = TransferStatus.SUSPENDED  # type: ignore
            transfer.save()

    def upload_impl(self, transfer: Transfer) -> None:
        """Process a Transfer."""
        # Pre-check: the local path must exist
        transfer.local_path.stat()

        # If no error, do the upload
        transfer.status = TransferStatus.ONGOING  # type: ignore

        runner = Runner(
            target=self.remote.dt_upload,
            args=(self.remote, transfer),
            kwargs={"chunk_callback": self.chunk_callback},
        )
        runner.start()

        while runner.is_alive():
            # Do not block the GUI
            QCoreApplication.processEvents()

            # The application is being stopped
            if State.about_to_quit:
                self.stop()
                break

        runner.join()
        if runner.error:
            # An exception occurred, re-raise it
            raise runner.error from None

        # And trigger the "done" callback
        self.done_callback(not transfer.is_file, transfer.file_size)

    def upload(self, transfer: Transfer) -> None:
        """Process a Transfer with error management."""
        try:
            self.upload_impl(transfer)
        except FileNotFoundError:
            log.info(
                f"Removing {transfer.local_path!r} from transfers as it does not exist anymore"
            )
            transfer.status = TransferStatus.ABORTED  # type: ignore
            transfer.save()
        except uploader.DirectTransferPaused:
            log.info(f"Pausing transfer of {transfer.local_path!r}")
            transfer.status = TransferStatus.PAUSED  # type: ignore
            transfer.save()
            self.stop()
        except CONNECTION_ERROR:
            log.warning(f"Network error for {transfer.local_path!r}", exc_info=True)
            transfer.error_count += 1
            transfer.error_count_total += 1
            transfer.save()
            self.requeue(transfer)
        except uploader.DirectTransferDuplicateFoundError as exc:
            log.info(str(exc))
            log.debug(f"Calling {self.dupe_callback} to ask what action to do")
            self.dupe_callback(exc.file, exc.doc)
        except Exception:
            # On any error, skip and retry on the next call to .start()
            # It has to be done manually.
            log.warning(f"Oups, cannot upload {transfer.local_path!r}", exc_info=True)
            transfer.error_count += 1
            transfer.error_count_total += 1
            transfer.save()
            self.requeue(transfer)
