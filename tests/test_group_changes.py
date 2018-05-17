# coding: utf-8
from logging import getLogger

from nuxeo.models import Document, Group

from . import DocRemote
from .common_unit_test import UnitTestCase

log = getLogger(__name__)


class TestGroupChanges(UnitTestCase):
    """
    Test that changes on groups are detected by Drive.
    See https://jira.nuxeo.com/browse/NXP-14830.
    """

    def setUp(self):
        remote = self.root_remote

        # Create test workspace
        workspaces_path = '/default-domain/workspaces'
        workspace_name = 'groupChangesTestWorkspace'
        self.workspace_path = workspaces_path + '/' + workspace_name

        self.workspace = remote.documents.create(
            Document(
                name=workspace_name,
                type='Workspace',
                properties={'dc:title': 'Group Changes Test Workspace'}
            ), parent_path=workspaces_path)

        # Create test groups
        group_names = self.get_group_names()
        for group in ('group1', 'group2', 'parentGroup', 'grandParentGroup'):
            if group in group_names:
                remote.groups.delete(group)

        for group in [
            Group(groupname='group1', memberUsers=['driveuser_1']),
            Group(groupname='group2', memberUsers=['driveuser_1']),
            Group(groupname='parentGroup', memberGroups=['group1']),
            Group(groupname='grandParentGroup', memberGroups=['parentGroup'])
        ]:
            remote.groups.create(group)

        group_names = self.get_group_names()
        assert 'group1' in group_names
        assert 'group2' in group_names
        assert 'parentGroup' in group_names
        assert 'grandParentGroup' in group_names

        self.admin_remote = DocRemote(
            self.nuxeo_url, self.admin_user,
            'nxdrive-test-administrator-device',
            self.version, password=self.password,
            base_folder=self.workspace_path)

    def tearDown(self):
        remote = self.root_remote

        # Delete test workspace
        self.workspace.delete()

        # Delete test groups
        remote.groups.delete('grandParentGroup')
        remote.groups.delete('parentGroup')
        remote.groups.delete('group2')
        remote.groups.delete('group1')

        group_names = self.get_group_names()
        assert 'group1' not in group_names
        assert 'group2' not in group_names
        assert 'parentGroup' not in group_names
        assert 'grandParentGroup' not in group_names

    def get_group_names(self):
        return [entry['groupname']
                for entry in self.remote_1.client.request(
                'GET', (self.remote_1.client.api_path
                        + '/groups/search?q=*')).json()['entries']]

    def test_group_changes_on_sync_root(self):
        """
        Test changes on a group that has access to a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Grant ReadWrite permission to group1 on syncRoot')
        self.admin_remote.operations.execute(
            command='Document.SetACE', input_obj='doc:' + sync_root_id,
            user='group1', permission='ReadWrite')

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists('/syncRoot')

        self._test_group_changes('/syncRoot', 'group1')

    def test_group_changes_on_sync_root_child(self):
        """
        Test changes on a group that has access
        to a child of a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Create child folder')
        child_id = self.admin_remote.make_folder('/syncRoot', 'child')

        log.debug('Grant ReadWrite permission to group1 on syncRoot')
        self.admin_remote.operations.execute(
            command='Document.SetACE',
            input_obj='doc:' + sync_root_id,
            user='group1',
            permission='ReadWrite')

        log.debug('Grant ReadWrite permission to group2 on child')
        self.admin_remote.operations.execute(
            command='Document.SetACE',
            input_obj='doc:' + child_id,
            user='group2',
            permission='ReadWrite')

        log.debug('Block inheritance on child')
        self.admin_remote.block_inheritance(child_id, overwrite=False)

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot and child are created locally')
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists('/syncRoot')
        assert self.local_root_client_1.exists('/syncRoot/child')

        self._test_group_changes('/syncRoot/child', 'group2')

    def test_group_changes_on_sync_root_parent(self):
        """
        Test changes on a group that has access
        to the parent of a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create parent folder')
        parent_id = self.admin_remote.make_folder('/', 'parent')

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/parent', 'syncRoot')

        log.debug('Grant ReadWrite permission to group1 on parent')
        self.admin_remote.operations.execute(
            command='Document.SetACE',
            input_obj='doc:' + parent_id,
            user='group1',
            permission='ReadWrite')

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists('/syncRoot')

        self._test_group_changes('/syncRoot', 'group1')

    def test_changes_with_parent_group(self):
        """
        Test changes on the parent group of a group
        that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups('parentGroup')

    def test_changes_with_grand_parent_group(self):
        """
        Test changes on the grandparent group of a group
        that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups('grandParentGroup')

    def _register_sync_root_user1(self, sync_root_id):
        user1_remote = DocRemote(
            self.nuxeo_url,
            self.user_1,
            'nxdrive-test-device-1',
            self.version,
            password=self.password_1,
            base_folder=sync_root_id,
            upload_tmp_dir=self.upload_tmp_dir)
        user1_remote.register_as_root(sync_root_id)

    def _test_group_changes(self, folder_path, group_name, need_parent=False):
        """
        Tests changes on the given group that has access to the given folder:
            - Remove the test user from the group.
            - Add the test user to the group.
            - Delete the group.
            - Create the group including the test user.
        """
        log.debug('Test changes on %s for %s with need_parent=%r',
                  group_name,
                  folder_path,
                  need_parent)
        remote = self.admin_remote
        local = self.local_root_client_1

        log.debug('Remove driveuser_1 from %s', group_name)
        group = remote.groups.get(group_name)
        group.memberUsers = []
        group.save()

        log.debug('Check that %s is deleted locally', folder_path)
        self.wait_sync(wait_for_async=True)
        assert not local.exists(folder_path)

        log.debug('Add driveuser_1 to %s', group_name)
        group.memberUsers = ['driveuser_1']
        group.save()

        log.debug('Check that %s is created locally', folder_path)
        self.wait_sync(wait_for_async=True)
        assert local.exists(folder_path)

        log.debug('Delete %s', group_name)
        remote.groups.delete(group_name)

        log.debug('Check that %s is deleted locally', folder_path)
        self.wait_sync(wait_for_async=True)
        assert not local.exists(folder_path)

        log.debug('Create %s', group_name)
        remote.groups.create(
            Group(groupname=group_name, memberUsers=['driveuser_1']))

        if need_parent:
            log.debug('%s should not be created locally since '
                      'the newly created group has not been added yet '
                      'as a subgroup of parentGroup', folder_path)
            self.wait_sync(wait_for_async=True)
            assert not local.exists(folder_path)

            log.trace('Add %s as a subgroup of parentGroup', group_name)
            group = remote.groups.get('parentGroup')
            group.memberGroups = [group_name]
            group.save()

        log.debug('Check that %s is created locally', folder_path)
        self.wait_sync(wait_for_async=True)
        assert local.exists(folder_path)

    def _test_group_changes_with_ancestor_groups(self, ancestor_group):
        """
        Test changes on a descendant group of the given group
        that has access to a synchronization root.
        """
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        log.debug('Create syncRoot folder')
        sync_root_id = self.admin_remote.make_folder('/', 'syncRoot')

        log.debug('Grant ReadWrite permission to %s on syncRoot',
                  ancestor_group)

        self.admin_remote.operations.execute(
            command='Document.SetACE', input_obj='doc:' + sync_root_id,
            user=ancestor_group, permission='ReadWrite')

        log.debug('Register syncRoot for driveuser_1')
        self._register_sync_root_user1(sync_root_id)

        log.debug('Check that syncRoot is created locally')
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists('/syncRoot')

        self._test_group_changes('/syncRoot', 'group1', need_parent=True)
