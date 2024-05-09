import os
import shutil
import time
from typing import Any, Callable, Optional
from uuid import uuid4

import pytest

from nxdrive.client.remote_client import Remote
from nxdrive.constants import TransferStatus
from nxdrive.dao.engine import EngineDAO
from nxdrive.dao.manager import ManagerDAO
from nxdrive.engine.engine import Engine
from nxdrive.engine.processor import Processor
from nxdrive.gui.view import DirectTransferModel
from nxdrive.manager import Manager
from nxdrive.objects import DocPair, Upload
from nxdrive.osi import AbstractOSIntegration
from nxdrive.qt import constants as qt
from nxdrive.qt.imports import QObject
from nxdrive.updater.darwin import Updater
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


class MockManagerDAO(ManagerDAO):
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


class MockProcessor(Processor):
    def __init__(self, engine, engine_dao):
        self.engine = engine
        self.dao = engine_dao
        super().__init__(self, engine, engine_dao)


class MockEngine(Engine):
    def __init__(self, tmp_path):
        local_folder = tmp_path

        super().__init__(self, local_folder)


class MockManager(Manager):
    def __init__(self, tmp_path):
        home = tmp_path

        super().__init__(self, home)


class MockUpdater(Updater):
    def __init__(self, tmp_path):
        final_app = tmp_path
        super().__init__(self, final_app)


class MockDirectTransferModel(DirectTransferModel):
    def __init__(
        self, translate: Callable[..., Any], /, *, parent: QObject = None
    ) -> None:
        super().__init__(translate, parent=parent)


@pytest.fixture()
def engine_dao(tmp_path):
    dao = MockEngineDAO
    dao.tmp = tmp_path
    return dao


@pytest.fixture()
def manager_dao(tmp_path):
    dao = MockManagerDAO
    dao.tmp = tmp_path
    return dao


@pytest.fixture()
def engine(engine_dao):
    engine = MockEngine
    engine.local_folder = os.path.expandvars("C:\\test\\%username%\\Drive")
    engine.dao = engine_dao
    engine.uid = f"{uuid4()}"
    return engine


@pytest.fixture()
def manager(tmp_path):
    manager = MockManager
    manager.osi = AbstractOSIntegration
    manager.home = tmp_path
    return manager


@pytest.fixture()
def updater(tmp_path):
    updater = MockUpdater
    updater.manager = MockManager
    updater.manager.osi = AbstractOSIntegration
    updater.final_app = tmp_path
    return updater


@pytest.fixture()
def processor(engine, engine_dao):
    processor = MockProcessor
    processor.engine = engine
    processor.remote = Remote
    processor.dao = engine_dao
    return processor


@pytest.fixture()
def upload():
    upload = Upload
    upload.path = "/tmp"
    upload.status = TransferStatus.ONGOING
    upload.engine = f"{engine}"
    upload.is_direct_edit = False
    upload.is_direct_transfer = True
    upload.filesize = "23.0"
    upload.batch = {"batchID": f"{str(uuid4())}"}
    upload.chunk_size = "345"
    upload.remote_parent_path = "/tmp/remote_path"
    upload.remote_parent_ref = "/tmp/remote_path_ref"
    upload.doc_pair = "test_file"
    upload.request_uid = str(uuid4())
    return upload


@pytest.fixture()
def direct_transfer_model():
    direct_transfer_model = MockDirectTransferModel
    direct_transfer_model.FINALIZING_STATUS = qt.UserRole + 13
    direct_transfer_model.items = [
        {
            "uid": 1,
            "name": "a.txt",
            "filesize": 142936511610,
            "status": "",
            "engine": "51a2c2dc641311ee87fb...bfc0ec09fa",
            "progress": 100.0,
            "doc_pair": 1,
            "remote_parent_path": "/default-domain/User...TestFolder",
            "remote_parent_ref": "7b7886ea-5ad9-460d-8...1607ea0081",
            "shadow": True,
            "finalizing": True,
        }
    ]
    return direct_transfer_model
