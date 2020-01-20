# coding: utf-8
from datetime import datetime
from pathlib import Path

from nxdrive.client.local import FileInfo
from nxdrive.constants import DelAction
from nxdrive.objects import RemoteFileInfo


def test_delete_doc(manager_factory, tmp):
    manager, engine = manager_factory()
    dao = engine.dao

    def doc_pair(name: str, synced: bool = True, with_rpaths: bool = False) -> str:
        """Create a valid doc pair in the database and return the local_path field."""
        # Craft the local file
        finfo = FileInfo(Path("."), Path(name), False, datetime.now())
        dao.insert_local_state(finfo)

        if synced:
            # Edit pair states to mimic a synced document
            doc_pair = dao.get_state_from_local(f"/{name}")
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
                    }
                )
                doc_pair.remote_parent_path = "remote-aprent-path"
                dao.update_remote_state(doc_pair, rinfo)

        return f"/{name}"

    with manager:
        # Test a file without associated doc pair
        engine.delete_doc(Path("inexistant"))

        # Test a file not synced
        engine.delete_doc(doc_pair("unsynced", synced=False))
        assert dao.get_state_from_local("/unsynced") is None

        # Test UNSYNC a synced file:
        engine.delete_doc(doc_pair("action unsync"), mode=DelAction.UNSYNC)
        assert dao.get_state_from_local("/action unsync") is None

        # Test UNSYNC a synced file with remote paths, to prevent such error:
        #   TypeError: unsupported operand type(s) for +: 'NoneType' and 'str'
        #   File "gui/application.py", line 479, in _doc_deleted
        #   File "engine/engine.py", line 302, in delete_doc
        engine.delete_doc(
            doc_pair("action unsync with paths", with_rpaths=True),
            mode=DelAction.UNSYNC,
        )
        assert dao.get_state_from_local("/action unsync with paths") is None
        assert len(dao.get_filters()) == 1

        # Test DELETE a synced file
        engine.delete_doc(doc_pair("action delete"), mode=DelAction.DEL_SERVER)
        assert dao.get_state_from_local("/action delete") is not None

        # Test no mode set
        engine.delete_doc(doc_pair("no mode set"))

        # Test ROLLBACK a synced file, this is a no-op for now
        engine.delete_doc(doc_pair("action rollback"), mode=DelAction.ROLLBACK)
