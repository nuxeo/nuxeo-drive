# coding: utf-8
"""
NXDRIVE-844: Crash when opening the conflicts window while
syncing many documents.
"""

from common import *


@action
def main(workspace, wspace_path, *args, **kwargs):
    """ Real actions to reproduce the issue. """

    files = range(101)

    start_drive(reset=True, msg='sync remote workspace and quit')

    create_files_remotely(workspace, files=files, random=False)
    start_drive(msg='sync remote files and quit')

    files = get_children(workspace.title)
    for doc in files:
        rename_remote(doc)
        rename_local(wspace_path, doc)
    start_drive(gdb=True, msg='open the conflicts window and see the CRASH!')


main()
