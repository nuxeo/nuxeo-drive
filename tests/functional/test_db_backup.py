# coding: utf-8
from sqlite3 import DatabaseError
from logging import getLogger

import nxdrive.engine.dao.utils
from nxdrive.engine.dao.sqlite import ConfigurationDAO

log = getLogger(__name__)


def test_create_backup(manager_factory, tmp, nuxeo_url, user_factory, monkeypatch):
    home = tmp()
    conf_folder = tmp() / "nuxeo-conf"
    user = user_factory()

    # Start and stop a manager
    with manager_factory(home=home, with_engine=False) as manager:
        manager.bind_server(
            conf_folder, nuxeo_url, user.uid, user.password, start_engine=False
        )

    # Check DB and backup exist
    assert (home / "manager.db").exists()
    assert len(list((home / "backups").glob("manager.db_*"))) == 1

    # Make fix_db() delete the db and raise an error to trigger a restore
    def buggy_db(database, *args, **kwargs):
        if database.name.startswith("manager"):
            database.unlink()
            raise DatabaseError()

    monkeypatch.setattr("nxdrive.engine.dao.sqlite.fix_db", buggy_db)

    def restore_db(self):
        nonlocal restored
        restored = True
        return nxdrive.engine.dao.utils.restore_backup(self._db)

    restored = False
    monkeypatch.setattr(ConfigurationDAO, "restore_backup", restore_db)

    with manager_factory(home=home, with_engine=False) as manager:
        assert (home / "manager.db").exists()
        assert restored
