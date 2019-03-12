# coding: utf-8
import os
import shutil
from copy import copy
from logging import getLogger
from math import floor, log10
from pathlib import Path

import pytest

from nxdrive.constants import ROOT

from .common import OneUserTest
from ..utils import random_png

log = getLogger(__name__)


@pytest.mark.skipif(
    "TEST_VOLUME" not in os.environ,
    reason="Deactivate if not launched on purpose with TEST_VOLUME set",
)
class VolumeTestCase(OneUserTest):

    NUMBER_OF_LOCAL_FILES = 10
    SYNC_TIMEOUT = 100  # in seconds

    def pow10floor(self, x):
        return int(floor(log10(float(x))) + 1)

    def create_tree(self, folders, files, depth, parent):
        if depth <= 0:
            return
        for folder in range(1, folders + 1):
            foldername = self.get_name(True, self.depth - depth + 1, folder)
            folderobj = dict()
            folderobj["path"] = os.path.join(parent["path"], foldername)
            if not self.fake:
                self.local_1.make_folder(parent["path"], foldername)
            folderobj["name"] = foldername
            folderobj["childs"] = dict()
            abspath = self.local_1.abspath(folderobj["path"])
            parent["childs"][foldername] = folderobj
            self.items += 1
            self.create_tree(folders, files, depth - 1, folderobj)
            for file_ in range(1, files + 1):
                filename = self.get_name(False, self.depth - depth + 1, file_)
                folderobj["childs"][filename] = dict()
                folderobj["childs"][filename]["name"] = filename
                if not self.fake:
                    file_path = os.path.join(abspath, filename)
                    random_png(file_path)
                self.items += 1

    def create(self, stopped=True, wait_for_sync=True):
        self.fake = False
        if not self.fake:
            self.engine_1.start()
            self.wait_sync()
            if not stopped:
                self.engine_1.stop()
        self.items = 0
        values = os.environ.get("TEST_VOLUME", "").split(",")
        if len(values) < 3:
            # Low volume by default to stick to 1h
            values = "3, 10, 2".split(",")
        self.fmt = ["", "", ""]
        for i in range(0, 3):
            self.fmt[i] = "%0" + str(self.pow10floor(values[i])) + "d"
        self.depth = int(values[2])
        self.num_files = int(values[1])
        self.num_folders = int(values[0])
        self.tree = dict()
        self.tree["childs"] = dict()
        self.tree["path"] = ROOT
        log.info(f"Generating in: {self.local_1.abspath(ROOT)}")
        self.create_tree(self.num_folders, self.num_files, self.depth, self.tree)

        log.info(f"Generated done in: {self.local_1.abspath(ROOT)}")
        if not self.fake:
            if not stopped:
                log.info("*** engine1 starting")
                self.engine_1.start()
            if wait_for_sync:
                self.wait_sync(timeout=self.items * 10)
                log.info("*** engine 1 synced")

    def get_name(self, folder: bool, depth: int, number: int):
        if folder:
            return "folder_" + self.fmt[2] + "_" + self.fmt[0] % (depth, number)
        return "file_" + self.fmt[2] + "_" + self.fmt[1] + ".png" % (depth, number)

    def get_path(self, folder, depth, number):
        child = ROOT
        for i in range(self.depth + 1 - depth, self.depth + 1):
            if i == 1 and not folder:
                child = ROOT / self.get_name(False, self.depth - i + 1, number)
            child = ROOT / self.get_name(True, self.depth - i + 1, number) / child
        return child

    def _check_folder(self, path: Path, removed=[], added=[]):
        # First get the remote id
        remote_id = self.local_1.get_remote_id(path)
        assert remote_id

        # get depth
        depth = int(path.name.split("_")[1])

        # calculated expected children
        children = dict()
        if depth != self.depth:
            for i in range(1, self.num_folders + 1):
                children[self.get_name(True, depth + 1, i)] = True
        for i in range(1, self.num_files + 1):
            children[self.get_name(False, depth, i)] = True
        for name in removed:
            if name in children:
                del children[name]
        for name in added:
            children[name] = True
        remote_refs = dict()

        # check locally
        os_children = os.listdir()
        assert len(os_children) == len(children)
        cmp_children = copy(children)
        for child in self.local_1.abspath(path).iterdir():
            name = child.name
            if name not in cmp_children:
                self.fail(f'Unexpected local child "{name}" in {path}')
            remote_ref = self.local_1.get_remote_id(child)
            assert remote_ref
            remote_refs[remote_ref] = name
            del cmp_children[name]
        assert not cmp_children

        # check remotely
        remote_children = self.remote_1.get_fs_children(remote_id)
        assert len(remote_children) == len(children)
        for child in remote_children:
            if child.uid not in remote_refs:
                self.fail(f'Unexpected remote child "{child.name}" in {path}')
            assert child.name == remote_refs[child.uid]

    def test_moves_while_creating(self):
        self.create(stopped=False, wait_for_sync=False)
        self._moves()

    def test_moves(self):
        self.create()
        self._moves()

    def test_moves_stopped(self):
        self.create()
        self._moves(stopped=True)

    def test_moves_while_creating_stopped(self):
        self.create(stopped=False, wait_for_sync=False)
        self._moves(stopped=True)

    def _moves(self, stopped=False):
        if stopped and not self.fake:
            self.engine_1.stop()
        # While we are started
        # Move one parent to the second children
        if len(self.tree["childs"]) < 3 or self.depth < 2:
            pytest.skip("Can't execute this test on so few data")
        # Move root 2 in, first subchild of 1
        root_2 = self.get_path(True, 1, 2)
        child = self.get_path(True, self.depth, 1)
        log.info(f"Will move {root_2} into {child}")
        if not self.fake:
            shutil.move(self.local_1.abspath(root_2), self.local_1.abspath(child))
        root_1 = self.get_path(True, 1, 1)
        root_3 = self.get_path(True, 1, 3)
        log.info(f"Will move {root_1} into {root_3}")
        if not self.fake:
            shutil.move(self.local_1.abspath(root_1), self.local_1.abspath(root_3))
        # Update paths
        child = ROOT / self.get_name(True, 1, 3) + str(child)
        root_2 = ROOT / str(child) + self.get_name(True, 1, 2)
        root_1 = ROOT / root_3 + self.get_name(True, 1, 1)
        if stopped and not self.fake:
            self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=self.items * 10)
        # Assert
        self._check_folder(root_3, added=[self.get_name(True, 1, 1)])
        self._check_folder(child, added=[self.get_name(True, 1, 2)])
        self._check_folder(root_1)
        self._check_folder(root_2)

    def test_copies(self):
        self.create()
        self._copies()

    def test_copies_stopped(self):
        self.create()
        self._copies(stopped=True)

    def test_copies_while_creating(self):
        self.create(stopped=False, wait_for_sync=False)
        self._copies()

    def test_copies_while_creating_stopped(self):
        self.create(stopped=False, wait_for_sync=False)
        self._copies(stopped=True)

    def _copies(self, stopped=False):
        if stopped and not self.fake:
            self.engine_1.stop()

        # Copy root 2 in, first subchild of 1
        root_2 = self.get_path(True, 1, 2)
        child = self.get_path(True, self.depth, 1)
        log.info(f"Will copy {root_2} into {child}")
        if not self.fake:
            shutil.copytree(
                self.local_1.abspath(root_2),
                self.local_1.abspath(child + self.get_name(True, 1, 2)),
            )
        root_1 = self.get_path(True, 1, 1)
        root_3 = self.get_path(True, 1, 3)
        # new copies
        root_4 = self.get_path(True, 1, self.num_folders + 1)
        root_5 = self.get_path(True, 1, self.num_folders + 2)
        log.info(f"Will copy {root_1} into {root_3}")
        if not self.fake:
            shutil.copytree(
                self.local_1.abspath(root_1),
                self.local_1.abspath(root_3 + self.get_name(True, 1, 1)),
            )

            log.info(f"Will copy {root_3} into {root_4}")
            log.info(f"Will copy {root_3} into {root_5}")
            shutil.copytree(self.local_1.abspath(root_3), self.local_1.abspath(root_4))
            shutil.copytree(self.local_1.abspath(root_3), self.local_1.abspath(root_5))
        # Update paths
        child = ROOT / self.get_name(True, 1, 3) + str(child)
        root_2 = ROOT / str(child) + self.get_name(True, 1, 2)
        root_1 = ROOT / root_3 + self.get_name(True, 1, 1)
        root_1_path = self.local_1.abspath(root_1)
        child_path = self.local_1.abspath(child)
        added_files = []
        # Copies files from one folder to another
        for path in child_path.iterdir():
            if not path.is_file():
                continue
            shutil.copy(path, root_1_path)
            added_files.append(path.name)

        if stopped and not self.fake:
            self.engine_1.start()
        self.wait_sync(wait_for_async=True, timeout=self.items * 10)
        # Assert
        self._check_folder(root_3, added=[self.get_name(True, 1, 1)])
        self._check_folder(child, added=[self.get_name(True, 1, 2)])
        self._check_folder(root_1, added=added_files)
        self._check_folder(root_2)
        # check original copied
        self._check_folder(self.get_path(True, 1, 1))
        self._check_folder(self.get_path(True, 1, 2))
        self._check_folder(
            self.get_path(True, 1, self.num_folders + 1),
            added=[self.get_name(True, 1, 1)],
        )
        self._check_folder(
            self.get_path(True, 1, self.num_folders + 2),
            added=[self.get_name(True, 1, 1)],
        )

    @pytest.mark.skipif(
        "TEST_REMOTE_SCAN_VOLUME" not in os.environ
        or int(os.environ["TEST_REMOTE_SCAN_VOLUME"]) == 0,
        reason="Skipped as TEST_REMOTE_SCAN_VOLUME is no set",
    )
    def test_remote_scan(self):
        nb_nodes = int(os.environ.get("TEST_REMOTE_SCAN_VOLUME", 20))
        # Random mass import
        self.root_remote.mass_import(self.ws.path, nb_nodes)
        # Wait for ES indexing
        self.root_remote.wait_for_async_and_es_indexing()
        # Synchronize
        self.engine_1.start()
        self.wait_sync(timeout=nb_nodes)
        # Check local tree
        doc_count = self.root_remote.result_set_query(
            "SELECT ecm:uuid FROM Document WHERE ecm:ancestorId = '%s'"
            "   AND ecm:isVersion = 0"
            "   AND ecm:currentLifeCycleState != 'deleted'"
            "   AND ecm:mixinType != 'HiddenInNavigation'" % self.workspace
        )["resultsCount"]
        local_file, local_folders = self.get_local_child_count(
            self.local_nxdrive_folder_1 / self.workspace_title
        )
        assert local_folders + local_file == doc_count
