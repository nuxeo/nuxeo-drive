from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Cursor
from threading import RLock
from typing import Any, List

from PyQt5 import QtCore

from nxdrive.client.local.base import FileInfo, LocalClientMixin
from nxdrive.constants import TransferStatus
from nxdrive.objects import DocPair, RemoteFileInfo


class Mock_Local_Client(LocalClientMixin):
    def __init__(self, *args) -> None:
        super().__init__(Path())
        self.abs_path = Path("dummy_absolute_path")
        self.default_file_info: FileInfo | None = FileInfo(
            Path(""), Path("dummy_local_path"), False, datetime.now(), digest_func="md5"
        )
        self.equal_digest = True
        self.exist = True
        self.ignored = True
        self.local_info = True
        self.made_folder = Path("")
        self.__name__ = "Mock_Local_Client"
        self.new_file_data = (Path(""), Path(""), "new_file")
        self.path = Path("")
        self.remote_id = "remote_ref"
        self.temp = True

    def __call__(self, *args, **kwargs):
        pass

    def abspath(self, ref: Path) -> Path:
        return self.abs_path

    def change_file_date(
        self, filepath: Path, /, *, mtime: str = None, ctime: str = None
    ) -> None:
        pass

    def delete(self, ref):
        pass

    def delete_final(self, ref: Path) -> None:
        pass

    def get_children_info(self, ref: Path) -> List[FileInfo]:
        file_info = FileInfo(
            Path(""), Path("dummy_local_path"), False, datetime.now(), digest_func="md5"
        )
        file_info2 = FileInfo(
            Path(""),
            Path("dummy_local_path2"),
            False,
            datetime.now(),
            digest_func="md5",
        )
        return [file_info, file_info2]

    def get_info(self, ref: Path, /, *, check: bool = True) -> FileInfo:
        return self.default_file_info

    def get_new_file(self, parent, name):
        return self.new_file_data

    def get_path(self, target: Path) -> Path:
        return self.path

    def get_remote_id(self, ref: Path, /, *, name: str = "ndrive") -> str:
        return self.remote_id

    def exists(self, ref: Path) -> bool:
        return self.exist

    def is_case_sensitive(self) -> bool:
        return False

    def is_equal_digests(
        self,
        local_digest: str | None,
        remote_digest: str | None,
        local_path: Path,
        /,
        *,
        remote_digest_algorithm: str = None,
    ) -> bool:
        return self.equal_digest

    def is_ignored(self, parent_ref: Path, file_name: str) -> bool:
        return self.ignored

    def is_temp_file(self, path) -> bool:
        return self.temp

    def make_folder(self, parent: Path, name: str) -> Path:
        return self.made_folder

    def move(self, ref, new_parent_ref, name: str = None):
        return self.default_file_info

    def rename(self, ref, to_name):
        return self.default_file_info

    def remove_remote_id(
        self, ref: Path, /, *, name: str = "ndrive", cleanup: bool = False
    ) -> None:
        return None

    def set_readonly(self, ref: Path) -> None:
        pass

    def set_remote_id(
        self, ref: Path, remote_id: bytes | str, /, *, name: str = "ndrive"
    ) -> None:
        return None

    def try_get_info(self, ref: Path) -> FileInfo | None:
        return self.default_file_info

    def unset_readonly(self, ref: Path) -> None:
        pass


class Mock_DAO:
    def __init__(self):
        self.acquired_state = "DocPair_object"
        self.db_children = []
        self.doc_pairs = [self, self]
        self.download = Mock_Download()
        self.filter = True
        self.folderish = False
        self.id = 1
        self.last_error = "DEDUP"
        self.local_digest = "md6"
        self.last_local_updated = "2025-07-04 11:41:23"
        self.local_name = "dummy_local_name"
        self.local_path = Path("dummy_local_path")
        self.local_parent_path = Path("dummy_local_parent_path")
        self.local_state = "dummy_local_state"
        self.lock = RLock()
        self.get_states = []
        self.get_state_index = 0
        self.pair_index: int = (
            2  # To control the index of doc_pair received from get_state_from_local
        )
        self.pair_state = "dummy_pair_state"
        self.processor = 0
        self.remote_can_create_child = False
        self.remote_digest = "dummy_remote_digest"
        self.remote_name = "dummy_remote_name"
        self.remote_path = "dummy_remote_path"
        self.remote_parent_path = "dummy_remote_parent_path"
        self.remote_parent_ref = "dummy_remote_parent_ref"
        self.remote_ref = "dummy_remote_ref"
        self.remote_state = "dummy_remote_state"
        self.session = Mock_Session()
        self.size = 1
        self.synchronize = True
        self.update_remote = True
        self.upload = Mock_Upload()
        self.version = 1
        # DocPair
        cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
        self.mocked_doc_pair = DocPair(cursor, ())
        self.mocked_doc_pair.id = 1
        self.mocked_doc_pair.local_path = Path("dummy_local_path")
        self.mocked_doc_pair.local_parent_path = Path("dummy_parent_path")
        self.mocked_doc_pair.remote_ref = "dummy_remote_ref"
        self.mocked_doc_pair.local_state = "dummy_local_state"
        self.mocked_doc_pair.remote_parent_path = "dummy_remote_parent_path"
        self.mocked_doc_pair.remote_state = "dummy_remote_state"
        self.mocked_doc_pair.pair_state = "dummy_pair_state"
        self.mocked_doc_pair.last_error = "dummy_last_error"

    def acquire_state(self, thread_id, doc_pair_id):
        return self.acquired_state

    def add_filter(self, path):
        pass

    def clean_scanned(self):
        pass

    def decrease_session_counts(self, uid):
        return self.session

    def delete_remote_state(self, doc_pair):
        pass

    def get_dedupe_pair(self, name, parent, row_id):
        return self.mocked_doc_pair

    def get_download(self, uid: int = None, path: Path = None, doc_pair: int = None):
        return self.download

    def get_dt_upload(self, **kwargs):
        return self.upload

    def get_upload(self, **kwargs: Any):
        return self.upload

    def get_local_children(self, path: Path):
        self.db_children.append(self)
        mock_dao2 = Mock_DAO()
        mock_dao2.local_name = "dummy_local_name2"
        self.db_children.append(mock_dao2)
        return self.db_children

    def get_new_remote_children(self, id: str):
        return self.doc_pairs

    def get_normal_state_from_remote(self, ref: str):
        return self.doc_pairs[0]

    def get_session(self, uid):
        return self.session

    def get_state_from_id(self, id: int, from_write=False):
        return self.doc_pairs[0]

    def get_state_from_local(self, path):
        if self.pair_index != -1:
            mock_dao = Mock_DAO()
            mock_dao.pair_state = "unsynchronized"
            self.doc_pairs.append(mock_dao)
            return self.doc_pairs[self.pair_index]
        else:
            mock_client_path = Mock_Local_Client().path
            # return a doc_pair when the path passed is the parent
            if mock_client_path.parent == path:
                return self.doc_pairs[0]
            return

    def get_states_from_partial_local(self, path, srtict: bool = True):
        return self.doc_pairs

    def get_states_from_remote(self, ref: str):
        if self.pair_index >= len(self.doc_pairs):
            self.pair_index = len(self.doc_pairs) - 1
        return [self.doc_pairs[self.pair_index], None]

    def get_state_from_remote_with_path(self, ref: str, path: str):
        value = self.get_states[self.get_state_index]
        self.get_state_index += 1
        return value

    def insert_local_state(self, child, path):
        return 2

    def insert_remote_state(
        self,
        info: RemoteFileInfo,
        remote_parent_path: str,
        local_path: Path,
        local_parent_path: Path,
    ):
        pass

    def is_filter(self, path: str):
        return self.filter

    def mark_descendants_remotely_created(self, doc_pair):
        pass

    def queue_children(self, row: DocPair):
        pass

    def _queue_pair_state(
        self, id: int, folderish: bool, pair_state: str, pair: DocPair
    ):
        pass

    def release_state(self, thread_id):
        pass

    def remove_state(
        self, doc_pair, remote_recursion: bool = True, recursive: bool = True
    ):
        return None

    def remove_transfer(
        self,
        nature,
        doc_pair: str = None,
        path: Path = None,
        is_direct_transfer: bool = False,
    ):
        pass

    def replace_local_paths(self, old_path, new_path):
        pass

    def reset_error(self, row, last_error: str = None):
        pass

    def set_conflict_state(self, row):
        pass

    def synchronize_state(
        self, row: DocPair, version: int = None, dynamic_states: bool = False
    ):
        return self.synchronize

    def update_config(self, name: str, value: Any):
        pass

    def update_last_transfer(self, row_id, transfer):
        pass

    def update_local_parent_path(self, doc_pair, new_name, new_path):
        pass

    def update_local_state(self, pair, child, versioned=False, queue: bool = True):
        pass

    def update_remote_name(self, row_id, remote_name):
        pass

    def update_remote_parent_path(self, doc_pair, new_path):
        pass

    def update_remote_state(
        self,
        row,
        info,
        remote_parent_path="",
        versioned=True,
        queue=True,
        force_update=False,
        no_digest=False,
    ):
        return self.update_remote

    def update_session(self, uid):
        return self.session

    def unsynchronize_state(self, row, last_error):
        pass

    def get_valid_duplicate_file(self, digest):
        return self.mocked_doc_pair


class Mock_Doc_Pair:
    def __init__(self, cursor: Cursor, data: tuple) -> None:
        self.creation_date = "2025-01-15"
        self.id = 1
        self.error_count = 0
        self.folderish = False
        self.last_error = "dummy_last_error"
        self.last_remote_updated = "dummy_last_remote_updated"
        self.local_digest = "dummy_local_digest"
        self.local_name = "dummy_local_name"
        self.local_path = Path("dummy_local_path")
        self.local_parent_path = Path("dummy_parent_path")
        self.remote_ref = "dummy_remote_ref"
        self.local_state = "dummy_local_state"
        self.pair_state = "dummy_pair_state"
        self.remote_can_delete = True
        self.remote_can_rename = True
        self.remote_can_update = False
        self.remote_can_create_child = True
        self.remote_name = "doc_pair_remote"
        self.remote_digest = "doc_pair_digest"
        self.remote_parent_path = "dummy_remote_parent_path"
        self.remote_parent_ref = "doc_pair_remote_parent_ref"
        self.remote_state = "dummy_remote_state"
        self.session = Mock_Session()
        self.size = 1
        # Custom attributes
        self.read_only = False

    def is_readonly(self) -> bool:
        return self.read_only


class Mock_Download:
    def __init__(self) -> None:
        self.status = TransferStatus.PAUSED


class Mock_Emitter:
    def __init__(self) -> None:
        pass

    def emit(self, *args):
        pass


class Mock_Engine:
    def __init__(self) -> None:
        self.dao = Mock_DAO()
        self.deleteReadonly = Mock_Emitter()
        self.directTranferError = Mock_Emitter()
        self.directTransferStats = Mock_Emitter()
        self.download_dir = Path("")
        self.local = self
        self.manager = self
        self.newLocked = Mock_Emitter()
        self.newReadonly = Mock_Emitter()
        self.noSpaceLeftOnDevice = Mock_Emitter()
        self.offline = False
        self.osi = self
        self.queue_manager = Mock_Queue_Manager()
        self.remote = Mock_Remote()
        self.rollback = False
        self.trash = False
        self.uid = "dummy_uid"
        self.unlock_return = 0

    def suspend(self):
        pass

    def handle_session_status(self, session):
        pass

    def is_offline(self) -> bool:
        return self.offline

    def local_rollback(self, force: bool = False):
        return self.rollback

    def lock_ref(self, ref, locker, is_abs: bool = False):
        pass

    def release_folder_lock(self):
        pass

    def send_sync_status(self, state, path):
        pass

    def set_local_folder_lock(self, path):
        pass

    def set_offline(self, value: bool = True):
        pass

    def unlock_ref(self, ref, unlock_parent: bool = True, is_abs: bool = False):
        return self.unlock_return

    def use_trash(self):
        return self.trash


class Mock_Nuxeo_Client:
    def __init__(self) -> None:
        self.reachable = False
        self.server_version = 1

    def is_reachable(self):
        return self.reachable


class Mock_Qt:
    def __init__(self) -> None:
        self.appUpdate = self
        self.changed = self
        self.getLastFiles = self
        self.setMessage: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal
        self.setStatus = self
        self.updateAvailable: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal
        self.updateProgress: QtCore.PYQT_SLOT = QtCore.pyqtBoundSignal

    def addButton(self, *args):
        pass

    def connect(self, *args):
        pass

    def emit(self, *args):
        pass

    def exec_(self):
        pass

    def setFlags(self, *args):
        pass

    def setIconPixmap(self, *args):
        pass

    def setText(self, *args):
        pass

    def setWindowTitle(self, *args):
        pass


class Mock_Queue_Manager:
    def __init__(self) -> None:
        pass

    def push_error(self, doc_pair, exception: Exception = None, interval: int = None):
        pass


class Mock_Remote:
    def __init__(self) -> None:
        self.can_scroll_descendants = False
        self.client = Mock_Nuxeo_Client()
        self.descendants = {
            "descendants": [Mock_Remote_File_Info()],
            "scroll_id": "scroll_id_data",
        }
        self.digest = "dummy_digest"
        self.fetch_value = {"uid": "dummy_uid"}
        self.filter_state = True
        self.folderish = False
        self.fs_item = {"item1": "item1_name"}
        self.is_trashed = True
        self.lock_created = datetime.now()
        self.lock_owner = "dummy_lock_owner"
        self.make_folder_output = Mock_Remote_File_Info()
        self.move2_out = {}
        self.name = "dummy_name"
        self.parent_uid = "dummy_parent_uid"
        self.path = "dummy_path"
        self.stream_update_value = Mock_Remote_File_Info()
        self.sync_root: bool = True
        self.uid = "dummy_uid"

    def cancel_batch(self, batch_details):
        pass

    def delete(self, fs_item_id, parent_fs_item_id: str = None):
        pass

    def fetch(self, ref, headers: dict = None, enrichers: list = None):
        return self.fetch_value

    def get_fs_info(self, fs_item_id, parent_fs_item_id=""):
        return self

    def get_fs_item(self, fs_item_id, parent_fs_item_id: str = None):
        self.fs_item

    def get_info(
        self, ref, raise_if_missing: bool = True, fetch_parent_uid: bool = True
    ):
        return self

    def is_filtered(self, path, filtered: bool = True):
        return self.filter_state

    def move(self, fs_item_id, new_parent_id):
        return self

    def move2(self, fs_item_id, parent_ref, name):
        return self.move2_out

    def make_folder(self, parent_foler, name, overwrite: bool = False):
        return self.make_folder_output

    def rename(self, fs_item_id, new_name):
        return self

    def scroll_descendants(self, fs_item_id: str, scroll_id: str, batch_size: int = 0):
        return self.descendants

    def stream_file(
        self,
        parent_id,
        file_path,
        filename: str = None,
        overwrite: bool = False,
        **kwargs: Any,
    ):
        return self.stream_update_value

    def stream_update(
        self,
        fs_item_id,
        file_path,
        parent_fs_item_id: str = None,
        filename: str = None,
        engine_uid: str = None,
    ):
        return self.stream_update_value

    def undelete(self, uid):
        pass

    def is_sync_root(self, item):
        return self.sync_root

    def expand_sync_root_name(self, sync_root):
        return Mock_Remote_File_Info()


class Mock_Remote_File_Info(RemoteFileInfo):
    def __init__(self) -> None:
        self.name = "dummy_name"
        self.uid = "dummy_uid"
        self.parent_uid = "dummy_parent_uid"
        self.path = "dummy_path"
        self.folderish = False
        self.last_modification_time = datetime.now()
        self.creation_time = datetime.now()
        self.last_contributor = None
        self.digest = None
        self.digest_algorithm = "md5"
        self.download_url = "dummy_url"
        self.can_rename = False
        self.can_delete = False
        self.can_update = False
        self.can_create_child = False
        self.lock_owner = "dummy_lock_owner"
        self.lock_created = datetime.now()
        self.can_scroll_descendants = False


class Mock_Session:
    def __init__(self) -> None:
        self.status = TransferStatus.PAUSED


class Mock_Upload:
    def __init__(self) -> None:
        self.batch = {}
        cursor = Cursor(Connection("tests/resources/databases/test_engine.db"))
        self.doc_pair = Mock_Doc_Pair(cursor, ())
        self.status = TransferStatus.PAUSED
