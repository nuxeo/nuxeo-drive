# coding: utf-8
""" Common functions for manual testing. """

import contextlib
import io
import os
import shutil
import socket
import subprocess
import sys
import time
import uuid

from nuxeo.client import Nuxeo
from nuxeo.models import Document

__all__ = (
    "action",
    "create_files_locally",
    "create_files_remotely",
    "create_folders_locally",
    "debug",
    "get_children",
    "pause",
    "rename_local",
    "rename_remote",
    "start_drive",
)


nuxeo = Nuxeo(
    host=os.getenv("NXDRIVE_TEST_NUXEO_URL", "http://localhost:8080/nuxeo"),
    auth=("Administrator", "Administrator"),
)


def create_files_locally(path, files=None, folders=None, random=True):
    """ Create several files locally. """

    if not files:
        return

    def create(doc, parent):
        if random:
            doc = f"doc_{uid()}.txt"
        elif isinstance(doc, int):
            doc = f"doc_{doc}.txt"

        with open(os.path.join(parent, doc), "w") as fileo:
            fileo.write(f"Content {doc}")
        debug(f"Created local file {parent}/{doc}")

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
            doc = f"doc_{uid()}.txt"
        elif isinstance(doc, int):
            doc = f"doc_{doc}.txt"

        doc_info = Document(
            name=doc,
            type="Note",
            properties={"dc:title": doc, "note:note": f"Content {doc}"},
        )
        nuxeo.documents.create(
            doc_info, parent_path=f"/default-domain/workspaces/{parent}"
        )
        debug(f"Created remote file {doc!r} in {parent!r}")
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
            folder = "test_folder_" + str(folder)

        full_path = os.path.join(parent, folder)
        os.mkdir(full_path)
        ret.append(folder)
        debug("Created local folder {!r} in {!r}".format(folder, parent))

    return ret


def create_workspace():
    """ Create a unique workspace. """

    path = f"tests-{uid()}"
    ws = Document(name=path, type="Workspace", properties={"dc:title": path})
    workspace = nuxeo.documents.create(ws, parent_path="/default-domain/workspaces")
    workspace.save()

    # Enable synchronization on this workspace
    operation = nuxeo.operations.new("NuxeoDrive.SetSynchronization")
    operation.params = {"enable": True}
    operation.input_obj = workspace.path
    operation.execute()

    debug("Created workspace {path}")
    return workspace


def get_children(workspace):
    """ Retrieve all children of a given workspace (can be a Document too). """

    docs = nuxeo.documents.query(
        {"pageProvider": "CURRENT_DOC_CHILDREN", "queryParams": [workspace.uid]}
    )
    return docs["entries"]


def rename_remote(document):
    """ Rename a document. """

    new_name = f"{document.title}_renamed-dist.txt"
    document.set({"dc:title": new_name, "dc:description": "Document remotely renamed"})
    document.save()
    debug(f"Remotely renamed {document.title!r} -> {new_name!r}")
    time.sleep(0.05)


def rename_local(parent, document):
    """ Rename a document locally. """

    doc = os.path.join(parent, document.title)
    new_name = f"{doc}_renamed-local.txt"
    os.rename(doc, new_name)
    with io.open(new_name, "w", encoding="utf-8") as handler:
        handler.write("Document remotely renamed")
    debug(f"Locally renamed {document.title!r} -> {new_name!r}")


# ---


def debug(*args):
    """ Print a line on STDERR. """

    print(">>>", *args, file=sys.stderr)


def uid():
    """ Generate a uniq ID. """

    return str(uuid.uuid1()).split("-")[0]


def pause():
    """ Mark a pause. """

    input("Press a key to continue ... ")


def start_drive(tag=None, reset=False, gdb=False, msg="", **kwargs):
    """ Start Drive and sync. """

    if reset:
        debug("Resetting Drive ... ")
        with contextlib.suppress(FileNotFoundError):
            shutil.rmtree(os.path.expanduser("~/.nuxeo-drive/logs"))
        user, pwd = nuxeo.client.auth
        cmd = (
            f"python -m nxdrive bind-server {user} {nuxeo.client.host} --password {pwd}"
        )
        system(cmd)

    if tag:
        debug(f"Switching to git branch {tag}")
        system(f"git checkout {tag}")

    if msg:
        msg = f"[{msg}]"

    cmd = "python -m nxdrive --log-level-console=ERROR --log-level-file=TRACE"
    if gdb:
        cmd = f"gdb --quiet --eval-command=r --args {cmd}"

    debug(f"Starting Drive ... {msg}")
    system(cmd, **kwargs)


def system(cmd, **kwargs):
    """ Execute a command on the host with redictection to null. """

    if kwargs.pop("background", False):
        subprocess.Popen(cmd.split(), stderr=open(os.devnull, "wb"))
        time.sleep(2)
    else:
        os.system(cmd)


def action(func):
    """
    Main logic.  Use that function as decorator on yours to facilitate tests.
    """

    def wrapped():
        # Create the workspace
        workspace = create_workspace()
        wspace_path = os.path.join(os.path.expanduser("~/Nuxeo Drive"), workspace.title)

        # Actions to reproduce the issue
        try:
            func(workspace, wspace_path)
        finally:
            # Remove the workspace
            debug("Purge and quit")
            try:
                workspace.delete()
            except socket.timeout:
                pass

    return wrapped
