"""
Uploader used by the synchronization engine.
"""
from pathlib import Path
from typing import Any, Dict, Optional

from ...objects import Upload
from . import BaseUploader


class SyncUploader(BaseUploader):
    """Upload capabilities for the synchronization engine."""

    def get_upload(
        self, *, path: Optional[Path], doc_pair: Optional[int]
    ) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *path*."""
        ret: Optional[Upload] = self.dao.get_upload(path=path)
        return ret

    def upload(
        self,
        file_path: Path,
        /,
        *,
        command: str = "",
        filename: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """See BaseUploader.upload_impl()."""
        item = self.upload_impl(file_path, command, filename=filename, **kwargs)

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer("upload", path=file_path)

        return item
