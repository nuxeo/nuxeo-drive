# coding: utf-8
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import nuxeo.client
import nuxeo.constants
import nuxeo.operations
from nuxeo.exceptions import HTTPError

from nxdrive.client.local_client import LocalClient
from nxdrive.client.remote_client import Remote
from nxdrive.objects import NuxeoDocumentInfo, RemoteFileInfo
from nxdrive.options import Options
from nxdrive.utils import force_encode, safe_filename


def patch_nxdrive_objects():
    """Some feature are not needed or are better disabled when testing."""

    # Need to do this one first because importing Manager will already import
    # nxdrive.engine.dao.utils and so changing the behavior of save_backup()
    # will not work.
    import nxdrive.engine.dao.utils

    nxdrive.engine.dao.utils.save_backup = lambda *args: True

    from nxdrive.manager import Manager
    from nxdrive.engine.queue_manager import QueueManager

    Manager._create_server_config_updater = lambda *args: None

    def dispose_all(self) -> None:
        for engine in self.get_engines().values():
            engine.dispose_db()
        self.dispose_db()

    def unbind_all(self) -> None:
        if not self._engines:
            self.load()
        for engine in self._engine_definitions:
            self.unbind_engine(engine.uid)

    def requeue_errors(self) -> None:
        with self._error_lock:
            for doc_pair in self._on_error_queue.values():
                doc_pair.error_next_try = 0

    Manager.dispose_all = dispose_all
    Manager.unbind_all = unbind_all
    QueueManager.requeue_errors = requeue_errors


patch_nxdrive_objects()


def make_tmp_file(folder: Path, content: bytes) -> Path:
    """Create a temporary file with the given content
    for streaming upload purposes.

    Make sure that you remove the temporary file with os.remove()
    when done with it.
    """
    import tempfile

    fd, path = tempfile.mkstemp(suffix="-nxdrive-file-to-upload", dir=folder)
    path = Path(path)
    try:
        path.write_bytes(force_encode(content))
    finally:
        os.close(fd)
    return path


# Operations cache
OPS_CACHE = None
SERVER_INFO = None

RawPath = Union[Path, str]


def force_path(ref: RawPath) -> Path:
    if not isinstance(ref, Path):
        ref = Path(ref.lstrip("/"))
    return ref


class LocalTest(LocalClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_content(self, ref: RawPath) -> bytes:
        ref = force_path(ref)
        return self.abspath(ref).read_bytes()

    def has_folder_icon(self, *args: Any, **kwargs: Any) -> bool:
        return True

    def set_folder_icon(self, *args: Any, **kwargs: Any) -> None:
        return

    def abspath(self, ref: RawPath) -> Path:
        ref = force_path(ref)
        return super().abspath(ref)

    def delete_final(self, ref: RawPath) -> None:
        ref = force_path(ref)
        return super().delete_final(ref)

    def exists(self, ref: RawPath) -> bool:
        ref = force_path(ref)
        return super().exists(ref)

    def get_children_info(self, ref: RawPath):
        ref = force_path(ref)
        return super().get_children_info(ref)

    def get_info(self, ref: RawPath):
        ref = force_path(ref)
        return super().get_info(ref)

    def get_path(self, abspath: RawPath):
        abspath = force_path(abspath)
        return super().get_path(abspath)

    def rename(self, ref: RawPath, to_name: str) -> Path:
        ref = force_path(ref)
        return super().rename(ref, to_name).filepath

    def update_content(
        self, ref: RawPath, content: bytes, xattr_names: Tuple[str, ...] = ("ndrive",)
    ) -> None:
        ref = force_path(ref)
        xattrs = {name: self.get_remote_id(ref, name=name) for name in xattr_names}

        self.abspath(ref).write_bytes(content)

        for name, value in xattrs.items():
            if value is not None:
                self.set_remote_id(ref, value, name=name)

    def make_folder(self, parent: RawPath, *args: Any, **kwargs: Any) -> Path:
        parent = force_path(parent)
        return super().make_folder(parent, *args, **kwargs)

    def make_file(self, parent: RawPath, name: str, content: bytes = None) -> Path:
        parent = force_path(parent)
        os_path, name = self._abspath_deduped(parent, name)
        locker = self.unlock_ref(parent, unlock_parent=False)
        try:
            if content:
                os_path.write_bytes(content)
            else:
                os_path.touch()
            return parent / name
        finally:
            self.lock_ref(parent, locker)

    def get_new_file(self, parent: RawPath, name: str) -> Tuple[Path, Path, str]:
        parent = force_path(parent)
        return super().get_new_file(parent, name)

    def move(self, ref: RawPath, new_parent_ref: RawPath, name: str = None):
        ref = force_path(ref)
        new_parent_ref = force_path(new_parent_ref)
        return super().move(ref, new_parent_ref, name=name)

    def delete(self, ref: RawPath) -> None:
        ref = force_path(ref)
        return super().delete(ref)


class RemoteBase(Remote):
    def __init__(self, *args, upload_tmp_dir: str = None, **kwargs):
        super().__init__(*args, **kwargs)

        self.upload_tmp_dir = (
            upload_tmp_dir if upload_tmp_dir is not None else tempfile.gettempdir()
        )

        # Save bandwith by caching operations details
        global OPS_CACHE
        if not OPS_CACHE:
            OPS_CACHE = self.operations.operations
            nuxeo.operations.API.ops = OPS_CACHE
        global SERVER_INFO
        if not SERVER_INFO:
            SERVER_INFO = self.client.server_info()
            nuxeo.client.NuxeoClient._server_info = SERVER_INFO

    def fs_exists(self, fs_item_id: str) -> bool:
        return self.execute(command="NuxeoDrive.FileSystemItemExists", id=fs_item_id)

    def get_children(self, ref: str) -> Dict[str, Any]:
        return self.execute(command="Document.GetChildren", input_obj=f"doc:{ref}")

    def get_children_info(self, ref: str, limit: int = 1000) -> List[NuxeoDocumentInfo]:
        ref = self._escape(self._check_ref(ref))
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

    def get_content(self, fs_item_id: str, **kwargs: Any) -> Path:
        """Download and return the binary content of a file system item

        Beware that the content is loaded in memory.

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_fs_info(fs_item_id)
        download_url = self.client.host + fs_item_info.download_url
        return self.download(download_url, digest=fs_item_info.digest, **kwargs)

    def get_roots(self) -> List[NuxeoDocumentInfo]:
        res = self.execute(command="NuxeoDrive.GetRoots")
        return self._filtered_results(res["entries"], fetch_parent_uid=False)

    def make_file(
        self, parent_id: str, name: str, content: bytes = None
    ) -> RemoteFileInfo:
        """
        Create a document with the given name and content.
        if content is None, creates a temporary file from the content then streams it.
        """
        if content is not None:
            file_path = make_tmp_file(self.upload_tmp_dir, content)
        else:
            file_path = name
        try:
            fs_item = self.upload(
                file_path, "NuxeoDrive.CreateFile", filename=name, parentId=parent_id
            )
            return RemoteFileInfo.from_dict(fs_item)
        finally:
            if content is not None:
                file_path.unlink()

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
                "NuxeoDrive.UpdateFile",
                filename=filename,
                mime_type=mime_type,
                id=ref,
            )
            return RemoteFileInfo.from_dict(fs_item)
        finally:
            file_path.unlink()

    def _filtered_results(
        self, entries: List[Dict], parent_uid: str = None, fetch_parent_uid: bool = True
    ) -> List[NuxeoDocumentInfo]:
        # Filter out filenames that would be ignored by the file system client
        # so as to be consistent.
        filtered = []
        for entry in entries:
            entry.update(
                {"root": self._base_folder_ref, "repository": self.client.repository}
            )
            if parent_uid is None and fetch_parent_uid:
                parent_uid = self.fetch(os.path.dirname(entry["path"]))["uid"]

            info = NuxeoDocumentInfo.from_dict(entry, parent_uid=parent_uid)
            name = info.name.lower()
            if name.endswith(Options.ignored_suffixes) or name.startswith(
                Options.ignored_prefixes
            ):
                continue

            filtered.append(info)

        return filtered


class RemoteTest(RemoteBase):

    _download_remote_error = None
    _upload_remote_error = None
    _server_error = None
    raise_on = None

    def download(self, *args, **kwargs):
        self._raise(self._download_remote_error, *args, **kwargs)
        return super().download(*args, **kwargs)

    def upload(self, *args, **kwargs):
        self._raise(self._upload_remote_error, *args, **kwargs)
        return super().upload(*args, **kwargs)

    def execute(self, *args, **kwargs):
        self._raise(self._server_error, *args, **kwargs)
        return super().execute(*args, **kwargs)

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
        self.execute(command="NuxeoDrive.SetActiveFactories", profile=profile)

    def deactivate_profile(self, profile):
        self.execute(
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

        self.client.request(
            "GET", url, params=params, headers=headers, timeout=tx_timeout
        )

    def wait_for_async_and_es_indexing(self):
        """ Use for test_volume only. """

        tx_timeout = 3600
        headers = {"Nuxeo-Transaction-Timeout": str(tx_timeout)}
        self.execute(
            command="Elasticsearch.WaitForIndexing",
            timeout=tx_timeout,
            headers=headers,
            timeoutSecond=tx_timeout,
            refresh=True,
        )

    def result_set_query(self, query):
        return self.execute(command="Repository.ResultSetQuery", query=query)

    def wait(self):
        self.execute(command="NuxeoDrive.WaitForElasticsearchCompletion")


class DocRemote(RemoteTest):
    def create(
        self,
        ref: str,
        doc_type: str,
        name: str = None,
        properties: Dict[str, str] = None,
    ):
        name = safe_filename(name)
        return self.execute(
            command="Document.Create",
            input_obj=f"doc:{ref}",
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
        if doc_type == "Note" and content is not None:
            properties["note:note"] = content
        doc = self.create(parent, doc_type, name=name, properties=properties)
        ref = doc["uid"]
        if doc_type != "Note" and content is not None:
            self.attach_blob(ref, content, name)
        return ref

    def make_file_in_user_workspace(
        self, content: bytes, filename: str
    ) -> RemoteFileInfo:
        """Stream the given content as a document in the user workspace"""
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(
                file_path, "UserWorkspace.CreateDocumentFromBlob", filename=filename
            )
        finally:
            file_path.unlink()

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
            "Blob.Attach",
            filename=filename,
            mime_type=mime_type,
            document=ref,
        )
        return ref

    def attach_blob(self, ref: str, blob: bytes, filename: str):
        file_path = make_tmp_file(self.upload_tmp_dir, blob)
        try:
            return self.upload(
                file_path, "Blob.Attach", filename=filename, document=ref
            )
        finally:
            file_path.unlink()

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
        return self.execute(
            command="Document.Move",
            input_obj=f"doc:{self._check_ref(ref)}",
            target=self._check_ref(target),
            name=name,
        )

    def update(self, ref: str, properties=None):
        return self.execute(
            command="Document.Update", input_obj=f"doc:{ref}", properties=properties
        )

    def copy(self, ref: str, target: str, name: str = None):
        return self.execute(
            command="Document.Copy",
            input_obj=f"doc:{self._check_ref(ref)}",
            target=self._check_ref(target),
            name=name,
        )

    def delete(self, ref: str, use_trash: bool = True):
        input_obj = f"doc:{self._check_ref(ref)}"
        if use_trash:
            try:
                if not self._has_new_trash_service:
                    return self.execute(
                        command="Document.SetLifeCycle",
                        input_obj=input_obj,
                        value="delete",
                    )
                else:
                    return self.execute(command="Document.Trash", input_obj=input_obj)
            except HTTPError as e:
                if e.status != 500:
                    raise
        return self.execute(command="Document.Delete", input_obj=input_obj)

    def delete_content(self, ref: str, xpath: str = None):
        return self.delete_blob(self._check_ref(ref), xpath=xpath)

    def delete_blob(self, ref: str, xpath: str = None):
        return self.execute(command="Blob.Remove", input_obj=f"doc:{ref}", xpath=xpath)

    def is_locked(self, ref: str) -> bool:
        data = self.fetch(ref, headers={"fetch-document": "lock"})
        return "lockCreated" in data

    def get_versions(self, ref: str):
        headers = {"X-NXfetch.document": "versionLabel"}
        versions = self.execute(
            command="Document.GetVersions",
            input_obj=f"doc:{self._check_ref(ref)}",
            headers=headers,
        )
        return [(v["uid"], v["versionLabel"]) for v in versions["entries"]]

    def create_version(self, ref: str, increment: str = "None"):
        doc = self.execute(
            command="Document.CreateVersion",
            input_obj=f"doc:{self._check_ref(ref)}",
            increment=increment,
        )
        return doc["uid"]

    def restore_version(self, version: str) -> str:
        doc = self.execute(
            command="Document.RestoreVersion",
            input_obj=f"doc:{self._check_ref(version)}",
        )
        return doc["uid"]

    def block_inheritance(self, ref: str, overwrite: bool = True):
        input_obj = f"doc:{self._check_ref(ref)}"

        self.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user="Administrator",
            permission="Everything",
            overwrite=overwrite,
        )

        self.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user="Everyone",
            permission="Everything",
            grant=False,
            overwrite=False,
        )
