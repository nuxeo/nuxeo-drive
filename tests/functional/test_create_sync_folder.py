from os import path

from nxdrive.engine.processor import Processor
from nxdrive.objects import DocPair


def test_create_folder(manager_factory, tmp_path):
    manager, engine = manager_factory()

    test_processor = Processor(engine, "")
    dp = DocPair
    dp.local_path = tmp_path
    dp.remote_ref = "defaultSyncRootFolderItemFactory"
    dp.folderish = True
    create_rem = test_processor._create_remotely

    full_path = create_rem(dp, dp, "default - domain - Workspaces - Administrator")
    assert str(path.join(tmp_path, "Administrator")) == str(full_path)

    full_path = create_rem(dp, dp, "default - domain1 - Workspaces - Administrator")
    assert str(
        path.join(tmp_path, "default - domain1 - Workspaces - Administrator")
    ) == str(full_path)

    dp.remote_ref = "defaultFileSystemItemFactory"

    full_path = create_rem(dp, dp, "Administrator")
    assert str(path.join(tmp_path, "Administrator_1")) == str(full_path)
