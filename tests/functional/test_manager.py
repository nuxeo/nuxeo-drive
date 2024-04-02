import os

import pytest

from nxdrive.exceptions import NoAssociatedSoftware
from nxdrive.gui.application import Application

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


def test_app_init_workflow(manager_factory):
    # Trigger workflow while launching app
    manager, _ = manager_factory()
    with manager:

        app = Application(manager)
        app.init_workflow()
        app.exit_app()


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
