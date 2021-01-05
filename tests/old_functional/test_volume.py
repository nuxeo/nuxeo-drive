import logging
import os
import shutil
from copy import copy
from pathlib import Path

import pytest

from nxdrive.constants import ROOT

from ..utils import random_png
from .common import OneUserTest


def configure_logs():
    """Configure the logging module to prevent too many data being logged."""

    from nxdrive.logging_config import configure

    configure(
        console_level="WARNING",
        file_level="WARNING",
        command_name="volume",
        force_configure=True,
    )


configure_logs()

log = logging.getLogger(__name__)

FOLDERS = FILES = DEPTH = 0

if "TEST_VOLUME" in os.environ:
    values_ = os.getenv("TEST_VOLUME", "")
    if not values_:
        del os.environ["TEST_VOLUME"]
    else:
        if values_.count(",") != 2:
            # Low volume by default
            values_ = "3,10,2"  # 200 documents

        FOLDERS, FILES, DEPTH = map(int, values_.split(","))
    del values_


def get_name(folder: bool, depth: int, number: int) -> str:
    if folder:
        return f"folder_{depth:03d}_{number:03d}"
    return f"file_{depth:03d}_{number:04d}.png"


def get_path(folder, depth, number) -> Path:
    child = ROOT
    for i in range(DEPTH + 1 - depth, DEPTH + 1):
        if i == 1 and not folder:
            child = ROOT / get_name(False, DEPTH - i + 1, number)
        child = ROOT / get_name(True, DEPTH - i + 1, number) / child
    return child


@pytest.mark.skipif(
    "TEST_VOLUME" not in os.environ,
    reason="Deactivate if not launched on purpose with TEST_VOLUME set",
)
class TestVolume(OneUserTest):
    def create_tree(self, folders, files, depth, parent) -> int:
        items = 0

        if depth < 1:
            return items

        for folder in range(folders):
            foldername = get_name(True, DEPTH - depth + 1, folder + 1)
            folderobj = {"path": os.path.join(parent["path"], foldername)}
            self.local_1.make_folder(parent["path"], foldername)
            items += 1

            folderobj["name"] = foldername
            folderobj["children"] = {}
            abspath = self.local_1.abspath(folderobj["path"])
            parent["children"][foldername] = folderobj

            items += self.create_tree(folders, files, depth - 1, folderobj)

            for file in range(files):
                filename = get_name(False, DEPTH - depth + 1, file + 1)
                folderobj["children"][filename] = {"name": filename}
                random_png(Path(abspath) / filename)
                items += 1

        return items

    def create(self, stopped=True, wait_for_sync=True):
        self.engine_1.start()
        self.wait_sync()
        if not stopped:
            self.engine_1.stop()

        self.tree = {"children": {}, "path": ROOT}
        items = self.create_tree(FOLDERS, FILES, DEPTH, self.tree)
        log.warning(f"Created {items:,} local documents.")

        if not stopped:
            self.engine_1.start()

        if wait_for_sync:
            self.wait_sync(timeout=items * 10)

        return items

    def _check_folder(self, path: Path, removed=[], added=[]):
        # First get the remote id
        remote_id = self.local_1.get_remote_id(path)
        assert remote_id

        # Get depth
        depth = int(path.name.split("_")[1])

        # Calculate expected children
        children = {}
        if depth != DEPTH:
            for i in range(1, FOLDERS + 1):
                children[get_name(True, depth + 1, i)] = True
        for i in range(FILES):
            children[get_name(False, depth, i)] = True
        for name in removed:
            children.pop(name, None)
        for name in added:
            children[name] = True

        # Local checks
        os_children = os.listdir()
        assert len(os_children) == len(children)
        cmp_children = copy(children)
        remote_refs = {}
        for child in self.local_1.abspath(path).iterdir():
            name = child.name
            file = cmp_children.pop(name, None)
            if not file:
                self.fail(f"Unexpected local child {name!r} in {path}")
            remote_ref = self.local_1.get_remote_id(child)
            assert remote_ref
            remote_refs[remote_ref] = name
        assert not cmp_children

        # Remote checks
        remote_children = self.remote_1.get_fs_children(remote_id)
        assert len(remote_children) == len(children)
        for child in remote_children:
            if child.uid not in remote_refs:
                self.fail(f'Unexpected remote child "{child.name}" in {path}')
            assert child.name == remote_refs[child.uid]

    def test_moves_while_creating(self):
        items = self.create(stopped=False, wait_for_sync=False)
        self._moves(items)

    def test_moves(self):
        items = self.create()
        self._moves(items)

    def test_moves_stopped(self):
        items = self.create()
        self._moves(items, stopped=True)

    def test_moves_while_creating_stopped(self):
        items = self.create(stopped=False, wait_for_sync=False)
        self._moves(items, stopped=True)

    def _moves(self, items: int, stopped: bool = False) -> None:
        if stopped:
            self.engine_1.stop()

        # While we are started
        # Move one parent to the second children
        if len(self.tree["children"]) < 3 or DEPTH < 2:
            self.app.quit()
            pytest.skip("Can't execute this test on so few data")

        # Move root 2 in, first subchild of 1
        root_2 = get_path(True, 1, 2)
        child = get_path(True, DEPTH, 1)
        shutil.move(self.local_1.abspath(root_2), self.local_1.abspath(child))

        root_1 = get_path(True, 1, 1)
        root_3 = get_path(True, 1, 3)
        shutil.move(self.local_1.abspath(root_1), self.local_1.abspath(root_3))

        # Update paths
        child = ROOT / get_name(True, 1, 3) / child
        root_2 = ROOT / child / get_name(True, 1, 2)
        root_1 = ROOT / root_3 / get_name(True, 1, 1)
        if stopped:
            self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=items * 10)

        # Checks
        self._check_folder(root_3, added=[get_name(True, 1, 1)])
        self._check_folder(child, added=[get_name(True, 1, 2)])
        self._check_folder(root_1)
        self._check_folder(root_2)

        # We should not have any error
        assert not self.engine_1.dao.get_errors(limit=0)

    def test_copies(self):
        items = self.create()
        self._copies(items)

    def test_copies_stopped(self):
        items = self.create()
        self._copies(items, stopped=True)

    def test_copies_while_creating(self):
        items = self.create(stopped=False, wait_for_sync=False)
        self._copies(items)

    def test_copies_while_creating_stopped(self):
        items = self.create(stopped=False, wait_for_sync=False)
        self._copies(items, stopped=True)

    def _copies(self, items: int, stopped: bool = False) -> None:
        if stopped:
            self.engine_1.stop()

        # Copy root 2 in, first subchild of 1
        root_2 = get_path(True, 1, 2)
        child = get_path(True, DEPTH, 1)
        shutil.copytree(
            self.local_1.abspath(root_2),
            self.local_1.abspath(child / get_name(True, 1, 2)),
        )

        # New copies
        root_1 = get_path(True, 1, 1)
        root_3 = get_path(True, 1, 3)
        root_4 = get_path(True, 1, DEPTH + 1)
        root_5 = get_path(True, 1, DEPTH + 2)
        shutil.copytree(
            self.local_1.abspath(root_1),
            self.local_1.abspath(root_3 / get_name(True, 1, 1)),
        )

        shutil.copytree(self.local_1.abspath(root_3), self.local_1.abspath(root_4))
        shutil.copytree(self.local_1.abspath(root_3), self.local_1.abspath(root_5))

        # Update paths
        child = ROOT / get_name(True, 1, 3) / child
        root_2 = ROOT / child / get_name(True, 1, 2)
        root_1 = ROOT / root_3 / get_name(True, 1, 1)
        root_1_path = self.local_1.abspath(root_1)
        child_path = self.local_1.abspath(child)

        # Copies files from one folder to another
        added_files = []
        for path in child_path.iterdir():
            if not path.is_file():
                continue
            shutil.copy(path, root_1_path)
            added_files.append(path.name)

        if stopped:
            self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=items * 10)

        # Checks
        self._check_folder(root_3, added=[get_name(True, 1, 1)])
        self._check_folder(child, added=[get_name(True, 1, 2)])
        self._check_folder(root_1, added=added_files)
        self._check_folder(root_2)

        # Check original copied
        self._check_folder(get_path(True, 1, 1))
        self._check_folder(get_path(True, 1, 2))
        self._check_folder(get_path(True, 1, DEPTH + 1), added=[get_name(True, 1, 1)])
        self._check_folder(get_path(True, 1, DEPTH + 2), added=[get_name(True, 1, 1)])

        # We should not have any error
        assert not self.engine_1.dao.get_errors(limit=0)


@pytest.mark.skipif(
    "TEST_REMOTE_SCAN_VOLUME" not in os.environ
    or int(os.environ["TEST_REMOTE_SCAN_VOLUME"]) == 0,
    reason="Skipped as TEST_REMOTE_SCAN_VOLUME is no set",
)
class TestVolumeRemoteScan(OneUserTest):
    def test_remote_scan(self):
        nb_nodes = int(os.getenv("TEST_REMOTE_SCAN_VOLUME", 20))

        # Random mass import
        self.root_remote.mass_import(self.ws.path, nb_nodes)

        # Wait for ES indexing
        self.root_remote.wait_for_async_and_es_indexing()

        # Synchronize
        self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=nb_nodes ** 2)

        query = (
            f"SELECT ecm:uuid FROM Document WHERE ecm:ancestorId = {self.workspace!r}"
            "   AND ecm:isVersion = 0"
            "   AND ecm:isTrashed = 0"
            "   AND ecm:mixinType != 'HiddenInNavigation'"
        )
        doc_count = self.root_remote.result_set_query(query)["resultsCount"]
        log.warning(f"Created {doc_count:,} documents (nb_nodes={nb_nodes:,}).")

        # Check local tree
        local_doc_count = sum(
            self.get_local_child_count(
                self.local_nxdrive_folder_1 / self.workspace_title
            )
        )
        assert local_doc_count == doc_count

        # We should not have any error
        assert not self.engine_1.dao.get_errors(limit=0)
