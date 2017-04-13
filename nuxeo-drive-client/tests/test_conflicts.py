import time
import shutil

from tests.common import OS_STAT_MTIME_RESOLUTION
from tests.common_unit_test import UnitTestCase
from tests.common_unit_test import RandomBug
# from nxdrive.osi import AbstractOSIntegration
from unittest import skip


class TestConflicts(UnitTestCase):

    def setUp(self):
        super(TestConflicts, self).setUp()
        self.workspace_id = ('defaultSyncRootFolderItemFactory#default#' + self.workspace)
        self.file_id = self.remote_file_system_client_1.make_file(self.workspace_id, 'test.txt', 'Some content').uid
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_client_1.exists('/test.txt'))

    def test_self_conflict(self):
        remote = self.remote_file_system_client_1
        local = self.local_client_1
        # Update content on both sides by the same user, remote last
        remote.update_content(self.file_id, 'Remote update')
        local.update_content('/test.txt', 'Local update')
        self.wait_sync(wait_for_async=True)

        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEqual(local.get_content('/test.txt'), 'Local update')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEqual(len(remote_children), 1)
        self.assertEqual(remote_children[0].uid, self.file_id)
        self.assertEqual(remote_children[0].name, 'test.txt')
        self.assertEqual(remote.get_content(remote_children[0].uid), 'Remote update')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

        # Update content on both sides by the same user, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self.wait_sync(wait_for_async=True)

        self.assertEqual(len(local.get_children_info('/')), 1)
        self.assertTrue(local.exists('/test.txt'))
        self.assertEqual(local.get_content('/test.txt'), 'Local update 2')

        remote_children = remote.get_children_info(self.workspace_id)
        self.assertEqual(len(remote_children), 1)
        self.assertEqual(remote_children[0].uid, self.file_id)
        self.assertEqual(remote_children[0].name, 'test.txt')
        self.assertEqual(remote.get_content(remote_children[0].uid), 'Remote update 2')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

    @RandomBug('NXDRIVE-771', target='linux', mode='BYPASS')
    def test_real_conflict(self):
        local = self.local_client_1
        remote = self.remote_file_system_client_2

        # Update content on both sides by different users, remote last
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        # Race condition is still possible
        remote.update_content(self.file_id, 'Remote update')
        local.update_content('/test.txt', 'Local update')
        self.wait_sync(wait_for_async=True)

        self.assertEqual(remote.get_content(self.file_id), 'Remote update')
        self.assertEqual(local.get_content('/test.txt'), 'Local update')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

        # Update content on both sides by different users, local last
        remote.update_content(self.file_id, 'Remote update 2')
        time.sleep(OS_STAT_MTIME_RESOLUTION)
        local.update_content('/test.txt', 'Local update 2')
        self.wait_sync(wait_for_async=True)

        self.assertEqual(remote.get_content(self.file_id), 'Remote update 2')
        self.assertEqual(local.get_content('/test.txt'), 'Local update 2')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

    def test_resolve_local(self):
        self.test_real_conflict()
        # Resolve to local file
        pair = self.engine_1.get_dao().get_normal_state_from_remote(self.file_id)
        self.assertIsNotNone(pair)
        self.engine_1.resolve_with_local(pair.id)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(self.remote_file_system_client_2.get_content(self.file_id), 'Local update 2')

    def test_resolve_remote(self):
        self.test_real_conflict()
        # Resolve to local file
        pair = self.engine_1.get_dao().get_normal_state_from_remote(self.file_id)
        self.assertIsNotNone(pair)
        self.engine_1.resolve_with_remote(pair.id)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(self.local_client_1.get_content('/test.txt'), 'Remote update 2')

    def test_resolve_duplicate(self):
        self.test_real_conflict()
        # Resolve to local file
        pair = self.engine_1.get_dao().get_normal_state_from_remote(self.file_id)
        self.assertIsNotNone(pair)
        self.engine_1.resolve_with_duplicate(pair.id)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(self.local_client_1.get_content('/test.txt'), 'Remote update 2')
        self.assertEqual(self.local_client_1.get_content('/test__1.txt'), 'Local update 2')

    def test_conflict_on_lock(self):
        doc_uid = self.file_id.split("#")[-1]
        local = self.local_client_1
        remote = self.remote_file_system_client_2
        self.remote_document_client_2.lock(doc_uid)
        local.update_content('/test.txt', 'Local update')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(local.get_content('/test.txt'), 'Local update')
        self.assertEqual(remote.get_content(self.file_id), 'Some content')
        remote.update_content(self.file_id, 'Remote update')
        self.wait_sync(wait_for_async=True)
        self.assertEqual(local.get_content('/test.txt'), 'Local update')
        self.assertEqual(remote.get_content(self.file_id), 'Remote update')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")
        self.remote_document_client_2.unlock(doc_uid)
        self.wait_sync(wait_for_async=True)
        self.assertEqual(local.get_content('/test.txt'), 'Local update')
        self.assertEqual(remote.get_content(self.file_id), 'Remote update')
        self.assertEqual(self.engine_1.get_dao().get_normal_state_from_remote(self.file_id).pair_state, "conflicted")

    # @skipIf(not AbstractOSIntegration.is_windows(),
    #        'Windows Office only test')
    @skip(('NXDRIVE-776: Random bug but we cannot use RandomBug because this'
           'test would take ~30 minutes to complete.'))
    def test_XLS_conflict_on_locked_document(self):
        self._XLS_local_update_on_locked_document(locked_from_start=False)

    # @skipIf(not AbstractOSIntegration.is_windows(),
    #        'Windows Office only test')
    @skip(('NXDRIVE-776: Random bug but we cannot use RandomBug because this'
           'test would take ~30 minutes to complete.'))
    def test_XLS_conflict_on_locked_document_from_start(self):
        self._XLS_local_update_on_locked_document()

    def _XLS_local_update_on_locked_document(self, locked_from_start=True):
        remote = self.remote_file_system_client_2
        local = self.local_client_1

        # user2: create remote XLS file
        fs_item_id = remote.make_file(self.workspace_id,
                                      'Excel 97 file.xls',
                                      b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00').uid
        doc_uid = fs_item_id.split("#")[-1]
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists('/Excel 97 file.xls'))

        if locked_from_start:
            # user2: lock document before user1 opening it
            self.remote_document_client_2.lock(doc_uid)
            self.wait_sync(wait_for_async=True)
            local.unset_readonly('/Excel 97 file.xls')

        # user1: simulate opening XLS file with MS Office ~= update its content
        local.update_content('/Excel 97 file.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01')
        self.wait_sync(wait_for_async=locked_from_start)
        pair_state = self.engine_1.get_dao().get_normal_state_from_remote(fs_item_id)
        self.assertIsNotNone(pair_state)
        if locked_from_start:
            # remote content hasn't changed, pair state is conflicted and remote_can_update flag is False
            self.assertEqual(remote.get_content(fs_item_id), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00')
            self.assertEqual(pair_state.pair_state, 'unsynchronized')
            self.assertFalse(pair_state.remote_can_update)
        else:
            # remote content has changed, pair state is synchronized and remote_can_update flag is True
            self.assertEqual(remote.get_content(fs_item_id), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01')
            self.assertEqual(pair_state.pair_state, 'synchronized')
            self.assertTrue(pair_state.remote_can_update)

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
        local.make_file('/', '787D3000')
        local.update_content('/787D3000', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00')
        local.unset_readonly('/Excel 97 file.xls')
        local.update_content('/Excel 97 file.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02')
        local.update_content('/787D3000', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03')
        shutil.move(local.abspath('/Excel 97 file.xls'), local.abspath('/1743B25F.tmp'))
        shutil.move(local.abspath('/787D3000'), local.abspath('/Excel 97 file.xls'))
        local.update_content('/Excel 97 file.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03\x04')
        local.update_content('/1743B25F.tmp', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00')
        local.update_content('/Excel 97 file.xls', b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03')
        local.delete_final('/1743B25F.tmp')
        self.wait_sync(wait_for_async=not locked_from_start)
        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertEqual(local.get_content('/Excel 97 file.xls'), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03')
        # remote content hasn't changed, pair state is conflicted and remote_can_update flag is False
        if locked_from_start:
            self.assertEqual(remote.get_content(fs_item_id), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00')
        else:
            self.assertEqual(remote.get_content(fs_item_id), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x01')
        pair_state = self.engine_1.get_dao().get_normal_state_from_remote(fs_item_id)
        self.assertIsNotNone(pair_state)
        self.assertEqual(pair_state.pair_state, 'unsynchronized')
        self.assertFalse(pair_state.remote_can_update)

        # user2: remote update, conflict is detected once again and remote_can_update flag is still False
        remote.update_content(fs_item_id, b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02', 'New Excel 97 file.xls')
        self.wait_sync(wait_for_async=True)

        self.assertEqual(len(local.get_children_info('/')), 2)
        self.assertTrue(local.exists('/Excel 97 file.xls'))
        self.assertEqual(local.get_content('/Excel 97 file.xls'), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x03')

        self.assertEqual(len(remote.get_children_info(self.workspace_id)), 2)
        self.assertEqual(remote.get_info(fs_item_id).name, 'New Excel 97 file.xls')
        self.assertEqual(remote.get_content(fs_item_id), b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1\x00\x00\x02')

        pair_state = self.engine_1.get_dao().get_normal_state_from_remote(fs_item_id)
        self.assertIsNotNone(pair_state)
        self.assertEqual(pair_state.pair_state, 'conflicted')
        self.assertFalse(pair_state.remote_can_update)

        # user2: unlock document, conflict is detected once again and remote_can_update flag is now True
        self.remote_document_client_2.unlock(doc_uid)
        self.wait_sync(wait_for_async=True)
        pair_state = self.engine_1.get_dao().get_normal_state_from_remote(fs_item_id)
        self.assertIsNotNone(pair_state)
        self.assertEqual(pair_state.pair_state, 'conflicted')
        self.assertTrue(pair_state.remote_can_update)
