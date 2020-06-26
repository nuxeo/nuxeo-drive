"""
Uploader used by the Direct Transfer feature.
"""
from logging import getLogger
from pathlib import Path
from typing import Any, Dict, Optional

from nuxeo.models import Document

from ...engine.activity import LinkingAction, UploadAction
from ...exceptions import DirectTransferDuplicateFoundError
from ...objects import Upload
from ..local import LocalClient
from . import BaseUploader

log = getLogger(__name__)


class DirectTransferUploader(BaseUploader):
    """Upload capabilities for the Direct Transfer feature."""

    linking_action = LinkingAction
    upload_action = UploadAction

    def get_document_by_uid(self, uid: str) -> Optional[Document]:
        """
        Fetch a document based on its UID.
        Return None if not found on the server.
        """
        ref = self.remote._escape(uid)
        query = f"SELECT * FROM Document WHERE ecm:uuid = '{ref}' AND ecm:isVersion = 0 LIMIT 1"
        results = self.remote.query(query)["entries"]
        return Document.parse(results[0]) if results else None

    def get_document_by_title(self, parent_path: str, name: str) -> Optional[Document]:
        """
        Fetch a document based on its parent's path and document's name.
        Return None if not found on the server.

        May be better to update the query when NXP-19605 will be available.
        A benchmark should be done then before choosing one or another.
        """
        parent_path = self.remote._escape(self.remote.check_ref(parent_path))
        name = self.remote._escape(name)
        query = (
            f"SELECT * FROM Document WHERE ecm:path STARTSWITH '{parent_path}/'"
            f" AND dc:title = '{name}' AND ecm:isVersion = 0 LIMIT 1"
        )
        results = self.remote.query(query)["entries"]
        return Document.parse(results[0]) if results else None

    def get_document_or_none(
        self, uid: str = "", parent_path: str = "", name: str = ""
    ) -> Optional[Document]:
        """
        Fetch a document based on given criteria.
        Return None if not found on the server.

        :param uid: Document reference (UID).
        :param path: Document reference (path).
        :rtype: Document or None
        """
        doc: Optional[Document] = None

        if uid:
            # The remote ref is known, so it means either the file has already been uploaded,
            # either a previous upload failed: the document was created, or not, and it has
            # a blob attached, or not. In any cases, we need to ensure the user can upload
            # without headhache.
            doc = self.get_document_by_uid(uid)

        if not doc:
            # We need to handle possbile duplicates based on the file name and
            # the destination folder on the server.
            # Note: using this way may still result in duplicates:
            #  - the user created 2 documents with the same name on Web-UI or another way
            #  - the user then deleted the 1st document
            #  - the other document has a path like "name.TIMESTAMP"
            # So then Drive will not see that document as a duplicate because it will check
            # a path with "name" only.
            doc = self.get_document_by_title(parent_path, name)

        return doc

    def get_upload(self, file_path: Path) -> Optional[Upload]:
        """Retrieve the eventual transfer associated to the given *file_path*."""
        ret: Optional[Upload] = self.dao.get_upload(path=file_path)
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
        parent_path = kwargs.pop("parent_path")
        engine_uid = kwargs.pop("engine_uid")
        replace_blob = kwargs.get("replace_blob", False)
        log.info(f"Direct Transfer of {file_path!r} into {parent_path!r}")

        # The remote file, when created, is stored in the file xattrs.
        # So retrieve it and if it is defined, the document creation should
        # be skipped to prevent duplicate creations.
        remote_ref = LocalClient.get_path_remote_id(file_path, name="remote")

        doc: Optional[Document] = self.get_document_or_none(
            uid=remote_ref, parent_path=parent_path, name=file_path.name
        )
        if doc:
            remote_ref = doc.uid

        if not replace_blob and doc and doc.properties.get("file:content"):
            # The document already exists and has a blob attached. Ask the user what to do.
            raise DirectTransferDuplicateFoundError(file_path, doc)

        # If the path is a folder, there is no more work to do
        # if file_path.is_dir():
        #     details: Dict[str, Any] = doc.as_dict() if doc else {}
        #     return details

        # Save the remote document's UID into the file xattrs, in case next steps fails
        if remote_ref:
            LocalClient.set_path_remote_id(file_path, remote_ref, name="remote")
        # Upload the blob and use the FileManager importer to create the document
        item = super().upload_impl(
            file_path,
            "FileManager.Import",
            context={"currentDocument": parent_path},
            params={"overwite": True},  # NXP-29286
            headers={"nx-es-sync": "true", "X-Batch-No-Drop": "true"},
            engine_uid=engine_uid,
            is_direct_transfer=True,
            remote_ref=remote_ref,
        )

        # Transfer is completed, delete the upload from the database
        self.dao.remove_transfer("upload", file_path)

        return item
