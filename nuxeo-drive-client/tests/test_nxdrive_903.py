# coding: utf-8
"""
 1 install Nuxeo 7.10
 2 install Drive 2.4.6
 3 use Administrator account and enable synchronization on Personal Workspace
 4 Client 1: configure Drive client to use Administrator user
 5 Client 1: create 10 folders
 6 Client 1: create 250 files in each folders
 7 Client 1: use attached scripts to do it
 8 Client 1: wait for synchronization
 9 Server: double-check the files are synchronized correctly
10 Client 2: install Drive 2.4.6 on a second client
11 Client 2: configure Drive client to use Administrator user
12 Client 2: wait for synchronization
13 Client 2: observe the folders and files and synchronized
14 Client 2: disable the network card (either wifi or cable)
15 Client 2: wait for Nuxeo client systray icon to switch to grey
16 Client 1: use the renameFoldersAndFiles.sh in the synchronized folder
   to rename all the files and folders
17 Client 1: wait for synchronization
18 Server: double-check the files and folders are renamed
19 Client 2: enable network card
20 Client 2: wait for synchronization
21 Client 2: only the folders are renamed

This scenario also happens when turning off or exiting Nuxeo Drive client
instead of disabling the network card.
"""

from __future__ import unicode_literals

import os.path

from tests.common_unit_test import RandomBug, UnitTestCase


class Test(UnitTestCase):

    @RandomBug('NXDRIVE-903', target='windows', mode='BYPASS')
    def test_nxdrive_903(self):
        """ On Windows, some files are postponed. Ignore the test if so. """

        remote = self.remote_document_client_1
        local_1, local_2 = self.local_client_1,  self.local_client_2
        engine_1, engine_2 = self.engine_1, self.engine_2
        nb_folders, nb_files = 5, 5

        # Steps 1 -> 13
        engine_1.start()
        self.wait_sync(wait_for_async=True)

        folders = [local_1.make_folder('/', 'folder_' + str(idx))
                   for idx in range(nb_folders)]
        files = {folder: [local_1.make_file(folder,
                                            'file_%s_%s.txt' % (num, idx),
                                            content=bytes(idx))
                          for idx in range(nb_files)]
                 for num, folder in enumerate(folders)}
        self.wait_sync()

        for folder in folders:
            assert local_1.exists(folder)
            assert remote.exists(folder)
            for file_ in files[folder]:
                assert local_1.exists(file_)
                assert remote.exists(file_)

        engine_2.start()
        self.wait_sync(wait_for_async=True,
                       wait_for_engine_1=False,
                       wait_for_engine_2=True)
        for folder in folders:
            assert local_2.exists(folder)
            for file_ in files[folder]:
                assert local_2.exists(file_)

        # Steps 14 -> 15
        engine_2.suspend()

        # Steps 16 -> 18
        new_folders = []
        new_files = {}
        for folder in folders:
            name = os.path.basename(folder)
            new_folder = local_1.rename(folder, name + '-renamed').path
            new_folders.append(new_folder)
            new_files[new_folder] = []
            for file_ in files[folder]:
                name = os.path.basename(file_)
                new_name = os.path.splitext(name)[0] + '-renamed.txt'
                new_file = local_1.rename(new_folder + '/' +  name, new_name)
                new_files[new_folder].append(new_file.path)
        self.wait_sync()

        for folder, new_folder in zip(folders, new_folders):
            assert local_1.exists(new_folder)
            assert remote.get_info(folder).name == os.path.basename(new_folder)
            for file_, new_file in zip(files[folder], new_files[new_folder]):
                assert local_1.exists(new_file)
                assert remote.get_info(file_).name == os.path.basename(new_file)

        # Steps 19 -> 21
        engine_2.resume()
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)

        # Get a list of all synchronized folders to have a better view of
        # what is synced as expected
        states = [local_2.exists(folder) for folder in new_folders]
        needed = [True] * nb_folders
        assert states == needed

        # Get a dict of all synchronized files sorted by folders
        # to have a better view of what is synced as expected
        states = {folder: [local_2.exists(file_)
                           for file_ in new_files[folder]]
                  for folder in new_folders}
        needed = {folder: [True] * nb_files for folder in new_folders}
        assert states == needed
