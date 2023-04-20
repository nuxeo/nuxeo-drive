from collections import namedtuple
from unittest.mock import patch

from nxdrive.engine.watcher.remote_watcher import RemoteWatcher


def test_sync_root_name(manager_factory):
    manager, engine = manager_factory()
    dao = engine.dao

    docpair = namedtuple(
        "DocPair",
        "local_path, local_parent_path, remote_ref, local_state, \
            remote_state, pair_state, last_error, remote_parent_path",
        defaults=(
            ".",
            ".",
            "org.nuxeo.drive.service.impl.DefaultTopLevelFolderItemFactory#",
            "synchronized",
            "synchronized",
            "synchronized",
            None,
            "",
        ),
    )
    test_watcher = RemoteWatcher(engine, dao)

    def get_changes():
        return eval(
            '{ "type": "test", "fileSystemChanges": [ { "repositoryId": "default", \
                "eventId": "securityUpdated", "eventDate": 1681875648592, "docUuid": \
                    "a7e4ce2a-e4a7-432a-b5e1-62b354606929", "fileSystemItem": {"id": \
                        "defaultSyncRootFolderItemFactory#default#a7e4ce2a-e4a7-432a-\
                        b5e1-62b354606929-test", "parentId": "org.nuxeo.drive.service.\
                            impl.DefaultTopLevelFolderItemFactory#", "name": "ROY", \
                            "folder": True, "creator": "Administrator", \
                                "lastContributor": "Administrator", \
                                    "creationDate": 1681875486061, \
                                        "lastModificationDate": 1681875528408, \
                                            "canRename": True, "canDelete": True, \
                                                "lockInfo": None, "path": "/org.nuxeo.\
                                                    drive.service.impl.DefaultTopLevelFolder\
                                                        ItemFactory#/defaultSyncRootFolderItemFactory\
                                                        #default#a7e4ce2a-e4a7-432a-b5e1-62b354606929-test",\
                                                         "userName": "Administrator", "canCreateChild": True,\
                                                              "canScrollDescendants": True }, "fileSystemItemId": \
                                                                "defaultSyncRootFolderItemFactory#default#a7e4ce2a-\
                                                                e4a7-432a-b5e1-62b354606929-test", \
                                                                    "fileSystemItemName": "ROY" } ]\
                                                                    , "syncDate": 1681875652000, "upp\
                                                                        erBound": 7834,\
                                                                          "hasTooManyChanges": True, \
                                                                            "activeSynchronizationRootDe\
                                                                            finitions": "default:ffed6ec7-\
                                                                                b6d3-41a7-ba10-801b7678a5\
                                                                                84-test,default:a7e4ce2a-e4a7-432a-b5e1-62b35460692\
                                                                                    9-test,default:db4e8005-c7aa-4f26-937b-23476e85\
                                                                                        2223-test,default:47176834-992d-4d81-9ce1-a\
                                                                                            51b7841d648-test" }'
        )

    def get_states_from_remote_(path):
        return [docpair]

    def update_remote_state_(*args, **kwargs):
        return False

    def unset_unsychronised_(*args):
        return

    def _force_remote_scan_(*args, **kwargs):
        return

    def get_state_from_id_(*args):
        return None

    def _find_remote_child_match_or_create_(parent_pair, new_info):
        assert "test" in new_info.id
        return None

    update_remote_states = test_watcher._update_remote_states

    with patch.object(test_watcher, "_get_changes", new=get_changes):
        with patch.object(test_watcher, "_force_remote_scan", new=_force_remote_scan_):
            with patch.object(
                test_watcher,
                "_find_remote_child_match_or_create",
                new=_find_remote_child_match_or_create_,
            ):
                with patch.object(
                    dao, "get_states_from_remote", new=get_states_from_remote_
                ):
                    with patch.object(
                        dao, "update_remote_state", new=update_remote_state_
                    ):
                        with patch.object(
                            dao, "unset_unsychronised", new=unset_unsychronised_
                        ):
                            with patch.object(
                                dao, "get_state_from_id", new=get_state_from_id_
                            ):
                                update_remote_states
