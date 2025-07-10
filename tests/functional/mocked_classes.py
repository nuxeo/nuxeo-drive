from datetime import datetime
from pathlib import Path
from sqlite3 import Connection, Cursor
from typing import Any, List

from nxdrive.client.local.base import FileInfo, LocalClientMixin
from nxdrive.objects import DocPair, RemoteFileInfo


class Mock_Local_Client(LocalClientMixin):
    def __init__(self) -> None:
        super().__init__(Path())
        self.abs_path = Path("dummy_absolute_path")
        self.default_file_info: FileInfo | None = FileInfo(
            Path(""), Path("dummy_local_path"), False, datetime.now(), digest_func="md5"
        )
        self.equal_digest = True
        self.exist = True
        self.ignored = True
        self.local_info = True
        self.path = Path("")
        self.remote_id = "remote_ref"
        self.temp = True

    def abspath(self, ref: Path) -> Path:
        return self.abs_path

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

    def remove_remote_id(
        self, ref: Path, /, *, name: str = "ndrive", cleanup: bool = False
    ) -> None:
        return None

    def set_remote_id(
        self, ref: Path, remote_id: bytes | str, /, *, name: str = "ndrive"
    ) -> None:
        return None

    def try_get_info(self, ref: Path) -> FileInfo | None:
        return self.default_file_info


class Mock_DAO:
    def __init__(self):
        self.acquired_state = "DocPair_object"
        self.db_children = []
        self.doc_pairs = [self, self]
        self.filter = True
        self.folderish = False
        self.id = 1
        self.local_digest = "md6"
        self.last_local_updated = "2025-07-04 11:41:23"
        self.local_name = "dummy_local_name"
        self.local_path = Path("dummy_local_path")
        self.local_state = "dummy_local_state"
        self.get_states = []
        self.get_state_index = 0
        self.pair_index: int = (
            2  # To control the index of doc_pair received from get_state_from_local
        )
        self.pair_state = "dummy_pair_state"
        self.processor = 0
        self.remote_can_create_child = False
        self.remote_name = "dummy_remote_name"
        self.remote_path = "dummy_remote_path"
        self.remote_parent_path = "dummy_remote_parent_path"
        self.remote_ref = "dummy_remote_ref"
        self.remote_state = "dummy_remote_state"
        self.update_remote = True
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

    def clean_scanned(self):
        pass

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

    def _queue_pair_state(
        self, id: int, folderish: bool, pair_state: str, pair: DocPair
    ):
        pass

    def release_state(self, thread_id):
        pass

    def remove_state(self, doc_pair):
        return None

    def replace_local_paths(self, old_path, new_path):
        pass

    def update_config(self, name: str, value: Any):
        pass

    def update_local_state(self, pair, child, versioned=False):
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

    def unsynchronize_state(self, row, last_error):
        pass


class Mock_Engine:
    def __init__(self) -> None:
        self.remote = Mock_Remote()


class Mock_Remote:
    def __init__(self) -> None:
        self.can_scroll_descendants = False
        self.folderish = False
        self.name = "dummy_name"
        self.path = "dummy_path"
        self.uid = "dummy_uid"

    def get_fs_info(self, fs_item_id, parent_fs_item_id=""):
        return self
