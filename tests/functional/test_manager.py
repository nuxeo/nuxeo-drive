import os
from unittest.mock import Mock

import pytest

from nxdrive.exceptions import NoAssociatedSoftware

from ..markers import windows_only


@windows_only
def test_open_local_file_no_soft(manager_factory, monkeypatch):
    """
    Ensure that manager.open_local_file() raises our exception
    when there is no associated software.
    """

    def startfile(path):
        raise OSError(
            1155,
            "No application is associated with the specified file for this operation.",
            path,
            1155,
        )

    monkeypatch.setattr(os, "startfile", startfile)
    with manager_factory(with_engine=False) as manager, pytest.raises(
        NoAssociatedSoftware
    ):
        manager.open_local_file("File.azerty")


def test_init_workflow_with_app(manager_factory):
    manager = manager_factory(with_engine=False)
    # manager = Manager(tmp_path)
    manager.db_backup_worker = Mock()

    manager.autolock_service = Mock()
    manager.server_config_updater = Mock()
    manager._create_server_config_updater = Mock()
    manager.sync_and_quit_worker = Mock()
    manager._create_db_backup_worker = Mock()
    manager._create_workflow_worker = Mock()

    # app = Application(manager)
    # app.manager
    # engine = Mock()
    # engine.remote = "test"
    # app.manager.engines = {"engine_uid": engine}
    # app.engine_model.engines_uid = ["engine_uid"]
    # app.init_workflow()
    # manager.close()
    # app.exit_app()
    # assert 1 == 0


# This test is commented because it causes other ft tests to fails
# @Options.mock()
# def test_manager_init_failed_migrations(manager_factory, tmp_path, monkeypatch):
#     """
#     Ensure that when the migrations fail, the xxx_broken_update option is saved.
#     """
#     from nxdrive.dao.migrations.manager import manager_migrations as orignal_migrations

#     assert Options.xxx_broken_update is None
#     assert Options.feature_auto_update

#     class MockedMigration:
#         """Mocked migration that raise an exception on upgrade."""

#         def upgrade(self, _):
#             raise sqlite3.Error("Mocked exception")

#     # Init the database with the initial migration
#     with manager_factory(home=tmp_path, with_engine=False) as _:
#         pass

#     new_migrations = orignal_migrations.copy()
#     new_migrations["9999_test"] = MockedMigration()

#     with pytest.raises(SystemExit):
#         monkeypatch.setattr(
#             "nxdrive.dao.migrations.manager.manager_migrations",
#             new_migrations,
#         )

#         try:
#             # Run the new failing migration
#             with manager_factory(home=tmp_path, with_engine=False) as _:
#                 pass
#         finally:
#             monkeypatch.undo()

#     assert Options.xxx_broken_update == __version__
#     assert not Options.feature_auto_update
