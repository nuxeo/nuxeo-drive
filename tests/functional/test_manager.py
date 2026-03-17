import logging
import os
from unittest.mock import Mock, patch

import pytest

from nxdrive.constants import TransferStatus
from nxdrive.exceptions import NoAssociatedSoftware
from nxdrive.objects import Session

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


def _make_session(uid: int = 1, completed_on: str = "2021-02-18 15:15:39") -> Session:
    return Session(
        uid=uid,
        remote_path="/default-domain/UserWorkspaces/Administrator/test_csv",
        remote_ref="08716a45-7154-4c2a-939c-bb70a7a2805e",
        status=TransferStatus.DONE,
        uploaded_items=3,
        total_items=3,
        engine="f513f5b371cc11eb85d008002733076e",
        created_on="2021-02-18 15:15:38",
        completed_on=completed_on,
        description="test-session (+2)",
        planned_items=3,
    )


def test_generate_csv_session_not_found(manager_factory):
    """generate_csv returns False when the session_id does not exist."""
    manager, engine = manager_factory()
    with manager:
        with patch.object(engine.dao, "get_session", return_value=None):
            result = manager.generate_csv(999, engine)
    assert result is False


def test_generate_csv_threadpool_available(manager_factory):
    """generate_csv returns True when the session exists and the threadpool is ready."""
    manager, engine = manager_factory()
    session = _make_session()
    with manager:
        with patch.object(engine.dao, "get_session", return_value=session):
            engine._threadpool = Mock()
            result = manager.generate_csv(session.uid, engine)
    assert result is True


def test_generate_csv_no_threadpool(manager_factory, caplog):
    """generate_csv returns False and logs a warning when _threadpool is None."""
    manager, engine = manager_factory()
    session = _make_session()
    with manager:
        with patch.object(engine.dao, "get_session", return_value=session):
            engine._threadpool = None
            with caplog.at_level(logging.WARNING):
                result = manager.generate_csv(session.uid, engine)
    assert result is False
    assert any("thread pool is not available" in r.message for r in caplog.records)


def test_generate_csv_async_success(manager_factory):
    """_generate_csv_async creates the CSV file and emits sessionUpdated signals."""
    manager, engine = manager_factory()
    dao = engine.dao
    session = _make_session()

    session_items = [
        {
            "path": "/default-domain/UserWorkspaces/Administrator/test_csv/file.txt",
            "properties": {"dc:title": "file.txt"},
            "type": "File",
        }
    ]

    signal_calls = []
    dao.sessionUpdated.connect(lambda done: signal_calls.append(done))

    with manager:
        with patch.object(dao, "get_session_items", return_value=session_items):
            manager._generate_csv_async(engine, session)

    csv_dir = manager.home / "csv"
    csv_files = list(csv_dir.glob("*.csv"))
    assert len(csv_files) == 1, "Expected one CSV output file"
    content = csv_files[0].read_text(encoding="utf-8")
    assert "file.txt" in content

    # sessionUpdated emitted with False (start) then True (done)
    assert False in signal_calls
    assert signal_calls[-1] is True


def test_generate_csv_async_exception(manager_factory, caplog):
    """_generate_csv_async handles exceptions and still emits sessionUpdated(True)."""
    manager, engine = manager_factory()
    dao = engine.dao
    session = _make_session()

    signal_calls = []
    dao.sessionUpdated.connect(lambda done: signal_calls.append(done))

    def raise_on_store(items):
        raise RuntimeError("simulated store_data failure")

    with manager:
        with patch.object(dao, "get_session_items", return_value=[]):
            with patch("nxdrive.session_csv.SessionCsv.store_data", new=raise_on_store):
                with caplog.at_level(logging.ERROR):
                    manager._generate_csv_async(engine, session)

    assert any("CSV generation error" in r.message for r in caplog.records)
    # finally block must still emit True even after a failure
    assert signal_calls[-1] is True
