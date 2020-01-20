# coding: utf-8
import shutil
from contextlib import suppress
from pathlib import Path
from time import sleep

from .common import OneUserTest
from .. import ensure_no_exception
from ..utils import random_png


class TestLocalMoveFolders(OneUserTest):
    def _setup(self, count: int = 10, wait_for_sync: bool = True):
        """
        1. Create folder a1 at the root
        2. Create folder a2 at the root
        3. Add *count* pictures in a1
        4. Add *count* pictures in a2
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()

        local = self.local_1
        remote = self.remote_1

        # Create a1 and a2
        self.folder_path_1 = local.make_folder("/", "a1")
        self.folder_path_2 = local.make_folder("/", "a2")

        names = {f"file{n + 1:03d}.png" for n in range(count)}

        for path in (self.folder_path_1, self.folder_path_2):
            for name in names:
                file_path = local.abspath(path) / name
                random_png(file_path)

        self.engine_1.start()

        if wait_for_sync:
            self.wait_sync(timeout=30, wait_win=True)

        # Check /a1 and /a2
        for folder in ("/a1", "/a2"):
            # Check local files
            assert local.exists(folder)
            children = [child.name for child in local.get_children_info(folder)]
            assert len(children) == count
            assert set(children) == names

            if wait_for_sync:
                # Check remote files
                uid = local.get_remote_id(folder)
                assert uid
                assert remote.fs_exists(uid)
                children = [child.name for child in remote.get_fs_children(uid)]
                assert len(children) == count
                assert set(children) == names

    def tearDown(self):
        with suppress(TypeError):
            self.engine_1._local_watcher.localScanFinished.disconnect(
                self.app.local_scan_finished
            )

    def test_local_move_folder_with_files(self):
        count = 10
        self._setup(count=count)
        local = self.local_1
        remote = self.remote_1
        remote_doc = self.remote_document_client_1
        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync()
        names = {f"file{n + 1:03d}.png" for n in range(count)}

        # Check that a1 doesn't exist anymore locally and remotely
        assert not local.exists("/a1")
        assert len(remote_doc.get_children_info(self.workspace)) == 1

        # Check /a2 and /a2/a1
        for folder in ("/a2", "/a2/a1"):
            assert local.exists(folder)
            children = [
                child.name
                for child in local.get_children_info(folder)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

            uid = local.get_remote_id(folder)
            assert uid
            assert remote.fs_exists(uid)
            children = [
                child.name
                for child in remote.get_fs_children(uid)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

    def test_local_move_folder_both_sides_while_stopped(self):
        self._test_local_move_folder_both_sides(False)

    def test_local_move_folder_both_sides_while_unbinded(self):
        self._test_local_move_folder_both_sides(True)

    def _test_local_move_folder_both_sides(self, unbind):
        """
        NXDRIVE-647: sync when a folder is renamed locally and remotely.
        """

        local = self.local_1
        remote = self.remote_document_client_1

        # Create initial folder and file
        folder = remote.make_folder("/", "Folder1")
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # First checks, everything should be online for every one
        assert remote.exists("/Folder1")
        assert local.exists("/Folder1")
        folder_pair_state = self.engine_1.dao.get_state_from_local(
            Path(self.workspace_title) / "Folder1"
        )
        assert folder_pair_state is not None
        folder_remote_ref = folder_pair_state.remote_ref

        # Unbind or stop engine
        if unbind:
            self.send_unbind_engine(1)
            self.wait_unbind_engine(1)
        else:
            self.engine_1.stop()

        # Make changes
        remote.update(folder, properties={"dc:title": "Folder1_ServerName"})
        local.rename("/Folder1", "Folder1_LocalRename")

        # Bind or start engine and wait for sync
        if unbind:
            self.send_bind_engine(1)
            self.wait_bind_engine(1)
        else:
            self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Check that nothing has changed
        assert len(remote.get_children_info(self.workspace)) == 1
        assert remote.exists(folder)
        assert remote.get_info(folder).name == "Folder1_ServerName"
        assert len(local.get_children_info("/")) == 1
        assert local.exists("/Folder1_LocalRename")

        # Check folder status
        folder_pair_state = self.engine_1.dao.get_normal_state_from_remote(
            folder_remote_ref
        )
        assert folder_pair_state.pair_state == "conflicted"

    def test_local_move_folder(self):
        """
        A simple test to ensure we do not create useless URLs.
        This is to handle cases when the user creates a new folder,
        it has the default name set to the local system:
            "New folder"
            "Nouveau dossier (2)"
            ...
        The folder is created directly and it generates useless URLs.
        So we move the document to get back good URLs. As the document has been
        renamed above, the document's title is aleady the good one.
        """
        local = self.local_1
        remote = self.remote_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        name_orig = "Nouveau dossier (42)"
        name_new = "C'est le vrai nom pârdi !"

        local.make_folder("/", name_orig)
        self.wait_sync()

        child = remote.get_children_info(self.workspace)[0]
        assert child.name == name_orig
        assert child.path.endswith(name_orig)

        # Rename to fix the meaningfulness URL
        local.rename(f"/{name_orig}", name_new)
        self.wait_sync()

        assert remote.exists(f"/{name_new}")
        child = remote.get_children_info(self.workspace)[0]
        assert child.name == name_new
        assert child.path.endswith(name_new)

    def test_local_move_root_folder_with_unicode(self):
        local = self.local_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        assert local.exists("/")

        with ensure_no_exception():
            # Rename the root folder
            root_path = local.base_folder.parent
            local.unlock_ref(root_path, is_abs=True)
            root_path.rename(root_path.with_name("root moved, 👆!"))

            self.wait_sync()

        assert not local.exists("/")

    def test_move_parent_while_syncing_a_lot_of_files(self):
        """NXDRIVE-947: Duplicates are created when the parent is renamed while syncing up.

        Steps:
            - Create a new folder and named as temp8 in Nuxeo Drive to sync up
            - Copy 1,000 files in the folder in Nuxeo Drive to sync up
            - While syncing up, rename the folder temp8 to temp9
        """
        sync_count = self.engine_1.dao.get_sync_count
        local = self.local_1
        remote = self.remote_1
        remote_doc = self.remote_document_client_1

        # NXDRIVE-987: count the number of local scan
        self.engine_1._local_watcher.localScanFinished.connect(
            self.app.local_scan_finished
        )

        count = 1000
        self._setup(count=count, wait_for_sync=False)  # 2,000 files

        # Wait for 1,000+ files to be synced before doing anything
        while sync_count() <= 1000:
            sleep(1)

        # Rename a1 to "a1 moved"
        src = local.abspath(self.folder_path_1)
        dst = src.with_name(f"{src.name} moved")
        shutil.move(src, dst)

        # Rename a2 to "a2 moved"
        src = local.abspath(self.folder_path_2)
        dst = src.with_name(f"{src.name} moved")
        shutil.move(src, dst)

        # Wait for the sync to finish
        self.wait_sync(timeout=100, wait_win=True)

        # Expected files
        names = {f"file{n + 1:03d}.png" for n in range(count)}

        # Check that a* doesn't exist anymore locally and remotely
        assert not local.exists("/a1")
        assert not local.exists("/a2")
        children = remote_doc.get_children_info(self.workspace)
        assert len(children) == 2
        for child in children:
            assert child.name in ("a1 moved", "a2 moved")

        # Check "a* moved" content
        for folder in ("/a1 moved", "/a2 moved"):
            # Local checks
            assert local.exists(folder)
            children = [
                child.name
                for child in local.get_children_info(folder)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

            # Remote checks
            uid = local.get_remote_id(folder)
            assert uid
            assert remote.fs_exists(uid)
            children = [
                child.name
                for child in remote.get_fs_children(uid)
                if not child.folderish
            ]
            assert len(children) == count
            assert set(children) == names

        # NXDRIVE-987: ensure there was only 1 local scan done
        assert self.app.local_scan_count == 1
