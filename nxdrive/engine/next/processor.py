# coding: utf-8
import shutil
from logging import getLogger
from pathlib import Path
from typing import Callable, TYPE_CHECKING

from ..processor import Processor as OldProcessor
from ...constants import (
    DOWNLOAD_TMP_FILE_PREFIX,
    DOWNLOAD_TMP_FILE_SUFFIX,
    PARTIALS_PATH,
    ROOT,
)
from ...objects import DocPair

if TYPE_CHECKING:
    from ..engine import Engine  # noqa

__all__ = ("Processor",)

log = getLogger(__name__)


class Processor(OldProcessor):
    def __init__(
        self, engine: "Engine", item_getter: Callable, name: str = None
    ) -> None:
        super().__init__(engine, item_getter, name=name)

    def _get_partial_folders(self) -> Path:
        local = self.engine.local
        if not local.exists(PARTIALS_PATH):
            local.make_folder(ROOT, str(PARTIALS_PATH))
        return local.abspath(PARTIALS_PATH)

    def _download_content(self, doc_pair: DocPair, file_path: Path) -> Path:

        # TODO Should share between threads
        name = "".join(
            [
                DOWNLOAD_TMP_FILE_PREFIX,
                doc_pair.remote_digest,
                str(self._thread_id),
                DOWNLOAD_TMP_FILE_SUFFIX,
            ]
        )
        file_out = self._get_partial_folders() / name
        # Check if the file is already on the HD
        pair = self._dao.get_valid_duplicate_file(doc_pair.remote_digest)
        if pair:
            shutil.copy(str(self.local.abspath(pair.local_path)), str(file_out))
            return file_out
        tmp_file = self.remote.stream_content(
            doc_pair.remote_ref,
            file_path,
            parent_fs_item_id=doc_pair.remote_parent_ref,
            file_out=file_out,
        )
        self._update_speed_metrics()
        return tmp_file

    def _update_remotely(self, doc_pair: DocPair, is_renaming: bool) -> None:
        log.warning("_update_remotely")
        os_path = self.local.abspath(doc_pair.local_path)
        if is_renaming:
            new_os_path = os_path.with_name(doc_pair.remote_name)
            log.debug(f"Replacing local file {os_path!r} by {new_os_path!r}.")
        else:
            new_os_path = os_path
        log.debug(f"Updating content of local file {os_path!r}.")
        tmp_file = self._download_content(doc_pair, new_os_path)
        # Delete original file and rename tmp file
        self.local.delete_final(doc_pair.local_path)
        rel_path = self.local.get_path(tmp_file)
        self.local.set_remote_id(rel_path, doc_pair.remote_ref)
        # Move rename
        updated_info = self.local.move(
            rel_path, doc_pair.local_parent_path, doc_pair.remote_name
        )
        doc_pair.local_digest = updated_info.get_digest()
        self._dao.update_last_transfer(doc_pair.id, "download")
        self._refresh_local_state(doc_pair, updated_info)

    def _create_remotely(
        self, doc_pair: DocPair, parent_pair: DocPair, name: str
    ) -> Path:
        local_parent_path = parent_pair.local_path
        # TODO Shared this locking system / Can have concurrent lock
        self._unlock_readonly(local_parent_path)
        tmp_file = None
        try:
            if doc_pair.folderish:
                log.debug(
                    f"Creating local folder {name!r} in "
                    f"{self.local.abspath(parent_pair.local_path)!r}"
                )
                # Might want do temp name to original
                path = self.local.make_folder(local_parent_path, name)

            else:
                path, os_path, name = self.local.get_new_file(local_parent_path, name)
                tmp_file = self._download_content(doc_pair, os_path)
                log.debug(
                    f"Creating local file {name!r} in "
                    f"{self.local.abspath(parent_pair.local_path)!r}"
                )
                # Move file to its folder - might want to split it in two for events
                self.local.move(self.local.get_path(tmp_file), local_parent_path, name)
                self._dao.update_last_transfer(doc_pair.id, "download")
        finally:
            self._lock_readonly(local_parent_path)
            # Clean .nxpart if needed
            if tmp_file and tmp_file.is_file():
                tmp_file.unlink()
        return path
