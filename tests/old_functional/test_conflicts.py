import shutil
import time

import pytest

from .common import OS_STAT_MTIME_RESOLUTION, SYNC_ROOT_FAC_ID, TwoUsersTest


class TestConflicts(TwoUsersTest):
    def setUp(self):
        self.workspace_id = f"{SYNC_ROOT_FAC_ID}{self.workspace}"
        self.file_id = self.remote_1.make_file(
            self.workspace_id, "test.txt", content=b"Some content"
        ).uid
        self.get_remote_state = self.engine_1.dao.get_normal_state_from_remote
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        assert self.local_1.exists("/test.txt")

    def test_self_conflict(self):
        remote = self.remote_1
        local = self.local_1
        # Update content on both sides by the same user, remote last
        remote.update_content(self.file_id, b"Remote update")
        local.update_content("/test.txt", b"Local update")
        self.wait_sync(wait_for_async=True)

        assert len(local.get_children_info("/")) == 1
        assert local.exists("/test.txt")
        assert local.get_content("/test.txt") == b"Local update"

        remote_children = remote.get_fs_children(self.workspace_id)
        assert len(remote_children) == 1
        assert remote_children[0].uid == self.file_id
        assert remote_children[0].name == "test.txt"
        assert remote.get_content(remote_children[0].uid) == b"Remote update"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

        # Update content on both sides by the same user, local last
        remote.update_content(self.file_id, b"Remote update 2")
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content("/test.txt", b"Local update 2")
        self.wait_sync(wait_for_async=True)

        assert len(local.get_children_info("/")) == 1
        assert local.exists("/test.txt")
        assert local.get_content("/test.txt") == b"Local update 2"

        remote_children = remote.get_fs_children(self.workspace_id)
        assert len(remote_children) == 1
        assert remote_children[0].uid == self.file_id
        assert remote_children[0].name == "test.txt"
        assert remote.get_content(remote_children[0].uid) == b"Remote update 2"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

    def test_conflict_renamed_modified(self):
        local = self.local_1
        remote = self.remote_2

        # Update content on both sides by different users, remote last
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Race condition is still possible
        remote.update_content(self.file_id, b"Remote update")
        remote.rename(self.file_id, "plop.txt")
        local.update_content("/test.txt", b"Local update")
        self.wait_sync(wait_for_async=True)

        assert remote.get_content(self.file_id) == b"Remote update"
        assert local.get_content("/test.txt") == b"Local update"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

    def test_resolve_local_renamed_modified(self):
        remote = self.remote_2

        self.test_conflict_renamed_modified()
        # Resolve to local file
        pair = self.get_remote_state(self.file_id)
        assert pair
        self.engine_1.resolve_with_local(pair.id)
        self.wait_sync(wait_for_async=True)

        remote_children = remote.get_fs_children(self.workspace_id)
        assert len(remote_children) == 1
        assert remote_children[0].uid == self.file_id
        assert remote_children[0].name == "test.txt"
        assert remote.get_content(remote_children[0].uid) == b"Local update"

    def test_real_conflict(self):
        local = self.local_1
        remote = self.remote_2

        # Update content on both sides by different users, remote last
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Race condition is still possible
        remote.update_content(self.file_id, b"Remote update")
        local.update_content("/test.txt", b"Local update")
        self.wait_sync(wait_for_async=True)

        assert remote.get_content(self.file_id) == b"Remote update"
        assert local.get_content("/test.txt") == b"Local update"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

        # Update content on both sides by different users, local last
        remote.update_content(self.file_id, b"Remote update 2")
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content("/test.txt", b"Local update 2")
        self.wait_sync(wait_for_async=True)

        assert remote.get_content(self.file_id) == b"Remote update 2"
        assert local.get_content("/test.txt") == b"Local update 2"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

    def test_resolve_local(self):
        self.test_real_conflict()
        # Resolve to local file
        pair = self.get_remote_state(self.file_id)
        assert pair
        self.engine_1.resolve_with_local(pair.id)
        self.wait_sync(wait_for_async=True)
        assert self.remote_2.get_content(self.file_id) == b"Local update 2"

    def test_resolve_local_folder(self):
        local = self.local_1
        remote = self.remote_1

        self.engine_1.suspend()
        folder = remote.make_folder(self.workspace_id, "ABC").uid
        self.engine_1.resume()
        self.wait_sync(wait_for_async=True)

        self.engine_1.suspend()
        local.rename("/ABC", "ABC_123")
        remote.rename(folder, "ABC_234")
        self.engine_1.resume()
        self.wait_sync(wait_for_async=True)

        pair = self.get_remote_state(folder)
        assert pair.pair_state == "conflicted"

        self.engine_1.resolve_with_local(pair.id)
        self.wait_sync(wait_for_async=True)
        pair = self.get_remote_state(folder)
        assert pair.pair_state == "synchronized"

        children = local.get_children_info("/")
        assert len(children) == 2
        assert not children[1].folderish
        assert children[0].folderish
        assert children[0].name == "ABC_123"

        children = remote.get_fs_children(self.workspace_id)
        assert len(children) == 2
        assert not children[0].folderish
        assert children[1].folderish
        assert children[1].name == "ABC_123"

    def test_resolve_remote(self):
        self.test_real_conflict()
        # Resolve to local file
        pair = self.get_remote_state(self.file_id)
        assert pair
        self.engine_1.resolve_with_remote(pair.id)
        self.wait_sync(wait_for_async=True)
        assert self.local_1.get_content("/test.txt") == b"Remote update 2"

    def test_conflict_on_lock(self):
        doc_uid = self.file_id.split("#")[-1]
        local = self.local_1
        remote = self.remote_2
        self.remote_document_client_2.lock(doc_uid)
        local.update_content("/test.txt", b"Local update")
        self.wait_sync(wait_for_async=True)
        assert local.get_content("/test.txt") == b"Local update"
        assert remote.get_content(self.file_id) == b"Some content"
        remote.update_content(self.file_id, b"Remote update")
        self.wait_sync(wait_for_async=True)
        assert local.get_content("/test.txt") == b"Local update"
        assert remote.get_content(self.file_id) == b"Remote update"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"
        self.remote_document_client_2.unlock(doc_uid)
        self.wait_sync(wait_for_async=True)
        assert local.get_content("/test.txt") == b"Local update"
        assert remote.get_content(self.file_id) == b"Remote update"
        assert self.get_remote_state(self.file_id).pair_state == "conflicted"

    @pytest.mark.randombug(
        "NXDRIVE-776: Random bug but we cannot use "
        "pytest.mark.random because this test would "
        "take ~30 minutes to complete.",
        mode="BYPASS",
    )
    def test_XLS_conflict_on_locked_document(self):
        self._XLS_local_update_on_locked_document(locked_from_start=False)

    @pytest.mark.randombug(
        "NXDRIVE-776: Random bug but we cannot use "
        "pytest.mark.random because this test would "
        "take ~30 minutes to complete.",
        mode="BYPASS",
    )
    def test_XLS_conflict_on_locked_document_from_start(self):
        self._XLS_local_update_on_locked_document()

    def _XLS_local_update_on_locked_document(self, locked_from_start=True):
        remote = self.remote_2
        local = self.local_1

        # user2: create remote XLS file
        fs_item_id = remote.make_file(
            self.workspace_id,
            "Excel 97 file.xls",
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00",
        ).uid
        doc_uid = fs_item_id.split("#")[-1]
        self.wait_sync(wait_for_async=True)
        assert local.exists("/Excel 97 file.xls")

        if locked_from_start:
            # user2: lock document before user1 opening it
            self.remote_document_client_2.lock(doc_uid)
            self.wait_sync(wait_for_async=True)
            local.unset_readonly("/Excel 97 file.xls")

        # user1: simulate opening XLS file with MS Office ~= update its content
        local.update_content(
            "/Excel 97 file.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01"
        )
        self.wait_sync(wait_for_async=locked_from_start)
        pair_state = self.get_remote_state(fs_item_id)
        assert pair_state
        if locked_from_start:
            # remote content hasn't changed, pair state is conflicted
            # and remote_can_update flag is False
            assert (
                remote.get_content(fs_item_id)
                == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00"
            )
            assert pair_state.pair_state == "unsynchronized"
            assert not pair_state.remote_can_update
        else:
            # remote content has changed, pair state is synchronized
            # and remote_can_update flag is True
            assert (
                remote.get_content(fs_item_id)
                == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01"
            )
            assert pair_state.pair_state == "synchronized"
            assert pair_state.remote_can_update

        if not locked_from_start:
            # user2: lock document after user1 opening it
            self.remote_document_client_2.lock(doc_uid)
            self.wait_sync(wait_for_async=True)

        # user1: simulate updating XLS file with MS Office
        # 1. Create empty file 787D3000
        # 2. Update 787D3000
        # 3. Update Excel 97 file.xls
        # 4. Update 787D3000
        # 5. Move Excel 97 file.xls to 1743B25F.tmp
        # 6. Move 787D3000 to Excel 97 file.xls
        # 7. Update Excel 97 file.xls
        # 8. Update 1743B25F.tmp
        # 9. Update Excel 97 file.xls
        # 10. Delete 1743B25F.tmp
        local.make_file("/", "787D3000")
        local.update_content("/787D3000", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00")
        local.unset_readonly("/Excel 97 file.xls")
        local.update_content(
            "/Excel 97 file.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02"
        )
        local.update_content(
            "/787D3000", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03"
        )
        shutil.move(local.abspath("/Excel 97 file.xls"), local.abspath("/1743B25F.tmp"))
        shutil.move(local.abspath("/787D3000"), local.abspath("/Excel 97 file.xls"))
        local.update_content(
            "/Excel 97 file.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03\x04"
        )
        local.update_content(
            "/1743B25F.tmp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00"
        )
        local.update_content(
            "/Excel 97 file.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03"
        )
        local.delete_final("/1743B25F.tmp")
        self.wait_sync(wait_for_async=not locked_from_start)
        assert len(local.get_children_info("/")) == 2
        assert (
            local.get_content("/Excel 97 file.xls")
            == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03"
        )
        # remote content hasn't changed, pair state is conflicted
        # and remote_can_update flag is False
        if locked_from_start:
            assert (
                remote.get_content(fs_item_id)
                == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00"
            )
        else:
            assert (
                remote.get_content(fs_item_id)
                == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01"
            )
        pair_state = self.get_remote_state(fs_item_id)
        assert pair_state
        assert pair_state.pair_state == "unsynchronized"
        assert not pair_state.remote_can_update

        # user2: remote update, conflict is detected once again
        # and remote_can_update flag is still False
        remote.update_content(
            fs_item_id,
            b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02",
            "New Excel 97 file.xls",
        )
        self.wait_sync(wait_for_async=True)

        assert len(local.get_children_info("/")) == 2
        assert local.exists("/Excel 97 file.xls")
        assert (
            local.get_content("/Excel 97 file.xls")
            == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03"
        )

        assert len(remote.get_fs_children(self.workspace_id)) == 2
        assert remote.get_fs_info(fs_item_id).name == "New Excel 97 file.xls"
        assert (
            remote.get_content(fs_item_id)
            == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02"
        )

        pair_state = self.get_remote_state(fs_item_id)
        assert pair_state
        assert pair_state.pair_state == "conflicted"
        assert not pair_state.remote_can_update

        # user2: unlock document, conflict is detected once again
        # and remote_can_update flag is now True
        self.remote_document_client_2.unlock(doc_uid)
        self.wait_sync(wait_for_async=True)
        pair_state = self.get_remote_state(fs_item_id)
        assert pair_state
        assert pair_state.pair_state == "conflicted"
        assert pair_state.remote_can_update
