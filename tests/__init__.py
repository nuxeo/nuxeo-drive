# coding: utf-8
import logging
import os
from typing import Any, Dict, List, Tuple

import nuxeo.client
import nuxeo.constants
import nuxeo.operations
from nuxeo.exceptions import HTTPError

from nxdrive.client import LocalClient, Remote
from nxdrive.constants import MAC
from nxdrive.engine.engine import Engine
from nxdrive.logging_config import configure
from nxdrive.manager import Manager
from nxdrive.objects import NuxeoDocumentInfo, RemoteFileInfo
from nxdrive.utils import make_tmp_file, safe_filename

# Automatically check all operations done with the Python client
nuxeo.constants.CHECK_PARAMS = True

# Remove features for tests
Engine.add_to_favorites = lambda *args: None
Manager._create_findersync_listener = lambda *args: None
Manager._create_updater = lambda *args: None
Manager._create_server_config_updater = lambda *args: None
Manager._handle_os = lambda: None
Manager.send_sync_status = lambda *args: None

if MAC:
    from nxdrive.osi.darwin.darwin import DarwinIntegration

    DarwinIntegration._cleanup = lambda *args: None
    DarwinIntegration._init = lambda *args: None
    DarwinIntegration._send_notification = lambda *args: None
    DarwinIntegration.send_sync_status = lambda *args: None
    DarwinIntegration.watch_folder = lambda *args: None
    DarwinIntegration.unwatch_folder = lambda *args: None


def configure_logger():
    formatter = logging.Formatter(
        "%(thread)-4d %(module)-14s %(levelname).1s %(message)s"
    )
    configure(
        console_level="TRACE",
        command_name="test",
        force_configure=True,
        formatter=formatter,
    )


# Configure test logger
configure_logger()
log = logging.getLogger(__name__)

# Operations cache
OPS_CACHE = None
SERVER_INFO = None


class LocalTest(LocalClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_content(self, ref: str) -> bytes:
        with open(self.abspath(ref), "rb") as f:
            return f.read()

    def has_folder_icon(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def set_folder_icon(self, *args: Any, **kwargs: Any) -> None:
        return

    def update_content(
        self, ref: str, content: bytes, xattr_names: Tuple[str, ...] = ("ndrive",)
    ) -> None:
        xattrs = {name: self.get_remote_id(ref, name=name) for name in xattr_names}

        with open(self.abspath(ref), "wb") as f:
            f.write(content)

        for name, value in xattrs.items():
            if value is not None:
                self.set_remote_id(ref, value, name=name)


class RemoteBase(Remote):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Save bandwith by caching operations details
        global OPS_CACHE
        if not OPS_CACHE:
            OPS_CACHE = self.operations.operations
            nuxeo.operations.API.ops = OPS_CACHE
        global SERVER_INFO
        if not SERVER_INFO:
            SERVER_INFO = self.client.server_info()
            nuxeo.client.NuxeoClient._server_info = SERVER_INFO

    def conflicted_name(self, original_name: str) -> str:
        """Generate a new name suitable for conflict deduplication."""
        return self.operations.execute(
            command="NuxeoDrive.GenerateConflictedItemName", name=original_name
        )

    def get_children(self, ref: str) -> Dict[str, Any]:
        return self.operations.execute(
            command="Document.GetChildren", input_obj="doc:" + ref
        )

    def get_children_info(self, ref: str, limit: int = 1000) -> List[NuxeoDocumentInfo]:
        ref = self._check_ref(ref)
        types = {"File", "Note", "Workspace", "Folder", "Picture"}

        query = (
            "SELECT * FROM Document"
            "       WHERE ecm:parentId = '%s'"
            "       AND ecm:primaryType IN ('%s')"
            "       %s"
            "       AND ecm:isVersion = 0"
            "       ORDER BY dc:title, dc:created LIMIT %d"
        ) % (ref, "', '".join(types), self._get_trash_condition(), limit)
        entries = self.query(query)["entries"]
        return self._filtered_results(entries)

    def get_content(self, fs_item_id: str, **kwargs: Any) -> str:
        """Download and return the binary content of a file system item

        Beware that the content is loaded in memory.

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_fs_info(fs_item_id)
        download_url = self.client.host + fs_item_info.download_url
        return self.download(download_url, digest=fs_item_info.digest, **kwargs)

    def get_roots(self) -> List[NuxeoDocumentInfo]:
        res = self.operations.execute(command="NuxeoDrive.GetRoots")
        return self._filtered_results(res["entries"], fetch_parent_uid=False)

    def make_file(self, parent_id: str, name: str, content: bytes) -> RemoteFileInfo:
        """Create a document with the given name and content

        Creates a temporary file from the content then streams it.
        """
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            fs_item = self.upload(
                file_path,
                filename=name,
                command="NuxeoDrive.CreateFile",
                parentId=parent_id,
            )
            return RemoteFileInfo.from_dict(fs_item)
        finally:
            os.remove(file_path)

    def update_content(
        self, ref: str, content: bytes, filename: str = None, mime_type: str = None
    ) -> RemoteFileInfo:
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            if filename is None:
                filename = self.get_fs_info(ref).name
            fs_item = self.upload(
                file_path,
                filename=filename,
                mime_type=mime_type,
                command="NuxeoDrive.UpdateFile",
                id=ref,
            )
            return RemoteFileInfo.from_dict(fs_item)
        finally:
            os.remove(file_path)


class RemoteTest(RemoteBase):

    _download_remote_error = None
    _upload_remote_error = None
    _server_error = None
    raise_on = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.exec_fn = self.operations.execute
        self.operations.execute = self.execute

    def download(self, *args, **kwargs):
        self._raise(self._download_remote_error, *args, **kwargs)
        return super().download(*args, **kwargs)

    def upload(self, *args, **kwargs):
        self._raise(self._upload_remote_error, *args, **kwargs)
        return super().upload(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._raise(self._server_error, *args, **kwargs)
        return self.exec_fn(*args, **kwargs)

    def make_download_raise(self, error):
        """ Make next calls to do_get() raise the provided exception. """
        self._download_remote_error = error

    def make_upload_raise(self, error):
        """ Make next calls to upload() raise the provided exception. """
        self._upload_remote_error = error

    def make_server_call_raise(self, error):
        """ Make next calls to the server raise the provided exception. """
        self._server_error = error

    def _raise(self, exc, *args, **kwargs):
        """ Make the next calls raise `exc` if `raise_on()` allowed it. """

        if exc:
            if not callable(self.raise_on):
                raise exc
            if self.raise_on(*args, **kwargs):
                raise exc

    def reset_errors(self):
        """ Remove custom errors. """

        self._download_remote_error = None
        self._upload_remote_error = None
        self._server_error = None
        self.raise_on = None

    def activate_profile(self, profile):
        self.operations.execute(
            command="NuxeoDrive.SetActiveFactories", profile=profile
        )

    def deactivate_profile(self, profile):
        self.operations.execute(
            command="NuxeoDrive.SetActiveFactories", profile=profile, enable=False
        )

    def mass_import(self, target_path, nb_nodes, nb_threads=12):
        tx_timeout = 3600
        url = "site/randomImporter/run"
        params = {
            "targetPath": target_path,
            "batchSize": 50,
            "nbThreads": nb_threads,
            "interactive": "true",
            "fileSizeKB": 1,
            "nbNodes": nb_nodes,
            "nonUniform": "true",
            "transactionTimeout": tx_timeout,
        }
        headers = {"Nuxeo-Transaction-Timeout": str(tx_timeout)}

        log.info(
            "Calling random mass importer on %s with %d threads " "and %d nodes",
            target_path,
            nb_threads,
            nb_nodes,
        )

        self.client.request(
            "GET", url, params=params, headers=headers, timeout=tx_timeout
        )

    def wait_for_async_and_es_indexing(self):
        """ Use for test_volume only. """

        tx_timeout = 3600
        headers = {"Nuxeo-Transaction-Timeout": str(tx_timeout)}
        self.operations.execute(
            command="Elasticsearch.WaitForIndexing",
            timeout=tx_timeout,
            headers=headers,
            timeoutSecond=tx_timeout,
            refresh=True,
        )

    def result_set_query(self, query):
        return self.operations.execute(command="Repository.ResultSetQuery", query=query)

    def log_on_server(self, message, level="WARN"):
        """ Log the current test server side.  Helpful for debugging. """
        return self.operations.execute(
            command="Log", message=message, level=level.lower()
        )

    def wait(self):
        self.operations.execute(command="NuxeoDrive.WaitForElasticsearchCompletion")


class DocRemote(RemoteTest):
    def create(
        self,
        ref: str,
        doc_type: str,
        name: str = None,
        properties: Dict[str, str] = None,
    ):
        name = safe_filename(name)
        return self.operations.execute(
            command="Document.Create",
            input_obj="doc:" + ref,
            type=doc_type,
            name=name,
            properties=properties,
        )

    def make_folder(self, parent: str, name: str, doc_type: str = "Folder") -> str:
        # TODO: make it possible to configure context dependent:
        # - SocialFolder under SocialFolder or SocialWorkspace
        # - Folder under Folder or Workspace
        # This configuration should be provided by a special operation on the
        # server.
        parent = self._check_ref(parent)
        doc = self.create(parent, doc_type, name=name, properties={"dc:title": name})
        return doc["uid"]

    def make_file(
        self, parent: str, name: str, content: bytes = None, doc_type: str = "File"
    ) -> str:
        """Create a document of the given type with the given name and content

        Creates a temporary file from the content then streams it.
        """
        parent = self._check_ref(parent)
        properties = {"dc:title": name}
        if doc_type is "Note" and content is not None:
            properties["note:note"] = content
        doc = self.create(parent, doc_type, name=name, properties=properties)
        ref = doc["uid"]
        if doc_type is not "Note" and content is not None:
            self.attach_blob(ref, content, name)
        return ref

    def make_file_in_user_workspace(
        self, content: bytes, filename: str
    ) -> RemoteFileInfo:
        """Stream the given content as a document in the user workspace"""
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(
                file_path,
                filename=filename,
                command="UserWorkspace.CreateDocumentFromBlob",
            )
        finally:
            os.remove(file_path)

    def stream_file(
        self,
        parent: str,
        name: str,
        file_path: str,
        filename: str = None,
        mime_type: str = None,
        doc_type: str = "File",
    ) -> str:
        """Create a document by streaming the file with the given path"""
        ref = self.make_file(parent, name, doc_type=doc_type)
        self.upload(
            file_path,
            filename=filename,
            mime_type=mime_type,
            command="Blob.Attach",
            document=ref,
        )
        return ref

    def attach_blob(self, ref: str, blob: bytes, filename: str):
        file_path = make_tmp_file(self.upload_tmp_dir, blob)
        try:
            return self.upload(
                file_path, filename=filename, command="Blob.Attach", document=ref
            )
        finally:
            os.remove(file_path)

    def get_content(self, ref: str) -> bytes:
        """
        Download and return the binary content of a document
        Beware that the content is loaded in memory.
        """

        if not isinstance(ref, NuxeoDocumentInfo):
            ref = self._check_ref(ref)
        return self.get_blob(ref)

    def update_content(
        self, ref: str, content: bytes, filename: str = None, **kwargs
    ) -> None:
        """Update a document with the given content

        Creates a temporary file from the content then streams it.
        """
        if filename is None:
            filename = self.get_info(ref).name
        self.attach_blob(self._check_ref(ref), content, filename)

    def move(self, ref: str, target: str, name: str = None):
        return self.operations.execute(
            command="Document.Move",
            input_obj="doc:" + self._check_ref(ref),
            target=self._check_ref(target),
            name=name,
        )

    def update(self, ref: str, properties=None):
        return self.operations.execute(
            command="Document.Update", input_obj="doc:" + ref, properties=properties
        )

    def copy(self, ref: str, target: str, name: str = None):
        return self.operations.execute(
            command="Document.Copy",
            input_obj="doc:" + self._check_ref(ref),
            target=self._check_ref(target),
            name=name,
        )

    def delete(self, ref: str, use_trash: bool = True):
        input_obj = "doc:" + self._check_ref(ref)
        if use_trash:
            try:
                if not self._has_new_trash_service:
                    return self.operations.execute(
                        command="Document.SetLifeCycle",
                        input_obj=input_obj,
                        value="delete",
                    )
                else:
                    return self.operations.execute(
                        command="Document.Trash", input_obj=input_obj
                    )
            except HTTPError as e:
                if e.status != 500:
                    raise
        return self.operations.execute(command="Document.Delete", input_obj=input_obj)

    def delete_content(self, ref: str, xpath: str = None):
        return self.delete_blob(self._check_ref(ref), xpath=xpath)

    def delete_blob(self, ref: str, xpath: str = None):
        return self.operations.execute(
            command="Blob.Remove", input_obj="doc:" + ref, xpath=xpath
        )

    def is_locked(self, ref: str) -> bool:
        data = self.fetch(ref, headers={"fetch-document": "lock"})
        return "lockCreated" in data

    def get_repository_names(self):
        return self.operations.execute(command="GetRepositories")["value"]

    def get_versions(self, ref: str):
        headers = {"X-NXfetch.document": "versionLabel"}
        versions = self.operations.execute(
            command="Document.GetVersions",
            input_obj="doc:" + self._check_ref(ref),
            headers=headers,
        )
        return [(v["uid"], v["versionLabel"]) for v in versions["entries"]]

    def create_version(self, ref: str, increment: str = "None"):
        doc = self.operations.execute(
            command="Document.CreateVersion",
            input_obj="doc:" + self._check_ref(ref),
            increment=increment,
        )
        return doc["uid"]

    def restore_version(self, version: str) -> str:
        doc = self.operations.execute(
            command="Document.RestoreVersion",
            input_obj="doc:" + self._check_ref(version),
        )
        return doc["uid"]

    def block_inheritance(self, ref: str, overwrite: bool = True):
        input_obj = "doc:" + self._check_ref(ref)

        self.operations.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user="Administrator",
            permission="Everything",
            overwrite=overwrite,
        )

        self.operations.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user="Everyone",
            permission="Everything",
            grant=False,
            overwrite=False,
        )
