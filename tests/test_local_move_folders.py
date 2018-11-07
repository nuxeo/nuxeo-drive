# coding: utf-8
import os
import shutil

from .common import UnitTestCase


class TestLocalMoveFolders(UnitTestCase):

    NUMBER_OF_LOCAL_IMAGE_FILES = 10

    def _setup(self):
        """
        1. Create folder a1 in Nuxeo Drive Test Workspace sycn root
        2. Create folder a2 in Nuxeo Drive Test Workspace sycn root
        3. Add 10 image files in a1
        4. Add 10 image files in a2
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()
        local = self.local_1
        remote = self.remote_1
        # Create a1 and a2
        self.folder_path_1 = local.make_folder("/", "a1")
        self.folder_path_2 = local.make_folder("/", "a2")

        num = self.NUMBER_OF_LOCAL_IMAGE_FILES
        names = set(["file%03d.png" % file_num for file_num in range(1, num + 1)])

        for path in [self.folder_path_1, self.folder_path_2]:
            for name in names:
                file_path = os.path.join(local.abspath(path), name)
                self.generate_random_png(file_path)

        self.engine_1.start()
        self.wait_sync(timeout=30, wait_win=True)

        # Check /a1 and /a2
        for folder in {"/a1", "/a2"}:
            # Check local files
            assert local.exists(folder)
            children = [child.name for child in local.get_children_info(folder)]
            assert len(children) == num
            assert set(children) == names

            # Check remote files
            uid = local.get_remote_id(folder)
            assert uid
            assert remote.fs_exists(uid)
            children = [child.name for child in remote.get_fs_children(uid)]
            assert len(children) == num
            assert set(children) == names

    def test_local_move_folder_with_files(self):
        self._setup()
        local = self.local_1
        remote = self.remote_1
        remote_doc = self.remote_document_client_1
        src = local.abspath(self.folder_path_1)
        dst = local.abspath(self.folder_path_2)
        shutil.move(src, dst)
        self.wait_sync()
        num = self.NUMBER_OF_LOCAL_IMAGE_FILES
        names = set(["file%03d.png" % file_num for file_num in range(1, num + 1)])

        # Check that a1 doesn't exist anymore locally and remotely
        assert not local.exists("/a1")
        assert len(remote_doc.get_children_info(self.workspace)) == 1

        # Check /a2 and /a2/a1
        for folder in {"/a2", "/a2/a1"}:
            assert local.exists(folder)
            children = [
                child.name
                for child in local.get_children_info(folder)
                if not child.folderish
            ]
            assert len(children) == num
            assert set(children) == names

            uid = local.get_remote_id(folder)
            assert uid
            assert remote.fs_exists(uid)
            children = [
                child.name
                for child in remote.get_fs_children(uid)
                if not child.folderish
            ]
            assert len(children) == num
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
        folder_pair_state = self.engine_1.get_dao().get_state_from_local(
            "/" + self.workspace_title + "/Folder1"
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
        folder_pair_state = self.engine_1.get_dao().get_normal_state_from_remote(
            folder_remote_ref
        )
        assert folder_pair_state.pair_state == "conflicted"
