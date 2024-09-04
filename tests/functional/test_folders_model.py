from unittest.mock import Mock, patch

from nxdrive.gui.folders_model import FoldersOnly


def test_folders_only():
    def request_(*args, **kwargs):
        return {
            "entries": [
                {
                    "entity-type": "document",
                    "uid": "11be49d0-875e-4054-a353-eff47b7358b3",
                    "path": "/default-domain/workspaces/Shared_WSP",
                    "type": "Workspace",
                    "parentRef": "e537253c-c59a-411a-a96a-25f972b4c22a",
                    "title": "Shared_WSP",
                    "facets": ["Folderish", "NXTag", "SuperSpace"],
                }
            ]
        }

    def request_with_error(*args, **kwargs):
        return 1 / 0

    folders_only = FoldersOnly(Mock())

    with patch.object(folders_only.remote.client, "request", new=request_):
        assert folders_only._get_root_folders()

    with patch.object(folders_only.remote.client, "request", new=request_with_error):
        assert folders_only._get_root_folders()
