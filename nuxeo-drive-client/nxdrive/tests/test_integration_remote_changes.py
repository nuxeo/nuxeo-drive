import time
from nxdrive.tests.common import IntegrationTestCase


class TestIntegrationRemoteChanges(IntegrationTestCase):

    def setUp(self):
        super(TestIntegrationRemoteChanges, self).setUp()
        self.last_sync_date = None
        self.last_root_definitions = None

    def get_changes(self):
        remote_client = self.remote_file_system_client_1
        summary = remote_client.get_changes(
            last_sync_date=self.last_sync_date,
            last_root_definitions=self.last_root_definitions)
        self.last_sync_date = summary['syncDate']
        self.last_root_definitions = summary['activeSynchronizationRootDefinitions']
        return summary

    def test_changes_without_active_roots(self):
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['fileSystemChanges'], [])
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        first_timestamp = summary['syncDate']
        self.assertTrue(first_timestamp > 0)

        time.sleep(1.0)
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['fileSystemChanges'], [])
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        second_time_stamp = summary['syncDate']
        self.assertTrue(second_time_stamp > first_timestamp)

    def test_changes_root_registrations(self):
        # Lets create some folders in Nuxeo
        remote_client = self.remote_document_client_1
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')
        remote_client.make_folder(folder_2, 'Folder 2.2')
        time.sleep(1.0)

        # Fetch an initial time stamp without any registered roots
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        self.assertEquals(summary['fileSystemChanges'], [])

        # Let's register one of the previously created folders as sync root
        ctl = self.controller_1
        ctl.bind_server(self.local_nxdrive_folder_1, self.nuxeo_url,
                        self.user_1, self.password_1)
        ctl.bind_root(self.local_nxdrive_folder_1, folder_1)

        # Would it be this possible to change the service to avoid having to put
        # this sleep here?
        time.sleep(1.0)
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEquals(len(root_defs), 1)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertEquals(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEquals(change['fileSystemItemName'], u"Folder 1")
        self.assertEquals(change['repositoryId'], "default")
        self.assertEquals(change['docUuid'], folder_1)

        # Let's register the second root
        ctl.bind_root(self.local_nxdrive_folder_1, folder_2)
        time.sleep(1.0)
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEquals(len(root_defs), 2)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertTrue(root_defs[1].startswith('default:'))
        self.assertEquals(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEquals(change['fileSystemItemName'], u"Folder 2")
        self.assertEquals(change['repositoryId'], "default")
        self.assertEquals(change['docUuid'], folder_2)

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEquals(len(root_defs), 2)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertTrue(root_defs[1].startswith('default:'))
        self.assertEquals(len(summary['fileSystemChanges']), 0)

        # Let's unregister both roots at the same time
        ctl.unbind_root(self.local_nxdrive_folder_1, folder_1)
        ctl.unbind_root(self.local_nxdrive_folder_1, folder_2)
        time.sleep(1.0)
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        raw_root_defs = summary['activeSynchronizationRootDefinitions']
        self.assertEquals(raw_root_defs, '')
        self.assertEquals(len(summary['fileSystemChanges']), 2)
        change = summary['fileSystemChanges'][0]
        self.assertEquals(change['eventId'], u"deleted")
        self.assertEquals(change['fileSystemItemName'], u"Folder 2")
        self.assertEquals(change['repositoryId'], "default")
        self.assertEquals(change['docUuid'], folder_2)
        change = summary['fileSystemChanges'][1]
        self.assertEquals(change['eventId'], u"deleted")
        self.assertEquals(change['fileSystemItemName'], u"Folder 1")
        self.assertEquals(change['repositoryId'], "default")
        self.assertEquals(change['docUuid'], folder_1)

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        raw_root_defs = summary['activeSynchronizationRootDefinitions']
        self.assertEquals(raw_root_defs, '')
        self.assertEquals(len(summary['fileSystemChanges']), 0)
