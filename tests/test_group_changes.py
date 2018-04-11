# coding: utf-8
from logging import getLogger

from .common import RemoteDocumentClientForTests
from .common_unit_test import UnitTestCase

log = getLogger(__name__)


class TestGroupChanges(UnitTestCase):
    """
    Test that changes on groups are detected by Drive.
    See https://jira.nuxeo.com/browse/NXP-14830.
    """

    def setUp(self):
        remote = self.remote_restapi_client_admin

        # Create test groups
        group_names = remote.get_group_names()
        self.assertTrue('group1' not in group_names)
        self.assertTrue('group2' not in group_names)
        self.assertTrue('parentGroup' not in group_names)
        self.assertTrue('grandParentGroup' not in group_names)

        remote.create_group('group1', member_users=['driveuser_1'])
        remote.create_group('group2', member_users=['driveuser_1'])
        remote.create_group('parentGroup', member_groups=['group1'])
        remote.create_group('grandParentGroup', member_groups=['parentGroup'])

        group_names = remote.get_group_names()
        self.assertTrue('group1' in group_names)
        self.assertTrue('group2' in group_names)
        self.assertTrue('parentGroup' in group_names)
        self.assertTrue('grandParentGroup' in group_names)

        # Create test workspace
        workspaces_path = '/default-domain/workspaces'
        workspace_name = 'groupChangesTestWorkspace'
        self.workspace_path = workspaces_path + '/' + workspace_name
        workspace = {'entity-type': 'document',
                     'name': workspace_name,
                     'type': 'Workspace',
                     'properties': {'dc:title': 'Group Changes Test Workspace'}
                     }
        remote.execute('path' + workspaces_path, method='POST', body=workspace)

        self.admin_remote = RemoteDocumentClientForTests(
            self.nuxeo_url, self.admin_user, 'nxdrive-test-administrator-device',
            self.version, password=self.password, base_folder=self.workspace_path)

    def tearDown(self):
        remote = self.remote_restapi_client_admin

        # Delete test workspace
        remote.execute('path' + self.workspace_path, method='DELETE')

        # Delete test groups
        remote.delete_group('grandParentGroup')
        remote.delete_group('parentGroup')
        remote.delete_group('group2')
        remote.delete_group('group1')

        group_names = remote.get_group_names()
        self.assertTrue('group1' not in group_names)
        self.assertTrue('group2' not in group_names)
        self.assertTrue('parentGroup' not in group_names)
        self.assertTrue('grandParentGroup' not in group_names)

    def test_group_changes_on_sync_root(self):
        """
        Test changes on a group that has access to a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Grant ReadWrite permission to group1 on syncRoot')
        self.admin_remote.execute("Document.SetACE",
                                  op_input='doc:' + sync_root_id,
                                  user='group1',
                                  permission="ReadWrite")

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_root_client_1.exists('/syncRoot'))

        self._test_group_changes('/syncRoot', 'group1')

    def test_group_changes_on_sync_root_child(self):
        """
        Test changes on a group that has access to a child of a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Create child folder')
        child_id = self.admin_remote.make_folder('/syncRoot', 'child')

        log.debug('Grant ReadWrite permission to group1 on syncRoot')
        self.admin_remote.execute("Document.SetACE",
                                  op_input='doc:' + sync_root_id,
                                  user='group1',
                                  permission="ReadWrite")

        log.debug("Grant ReadWrite permission to group2 on child")
        self.admin_remote.execute("Document.SetACE",
                                  op_input='doc:' + child_id,
                                  user='group2',
                                  permission="ReadWrite")
        log.debug('Block inheritance on child')
        self.admin_remote.block_inheritance(child_id, overwrite=False)

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot and child are created locally')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_root_client_1.exists('/syncRoot'))
        self.assertTrue(self.local_root_client_1.exists('/syncRoot/child'))

        self._test_group_changes('/syncRoot/child', 'group2')

    def test_group_changes_on_sync_root_parent(self):
        """
        Test changes on a group that has access to the parent of a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create parent folder')
        parent_id = self.admin_remote.make_folder('/', 'parent')

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/parent', 'syncRoot')

        log.debug('Grant ReadWrite permission to group1 on parent')
        self.admin_remote.execute("Document.SetACE",
                                  op_input='doc:' + parent_id,
                                  user='group1',
                                  permission="ReadWrite")

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_root_client_1.exists('/syncRoot'))

        self._test_group_changes('/syncRoot', 'group1')

    def test_changes_with_parent_group(self):
        """
        Test changes on the parent group of a group that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups('parentGroup')

    def test_changes_with_grand_parent_group(self):
        """
        Test changes on the grandparent group of a group that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups('grandParentGroup')

    def _register_sync_root_user1(self, sync_root_id):
        user1_remote = RemoteDocumentClientForTests(
            self.nuxeo_url, self.user_1, 'nxdrive-test-device-1', self.version,
            password=self.password_1, base_folder=sync_root_id,
            upload_tmp_dir=self.upload_tmp_dir)
        user1_remote.register_as_root(sync_root_id)

    def _test_group_changes(self, folder_path, group_name, needsParentGroup=False):
        """
        Tests changes on the given group that has access to the given folder:
            - Remove the test user from the group.
            - Add the test user to the group.
            - Delete the group.
            - Create the group including the test user.
        """
        log.debug('Test changes on %s for %s with needsParentGroup=%r',
                  group_name,
                  folder_path,
                  needsParentGroup)
        remote = self.remote_restapi_client_admin
        local = self.local_root_client_1

        log.debug('Remove driveuser_1 from %s', group_name)
        remote.update_group(group_name, member_users=[])

        log.debug('Check that %s is deleted locally', folder_path)
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists(folder_path))

        log.debug('Add driveuser_1 to %s', group_name)
        remote.update_group(group_name, member_users=['driveuser_1'])

        log.debug('Check that %s is created locally', folder_path)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists(folder_path))

        log.debug('Delete %s', group_name)
        remote.delete_group(group_name)

        log.debug('Check that %s is deleted locally', folder_path)
        self.wait_sync(wait_for_async=True)
        self.assertFalse(local.exists(folder_path))

        log.debug('Create %s', group_name)
        remote.create_group(group_name, member_users=['driveuser_1'])

        if needsParentGroup:
            log.debug('%s should not be created locally since the newly created group has not been added yet'
                      ' as a subgroup of parentGroup', folder_path)
            self.wait_sync(wait_for_async=True)
            self.assertFalse(local.exists(folder_path))

            log.trace("Add %s as a subgroup of parentGroup", group_name)
            remote.update_group('parentGroup', member_groups=[group_name])

        log.debug('Check that %s is created locally', folder_path)
        self.wait_sync(wait_for_async=True)
        self.assertTrue(local.exists(folder_path))

    def _test_group_changes_with_ancestor_groups(self, ancestor_group):
        """
        Test changes on a descendant group of the given group that has access to a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Grant ReadWrite permission to %s on syncRoot', ancestor_group)
        self.admin_remote.execute("Document.SetACE",
                                  op_input='doc:' + sync_root_id,
                                  user=ancestor_group,
                                  permission="ReadWrite")

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        self.assertTrue(self.local_root_client_1.exists('/syncRoot'))

        self._test_group_changes('/syncRoot', 'group1', needsParentGroup=True)
