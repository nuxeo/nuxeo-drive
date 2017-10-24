# coding: utf-8
import sys
import unittest

from tests.common import IntegrationTestCase


class TestRemoteChanges(IntegrationTestCase):

    def setUp(self):
        super(TestRemoteChanges, self).setUp()
        self.last_sync_date = None
        self.last_event_log_id = None
        self.last_root_definitions = None
        # Initialize last event log id (lower bound)
        self.wait()
        self.get_changes()

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
        self.assertEqual(summary['hasTooManyChanges'], False)
        self.assertEqual(summary['fileSystemChanges'], [])
        self.assertEqual(summary['activeSynchronizationRootDefinitions'], '')
        first_timestamp = summary['syncDate']
        self.assertTrue(first_timestamp > 0)
        if remote_client.is_event_log_id_available():
            first_event_log_id = summary['upperBound']
            self.assertTrue(first_event_log_id > 0)

        self.wait()
        summary = self.get_changes()

        self.assertEqual(summary['hasTooManyChanges'], False)
        self.assertEqual(summary['fileSystemChanges'], [])
        self.assertEqual(summary['activeSynchronizationRootDefinitions'], '')
        second_time_stamp = summary['syncDate']
        self.assertTrue(second_time_stamp >= first_timestamp)
        if remote_client.is_event_log_id_available():
            second_event_log_id = summary['upperBound']
            self.assertTrue(second_event_log_id >= first_event_log_id)

    @unittest.skipIf(sys.platform == 'win32', 'NXDRIVE-739: Need refactor')
    def test_changes_root_registrations(self):
        # Lets create some folders in Nuxeo
        remote_client = self.remote_document_client_1
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        folder_2 = remote_client.make_folder(self.workspace, 'Folder 2')
        remote_client.make_folder(folder_2, 'Folder 2.2')

        # Check no changes without any registered roots
        self.wait()
        summary = self.get_changes()
        self.assertEqual(summary['hasTooManyChanges'], False)
        self.assertEqual(summary['activeSynchronizationRootDefinitions'], '')
        self.assertEqual(summary['fileSystemChanges'], [])

        # Let's register one of the previously created folders as sync root
        self.setUpDrive_1(root=folder_1)

        self.wait()
        summary = self.get_changes()

        self.assertEqual(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEqual(len(root_defs), 1)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertEqual(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['fileSystemItemName'], u"Folder 1")
        self.assertEqual(change['repositoryId'], "default")
        self.assertEqual(change['docUuid'], folder_1)

        # Let's register the second root
        self.bind_root(self.ndrive_1_options, folder_2, self.local_nxdrive_folder_1)

        self.wait()
        summary = self.get_changes()

        self.assertEqual(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEqual(len(root_defs), 2)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertTrue(root_defs[1].startswith('default:'))
        self.assertEqual(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['fileSystemItemName'], u"Folder 2")
        self.assertEqual(change['repositoryId'], "default")
        self.assertEqual(change['docUuid'], folder_2)

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        self.assertEqual(summary['hasTooManyChanges'], False)
        root_defs = summary['activeSynchronizationRootDefinitions'].split(',')
        self.assertEqual(len(root_defs), 2)
        self.assertTrue(root_defs[0].startswith('default:'))
        self.assertTrue(root_defs[1].startswith('default:'))
        self.assertEqual(len(summary['fileSystemChanges']), 0)

        # Let's unregister both roots at the same time
        self.unbind_root(self.ndrive_1_options, folder_1, self.local_nxdrive_folder_1)
        self.unbind_root(self.ndrive_1_options, folder_2, self.local_nxdrive_folder_1)

        self.wait()
        summary = self.get_changes()

        self.assertEqual(summary['hasTooManyChanges'], False)
        raw_root_defs = summary['activeSynchronizationRootDefinitions']
        self.assertEqual(raw_root_defs, '')
        self.assertEqual(len(summary['fileSystemChanges']), 2)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['eventId'], u"deleted")
        self.assertIsNone(change['fileSystemItemName'])
        self.assertEqual(change['repositoryId'], "default")
        self.assertEqual(change['docUuid'], folder_2)
        change = summary['fileSystemChanges'][1]
        self.assertEqual(change['eventId'], u"deleted")
        self.assertIsNone(change['fileSystemItemName'])
        self.assertEqual(change['repositoryId'], "default")
        self.assertEqual(change['docUuid'], folder_1)

        # Let's do nothing and refetch the changes
        summary = self.get_changes()
        self.assertEqual(summary['hasTooManyChanges'], False)
        raw_root_defs = summary['activeSynchronizationRootDefinitions']
        self.assertEqual(raw_root_defs, '')
        self.assertEqual(len(summary['fileSystemChanges']), 0)

    @unittest.skipIf(sys.platform == 'win32', 'NXDRIVE-739: Need refactor')
    def test_sync_root_parent_registration(self):
        # Create a folder
        remote_client = self.remote_document_client_1
        folder_1 = remote_client.make_folder(self.workspace, 'Folder 1')
        self.wait()
        self.get_changes()

        # Mark Folder 1 as a sync root
        self.setUpDrive_1(root=folder_1)
        self.wait()
        summary = self.get_changes()

        self.assertEqual(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['eventId'], u'rootRegistered')
        self.assertEqual(change['fileSystemItemName'], u'Folder 1')
        self.assertEqual(change['fileSystemItemId'], u'defaultSyncRootFolderItemFactory#default#%s' % folder_1)

        # Mark parent folder as a sync root, should unregister Folder 1
        self.bind_root(self.ndrive_1_options, self.workspace, self.local_nxdrive_folder_1)
        self.wait()
        summary = self.get_changes()

        self.assertEqual(len(summary['fileSystemChanges']), 2)
        for change in summary['fileSystemChanges']:
            if change['eventId'] == u'rootRegistered':
                self.assertEqual(change['fileSystemItemName'], u'Nuxeo Drive Test Workspace')
                self.assertEqual(change['fileSystemItemId'],
                                 u'defaultSyncRootFolderItemFactory#default#%s' % self.workspace)
                self.assertIsNotNone(change['fileSystemItem'])
            elif change['eventId'] == u'deleted':
                self.assertIsNone(change['fileSystemItemName'])
                self.assertEqual(change['fileSystemItemId'], u'default#%s' % folder_1)
                self.assertIsNone(change['fileSystemItem'])
            else:
                self.fail('Unexpected event %s' % change['eventId'])

    @unittest.skipIf(sys.platform == 'win32', 'NXDRIVE-739: Need refactor')
    def test_lock_unlock_events(self):
        remote = self.remote_document_client_1
        doc_id = remote.make_file(self.workspace, 'TestLocking.txt', 'File content')
        self.setUpDrive_1()
        self.wait()
        self.get_changes()

        remote.lock(doc_id)
        self.wait()
        summary = self.get_changes()
        self.assertEqual(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['eventId'], u"documentLocked")
        self.assertEqual(change['docUuid'], doc_id)
        self.assertEqual(change['fileSystemItemName'], u"TestLocking.txt")

        remote.unlock(doc_id)
        self.wait()
        summary = self.get_changes()
        self.assertEqual(len(summary['fileSystemChanges']), 1)
        change = summary['fileSystemChanges'][0]
        self.assertEqual(change['eventId'], u"documentUnlocked")
        self.assertEqual(change['docUuid'], doc_id)
        self.assertEqual(change['fileSystemItemName'], u"TestLocking.txt")
