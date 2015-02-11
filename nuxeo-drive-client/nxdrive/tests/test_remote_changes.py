from nxdrive.tests.common import IntegrationTestCase


class TestRemoteChanges(IntegrationTestCase):

    def setUp(self):
        super(TestRemoteChanges, self).setUp()
        self.last_sync_date = None
        self.last_event_log_id = None
        self.last_root_definitions = None

    def get_changes(self):
        remote_client = self.remote_file_system_client_1
        summary = remote_client.get_changes(self.last_root_definitions,
                                            log_id=self.last_event_log_id,
                                            last_sync_date=self.last_sync_date)
        self.last_sync_date = summary['syncDate']
        if remote_client.is_event_log_id_available():
            self.last_event_log_id = summary['upperBound']
        self.last_root_definitions = (
            summary['activeSynchronizationRootDefinitions'])
        return summary

    def test_changes_without_active_roots(self):
        remote_client = self.remote_file_system_client_1
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['fileSystemChanges'], [])
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        first_timestamp = summary['syncDate']
        self.assertTrue(first_timestamp > 0)
        if remote_client.is_event_log_id_available():
            first_event_log_id = summary['upperBound']
            self.assertTrue(first_event_log_id > 0)

        self.wait_audit_change_finder_if_needed()
        summary = self.get_changes()

        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['fileSystemChanges'], [])
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        second_time_stamp = summary['syncDate']
        self.assertTrue(second_time_stamp >= first_timestamp)
        if remote_client.is_event_log_id_available():
            second_event_log_id = summary['upperBound']
            self.assertTrue(second_event_log_id >= first_event_log_id)

    def test_changes_root_registrations(self):
        # Lets create some folders in Nuxeo
        remote_client = self.remote_document_client_1
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')
        remote_client.make_folder(folder_2, 'Folder 2.2')

        # Fetch an initial time stamp without any registered roots
        self.wait_audit_change_finder_if_needed()
        self.wait()
        summary = self.get_changes()
        self.assertEquals(summary['hasTooManyChanges'], False)
        self.assertEquals(summary['activeSynchronizationRootDefinitions'], '')
        self.assertEquals(summary['fileSystemChanges'], [])

        # Let's register one of the previously created folders as sync root
        self.setUpDrive_1(root=folder_1)

        self.wait_audit_change_finder_if_needed()
        self.wait()
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
        self.bind_root(self.ndrive_1, folder_2, self.local_nxdrive_folder_1)

        self.wait_audit_change_finder_if_needed()
        self.wait()
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
        self.unbind_root(self.ndrive_1, folder_1, self.local_nxdrive_folder_1)
        self.unbind_root(self.ndrive_1, folder_2, self.local_nxdrive_folder_1)

        self.wait_audit_change_finder_if_needed()
        self.wait()
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
