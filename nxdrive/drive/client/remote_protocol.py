"""Protocol (structural type) for remote sync clients.

Each server-type package provides an implementation of this interface
so that the ``Processor``, ``Engine``, and watcher code
can work with any server type without caring about specifics.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from typing_extensions import Protocol, runtime_checkable

from nxdrive.drive.objects import RemoteFileInfo


@runtime_checkable
class RemoteClientProtocol(Protocol):
    """Minimal contract that every remote sync client must satisfy."""

    def get_filesystem_root_info(self) -> RemoteFileInfo:
        """Return info for the top-level sync root."""
        ...

    def get_fs_children(
        self, fs_item_id: str, /, *, filtered: bool = True
    ) -> List[RemoteFileInfo]:
        """List children of a remote folder."""
        ...

    def get_fs_info(
        self, fs_item_id: str, /, *, parent_fs_item_id: str = None
    ) -> RemoteFileInfo:
        """Return info for a single remote item."""
        ...

    def get_info(
        self,
        ref: str,
        /,
        *,
        raise_if_missing: bool = True,
        parent_fs_item_id: str = None,
    ) -> Optional[RemoteFileInfo]:
        """Return info or *None* if missing (when *raise_if_missing* is False)."""
        ...

    def fetch(
        self,
        ref: str,
        /,
        *,
        headers: Dict[str, str] = None,
        enrichers: List[str] = None,
    ) -> Dict[str, Any]:
        """Return the raw dict representation of a remote item."""
        ...

    def stream_content(
        self,
        fs_item_id: str,
        file_path: Path,
        file_out: Path,
        /,
        **kwargs: Any,
    ) -> Path:
        """Download remote content to *file_out*."""
        ...

    def stream_file(
        self,
        parent_id: str,
        file_path: Path,
        /,
        *,
        filename: str = None,
        **kwargs: Any,
    ) -> RemoteFileInfo:
        """Upload a new file under *parent_id*."""
        ...

    def stream_update(
        self,
        fs_item_id: str,
        file_path: Path,
        /,
        *,
        parent_fs_item_id: str = None,
        filename: str = None,
    ) -> RemoteFileInfo:
        """Update the content of an existing remote file."""
        ...

    def make_folder(
        self, parent_id: str, name: str, /, *, overwrite: bool = False
    ) -> RemoteFileInfo:
        """Create a folder under *parent_id*."""
        ...

    def delete(self, fs_item_id: str, /, *, parent_fs_item_id: str = None) -> None:
        """Delete a remote item."""
        ...

    def rename(self, fs_item_id: str, new_name: str, /) -> RemoteFileInfo:
        """Rename a remote item."""
        ...

    def move2(self, fs_item_id: str, parent_ref: str, name: str, /) -> Dict[str, Any]:
        """Move a remote item to *parent_ref* and rename to *name*."""
        ...
