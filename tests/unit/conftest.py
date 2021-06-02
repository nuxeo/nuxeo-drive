import shutil
import time
from typing import Optional
from uuid import uuid4

import pytest

from nxdrive.dao.engine import EngineDAO
from nxdrive.objects import DocPair
from nxdrive.utils import normalized_path


class MockEngineDAO(EngineDAO):
    """Convenient class with auto-cleanup at exit."""

    tmp = None

    def __init__(self, fname):
        root = normalized_path(__file__).parent.parent
        src = root / "resources" / "databases" / fname
        dst = self.tmp / src.with_name(f"{uuid4()}.db").name
        shutil.copy(src, dst)
        time.sleep(1)
        super().__init__(dst)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.dispose()
        self.db.unlink()

    def _get_adjacent_sync_file(
        self, ref: str, comp: str, order: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        if state is None:
            return None

        mode = f" AND last_transfer='{sync_mode}' " if sync_mode else ""
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States "
            f"WHERE last_sync_date {comp} ? "
            "   AND (pair_state != 'unsynchronized' "
            "   AND pair_state != 'conflicted') "
            "   AND folderish = 0 "
            f"{mode}"
            f"ORDER BY last_sync_date {order}"
            " LIMIT 1",
            (state.last_sync_date,),
        ).fetchone()

    def _get_adjacent_folder_file(
        self, ref: str, comp: str, order: str
    ) -> Optional[DocPair]:
        state = self.get_normal_state_from_remote(ref)
        if not state:
            return None
        c = self._get_read_connection().cursor()
        return c.execute(
            "SELECT *"
            "  FROM States"
            " WHERE remote_parent_ref = ?"
            f"  AND remote_name {comp} ?"
            "   AND folderish = 0 "
            f"ORDER BY remote_name {order}"
            " LIMIT 1",
            (state.remote_parent_ref, state.remote_name),
        ).fetchone()

    def get_previous_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, "<", "DESC")

    def get_next_folder_file(self, ref: str) -> Optional[DocPair]:
        return self._get_adjacent_folder_file(ref, ">", "ASC")

    def get_previous_sync_file(
        self, ref: str, sync_mode: str = None
    ) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, ">", "ASC", sync_mode)

    def get_next_sync_file(self, ref: str, sync_mode: str = None) -> Optional[DocPair]:
        return self._get_adjacent_sync_file(ref, "<", "DESC", sync_mode)


@pytest.fixture()
def engine_dao(tmp_path):
    dao = MockEngineDAO
    dao.tmp = tmp_path
    return dao
