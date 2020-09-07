"""
Uploader used by the Direct Transfer feature.
"""
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

from ...engine.activity import LinkingAction, UploadAction
from ...objects import Upload
from . import BaseUploader

log = getLogger(__name__)


class DirectTransferUploader(BaseUploader):
    """Upload capabilities for the Direct Transfer feature."""

    linking_action = LinkingAction
    upload_action = UploadAction

    def exists(self, parent_ref: str, name: str) -> bool:
        """
        Fetch a document based on its parent's UID and document's name.
        Return True if such document exists.
        """
        name = self.remote._escape(name)
        query = (
            "SELECT * FROM Document"
            f" WHERE ecm:parentId = '{parent_ref}' AND dc:title = '{name}'"
            " AND ecm:isProxy = 0"
            " AND ecm:isVersion = 0"
            " AND ecm:isTrashed = 0"
        )
        return bool(self.remote.query(query)["entries"])

    def get_upload(self, file_path: Path) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *file_path*."""
        ret: Optional[Upload] = self.dao.get_dt_upload(path=file_path)
        return ret

    def upload(
        self,
        file_path: Path,
        command: str = None,
        filename: str = None,
        mime_type: str = None,
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
        doc_pair = kwargs.pop("doc_pair")

        log.info(
            f"Direct Transfer of {file_path!r} into {doc_pair.remote_parent_path!r} ({doc_pair.remote_parent_ref!r})"
        )

        if doc_pair.duplicate_behavior == "ignore" and self.exists(
            doc_pair.remote_parent_ref, file_path.name
        ):
            msg = f"Ignoring the transfer as a document already has the name {file_path.name!r} on the server"
            log.debug(msg)
            return {}

        # Only replace the document if the user wants to
        overwrite = doc_pair.duplicate_behavior == "override"

        if doc_pair.folderish:
            item = self.upload_folder(
                input_obj=doc_pair.remote_parent_path,
                params={"title": doc_pair.local_name},
            )
            self.dao.update_remote_parent_path_dt(
                str(file_path), item["path"], item["uid"]
            )
        else:
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
            )

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer("upload", file_path, is_direct_transfer=True)

        return item

    def upload_folder(self, **kwargs: Any) -> Dict[str, Any]:
        """Create a folder using the FileManager."""
        res: Dict[str, Any] = self.remote.execute(
            command="FileManager.CreateFolder",
            **kwargs,
        )
        return res
