"""
Uploader used by the Direct Transfer feature.
"""
import json
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

from nuxeo.utils import guess_mimetype

from ...engine.activity import LinkingAction, UploadAction
from ...metrics.constants import (
    DT_DUPLICATE_BEHAVIOR,
    DT_FILE_EXTENSION,
    DT_FILE_MIMETYPE,
    DT_FILE_SIZE,
    DT_SESSION_NUMBER,
    REQUEST_METRICS,
)
from ...objects import DocPair, Upload
from . import BaseUploader

log = getLogger(__name__)


class DirectTransferUploader(BaseUploader):
    """Upload capabilities for the Direct Transfer feature."""

    linking_action = LinkingAction
    upload_action = UploadAction

    def get_upload(
        self, *, path: Optional[Path], doc_pair: Optional[int]
    ) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *doc_pair*."""
        ret: Optional[Upload] = self.dao.get_dt_upload(doc_pair=doc_pair)
        return ret

    def upload(
        self,
        file_path: Path,
        /,
        *,
        command: str = None,
        filename: str = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Upload a given file to the given folderish document on the server.

        Note about possible duplicate creation via a race condition client <-> server.
        Given the local *file* with the path "$HOME/some-folder/subfolder/file.odt",
        the file name is "file.odt".

        Scenario:
            - Step 1: local, check for a doc with the path name "file.odt" => nothing returned, continuing;
            - Step 2: server, a document with a path name set to "file.odt" is created;
            - Step 3: local, create the document with the path name "file.odt".

        Even if the elapsed time between steps 1 and 3 is really short, it may happen.

        What can be done to prevent such scenario is not on the Nuxeo Drive side but on the server one.
        For now, 2 options are possible but not qualified to be done in a near future:
            - https://jira.nuxeo.com/browse/NXP-22959;
            - create a new operation `Document.GetOrCreate` that ensures atomicity.
        """
        doc_pair: DocPair = kwargs.pop("doc_pair")

        log.info(
            f"Direct Transfer of {file_path!r} into {doc_pair.remote_parent_path!r} ({doc_pair.remote_parent_ref!r})"
        )

        if doc_pair.duplicate_behavior == "ignore" and self.remote.exists_in_parent(
            doc_pair.remote_parent_ref, file_path.name, doc_pair.folderish
        ):
            msg = f"Ignoring the transfer as a document already has the name {file_path.name!r} on the server"
            log.debug(msg)
            return {}

        if doc_pair.folderish:
            item = self.remote.upload_folder(
                doc_pair.remote_parent_path,
                {"title": doc_pair.local_name},
                headers={DT_SESSION_NUMBER: doc_pair.session},
            )
            self.dao.update_remote_parent_path_dt(file_path, item["path"], item["uid"])
        else:
            # Only replace the document if the user wants to
            overwrite = doc_pair.duplicate_behavior == "override"

            # Upload the blob and use the FileManager importer to create the document
            item = super().upload_impl(
                file_path,
                "FileManager.Import",
                context={"currentDocument": doc_pair.remote_parent_path},
                params={"overwite": overwrite},  # NXP-29286
                engine_uid=kwargs.get("engine_uid", ""),
                is_direct_transfer=True,
                remote_parent_path=doc_pair.remote_parent_path,
                remote_parent_ref=doc_pair.remote_parent_ref,
                doc_pair=doc_pair.id,
                headers={
                    REQUEST_METRICS: json.dumps(
                        {
                            DT_FILE_EXTENSION: file_path.suffix or "None",
                            DT_FILE_MIMETYPE: guess_mimetype(file_path),
                            DT_FILE_SIZE: str(doc_pair.size),
                            DT_DUPLICATE_BEHAVIOR: doc_pair.duplicate_behavior,
                            DT_SESSION_NUMBER: doc_pair.session,
                        }
                    )
                },
            )
        self.dao.save_session_item(doc_pair.session, item)
        return item
