# coding: utf-8
import os
import tempfile
import unittest

from nxdrive.manager import Manager
from nxdrive.options import Options
from nxdrive.utils import normalized_path
from .common import clean_dir


class ManagerDAOTest(unittest.TestCase):
    def setUp(self):
        if Manager._singleton:
            Manager._singleton = None

        self.tmpdir = normalized_path(os.environ.get("WORKSPACE", "")) / "tmp"
        self.addCleanup(clean_dir, self.tmpdir)
        if not self.tmpdir.is_dir():
            self.tmpdir.mkdir(parents=True)

        self.test_folder = normalized_path(
            tempfile.mkdtemp("-nxdrive-tests", dir=self.tmpdir)
        )

    def tearDown(self):
        Manager._singleton = None

    @Options.mock()
    def _create_manager(self):
        Options.nxdrive_home = self.test_folder
        manager = Manager()
        return manager

    def test_autolock(self):
        # Create Manager
        manager = self._create_manager()
        self.addCleanup(manager.stop)

        dao = manager.get_dao()
        dao.lock_path("/test_1", 1, "doc_id_1")
        dao.lock_path("/test_2", 2, "doc_id_2")
        dao.lock_path("/test_3", 3, "doc_id_3")
        # Verify that it does fail
        dao.lock_path("/test_3", 4, "doc_id_4")
        assert len(dao.get_locked_paths()) == 3
        dao.unlock_path("/test")
        assert len(dao.get_locked_paths()) == 3
        dao.unlock_path("/test_1")
        locks = dao.get_locks()
        assert len(locks) == 2
        assert locks[0].path == "/test_2"
        assert locks[0].process == 2
        assert locks[0].remote_id == "doc_id_2"
        assert locks[1].path == "/test_3"
        # Verify it has auto-update
        assert locks[1].process == 4
        assert locks[1].remote_id == "doc_id_4"

    def test_notifications(self):
        from nxdrive.notification import Notification

        notif = Notification("warning", flags=Notification.FLAG_DISCARDABLE)
        notif2 = Notification("plop")

        # Create Manager
        manager = self._create_manager()
        self.addCleanup(manager.stop)

        dao = manager.get_dao()
        dao.insert_notification(notif)
        dao.insert_notification(notif2)
        assert len(dao.get_notifications()) == 2
        dao.discard_notification(notif.uid)
        assert len(dao.get_notifications(discarded=False)) == 1
        assert len(dao.get_notifications()) == 2
        dao.remove_notification(notif.uid)
        assert len(dao.get_notifications()) == 1
        dao.discard_notification(notif2.uid)
        assert len(dao.get_notifications()) == 1
        assert len(dao.get_notifications(discarded=True)) == 1
