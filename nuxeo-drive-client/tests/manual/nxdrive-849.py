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

from __future__ import print_function

import os
import os.path
import shutil
import socket
import subprocess
import sys
import time
import uuid

from nuxeo.nuxeo import Nuxeo


nuxeo = Nuxeo(base_url='http://127.0.0.1:8080/nuxeo/',
              auth={'username': 'Administrator', 'password': 'Administrator'})


def actions(workspace):
    """ Real actions to reproduce the issue. """

    num_fol = 10
    num_fil = 250
    wspace_path = os.path.join(os.path.expanduser('~/Nuxeo Drive'),
                               workspace.title)

    start_drive(reset=True, msg='sync remote workspace and quit')
    folders = create_folders_locally(wspace_path, folders=range(num_fol))
    start_drive(msg='sync local folders and quit')
    children = get_children(workspace.title)

    start_drive(msg='files locally created and folders remotely renamed',
                background=True)
    time.sleep(3)
    create_files_locally(wspace_path, files=range(num_fil), folders=folders)
    for folder in children:
        rename(folder)
    pause()


def create_files_locally(path, files=None, folders=None, random=True):
    """ Create several files locally. """

    if not files:
        return

    def create(doc, parent):
        if random:
            doc = 'doc_' + str(uuid.uuid1()).split('-')[0] + '.txt'
        elif isinstance(doc, int):
            doc = 'doc_' + str(doc) + '.txt'

        with open(os.path.join(parent, doc), 'w') as fileo:
            fileo.write('Content ' + doc)
        debug('Created local file {!r}'.format(parent + '/' + doc))

    if folders:
        for folder in folders:
            for document in files:
                create(document, os.path.join(path, folder))
    else:
        for document in files:
            create(document, path)


def create_folders_locally(path, folders=None):
    """ Create several folders locally. """

    if not folders:
        return

    ret = []
    for folder in folders:
        if isinstance(folder, int):
            folder = 'test_folder_' + str(folder)

        full_path = os.path.join(path, folder)
        os.mkdir(full_path)
        ret.append(full_path)
        debug('Created local folder {!r}'.format(full_path))

    return ret


def create_workspace():
    """ Create a uniq workspace. """

    path = 'tests-' + str(uuid.uuid1()).split('-')[0]
    ws = {'name': path,
          'type': 'Workspace',
          'properties': {'dc:title': path}}
    workspace = nuxeo.repository().create('/default-domain/workspaces', ws)
    workspace.save()

    # Enable synchronization on this workspace
    operation = nuxeo.operation('NuxeoDrive.SetSynchronization')
    operation.params({'enable': True})
    operation.input(workspace.path)
    operation.execute()

    debug('Created workspace ' + path)
    return workspace


def get_children(path):

    doc = nuxeo.repository().fetch('/default-domain/workspaces/' + path)
    docs = nuxeo.repository().query({'pageProvider': 'CURRENT_DOC_CHILDREN',
                                     'queryParams': [doc.uid]})
    return docs['entries']


def rename(document):
    """ Rename a document. """

    document.properties.update({
        'dc:title': document.title + '_renamed',
        'dc:description': 'Document renamed'})
    nuxeo.repository().update(document)


# ---


def debug(*args):
    """ Print a line on STDERR. """

    print('>>>', *args, file=sys.stderr)


def pause():
    """ Mark a pause. """

    raw_input('Press a key to continue ... ')


def start_drive(tag=None, reset=False, msg='', **kwargs):
    """ Start Drive and sync. """

    if reset:
        debug('Resetting Drive ... ')
        shutil.rmtree(os.path.expanduser('~/.nuxeo-drive'))
        system(('ndrive bind-server'
                ' Administrator'
                ' http://127.0.0.1:8080/nuxeo'
                ' --password Administrator'))

    if tag:
        debug('Switching to git branch ' + tag)
        system('git checkout ' + tag)

    if msg:
        msg = '[' + msg + ']'

    debug('Starting Drive ... ' + msg)
    system('ndrive --log-level-console=ERROR --log-level-file=DEBUG', **kwargs)


def system(cmd, **kwargs):
    """ Execute a command on the host with redictection to null. """

    if kwargs.pop('background', False):
        subprocess.Popen(cmd.split(), stderr=open(os.devnull, 'wb'))
        time.sleep(2)
    else:
        subprocess.check_call(cmd.split(), stderr=open(os.devnull, 'wb'))


def main():
    """ Main logic. """

    # Create the workspace
    workspace = create_workspace()

    # Actions to reproduce the issue
    try:
        actions(workspace)
    finally:
        # Remove the workspace
        debug('Purge and quit')
        try:
            workspace.delete()
        except socket.timeout:
            pass


if __name__ == '__main__':
    exit(main())
