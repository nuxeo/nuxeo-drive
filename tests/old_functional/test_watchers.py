from copy import deepcopy
from pathlib import Path
from queue import Queue
from shutil import copyfile
from time import sleep
from unittest.mock import patch

from nxdrive.constants import ROOT

from ..markers import not_windows
from . import LocalTest
from .common import OneUserTest


def copy_queue(queue: Queue) -> Queue:
    result = deepcopy(queue.queue)
    result.reverse()
    return result


class TestWatchers(OneUserTest):
    def get_local_client(self, path):
        if self._testMethodName in {
            "test_local_scan_encoding",
            "test_watchdog_encoding",
        }:
            return LocalTest(path)
        return super().get_local_client(path)

    def make_local_tree(self, root=None, local_client=None):
        nb_files, nb_folders = 6, 4
        if not local_client:
            local_client = LocalTest(self.engine_1.local_folder)
        if not root:
            root = Path(self.workspace_title)
            if not local_client.exists(root):
                local_client.make_folder(Path(), self.workspace_title)
                nb_folders += 1
        # create some folders
        folder_1 = local_client.make_folder(root, "Folder 1")
        folder_1_1 = local_client.make_folder(folder_1, "Folder 1.1")
        folder_1_2 = local_client.make_folder(folder_1, "Folder 1.2")
        folder_2 = local_client.make_folder(root, "Folder 2")

        # create some files
        local_client.make_file(
            folder_2, "Duplicated File.txt", content=b"Some content."
        )

        local_client.make_file(folder_1, "File 1.txt", content=b"aaa")
        local_client.make_file(folder_1_1, "File 2.txt", content=b"bbb")
        local_client.make_file(folder_1_2, "File 3.txt", content=b"ccc")
        local_client.make_file(folder_2, "File 4.txt", content=b"ddd")
        local_client.make_file(root, "File 5.txt", content=b"eee")
        return nb_files, nb_folders

    def get_full_queue(self, queue, dao=None):
        if dao is None:
            dao = self.engine_1.dao
        result = []
        while queue:
            result.append(dao.get_state_from_id(queue.pop().id))
        return result

    def test_local_scan(self):
        files, folders = self.make_local_tree()
        self.queue_manager_1.suspend()
        self.queue_manager_1._disable = True
        self.engine_1.start()
        self.wait_sync()

        # Workspace should have been reconcile
        res = self.engine_1.dao.get_states_from_partial_local(ROOT)
        # With root
        count = folders + files + 1
        assert len(res) == count

    def test_reconcile_scan(self):
        files, folders = self.make_local_tree()
        self.make_server_tree()
        # Wait for ES indexing
        self.wait()
        manager = self.queue_manager_1
        manager.suspend()
        manager._disable = True
        self.engine_1.start()
        self.wait_sync()
        # Depending on remote scan results order, the remote
        # duplicated file with the same digest as the local file
        # might come first, in which case we get an extra synchronized file,
        # or not, in which case we get a conflicted file
        assert self.engine_1.dao.get_sync_count() >= folders + files
        # Verify it has been reconciled and all items in queue are synchronized
        queue = self.get_full_queue(copy_queue(manager._local_file_queue))
        for item in queue:
            if item.remote_name == "Duplicated File.txt":
                assert item.pair_state in ["synchronized", "conflicted"]
            else:
                assert item.pair_state == "synchronized"
        queue = self.get_full_queue(copy_queue(manager._local_folder_queue))
        for item in queue:
            assert item.pair_state == "synchronized"

    def test_remote_scan(self):
        total = len(self.make_server_tree())
        # Add the workspace folder + the root
        total += 2
        # Wait for ES indexing
        self.wait()
        self.queue_manager_1.suspend()
        self.queue_manager_1._disable = True
        self.engine_1.start()
        self.wait_sync()
        res = self.engine_1.dao.get_states_from_partial_local(ROOT)
        assert len(res) == total

    def test_local_watchdog_creation(self):
        # Test the creation after first local scan
        self.queue_manager_1.suspend()
        self.queue_manager_1._disable = True
        self.engine_1.start()
        self.wait_sync()
        metrics = self.queue_manager_1.get_metrics()
        assert not metrics["local_folder_queue"]
        assert not metrics["local_file_queue"]
        files, folders = self.make_local_tree()
        self.wait_sync(timeout=3, fail_if_timeout=False)
        metrics = self.queue_manager_1.get_metrics()
        assert metrics["local_folder_queue"]
        assert metrics["local_file_queue"]
        res = self.engine_1.dao.get_states_from_partial_local(ROOT)
        # With root
        assert len(res) == folders + files + 1

    def _delete_folder_1(self):
        path = Path("Folder 1")
        self.local_1.delete_final(path)
        self.wait_sync(timeout=1, fail_if_timeout=False, wait_win=True)

        timeout = 5
        while not self.engine_1._local_watcher.empty_events():
            sleep(1)
            timeout -= 1
            if timeout < 0:
                break
        return Path(self.workspace_title) / path

    def test_local_watchdog_delete_non_synced(self):
        # Test the deletion after first local scan
        self.test_local_scan()
        path = self._delete_folder_1()
        children = self.engine_1.dao.get_states_from_partial_local(path)
        assert not children

    def test_local_scan_delete_non_synced(self):
        # Test the deletion after first local scan
        self.test_local_scan()
        self.engine_1.stop()
        path = self._delete_folder_1()
        self.engine_1.start()
        self.wait_sync(timeout=5, fail_if_timeout=False)
        children = self.engine_1.dao.get_states_from_partial_local(path)
        assert not children

    def test_local_watchdog_delete_synced(self):
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        path = self._delete_folder_1()
        child = self.engine_1.dao.get_state_from_local(path)
        assert child.pair_state == "locally_deleted"
        children = self.engine_1.dao.get_states_from_partial_local(path)
        assert len(children) == 5
        for child in children:
            assert child.pair_state == "locally_deleted"

    def test_local_scan_delete_synced(self):
        # Test the deletion after first local scan
        self.test_reconcile_scan()
        self.engine_1.stop()
        path = self._delete_folder_1()
        self.engine_1.start()
        self.wait_sync(timeout=5, fail_if_timeout=False)
        child = self.engine_1.dao.get_state_from_local(path)
        assert child.pair_state == "locally_deleted"
        children = self.engine_1.dao.get_states_from_partial_local(path)
        assert len(children) == 5
        for child in children:
            assert child.pair_state == "locally_deleted"

    def test_local_scan_error(self):
        local = self.local_1
        remote = self.remote_document_client_1
        # Synchronize test workspace
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()
        # Create a local file and use an invalid digest function
        # in local watcher file system client to trigger an error
        # during local scan
        local.make_file("/", "Test file.odt", content=b"Content")

        with patch.object(self.engine_1.local, "_digest_func", return_value="invalid"):
            self.engine_1.start()
            self.wait_sync()
            self.engine_1.stop()
            assert not remote.exists("/Test file.odt")

        self.engine_1.start()
        self.wait_sync()
        assert remote.exists("/Test file.odt")

    def test_local_scan_encoding(self):
        local = self.local_1
        remote = self.remote_document_client_1
        # Synchronize test workspace
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()
        # Create files with Unicode combining accents,
        # Unicode latin characters and no special characters
        local.make_file("/", "Accentue\u0301.odt", content=b"Content")
        local.make_folder("/", "P\xf4le applicatif")
        local.make_file(
            "/P\xf4le applicatif",
            "e\u0302tre ou ne pas \xeatre.odt",
            content=b"Content",
        )
        local.make_file("/", "No special character.odt", content=b"Content")
        # Launch local scan and check upstream synchronization
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()
        assert remote.exists("/Accentue\u0301.odt")
        assert remote.exists("/P\xf4le applicatif")
        assert remote.exists("/P\xf4le applicatif/e\u0302tre ou ne pas \xeatre.odt")
        assert remote.exists("/No special character.odt")

        # Check rename using normalized names as previous local scan
        # has normalized them on the file system
        local.rename(
            "/Accentu\xe9.odt", "Accentue\u0301 avec un e\u0302 et un \xe9.odt"
        )
        local.rename("/P\xf4le applicatif", "P\xf4le applique\u0301")
        # LocalClient.rename calls LocalClient.get_info then
        # the FileInfo constructor which normalizes names
        # on the file system, thus we need to use
        # the normalized name for the parent folder
        local.rename(
            "/P\xf4le appliqu\xe9/\xeatre ou ne pas \xeatre.odt",
            "avoir et e\u0302tre.odt",
        )
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.engine_1.stop()
        assert (
            remote.get_info("/Accentue\u0301 avec un e\u0302 et un \xe9.odt").name
            == "Accentu\xe9 avec un \xea et un \xe9.odt"
        )
        assert remote.get_info("/P\xf4le applique\u0301").name == "P\xf4le appliqu\xe9"
        assert (
            remote.get_info("/P\xf4le appliqu\xe9/avoir et e\u0302tre.odt").name
            == "avoir et \xeatre.odt"
        )
        # Check content update
        # NXDRIVE-389: Reload the engine to be sure that
        # the pairs are all synchronized
        local.update_content(
            "/Accentu\xe9 avec un \xea et un \xe9.odt", b"Updated content"
        )
        local.update_content(
            "/P\xf4le appliqu\xe9/avoir et \xeatre.odt", b"Updated content"
        )
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()
        assert (
            remote.get_content("/Accentue\u0301 avec un e\u0302 et un \xe9.odt")
            == b"Updated content"
        )
        # NXDRIVE-389: Will be Content and not Updated content
        # it is not consider as synced, so conflict is generated
        assert (
            remote.get_content("/P\xf4le appliqu\xe9/avoir et e\u0302tre.odt")
            == b"Updated content"
        )

        # Check delete
        local.delete_final("/Accentu\xe9 avec un \xea et un \xe9.odt")
        local.delete_final("/P\xf4le appliqu\xe9/avoir et \xeatre.odt")
        self.engine_1.start()
        self.wait_sync()
        self.engine_1.stop()
        assert not remote.exists("/Accentue\u0301.odt")
        assert not remote.exists("/Accentu\xe9 avec un \xea et un \xe9.odt")
        assert not remote.exists("/P\xf4le applicatif/e\u0302tre ou ne pas \xeatre.odt")
        assert not remote.exists("/P\xf4le applicatif/avoir et e\u0302tre.odt")

    @not_windows(reason="Windows cannot have file ending with a space.")
    def test_watchdog_space_remover(self):
        """
        Test files and folders ending with space.
        """

        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync()

        local.make_file("/", "Accentue\u0301.odt ", content=b"Content")
        self.wait_sync()
        assert remote.exists("/Accentue\u0301.odt")
        assert not remote.exists("/Accentue\u0301.odt ")

        local.rename("/Accentu\xe9.odt", "Accentu\xe9 avec un \xea et un \xe9.odt ")
        self.wait_sync()
        assert (
            remote.get_info("/Accentu\xe9 avec un \xea et un \xe9.odt").name
            == "Accentu\xe9 avec un \xea et un \xe9.odt"
        )

    def test_watchdog_encoding(self):
        local = self.local_1
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync()

        # Create files with Unicode combining accents, Unicode latin characters
        # and no special characters
        local.make_file("/", "Accentue\u0301.odt", content=b"Content")
        local.make_folder("/", "P\xf4le applicatif")
        local.make_folder("/", "Sub folder")
        local.make_file(
            "/Sub folder", "e\u0302tre ou ne pas \xeatre.odt", content=b"Content"
        )
        local.make_file("/", "No special character.odt", content=b"Content")
        self.wait_sync()
        assert remote.exists("/Accentue\u0301.odt")
        assert remote.exists("/P\xf4le applicatif")
        assert remote.exists("/Sub folder")
        assert remote.exists("/Sub folder/e\u0302tre ou ne pas \xeatre.odt")
        assert remote.exists("/No special character.odt")

        # Check rename using normalized names as previous watchdog handling has
        # normalized them on the file system
        local.rename(
            "/Accentu\xe9.odt", "Accentue\u0301 avec un e\u0302 et un \xe9.odt"
        )
        local.rename("/P\xf4le applicatif", "P\xf4le applique\u0301")
        local.rename(
            "/Sub folder/\xeatre ou ne pas \xeatre.odt", "avoir et e\u0302tre.odt"
        )
        self.wait_sync()
        assert (
            remote.get_info("/Accentue\u0301 avec un e\u0302 et un \xe9.odt").name
            == "Accentu\xe9 avec un \xea et un \xe9.odt"
        )
        assert remote.get_info("/P\xf4le applique\u0301").name == "P\xf4le appliqu\xe9"
        info = remote.get_info("/Sub folder/avoir et e\u0302tre.odt")
        assert info.name == "avoir et \xeatre.odt"

        # Check content update
        local.update_content(
            "/Accentu\xe9 avec un \xea et un \xe9.odt", b"Updated content"
        )
        local.update_content("/Sub folder/avoir et \xeatre.odt", b"Updated content")
        self.wait_sync()
        assert (
            remote.get_content("/Accentue\u0301 avec un e\u0302 et un \xe9.odt")
            == b"Updated content"
        )
        content = remote.get_content("/Sub folder/avoir et e\u0302tre.odt")
        assert content == b"Updated content"

        # Check delete
        local.delete_final("/Accentu\xe9 avec un \xea et un \xe9.odt")
        local.delete_final("/Sub folder/avoir et \xeatre.odt")
        self.wait_sync()
        assert not remote.exists("/Accentue\u0301.odt")
        assert not remote.exists("/Accentue\u0301 avec un e\u0302 et un \xe9.odt")
        assert not remote.exists("/Sub folder/avoir et e\u0302tre.odt")
        assert not remote.exists("/Sub folder/e\u0302tre ou ne pas \xeatre.odt")

    def test_watcher_remote_id_setter(self):
        local = self.local_1
        # As some user can rewrite same file for no reason
        # Start engine
        self.engine_1.start()
        # Wait for test workspace synchronization
        self.wait_sync()
        # Create files with Unicode combining accents,
        # Unicode latin characters and no special characters
        file_path = local.abspath("/Test.pdf")
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        # Wait for test workspace synchronization
        self.wait_sync()
        remote_id = local.get_remote_id("/Test.pdf")
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        self.wait_sync()
        assert remote_id == local.get_remote_id("/Test.pdf")

    def test_watcher_remote_id_setter_stopped(self):
        # Some user can rewrite the same file for no reason

        self.engine_1.start()
        self.wait_sync()

        file_path = self.local_1.abspath("/Test.pdf")
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        # Give some time for the local watcher to handle the copy
        sleep(5)

        self.engine_1.stop()
        remote_id = self.local_1.get_remote_id("/Test.pdf")
        copyfile(self.location / "resources" / "files" / "testFile.pdf", file_path)
        self.engine_1.start()
        self.wait_sync()
        assert remote_id == self.local_1.get_remote_id("/Test.pdf")
