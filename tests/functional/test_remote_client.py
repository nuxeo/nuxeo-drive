import hashlib
import operator
from pathlib import Path
from shutil import copyfile
from tempfile import mkdtemp
from unittest.mock import Mock, patch

import pytest
from nuxeo.models import Document

from nxdrive.engine.activity import Action, DownloadAction, UploadAction
from nxdrive.exceptions import NotFound
from nxdrive.metrics.constants import GLOBAL_METRICS
from nxdrive.objects import RemoteFileInfo, SubTypeEnricher
from nxdrive.options import Options
from nxdrive.utils import shortify

from .. import env
from . import LocalTest, make_tmp_file
from .conftest import FS_ITEM_ID_PREFIX, OneUserTest, TwoUsersTest


def get_current_action_download(*args, **kwargs):
    obj = DownloadAction("path", 1)
    obj.transferred_chunks = 1
    obj.chunk_transfer_end_time_ns = 300000000000
    obj.chunk_transfer_start_time_ns = 1000000000
    obj.chunk_size = 10
    obj.transferred_chunks = 2
    return obj


def get_current_action_upload(*args, **kwargs):
    obj = UploadAction("path", 1)
    obj.transferred_chunks = 1
    obj.chunk_transfer_end_time_ns = 3000000000
    obj.chunk_transfer_start_time_ns = 1000000000
    obj.chunk_size = 10
    obj.transferred_chunks = 2
    return obj


def get_current_no_action(*args, **kwargs):
    return None


@pytest.mark.parametrize(
    "username",
    [
        "ndt-Alice",
        "ndt-bob@bar.com",
        # "ndt-éléonor",
        # "ndt-東京スカイツリー",
    ],
)
def test_personal_space(manager_factory, tmp, nuxeo_url, user_factory, username):
    """Test personal space retrieval with problematic usernames."""
    # Note: non-ascii characters are not yet handled, and it is not likely to happen soon.

    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory(username=username)
    manager, engine = manager_factory(user=user)

    with manager:
        manager.bind_server(
            conf_folder,
            nuxeo_url,
            user.uid,
            password=user.properties["password"],
            start_engine=False,
        )

        folder = engine.remote.personal_space()
        assert isinstance(folder, Document)


@pytest.mark.parametrize(
    "name",
    [
        "My \r file",
        "ndt-bob@bar.com",
        "ndt-éléonor",
        "ndt-東京スカイツリー",
    ],
)
def test_exists_in_parent(name, manager_factory):
    manager, engine = manager_factory()
    with manager:
        method = engine.remote.exists_in_parent
        assert not method("/", name, False)
        assert not method("/", name, True)


@Options.mock()
def test_custom_metrics_global_headers(manager_factory):
    manager, engine = manager_factory()
    with manager:
        remote = engine.remote
        headers = remote.client.headers

        # Direct Edit feature is enable by default
        metrics = remote.custom_global_metrics
        assert metrics["feature.direct_edit"] == 1
        assert '"feature.direct_edit": 1' in headers[GLOBAL_METRICS]

        # Direct Edit feature is now disabled, check metrics are up-to-date
        Options.feature_direct_edit = False
        manager.reload_client_global_headers()
        metrics = remote.custom_global_metrics
        assert metrics["feature.direct_edit"] == 0
        assert '"feature.direct_edit": 0' in headers[GLOBAL_METRICS]

    Options.feature_direct_edit = True


@Options.mock()
@pytest.mark.parametrize("option", list(range(7)))
def test_expand_sync_root_name_levels(option, manager_factory, obj_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with manager:
        # Create (sub)folders
        parent = env.WS_DIR
        potential_names = []
        for num in range(option + 1):
            title = f"folder {num}"
            potential_names.append(shortify(title))
            doc = obj_factory(title=title, parent=parent, user=remote.user_id)
            parent = doc.path

        # *doc* is the latest created folder, craft the awaited object for next steps
        sync_root = RemoteFileInfo.from_dict(
            {
                "id": doc.uid,
                "name": doc.title,
                "parentId": doc.parentRef,
                "path": doc.path,
                "folderish": True,
            }
        )

        # Finally, let's guess its final name
        Options.sync_root_max_level = option
        sync_root = remote.expand_sync_root_name(sync_root)

        if option != Options.sync_root_max_level:
            # Typically the option was outside bounds, here it is "7".
            # We shrink the posibble folder names to ease code for checking the final
            # name
            potential_names = potential_names[option - Options.sync_root_max_level :]

        # Check
        final_name = " - ".join(potential_names[: Options.sync_root_max_level + 1])
        assert sync_root.name == final_name


@Options.mock()
@pytest.mark.parametrize("option", list(range(7)))
def test_expand_sync_root_name_length(option, manager_factory, obj_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with manager:
        # Create (sub)folders
        parent = env.WS_DIR
        potential_names = []
        for num in range(option + 1):
            title = "folder" + "r" * 50 + f" {num}"  # > 50 chars
            potential_names.append(shortify(title, limit=46))
            doc = obj_factory(title=title, parent=parent, user=remote.user_id)
            parent = doc.path

        # *doc* is the latest created folder, craft the awaited object for next steps
        sync_root = RemoteFileInfo.from_dict(
            {
                "id": doc.uid,
                "name": doc.title,
                "parentId": doc.parentRef,
                "path": doc.path,
                "folderish": True,
            }
        )

        # Finally, let's guess its final name
        Options.sync_root_max_level = option
        sync_root = remote.expand_sync_root_name(sync_root)

        if option != Options.sync_root_max_level:
            # Typically the option was outside bounds, here it is "7".
            # We shrink the posibble folder names to ease code for checking the final
            # name
            potential_names = potential_names[option - Options.sync_root_max_level :]

        # Check
        final_name = " - ".join(potential_names[: Options.sync_root_max_level + 1])
        assert sync_root.name == final_name
        assert sync_root.name.count("…") == Options.sync_root_max_level or 1
        assert len(sync_root.name) <= 250


def test_upload_folder_type(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def request_(*args, **kwargs):
        return "mocked-value"

    with manager:
        with patch.object(remote.client, "request", new=request_):
            folder_type = remote.upload_folder_type("string", {"key": "value"})
        assert folder_type == "mocked-value"


def test_cancel_batch(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    return_val = None
    with manager:
        return_val = remote.cancel_batch({"key": "value"})
        assert not return_val


def test_filter_schema(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def get_config_types_(*args, **kwargs):
        configTypes = {"doctypes": {1: {"schemas": "file"}}}
        return configTypes

    returned_val = None
    obj_ = SubTypeEnricher("uid", "path", "title", ["str"], {"key": "val"})
    with manager:
        with patch.object(remote, "get_config_types", new=get_config_types_):
            returned_val = remote.filter_schema(obj_)
        assert returned_val == ["1"]


def test_get_note(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def fetch_(*args, **kwargs):
        return {"properties": {"key": "val"}}

    returned_val = None
    with manager:
        with patch.object(remote, "fetch", new=fetch_):
            returned_val = remote.get_note("")
    assert returned_val == b""


def test_is_filtered(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def is_filter_(*args, **kwargs):
        return True

    returned_val = None
    with manager:
        with patch.object(remote.dao, "is_filter", new=is_filter_):
            returned_val = remote.is_filtered("")
    assert returned_val


def test_transfer_start_callback(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    obj1_ = Mock()
    with manager:
        with patch.object(
            Action, "get_current_action", new=get_current_action_download
        ):
            returned_val = remote.transfer_start_callback(obj1_)
    assert not returned_val


def test_transfer_end_callback(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def set_transfer_progress_(*args, **kwargs):
        return

    def get_download_(*args, **kwargs):
        mocked_download_obj_ = Mock()
        mocked_download_obj_.name = "mocked-download-obj"
        mocked_download_obj_.progress = 80
        mocked_download_obj_.status = 2
        return mocked_download_obj_

    def get_upload_(*args, **kwargs):
        mocked_upload_obj_ = Mock()
        mocked_upload_obj_.name = "mocked-upload-obj"
        mocked_upload_obj_.progress = 80
        mocked_upload_obj_.status = 2
        return mocked_upload_obj_

    obj1_ = Mock()
    with manager:
        with patch.object(
            Action, "get_current_action", new=get_current_action_download
        ):
            with patch.object(remote.dao, "get_download", new=get_download_):
                with patch.object(
                    remote.dao, "set_transfer_progress", new=set_transfer_progress_
                ):
                    with pytest.raises(Exception) as err:
                        remote.transfer_end_callback(obj1_)
                        assert err
        with patch.object(Action, "get_current_action", new=get_current_action_upload):
            with patch.object(remote.dao, "get_upload", new=get_upload_):
                with pytest.raises(Exception) as err:
                    remote.transfer_end_callback(obj1_)
                    assert err
        with patch.object(Action, "get_current_action", new=get_current_no_action):
            remote.transfer_end_callback(obj1_)
            assert not remote.transfer_end_callback(obj1_)


def test_download(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    def mocked_request(*args, **kwargs):
        obj_ = Mock()
        obj_.content = "content"
        obj_.headers = {"Content-Length": ((Options.tmp_file_limit * 1024 * 1024) + 1)}
        return obj_

    def stat_():
        obj = Mock()
        obj.st_size = 100
        return obj

    dummy_file_out = Mock()
    dummy_file_out.stat = stat_
    dummy_file_out.name = "dummy_file_out"

    dummy_file_path = env.WS_DIR

    dummy_file_path = Path(dummy_file_path)
    dummy_file_out = Path(dummy_file_path)

    with manager:
        with patch.object(remote.client, "request", new=mocked_request):
            returned_val = remote.download(
                "dummy_url", dummy_file_path, "", "dummy_digest"
            )
            assert returned_val == "content"

        with patch.object(remote.client, "request", new=mocked_request):
            with patch.object(remote.dao, "get_download", return_value=None):
                with patch.object(remote.dao, "save_download", return_value=None):
                    with patch.object(remote, "operations", return_value=None):
                        returned_val = remote.download(
                            "dummy_url", dummy_file_path, dummy_file_out, "dummy_digest"
                        )
                        assert returned_val


def test_reload_global_headers(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    headers = Mock()

    def mocked_update(*args, **kwargs):
        return

    headers.update = mocked_update

    with patch.object(headers, "update", return_value=None):
        assert not remote.reload_global_headers()


def test_escape(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    assert remote.escape("/Users/user/Nuxeo'")


def test_revoke_token(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    assert not remote.revoke_token()


def test_update_token(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    assert not remote.update_token("dummy_token")


def test_check_integrity_simple(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    dummy_file_path = env.WS_DIR
    dummy_file_path = Path(dummy_file_path)

    assert not remote.check_integrity_simple("dummy_digest", dummy_file_path)


def test_upload(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    import os

    local_path = Path(os.path.realpath(__file__))

    with pytest.raises(Exception):
        remote.upload(local_path)


def test_upload_folder(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    remote.operations = Mock()

    def mocked_execute(*args, **kwargs):
        return {"res": 0}

    remote.operations.execute = mocked_execute

    dummy_file_path = env.WS_DIR

    assert remote.upload_folder(dummy_file_path, {"params": 0}, headers={})


def test_make_folder(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with patch.object(
        remote,
        "execute",
        return_value={"id": 0, "parentId": 0, "path": "/", "name": "dummy"},
    ):
        assert remote.make_folder("dummy_parent", "dummy_name")


def test_delete(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with patch.object(
        remote,
        "execute",
        return_value={"id": 0, "parentId": 0, "path": "/", "name": "dummy"},
    ):
        assert not remote.delete("dummy_fs_item_id")


def test_rename(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    with patch.object(
        remote,
        "execute",
        return_value={"id": 0, "parentId": 0, "path": "/", "name": "dummy"},
    ):
        assert remote.rename("dummy_fs_item_id", "dummy_parent_fs_item_id")


def test_undelete(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    remote.documents = Mock()

    def mocked_execute(*args, **kwargs):
        return True

    remote.documents.untrash = mocked_execute

    dummy_file_path = env.WS_DIR

    assert not remote.undelete(dummy_file_path)


def test_move(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    dummy_file_path = env.WS_DIR

    with patch.object(
        remote,
        "execute",
        return_value={"id": 0, "parentId": 0, "path": "/", "name": "dummy"},
    ):
        assert remote.rename(dummy_file_path, dummy_file_path)


def test_move2(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote

    remote.documents = Mock()

    def mocked_move(*args, **kwargs):
        return

    remote.documents.move = mocked_move

    dummy_file_path = env.WS_DIR

    dummy_file_path = f"{str(env.WS_DIR)}#"

    with patch.object(
        remote,
        "execute",
        return_value={"id": 0, "parentId": 0, "path": "/", "name": "dummy"},
    ):
        assert not remote.move2(dummy_file_path, dummy_file_path, "dummy_name")


class TestRemoteFileSystemClient(OneUserTest):
    def setUp(self):
        # Bind the test workspace as sync root for user 1
        remote_doc = self.remote_document_client_1
        remote = self.remote_1
        remote_doc.register_as_root(self.workspace)

        # Fetch the id of the workspace folder item
        info = remote.get_filesystem_root_info()
        self.workspace_id = remote.get_fs_children(info.uid)[0].uid

    #
    # Test the API common with the local client API
    #

    def test_get_fs_info(self):
        remote = self.remote_1

        # Check file info
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        info = remote.get_fs_info(fs_item_id)
        assert info is not None
        assert info.name == "Document 1.txt"
        assert info.uid == fs_item_id
        assert info.parent_uid == self.workspace_id
        assert not info.folderish
        if info.last_contributor:
            assert info.last_contributor == self.user_1
        digest_algorithm = info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of doc 1.")
        assert info.digest == digest
        file_uid = fs_item_id.rsplit("#", 1)[1]
        # NXP-17827: nxbigile has been replace to nxfile, keep handling both
        url = f"/default/{file_uid}/blobholder:0/Document%201.txt"
        cond = info.download_url in (f"nxbigfile{url}", f"nxfile{url}")
        assert cond

        # Check folder info
        fs_item_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        info = remote.get_fs_info(fs_item_id)
        assert info is not None
        assert info.name == "Folder 1"
        assert info.uid == fs_item_id
        assert info.parent_uid == self.workspace_id
        assert info.folderish
        if info.last_contributor:
            assert info.last_contributor == self.user_1
        assert info.digest_algorithm is None
        assert info.digest is None
        assert info.download_url is None

        # Check non existing file info
        fs_item_id = f"{FS_ITEM_ID_PREFIX}fakeId"
        with pytest.raises(NotFound):
            remote.get_fs_info(fs_item_id)

    def test_get_content(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Check file with content
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.get_content(fs_item_id) == b"Content of doc 1."

        # Check file without content
        doc_uid = remote_doc.make_file_with_no_blob(self.workspace, "Document 2.txt")
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        with pytest.raises(NotFound):
            remote.get_content(fs_item_id)

    def test_stream_content(self):
        remote = self.remote_1

        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        file_path = self.local_test_folder_1 / "Document 1.txt"
        file_out = Path(mkdtemp()) / file_path.name
        tmp_file = remote.stream_content(
            fs_item_id, file_path, file_out, engine_uid=self.engine_1.uid
        )
        assert tmp_file.exists()
        assert tmp_file.name == "Document 1.txt"
        assert tmp_file.read_bytes() == b"Content of doc 1."

    def test_get_fs_children(self):
        remote = self.remote_1

        # Create documents
        folder_1_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        folder_2_id = remote.make_folder(self.workspace_id, "Folder 2").uid
        file_1_id = remote.make_file(
            self.workspace_id, "File 1", content=b"Content of file 1."
        ).uid
        file_2_id = remote.make_file(
            folder_1_id, "File 2", content=b"Content of file 2."
        ).uid

        # Check workspace children
        workspace_children = remote.get_fs_children(self.workspace_id)
        assert workspace_children is not None
        assert len(workspace_children) == 3
        assert workspace_children[0].uid == folder_1_id
        assert workspace_children[0].name == "Folder 1"
        assert workspace_children[0].folderish
        assert workspace_children[1].uid == folder_2_id
        assert workspace_children[1].name == "Folder 2"
        assert workspace_children[1].folderish
        assert workspace_children[2].uid == file_1_id
        assert workspace_children[2].name == "File 1"
        assert not workspace_children[2].folderish

        # Check folder_1 children
        folder_1_children = remote.get_fs_children(folder_1_id)
        assert folder_1_children is not None
        assert len(folder_1_children) == 1
        assert folder_1_children[0].uid == file_2_id
        assert folder_1_children[0].name == "File 2"

    def test_scroll_descendants(self):
        remote = self.remote_1

        # Create documents
        folder_1 = remote.make_folder(self.workspace_id, "Folder 1").uid
        folder_2 = remote.make_folder(self.workspace_id, "Folder 2").uid
        file_1 = remote.make_file(
            self.workspace_id, "File 1.txt", content=b"Content of file 1."
        ).uid
        file_2 = remote.make_file(
            folder_1, "File 2.txt", content=b"Content of file 2."
        ).uid

        # Wait for ES completion
        self.wait()

        # Check workspace descendants in one breath, ordered by remote path
        scroll_res = remote.scroll_descendants(self.workspace_id, None)
        assert isinstance(scroll_res, dict)
        assert "scroll_id" in scroll_res
        descendants = sorted(scroll_res["descendants"], key=operator.attrgetter("name"))
        assert len(descendants) == 4

        # File 1.txt
        assert descendants[0].uid == file_1
        assert descendants[0].name == "File 1.txt"
        assert not descendants[0].folderish
        # File 2.txt
        assert descendants[1].name == "File 2.txt"
        assert not descendants[1].folderish
        assert descendants[1].uid == file_2
        # Folder 1
        assert descendants[2].uid == folder_1
        assert descendants[2].name == "Folder 1"
        assert descendants[2].folderish
        # Folder 2
        assert descendants[3].uid == folder_2
        assert descendants[3].name == "Folder 2"
        assert descendants[3].folderish

        # Check workspace descendants in several steps, ordered by remote path
        descendants = []
        scroll_id = None
        while True:
            scroll_res = remote.scroll_descendants(
                self.workspace_id, scroll_id, batch_size=2
            )
            assert isinstance(scroll_res, dict)
            scroll_id = scroll_res["scroll_id"]
            if partial_descendants := scroll_res["descendants"]:
                descendants.extend(partial_descendants)
            else:
                break
        descendants = sorted(descendants, key=operator.attrgetter("name"))
        assert len(descendants) == 4

        # File 1.txt
        assert descendants[0].uid == file_1
        assert descendants[0].name == "File 1.txt"
        assert not descendants[0].folderish
        # File 2.txt
        assert descendants[1].name == "File 2.txt"
        assert not descendants[1].folderish
        assert descendants[1].uid == file_2
        # Folder 1
        assert descendants[2].uid == folder_1
        assert descendants[2].name == "Folder 1"
        assert descendants[2].folderish
        # Folder 2
        assert descendants[3].uid == folder_2
        assert descendants[3].name == "Folder 2"
        assert descendants[3].folderish

    def test_make_folder(self):
        remote = self.remote_1

        fs_item_info = remote.make_folder(self.workspace_id, "My new folder")
        assert fs_item_info is not None
        assert fs_item_info.name == "My new folder"
        assert fs_item_info.folderish
        assert fs_item_info.digest_algorithm is None
        assert fs_item_info.digest is None
        assert fs_item_info.download_url is None

    def test_make_file(self):
        remote = self.remote_1

        # Check File document creation
        fs_item_info = remote.make_file(
            self.workspace_id, "My new file.odt", content=b"Content of my new file."
        )
        assert fs_item_info is not None
        assert fs_item_info.name == "My new file.odt"
        assert not fs_item_info.folderish
        digest_algorithm = fs_item_info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of my new file.")
        assert fs_item_info.digest == digest

        # Check Note document creation
        fs_item_info = remote.make_file(
            self.workspace_id, "My new note.txt", content=b"Content of my new note."
        )
        assert fs_item_info is not None
        assert fs_item_info.name == "My new note.txt"
        assert not fs_item_info.folderish
        digest_algorithm = fs_item_info.digest_algorithm
        assert digest_algorithm == "md5"
        digest = self._get_digest(digest_algorithm, b"Content of my new note.")
        assert fs_item_info.digest == digest

    def test_make_file_custom_encoding(self):
        remote = self.remote_1

        # Create content encoded in utf-8 and cp1252
        unicode_content = "\xe9"  # e acute
        utf8_encoded = unicode_content.encode("utf-8")
        utf8_digest = hashlib.md5(utf8_encoded).hexdigest()
        cp1252_encoded = unicode_content.encode("cp1252")

        # Make files with this content
        utf8_fs_id = remote.make_file(
            self.workspace_id, "My utf-8 file.txt", content=utf8_encoded
        ).uid
        cp1252_fs_id = remote.make_file(
            self.workspace_id, "My cp1252 file.txt", content=cp1252_encoded
        ).uid

        # Check content
        utf8_content = remote.get_content(utf8_fs_id)
        assert utf8_content == utf8_encoded
        cp1252_content = remote.get_content(cp1252_fs_id)
        assert cp1252_content == utf8_encoded

        # Check digest
        utf8_info = remote.get_fs_info(utf8_fs_id)
        assert utf8_info.digest == utf8_digest
        cp1252_info = remote.get_fs_info(cp1252_fs_id)
        assert cp1252_info.digest == utf8_digest

    def test_update_content(self):
        remote = self.remote_1

        # Create file
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid

        # Check file update
        remote.update_content(fs_item_id, b"Updated content of doc 1.")
        assert remote.get_content(fs_item_id) == b"Updated content of doc 1."

    def test_delete(self):
        remote = self.remote_1

        # Create file
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.fs_exists(fs_item_id)

        # Delete file
        remote.delete(fs_item_id)
        assert not remote.fs_exists(fs_item_id)

    def test_exists(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Check existing file system item
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        assert remote.fs_exists(fs_item_id)

        # Check non existing file system item (non existing document)
        fs_item_id = f"{FS_ITEM_ID_PREFIX}fakeId"
        assert not remote.fs_exists(fs_item_id)

        # Check non existing file system item (document without content)
        doc_uid = remote_doc.make_file_with_no_blob(self.workspace, "Document 2.txt")
        fs_item_id = FS_ITEM_ID_PREFIX + doc_uid
        assert not remote.fs_exists(fs_item_id)

    #
    # Test the API specific to the remote file system client
    #

    def test_get_fs_item(self):
        remote = self.remote_1

        # Check file item
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid
        fs_item = remote.get_fs_item(fs_item_id)
        assert fs_item is not None
        assert fs_item["name"] == "Document 1.txt"
        assert fs_item["id"] == fs_item_id
        assert not fs_item["folder"]

        # Check file item using parent id
        fs_item = remote.get_fs_item(fs_item_id, parent_fs_item_id=self.workspace_id)
        assert fs_item is not None
        assert fs_item["name"] == "Document 1.txt"
        assert fs_item["id"] == fs_item_id
        assert fs_item["parentId"] == self.workspace_id

        # Check folder item
        fs_item_id = remote.make_folder(self.workspace_id, "Folder 1").uid
        fs_item = remote.get_fs_item(fs_item_id)
        assert fs_item is not None
        assert fs_item["name"] == "Folder 1"
        assert fs_item["id"] == fs_item_id
        assert fs_item["folder"]

        # Check non existing file system item
        fs_item_id = f"{FS_ITEM_ID_PREFIX}fakeId"
        assert remote.get_fs_item(fs_item_id) is None

    def test_streaming_upload(self):
        remote = self.remote_1

        # Create a document by streaming a text file
        file_path = make_tmp_file(remote.upload_tmp_dir, b"Some content.")
        try:
            fs_item_info = remote.stream_file(
                self.workspace_id, file_path, filename="My streamed file.txt"
            )
        finally:
            file_path.unlink()
        fs_item_id = fs_item_info.uid
        assert fs_item_info.name == "My streamed file.txt"
        assert remote.get_content(fs_item_id) == b"Some content."

        # Update a document by streaming a new text file
        file_path = make_tmp_file(remote.upload_tmp_dir, b"Other content.")
        try:
            fs_item_info = remote.stream_update(
                fs_item_id, file_path, filename="My updated file.txt"
            )
        finally:
            file_path.unlink()
        assert fs_item_info.uid == fs_item_id
        assert fs_item_info.name == "My updated file.txt"
        assert remote.get_content(fs_item_id) == b"Other content."

        # Create a document by streaming a binary file
        file_path = self.upload_tmp_dir / "testFile.pdf"
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        local_client = LocalTest(self.upload_tmp_dir)
        assert fs_item_info.name == "testFile.pdf"
        assert (
            fs_item_info.digest == local_client.get_info("/testFile.pdf").get_digest()
        )

    def test_mime_type_doc_type_association(self):
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # Upload a PDF file, should create a File document
        file_path = self.upload_tmp_dir / "testFile.pdf"
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        doc_type = remote_doc.get_info(doc_uid).doc_type
        assert doc_type == "File"

        # Upload a JPG file, should create a Picture document
        file_path = self.upload_tmp_dir / "cat.jpg"
        copyfile(self.location / "resources" / "files" / "cat.jpg", file_path)
        fs_item_info = remote.stream_file(self.workspace_id, file_path)
        fs_item_id = fs_item_info.uid
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        doc_type = remote_doc.get_info(doc_uid).doc_type
        assert doc_type == "Picture"

    def test_unregister_nested_roots(self):
        # Check that registering a parent folder of an existing root
        # automatically unregister sub folders to avoid synchronization
        # inconsistencies
        remote = self.remote_document_client_1

        # By default no root is synchronized
        remote.unregister_as_root(self.workspace)
        self.wait()
        assert not remote.get_roots()

        folder = remote.make_folder(self.workspace, "Folder")
        sub_folder_1 = remote.make_folder(folder, "Sub Folder 1")
        sub_folder_2 = remote.make_folder(folder, "Sub Folder 2")

        # Register the sub folders as roots
        remote.register_as_root(sub_folder_1)
        remote.register_as_root(sub_folder_2)
        assert len(remote.get_roots()) == 2

        # Register the parent folder as root
        remote.register_as_root(folder)
        roots = remote.get_roots()
        assert len(roots) == 1
        assert roots[0].uid == folder

        # Unregister the parent folder
        remote.unregister_as_root(folder)
        assert not remote.get_roots()

    def test_lock_unlock(self):
        remote = self.remote_document_client_1
        doc_id = remote.make_file(
            self.workspace, "TestLocking.txt", content=b"File content"
        )

        status = remote.is_locked(doc_id)
        assert not status
        remote.lock(doc_id)
        assert remote.is_locked(doc_id)

        remote.unlock(doc_id)
        assert not remote.is_locked(doc_id)

    @staticmethod
    def _get_digest(algorithm: str, content: bytes) -> str:
        hasher = getattr(hashlib, algorithm)
        if hasher is None:
            raise RuntimeError(f"Unknown digest algorithm: {algorithm}")
        return hasher(content).hexdigest()


class TestRemoteFileSystemClient2(TwoUsersTest):
    def setUp(self):
        # Bind the test workspace as sync root for user 1
        remote_doc = self.remote_document_client_1
        remote = self.remote_1
        remote_doc.register_as_root(self.workspace)

        # Fetch the id of the workspace folder item
        info = remote.get_filesystem_root_info()
        self.workspace_id = remote.get_fs_children(info.uid)[0].uid

    def test_modification_flags_locked_document(self):
        remote = self.remote_1
        fs_item_id = remote.make_file(
            self.workspace_id, "Document 1.txt", content=b"Content of doc 1."
        ).uid

        # Check flags for a document that isn't locked
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        assert info.lock_owner is None
        assert info.lock_created is None

        # Check flags for a document locked by the current user
        doc_uid = fs_item_id.rsplit("#", 1)[1]
        remote.lock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        lock_info_available = remote.get_fs_item(fs_item_id).get("lockInfo") is not None
        if lock_info_available:
            assert info.lock_owner == self.user_1
            assert info.lock_created is not None
        remote.unlock(doc_uid)

        # Check flags for a document locked by another user
        self.remote_2.lock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert not info.can_rename
        assert not info.can_update
        assert not info.can_delete
        if lock_info_available:
            assert info.lock_owner == self.user_2
            assert info.lock_created is not None

        # Check flags for a document unlocked by another user
        self.remote_2.unlock(doc_uid)
        info = remote.get_fs_info(fs_item_id)
        assert info.can_rename
        assert info.can_update
        assert info.can_delete
        assert info.lock_owner is None
        assert info.lock_created is None
