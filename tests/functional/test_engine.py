import logging
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from nxdrive.client.local import FileInfo
from nxdrive.constants import DelAction, TransferStatus
from nxdrive.exceptions import ThreadInterrupt, UnknownDigest
from nxdrive.manager import Manager
from nxdrive.objects import RemoteFileInfo, Session
from nxdrive.session_csv import SessionCsv

from .. import ensure_no_exception


def test_conflict_resolver(manager_factory, tmp, caplog):
    manager, engine = manager_factory()
    dao = engine.dao

    def bad(*args, **kwargs):
        raise ThreadInterrupt("Mock'ed exception")

    def unknown_digest(*args, **kwargs):
        raise UnknownDigest("Mock'ed exception")

    def doc_pair(name: str) -> int:
        """Create a valid doc pair in the database and return the row ID."""
        # Craft the local file
        path = tmp()
        file = path / name
        file.parent.mkdir()
        file.write_text("azerty")

        finfo = FileInfo(path, file, False, datetime.now())
        rowid = dao.insert_local_state(finfo, None)

        # Edit pair states to mimic a synced document
        doc_pair = dao.get_state_from_id(rowid)
        doc_pair.local_state = "modified"
        doc_pair.remote_state = "modified"
        dao.update_local_state(doc_pair, finfo)
        dao.update_remote_name(rowid, name)

        return rowid

    with caplog.at_level(logging.ERROR), ensure_no_exception(), manager:
        caplog.clear()

        # Test a conflict with an inexistent doc_pair
        engine.conflict_resolver(42)

        # Test a conflict
        rowid = doc_pair("conflict")
        engine.conflict_resolver(rowid, emit=False)

        # Test a conflict with unknown digest
        with patch.object(engine.local, "is_equal_digests", new=unknown_digest):
            engine.conflict_resolver(rowid)

        # Test a conflict when the Engine is stopped and the digest computation fails accordingly.
        # It should not fail.
        engine.stop()
        with patch.object(engine.local, "is_equal_digests", new=bad):
            engine.conflict_resolver(rowid, emit=False)

        assert not caplog.records


def test_delete_doc(manager_factory, tmp):
    manager, engine = manager_factory()
    dao = engine.dao

    def doc_pair(name: str, synced: bool = True, with_rpaths: bool = False) -> Path:
        """Create a valid doc pair in the database and return the local_path field."""
        # Craft the local file
        finfo = FileInfo(Path("."), Path(name), False, datetime.now())
        dao.insert_local_state(finfo, Path(name).parent)
        local_path = Path(f"/{name}")

        if synced:
            # Edit pair states to mimic a synced document
            doc_pair = dao.get_state_from_local(local_path)
            assert doc_pair is not None
            assert doc_pair.local_name == name
            doc_pair.local_state = "synchronized"
            doc_pair.remote_state = "synchronized"
            dao.update_local_state(doc_pair, finfo)

            if with_rpaths:
                # Also set fake remote paths
                rinfo = RemoteFileInfo.from_dict(
                    {
                        "id": "self-uid",
                        "parentId": "parent-uid",
                        "path": "/some/path",
                        "name": name,
                        "digest": "0" * 32,
                    }
                )
                doc_pair.remote_parent_path = "remote-aprent-path"
                dao.update_remote_state(doc_pair, rinfo)

        return local_path

    with manager:
        # Test a file without associated doc pair
        engine.delete_doc(Path("inexistent"))

        # Test a file not synced
        engine.delete_doc(doc_pair("unsynced", synced=False))
        assert dao.get_state_from_local(Path("/unsynced")) is None

        # Test UNSYNC a synced file:
        engine.delete_doc(doc_pair("action unsync"), mode=DelAction.UNSYNC)
        assert dao.get_state_from_local(Path("/action unsync")) is None

        # Test UNSYNC a synced file with remote paths, to prevent such error:
        #   TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'
        #   File "gui/application.py", line 479, in _doc_deleted
        #   File "engine/engine.py", line 302, in delete_doc
        engine.delete_doc(
            doc_pair("action unsync with paths", with_rpaths=True),
            mode=DelAction.UNSYNC,
        )
        assert dao.get_state_from_local(Path("/action unsync with paths")) is None
        assert len(dao.get_filters()) == 1

        # Test DELETE a synced file
        engine.delete_doc(doc_pair("action delete"), mode=DelAction.DEL_SERVER)
        assert dao.get_state_from_local(Path("/action delete")) is not None

        # Test no mode set
        engine.delete_doc(doc_pair("no mode set"))

        # Test ROLLBACK a synced file, this is a no-op for now
        engine.delete_doc(doc_pair("action rollback"), mode=DelAction.ROLLBACK)


def test_temporary_csv_cleanup(tmp, user_factory, nuxeo_url):
    session = Session(
        uid=2,
        remote_path="/default-domain/UserWorkspaces/Administrator/test_csv",
        remote_ref="08716a45-7154-4c2a-939c-bb70a7a2805e",
        status=TransferStatus.DONE,
        uploaded_items=10,
        total_items=10,
        engine="f513f5b371cc11eb85d008002733076e",
        created_on="2021-02-18 15:15:38",
        completed_on="2021-02-18 15:15:39",
        description="icons-svg (+9)",
        planned_items=10,
    )
    with Manager(tmp()) as manager:
        session_csv = SessionCsv(manager, session)

        session_csv.create_tmp()
        assert session_csv.output_tmp.is_file()
        assert not session_csv.output_file.is_file()
        conf_folder = manager.home / "nuxeo-conf"
        user = user_factory()
        manager.bind_server(
            conf_folder,
            nuxeo_url,
            user.uid,
            password=user.properties["password"],
            start_engine=False,
        )
        assert not session_csv.output_tmp.is_file()


def test_token_management(manager_factory):
    manager, engine = manager_factory()
    with manager:
        # The default token is a Nuxeo one (string)
        assert isinstance(engine._load_token(), str)

        # Ensure it works with empty tokens, preventing:
        #     TypeError: object of type 'NoneType' has no len()
        engine._save_token(None)

        # Save an OAuth2 token
        token = {
            "access_token": "...",
            "refresh_token": "...",
            "token_type": "bearer",
            "expires_in": 3599,
            "expires_at": 1618242664,
        }
        engine._save_token(token)
        assert engine._load_token() == token

        # Alter the stored token and check the loading will not fail
        engine.dao.update_config("remote_token", "blablabla")
        assert not engine._load_token()


def test_can_use_trash(manager_factory):
    manager, engine = manager_factory()
    with manager:
        assert engine.use_trash()
