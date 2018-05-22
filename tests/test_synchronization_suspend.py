# coding: utf-8
import sys

import pytest

from nxdrive.osi import AbstractOSIntegration
from .common import UnitTestCase


class TestSynchronizationSuspend(UnitTestCase):

    @pytest.mark.randombug(
        'NXDRIVE-805', condition=(sys.platform == 'win32'), repeat=2)
    def test_basic_synchronization_suspend(self):
        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Let's create some document on the client and the server
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        assert remote.exists('/Folder 3')
        assert local.exists('/Folder 1')
        assert local.exists('/Folder 2')
        assert local.exists('/File 5.txt')
        self.engine_1.get_queue_manager().suspend()
        local.make_folder('/', 'Folder 4')
        local.make_file('/Folder 4', 'Test.txt', 'Plop')
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        assert len(remote.get_children_info(self.workspace_1)) == 4
        assert self.engine_1.get_queue_manager().is_paused()

    def test_synchronization_local_watcher_paused_when_offline(self):
        """ NXDRIVE-680: fix unwanted local upload when offline. """

        local = self.local_1
        remote = self.remote_document_client_1
        engine = self.engine_1

        # Create one file locally and wait for sync
        engine.start()
        self.wait_sync(wait_for_async=True)
        local.make_file('/', 'file1.txt', content=b'42')
        self.wait_sync()

        # Checks
        assert remote.exists('/file1.txt')
        assert local.exists('/file1.txt')

        # Simulate offline mode (no more network for instance)
        engine.get_queue_manager().suspend()

        # Create a bunch of files locally
        local.make_folder('/', 'files')
        for num in range(60 if AbstractOSIntegration.is_windows() else 20):
            local.make_file('/files', 'file-' + str(num) + '.txt',
                            content=b'Content of file-' + str(num))
        self.wait_sync(fail_if_timeout=False)

        # Checks
        assert len(remote.get_children_info(self.workspace_1)) == 1
        assert engine.get_queue_manager().is_paused()

        # Restore network connection
        engine.get_queue_manager().resume()

        # Wait for sync and check synced files
        self.wait_sync(wait_for_async=True)
        assert len(remote.get_children_info(self.workspace_1)) == 2
        assert not engine.get_queue_manager().is_paused()

    @pytest.mark.randombug(
        'NXDRIVE-812', condition=(sys.platform == 'linux2'), mode='BYPASS')
    def test_synchronization_end_with_children_ignore_parent(self):
        """ NXDRIVE-655: children of ignored folder are not ignored. """

        local = self.local_1
        remote = self.remote_document_client_1
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        # Let's create some document on the client and the server
        local.make_folder('/', 'Folder 3')
        self.make_server_tree()

        # Launch ndrive and check synchronization
        self.wait_sync(wait_for_async=True)
        assert remote.exists('/Folder 3')
        assert local.exists('/Folder 1')
        assert local.exists('/Folder 2')
        assert local.exists('/File 5.txt')
        local.make_folder('/', '.hidden')
        local.make_file('/.hidden', 'Test.txt', 'Plop')
        local.make_folder('/.hidden', 'normal')
        local.make_file('/.hidden/normal', 'Test.txt', 'Plop')
        # Should not try to sync therefor it should not timeout
        self.wait_sync(wait_for_async=True)
        assert len(remote.get_children_info(self.workspace_1)) == 4
