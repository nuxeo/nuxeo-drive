from logging import getLogger

from nuxeo.exceptions import HTTPError
from nuxeo.models import Document, Group

from .. import env
from .common import OneUserTest, root_remote, salt

log = getLogger(__name__)


class TestGroupChanges(OneUserTest):
    """
    Test that changes on groups are detected by Drive.
    See https://jira.nuxeo.com/browse/NXP-14830.
    """

    def setUp(self):
        self.group1 = salt("group1")
        self.group2 = salt("group2")
        self.parent_group = salt("parentGroup")
        self.grand_parent_group = salt("grandParentGroup")
        self.new_groups = (
            Group(groupname=self.group1, memberUsers=[self.user_1]),
            Group(groupname=self.group2, memberUsers=[self.user_1]),
            Group(groupname=self.parent_group, memberGroups=[self.group1]),
            Group(groupname=self.grand_parent_group, memberGroups=[self.parent_group]),
        )
        for group in self.new_groups:
            self.root_remote.groups.create(group)

        # Create test workspace
        workspace_name = salt("groupChangesTestWorkspace")
        self.workspace_group = self.root_remote.documents.create(
            Document(
                name=workspace_name,
                type="Workspace",
                properties={"dc:title": workspace_name},
            ),
            parent_path=env.WS_DIR,
        )
        self.workspace_path = self.workspace_group.path

        self.admin_remote = root_remote(base_folder=self.workspace_path)

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

    def tearDown(self):
        self.workspace_group.delete()
        for group in reversed(self.new_groups):
            try:
                self.root_remote.groups.delete(group.groupname)
            except HTTPError as exc:
                if exc.status == 404:
                    continue
                raise

    def set_ace(self, user, doc):
        log.info(f"Grant ReadWrite permission to  {user} on {doc}")
        self.admin_remote.execute(
            command="Document.SetACE",
            input_obj=f"doc:{doc}",
            user=user,
            permission="ReadWrite",
        )

    def test_group_changes_on_sync_root(self):
        """
        Test changes on a group that has access to a synchronization root.
        """
        log.info("Create syncRoot folder")
        sync_root_id = self.admin_remote.make_folder("/", "syncRoot")

        self.set_ace(self.group1, sync_root_id)

        log.info("Register syncRoot for driveuser_1")
        self.remote_1.register_as_root(sync_root_id)

        log.info("Check that syncRoot is created locally")
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists("/syncRoot")

        self._test_group_changes("/syncRoot", self.group1)

    def test_group_changes_on_sync_root_child(self):
        """
        Test changes on a group that has access
        to a child of a synchronization root.
        """
        log.info("Create syncRoot folder")
        sync_root_id = self.admin_remote.make_folder("/", "syncRoot")

        log.info("Create child folder")
        child_id = self.admin_remote.make_folder("/syncRoot", "child")

        self.set_ace(self.group1, sync_root_id)
        self.set_ace(self.group2, child_id)

        log.info("Block inheritance on child")
        self.admin_remote.block_inheritance(child_id, overwrite=False)

        log.info("Register syncRoot for driveuser_1")
        self.remote_1.register_as_root(sync_root_id)

        log.info("Check that syncRoot and child are created locally")
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists("/syncRoot")
        assert self.local_root_client_1.exists("/syncRoot/child")

        self._test_group_changes("/syncRoot/child", self.group2)

    def test_group_changes_on_sync_root_parent(self):
        """
        Test changes on a group that has access
        to the parent of a synchronization root.
        """
        log.info("Create parent folder")
        parent_id = self.admin_remote.make_folder("/", "parent")

        log.info("Create syncRoot folder")
        sync_root_id = self.admin_remote.make_folder("/parent", "syncRoot")

        self.set_ace(self.group1, parent_id)

        log.info("Register syncRoot for driveuser_1")
        self.remote_1.register_as_root(sync_root_id)

        log.info("Check that syncRoot is created locally")
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists("/syncRoot")

        self._test_group_changes("/syncRoot", self.group1)

    def test_changes_with_parent_group(self):
        """
        Test changes on the parent group of a group
        that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups(self.parent_group)

    def test_changes_with_grand_parent_group(self):
        """
        Test changes on the grandparent group of a group
        that has access to a synchronization root.
        """
        self._test_group_changes_with_ancestor_groups(self.grand_parent_group)

    def _test_group_changes(self, folder_path, group_name, need_parent=False):
        """
        Tests changes on the given group that has access to the given folder:
            - Remove the test user from the group.
            - Add the test user to the group.
            - Delete the group.
            - Create the group including the test user.
        """
        log.info(
            "Test changes on %s for %s with need_parent=%r",
            group_name,
            folder_path,
            need_parent,
        )
        remote = self.admin_remote
        local = self.local_root_client_1

        log.info("Remove driveuser_1 from %s", group_name)
        group = remote.groups.get(group_name)
        group.memberUsers = []
        group.save()

        log.info("Check that %s is deleted locally", folder_path)
        self.wait_sync(wait_for_async=True)
        assert not local.exists(folder_path)

        log.info("Add driveuser_1 to %s", group_name)
        group.memberUsers = [self.user_1]
        group.save()

        log.info("Check that %s is created locally", folder_path)
        self.wait_sync(wait_for_async=True)
        assert local.exists(folder_path)

        log.info("Delete %s", group_name)
        remote.groups.delete(group_name)

        log.info("Check that %s is deleted locally", folder_path)
        self.wait_sync(wait_for_async=True)
        assert not local.exists(folder_path)

        log.info("Create %s", group_name)
        remote.groups.create(Group(groupname=group_name, memberUsers=[self.user_1]))

        if need_parent:
            log.info(
                "%s should not be created locally since "
                "the newly created group has not been added yet "
                "as a subgroup of parentGroup",
                folder_path,
            )
            self.wait_sync(wait_for_async=True)
            assert not local.exists(folder_path)

            log.debug("Add %s as a subgroup of parentGroup", group_name)
            group = remote.groups.get(self.parent_group)
            group.memberGroups = [group_name]
            group.save()

        log.info("Check that %s is created locally", folder_path)
        self.wait_sync(wait_for_async=True)
        assert local.exists(folder_path)

    def _test_group_changes_with_ancestor_groups(self, ancestor_group):
        """
        Test changes on a descendant group of the given group
        that has access to a synchronization root.
        """
        log.info("Create syncRoot folder")
        sync_root_id = self.admin_remote.make_folder("/", "syncRoot")

        self.set_ace(ancestor_group, sync_root_id)

        log.info("Register syncRoot for driveuser_1")
        self.remote_1.register_as_root(sync_root_id)

        log.info("Check that syncRoot is created locally")
        self.wait_sync(wait_for_async=True)
        assert self.local_root_client_1.exists("/syncRoot")

        self._test_group_changes("/syncRoot", self.group1, need_parent=True)
