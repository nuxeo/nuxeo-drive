# coding: utf-8
"""
NXDRIVE-849: Handle remote rename when doing full remote scan.

Steps:
    1. install Nuxeo Server 7.10
    2. install Drive client on 2 machines (2.1.1221)
    3. create User1
    4. create User2
    5. User1: Server: Create Folder "MEFolder" and share with User2 with Manage Everything permission
    6. User1: Server: Create a folder named "MEFolder" in the personal workspace
    7. User1: Client: Launch Drive client and wait for sync completion
    8. User1: Client: from the MEFolder folder, start the createFolders.sh script (this will create 10 folders)
    9. User1: Client: wait for sync completion
    10. User2: Client: Launch Drive client and wait for sync completion
    11. User2: Client: Quit Drive client
    12. User1: Client: from the MEFolder folder, start the createFiles.sh script (this will create 250 files per folder)
    13. User1: Client: wait for sync completion
    14. User1: Client: from the MEFolder folder, start the renameFolders.sh script (this will rename the 10 folders through REST)
    15. User2: Client: now don't wait for previou step sync completion and immediately start Drive client, then wait for sync completion

Expected result:
    - Folders should be renamed in Drive client along with sync.

Actual result:
    - Folders rename is unsuccessful in Drive client, but all files are synced successfully.
"""

import time

from common import *


@action
def main(workspace, wspace_path, *args, **kwargs):
    """ Real actions to reproduce the issue. """

    num_fol = 10
    num_fil = 100

    start_drive(reset=True, msg='sync remote workspace and quit')
    folders = create_folders_locally(wspace_path, folders=range(num_fol))
    start_drive(msg='sync local folders and quit')
    children = get_children(workspace.title)

    create_files_remotely(workspace, files=range(num_fil), folders=folders)
    time.sleep(5)
    start_drive(msg='files remotely created and folders remotely renamed',
                background=True)
    for folder in children:
        rename_remote(folder)
    pause()
