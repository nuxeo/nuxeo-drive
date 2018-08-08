# coding: utf-8
"""
NXDRIVE-844: Crash when opening the conflicts window while
syncing many documents.
"""

from common import (
    action,
    create_files_remotely,
    get_children,
    rename_local,
    rename_remote,
    start_drive,
)


@action
def main(workspace, wspace_path, *args, **kwargs):
    """ Real actions to reproduce the issue. """

    start_drive(reset=True, msg="sync remote workspace and quit")

    create_files_remotely(workspace, files=range(101), random=False)
    start_drive(msg="sync remote files and quit")

    for doc in get_children(workspace):
        rename_remote(doc)
        rename_local(wspace_path, doc)
    start_drive(msg="open the conflicts window and see the CRASH!")


main()
