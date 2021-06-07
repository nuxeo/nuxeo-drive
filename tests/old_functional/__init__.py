import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple, Union

import nuxeo.client
import nuxeo.constants
import nuxeo.operations
from nuxeo.models import Blob, FileBlob

from nxdrive.client.local import LocalClient
from nxdrive.client.remote_client import Remote
from nxdrive.objects import NuxeoDocumentInfo, RemoteFileInfo
from nxdrive.options import Options
from nxdrive.utils import force_encode, safe_filename

from .. import env


def patch_nxdrive_objects():
    """Some feature are not needed or are better disabled when testing."""

    # Need to do this one first because importing Manager will already import
    # nxdrive.dao.utils and so changing the behavior of save_backup()
    # will not work.
    import nxdrive.dao.utils

    nxdrive.dao.utils.save_backup = lambda *args: True

    from nxdrive.poll_workers import ServerOptionsUpdater

    @property
    def enable(self) -> bool:
        return False

    ServerOptionsUpdater.enable = enable

    from nxdrive.gui.application import Application

    Application.init_nxdrive_listener = lambda *args: None

    from nxdrive.engine.queue_manager import QueueManager
    from nxdrive.manager import Manager

    def dispose_all(self) -> None:
        for engine in self.engines.copy().values():
            engine.dispose_db()
        self.dispose_db()

    def unbind_all(self) -> None:
        if not self.engines:
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

    def copy(self, srcref: RawPath, dstref: RawPath) -> None:
        """Make a copy of the file (with xattr included)."""
        remote_id = self.get_remote_id(srcref)
        shutil.copy2(self.abspath(srcref), self.abspath(dstref))
        self.set_remote_id(dstref, remote_id)

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

        # Save bandwidth by caching operations details
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

    def get_children_info(self, ref: str) -> List[NuxeoDocumentInfo]:
        ref = self.escape(self.check_ref(ref))
        types = "', '".join(
            ("Note", "Workspace", "Picture", env.DOCTYPE_FILE, env.DOCTYPE_FOLDERISH)
        )

        query = (
            "SELECT * FROM Document"
            f"       WHERE ecm:parentId = '{ref}'"
            f"         AND ecm:primaryType IN ('{types}')"
            f"             {self._get_trash_condition()}"
            "          AND ecm:isVersion = 0"
            "     ORDER BY dc:title, dc:created"
        )
        entries = self.query(query, page_size=1000)["entries"]
        return self._filtered_results(entries)

    def get_content(self, fs_item_id: str, **kwargs: Any) -> Path:
        """Download and return the binary content of a file system item

        Beware that the content is loaded in memory.

        Raises NotFound if file system item with id fs_item_id
        cannot be found
        """
        fs_item_info = self.get_fs_info(fs_item_id)
        url = self.client.host + fs_item_info.download_url

        # Placeholders
        file_path = file_out = ""

        return self.download(url, file_path, file_out, fs_item_info.digest, **kwargs)

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
                file_path,
                command="NuxeoDrive.CreateFile",
                filename=name,
                parentId=parent_id,
            )
            return RemoteFileInfo.from_dict(fs_item)
        finally:
            if content is not None:
                file_path.unlink()

    def update_content(
        self, ref: str, content: bytes, filename: str = None
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
                command="NuxeoDrive.UpdateFile",
                filename=filename,
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
                {"root": self.base_folder_ref, "repository": self.client.repository}
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
        """Make next calls to do_get() raise the provided exception."""
        self._download_remote_error = error

    def make_upload_raise(self, error):
        """Make next calls to upload() raise the provided exception."""
        self._upload_remote_error = error

    def make_server_call_raise(self, error):
        """Make next calls to the server raise the provided exception."""
        self._server_error = error

    def _raise(self, exc, *args, **kwargs):
        """Make the next calls raise `exc` if `raise_on()` allowed it."""

        if exc:
            if not callable(self.raise_on):
                raise exc
            if self.raise_on(*args, **kwargs):
                raise exc

    def reset_errors(self):
        """Remove custom errors."""

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

    def mass_import(self, target_path, nb_nodes):
        """Used in test_volume.py only.

        *nb_nodes* is the minimum number of documents to create on the server.
        A tradeoff has been made for performance over an exact number.
        Randomness and threading inside, it is OK for us.

        To get the real documents number, use a specific NXQL query
        (see test_remote_scan() from test_volume.py).
        """
        tx_timeout = 3600
        url = "site/randomImporter/run"
        params = {
            "targetPath": target_path,
            "batchSize": 50,
            "nbThreads": 12,
            "interactive": "true",
            "fileSizeKB": 10,
            "nbNodes": nb_nodes,
            "nonUniform": "true",
            "transactionTimeout": tx_timeout,
        }
        headers = {"Nuxeo-Transaction-Timeout": str(tx_timeout)}

        self.client.request(
            "GET", url, params=params, headers=headers, timeout=tx_timeout
        )

    def wait_for_async_and_es_indexing(self):
        """Used in test_volume.py only."""

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
        """
        Create a document of type *doc_type*.
        The operation will not use the FileManager.
        """
        name = safe_filename(name)
        return self.execute(
            command="Document.Create",
            input_obj=f"doc:{ref}",
            type=doc_type,
            name=name,
            properties=properties,
        )

    def make_folder(
        self, parent: str, name: str, doc_type: str = env.DOCTYPE_FOLDERISH
    ) -> str:
        """
        Create a folderish document of the given *doc_type* with the given *name*.
        The operation will not use the FileManager.
        """
        parent = self.check_ref(parent)
        doc = self.create(parent, doc_type, name=name, properties={"dc:title": name})
        return doc["uid"]

    def make_file_with_blob(
        self, parent: str, name: str, content: bytes, doc_type: str = env.DOCTYPE_FILE
    ) -> str:
        """
        Create a non-folderish document of the given *doc_type* with the given *name*
        and attach a blob with *contents*.
        The operation will not use the FileManager.
        """
        doc_id = self.make_file_with_no_blob(parent, name, doc_type=doc_type)
        self.attach_blob(doc_id, content, name)
        return doc_id

    def make_file_with_no_blob(
        self, parent: str, name: str, doc_type: str = env.DOCTYPE_FILE
    ) -> str:
        """
        Create a document of the given *doc_type* with the given *name*.
        The operation will not use the FileManager.
        """
        parent = self.check_ref(parent)
        doc = self.create(parent, doc_type, name=name, properties={"dc:title": name})
        return doc["uid"]

    def make_file(
        self,
        parent: str,
        name: str,
        content: bytes = None,
        file_path: Path = None,
    ) -> str:
        """
        Create a document with the given *name* and *content* using the FileManager.
        If *file_path* points to a local file, it will be used instead of *content*.

        Note: if *content* is "seen" as plain text by the FileManager, the created document
              will be a Note. It this is not what you want, use make_file_with_blob().
        """
        tmp_created = file_path is None
        if not file_path:
            file_path = make_tmp_file(self.upload_tmp_dir, content)

        try:
            file_blob = FileBlob(str(file_path))
            file_blob.name = safe_filename(name)
            blob = self.uploads.batch().upload(file_blob)
            return self.file_manager_import(self.check_ref(parent), blob)
        finally:
            if tmp_created:
                file_path.unlink()

    def file_manager_import(self, parent: str, blob: Blob) -> str:
        """
        Use the FileManager to import and create a document in *parent*
        based on the given already uploaded *blob*.
        """
        op = self.operations.new("FileManager.Import")
        op.context = {"currentDocument": parent}
        op.input_obj = blob
        return op.execute()["uid"]

    def make_file_in_user_workspace(
        self, content: bytes, filename: str
    ) -> RemoteFileInfo:
        """Stream the given content as a document in the user workspace"""
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(
                file_path,
                command="UserWorkspace.CreateDocumentFromBlob",
                filename=filename,
            )
        finally:
            file_path.unlink()

    def stream_file(self, parent: str, file_path: Path, **kwargs) -> NuxeoDocumentInfo:
        """Create a document by streaming the file with the given path"""
        ref = self.make_file(parent, file_path.name, file_path=file_path)
        return self.get_info(ref)

    def attach_blob(self, ref: str, content: bytes, filename: str):
        file_path = make_tmp_file(self.upload_tmp_dir, content)
        try:
            return self.upload(
                file_path, command="Blob.Attach", filename=filename, document=ref
            )
        finally:
            file_path.unlink()

    def get_content(self, ref: str) -> bytes:
        """
        Download and return the binary content of a document
        Beware that the content is loaded in memory.
        """
        if not isinstance(ref, NuxeoDocumentInfo):
            ref = self.check_ref(ref)
        return self.get_blob(ref)

    def update_content(self, ref: str, content: bytes, filename: str = None) -> None:
        """Update a document with the given content."""
        if filename is None:
            filename = self.get_info(ref).name
        self.attach_blob(self.check_ref(ref), content, filename)

    def move(self, ref: str, target: str, name: str = None):
        return self.documents.move(
            self.check_ref(ref), self.check_ref(target), name=name
        )

    def create_proxy(self, ref: str, output_ref: str):
        kwargs = {"Destination Path": output_ref}
        return self.execute(
            command="Document.CreateLiveProxy",
            input_obj=self.check_ref(ref),
            **kwargs,
        )

    def update(self, ref: str, properties=None):
        return self.execute(
            command="Document.Update", input_obj=f"doc:{ref}", properties=properties
        )

    def copy(self, ref: str, target: str, name: str = None):
        return self.execute(
            command="Document.Copy",
            input_obj=f"doc:{self.check_ref(ref)}",
            target=self.check_ref(target),
            name=name,
        )

    def delete(self, ref: str, use_trash: bool = True):
        meth = "trash" if use_trash else "delete"
        return getattr(self.documents, meth)(self.check_ref(ref))

    def delete_content(self, ref: str, xpath: str = None):
        return self.delete_blob(self.check_ref(ref), xpath=xpath)

    def delete_blob(self, ref: str, xpath: str = None):
        return self.execute(command="Blob.Remove", input_obj=f"doc:{ref}", xpath=xpath)

    def is_locked(self, ref: str) -> bool:
        return bool(self.documents.fetch_lock_status(ref))

    def get_versions(self, ref: str):
        headers = {"fetch-document": "versionLabel"}
        versions = self.execute(
            command="Document.GetVersions",
            input_obj=f"doc:{self.check_ref(ref)}",
            headers=headers,
        )
        return [(v["uid"], v["versionLabel"]) for v in versions["entries"]]

    def create_version(self, ref: str, increment: str = "None"):
        doc = self.execute(
            command="Document.CreateVersion",
            input_obj=f"doc:{self.check_ref(ref)}",
            increment=increment,
        )
        return doc["uid"]

    def restore_version(self, version: str) -> str:
        doc = self.execute(
            command="Document.RestoreVersion",
            input_obj=f"doc:{self.check_ref(version)}",
        )
        return doc["uid"]

    def block_inheritance(self, ref: str, overwrite: bool = True):
        input_obj = f"doc:{self.check_ref(ref)}"

        self.execute(
            command="Document.SetACE",
            input_obj=input_obj,
            user=env.NXDRIVE_TEST_USERNAME,
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
