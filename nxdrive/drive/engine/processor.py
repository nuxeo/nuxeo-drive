"""Server-agnostic processor base class.

Provides the interface that ``QueueManager`` and ``Engine`` depend on
(signals, ``get_current_pair()``, ``soft_locks``).  The concrete
sync logic lives in each server-type package
(e.g. ``nuxeo/engine/processor.py``).
"""

from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Callable, Dict, List, Optional

from nxdrive.drive.engine.workers import EngineWorker
from nxdrive.drive.exceptions import PairInterrupt
from nxdrive.drive.objects import DocPair
from nxdrive.drive.qt.imports import Signal

if TYPE_CHECKING:
    from nxdrive.drive.engine.engine import Engine

__all__ = ("Processor",)


class Processor(EngineWorker):
    """Base processor — subclass in each server-type package."""

    pairSyncStarted = Signal(object)
    pairSyncEnded = Signal(object)

    path_locker = Lock()
    soft_locks: Dict[str, Dict[Path, bool]] = {}
    readonly_locks: Dict[str, Dict[Path, List[int]]] = {}
    readonly_locker = Lock()

    def __init__(self, engine: "Engine", item_getter: Callable, /) -> None:
        super().__init__(engine, engine.dao, "Processor")
        self._get_item = item_getter
        self.engine = engine
        self.local = self.engine.local
        self.remote = self.engine.remote
        self._current_doc_pair: Optional[DocPair] = None

    def get_current_pair(self) -> Optional[DocPair]:
        return self._current_doc_pair

    def _ensure_remote_first_pass(self, doc_pair: DocPair, /) -> None:
        """Hold back local creations until the remote watcher completed its first pass,
        else a document created server-side while Drive was stopped is duplicated
        instead of being flagged as a conflict."""
        watcher = getattr(self.engine, "_remote_watcher", None)
        if watcher is not None and not watcher.first_pass_done:
            raise PairInterrupt(f"Waiting for the first remote pass: {doc_pair!r}")

    def _execute(self) -> None:
        raise NotImplementedError
