# coding: utf-8
"""
NXDRIVE-904:
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

from nuxeo.client import Nuxeo
from nuxeo.models import Document

nuxeo = Nuxeo(host=os.environ.get('NXDRIVE_TEST_NUXEO_URL',
                                  'http://localhost:8080/nuxeo'),
              auth=('Administrator', 'Administrator'))


def actions(workspace):
    """ Real actions to reproduce the issue. """

    num_fol = 11
    num_fil = 250
    wspace_path = os.path.join(os.path.expanduser('~/Nuxeo Drive'),
                               workspace.title)

    start_drive(reset=True, msg='sync remote workspace and quit')
    folders = create_folders_locally(wspace_path, folders=range(num_fol))
    start_drive(msg='sync folders and quit')

    create_files_remotely(
        workspace, files=range(num_fil), folders=folders, random=False)
    start_drive(msg='sync files, quit and launch renameAndDeleteFiles.sh')
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


def create_files_remotely(workspace, files=None, folders=None, random=True):
    """ Create several files remotely. """

    if not files:
        return

    def create(doc, parent, n=0):
        if random:
            doc = 'doc_' + str(uuid.uuid1()).split('-')[0] + '.txt'
        elif isinstance(doc, int):
            doc = 'doc_' + str(n) + '.txt'
            n += 1

        doc_info = Document(name=doc, type='Note', properties={
            'dc:title': doc, 'note:note': 'Content ' + doc})
        nuxeo.documents.create(
            doc_info, parent_path='/default-domain/workspaces/' + parent)
        debug('Created remote file {!r} in {!r}'.format(doc, parent))

    if folders:
        for i, folder in enumerate(folders):
            for j, document in enumerate(files):
                create(document,
                       os.path.join(workspace.title, folder),
                       n=i * len(files) + j)
    else:
        for document in files:
            create(document, workspace.title)


def create_folders_locally(parent, folders=None):
    """ Create several folders locally. """

    if not folders:
        return

    ret = []
    for folder in folders:
        if isinstance(folder, int):
            folder = 'test_folder_' + str(folder)

        full_path = os.path.join(parent, folder)
        os.mkdir(full_path)
        ret.append(folder)
        debug('Created local folder {!r} in {!r}'.format(folder, parent))

    return ret


def create_workspace():
    """ Create a uniq workspace. """

    path = 'tests-' + str(uuid.uuid1()).split('-')[0]
    ws = Document(name=path, type='Workspace', properties={'dc:title': path})
    workspace = nuxeo.documents.create(
        ws, parent_path='/default-domain/workspaces')

    # Enable synchronization on this workspace
    operation = nuxeo.operations.new('NuxeoDrive.SetSynchronization')
    operation.params = {'enable': True}
    operation.input_obj = workspace.path
    operation.execute()

    debug('Created workspace ' + path)
    return workspace


def get_children(path):

    doc = nuxeo.documents.get(path='/default-domain/workspaces/' + path)
    docs = nuxeo.client.query({'pageProvider': 'CURRENT_DOC_CHILDREN',
                               'queryParams': [doc.uid]})
    return docs['entries']


def rename(document):
    """ Rename a document. """

    new_name = document.title + '_renamed'
    document.properties.update({
        'dc:title': new_name,
        'dc:description': 'Document renamed'})
    nuxeo.documents.put(document)
    debug('Renamed {!r} -> {!r}'.format(document.title, new_name))


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
        try:
        # shutil.rmtree(os.path.expanduser('~/.nuxeo-drive'))
            shutil.rmtree(os.path.expanduser('~/.nuxeo-drive/logs'))
        except OSError:
            pass
        """
        system(('ndrive bind-server'
                ' Administrator '
                + os.environ.get('NXDRIVE_TEST_NUXEO_URL',
                                 'http://localhost:8080/nuxeo')
                + ' --password Administrator'))
        # """

    if tag:
        debug('Switching to git branch ' + tag)
        system('git checkout ' + tag)

    if msg:
        msg = '[' + msg + ']'

    debug('Starting Drive ... ' + msg)
    system('ndrive --log-level-console=ERROR --log-level-file=TRACE', **kwargs)


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
