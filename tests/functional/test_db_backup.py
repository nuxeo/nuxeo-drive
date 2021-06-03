from datetime import datetime
from logging import getLogger
from sqlite3 import DatabaseError
from time import sleep

import nxdrive.dao.utils
from nxdrive.dao.base import BaseDAO

from .. import ensure_no_exception

log = getLogger(__name__)


def test_create_backup(manager_factory, tmp, nuxeo_url, user_factory, monkeypatch):
    home = tmp()
    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory()

    # Start and stop a manager
    with manager_factory(home=home, with_engine=False) as manager:
        manager.bind_server(
            conf_folder,
            nuxeo_url,
            user.uid,
            password=user.properties["password"],
            start_engine=False,
        )

    # Check DB and backup exist
    assert (home / "manager.db").exists()
    assert len(list((home / "backups").glob("manager.db_*"))) == 1

    # Make fix_db() delete the db and raise an error to trigger a restore
    def buggy_db(database, *args, **kwargs):
        if database.name.startswith("manager"):
            database.unlink()
            raise DatabaseError("Mock")

    monkeypatch.setattr("nxdrive.dao.base.fix_db", buggy_db)

    # Before NXDRIVE-1574, there was an error when restoring the DB:
    #    AttributeError: 'ManagerDAO' object has no attribute '_lock'
    # This should not be the case anymore.

    with ensure_no_exception(), manager_factory(home=home, with_engine=False):
        assert (home / "manager.db").exists()

    def restore_db(self):
        nonlocal restored
        restored = True
        return nxdrive.dao.utils.restore_backup(self.db)

    restored = False
    monkeypatch.setattr(BaseDAO, "restore_backup", restore_db)

    with manager_factory(home=home, with_engine=False) as manager:
        assert (home / "manager.db").exists()
        assert restored


def test_delete_old_backups(tmp):
    home = tmp()
    backups = home / "backups"
    backups.mkdir(parents=True, exist_ok=True)

    db = home / "manager.db"
    db.touch()

    today = int(datetime.now().timestamp())
    yesterday = today - 86400

    for i in range(3):
        # Creating 3 files with timestamps of today
        (backups / f"manager.db_{today - i * 1000}").touch()
        # And 3 files with timestamps of yesterday
        (backups / f"manager.db_{yesterday - i * 1000}").touch()

    sleep(1)
    nxdrive.dao.utils.save_backup(db)

    remaining_backups = sorted(backups.glob("manager.db_*"))

    # # of the previous ones should remain + the new one
    assert len(remaining_backups) == 4
    # The oldest should be more recent than the yesterday timestamp
    assert int(remaining_backups[0].name.split("_")[-1]) > yesterday
    # The newest should be more recent than the today timestamp
    assert int(remaining_backups[-1].name.split("_")[-1]) > today
