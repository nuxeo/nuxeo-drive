# coding: utf-8
""" Common functions for manual testing. """

from __future__ import print_function, unicode_literals

import io
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid

from nuxeo.nuxeo import Nuxeo

__all__ = [
    'create_files_locally',
    'create_files_remotely',
    'create_folders_locally',
    'get_children',
    'rename_remote',
    'rename_local',

    'debug',
    'pause',
    'start_drive',
    'action',
]


nuxeo = Nuxeo(base_url=os.environ.get('NXDRIVE_TEST_NUXEO_URL',
                                      'http://localhost:8080/nuxeo'),
              auth={'username': 'Administrator',
                    'password': 'Administrator'})


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

    def create(doc, parent):
        if random:
            doc = 'doc_' + str(uuid.uuid1()).split('-')[0] + '.txt'
        elif isinstance(doc, int):
            doc = 'doc_' + str(doc) + '.txt'

        doc_infos = {'name': doc,
                     'type': 'Note',
                     'properties': {'dc:title': doc,
                                    'note:note': 'Content ' + doc}}
        nuxeo.repository().create(
            '/default-domain/workspaces/' + parent, doc_infos)
        debug('Created remote file {!r} in {!r}'.format(doc, parent))
        time.sleep(0.05)

    if folders:
        for folder in folders:
            for document in files:
                create(document, os.path.join(workspace.title, folder))
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


def rename_remote(document):
    """ Rename a document. """

    new_name = document.title + '_renamed-dist.txt'
    document.properties.update({
        'dc:title': new_name,
        'dc:description': 'Document remotely renamed'})
    nuxeo.repository().update(document)
    debug('Remotely renamed {!r} -> {!r}'.format(document.title, new_name))
    time.sleep(0.05)


def rename_local(parent, document):
    """ Rename a document locally. """

    doc = os.path.join(parent, document.title)
    new_name = doc + '_renamed-local.txt'
    os.rename(doc, new_name)
    with io.open(new_name, 'w', encoding='utf-8') as handler:
        handler.write('Document remotely renamed')
    debug('Locally renamed {!r} -> {!r}'.format(document.title, new_name))


# ---


def debug(*args):
    """ Print a line on STDERR. """

    print('>>>', *args, file=sys.stderr)


def pause():
    """ Mark a pause. """

    raw_input('Press a key to continue ... ')


def start_drive(tag=None, reset=False, gdb=False, msg='', **kwargs):
    """ Start Drive and sync. """

    if reset:
        debug('Resetting Drive ... ')
        shutil.rmtree(os.path.expanduser('~/.nuxeo-drive/logs'))
        """
        system(('ndrive bind-server'
                ' Administrator'
                ' http://127.0.0.1:8080/nuxeo'
                ' --password Administrator'))
        """

    if tag:
        debug('Switching to git branch ' + tag)
        system('git checkout ' + tag)

    if msg:
        msg = '[' + msg + ']'

    cmd = ('python nuxeo-drive-client/scripts/ndrive.py'
           ' --log-level-console=ERROR'
           ' --log-level-file=TRACE'
           )
    if gdb:
        cmd = 'gdb --quiet --eval-command=r --args ' + cmd

    debug('Starting Drive ... ' + msg)
    system(cmd, **kwargs)


def system(cmd, **kwargs):
    """ Execute a command on the host with redictection to null. """

    if kwargs.pop('background', False):
        subprocess.Popen(cmd.split(), stderr=open(os.devnull, 'wb'))
        time.sleep(2)
    else:
        subprocess.check_call(cmd.split(), stderr=open(os.devnull, 'wb'))


def action(func):
    """
    Main logic.  Use that function as decorator on yours to facilitate tests.
    """

    def wrapped():
        # Create the workspace
        workspace = create_workspace()
        wspace_path = os.path.join(os.path.expanduser('~/Nuxeo Drive'),
                                   workspace.title)

        # Actions to reproduce the issue
        try:
            func(workspace, wspace_path)
        finally:
            # Remove the workspace
            debug('Purge and quit')
            try:
                workspace.delete()
            except socket.timeout:
                pass

    return wrapped
