import os
from unittest.mock import patch

from nxdrive.constants import WINDOWS

from .common import OneUserTest

# Number of chars in path "C:\...\Nuxeo..." is approx 96 chars
FOLDER_A = "A" * 90
FOLDER_B = "B" * 90
FOLDER_C = "C" * 90
FOLDER_D = "D" * 50
FILE = "F" * 255 + ".txt"


class TestLongPath(OneUserTest):
    def setUp(self):
        self.remote_1 = self.remote_document_client_1
        self.folder_a = self.remote_1.make_folder("/", FOLDER_A)
        self.folder_b = self.remote_1.make_folder(self.folder_a, FOLDER_B)
        self.folder_c = self.remote_1.make_folder(self.folder_b, FOLDER_C)
        self.remote_1.make_file(self.folder_c, "File1.txt", content=b"Sample Content")

    def tearDown(self):
        self.remote_1.delete(self.folder_a, use_trash=False)

    def test_long_path(self):
        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        parent_path = (
            self.local_1.abspath("/") / FOLDER_A / FOLDER_B / FOLDER_C / FOLDER_D
        )
        if WINDOWS:
            parent_path = f"\\\\?\\{parent_path}"
        os.makedirs(parent_path, exist_ok=True)

        new_file = os.path.join(parent_path, "File2.txt")
        with open(new_file, "wb") as f:
            f.write(b"Hello world")

        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        remote_children_of_c = self.remote_1.get_children_info(self.folder_c)
        assert len(remote_children_of_c) == 2
        folder = [item for item in remote_children_of_c if item.name == FOLDER_D][0]
        assert folder.name == FOLDER_D

        remote_children_of_d = self.remote_1.get_children_info(folder.uid)
        assert len(remote_children_of_d) == 1
        assert remote_children_of_d[0].name == "File2.txt"

    def test_setup_on_long_path(self):
        """NXDRIVE-689: Fix error when adding a new account when installation
        path is greater than 245 characters.
        """

        self.engine_1.stop()
        self.engine_1.reinit()

        # On Mac, avoid permission denied error
        self.engine_1.local.clean_xattr_root()

        test_folder_len = 245 - len(str(self.local_nxdrive_folder_1))
        self.local_nxdrive_folder_1 = self.local_nxdrive_folder_1 / (
            "A" * test_folder_len
        )
        assert len(str(self.local_nxdrive_folder_1)) > 245

        self.manager_1.unbind_all()
        self.engine_1 = self.manager_1.bind_server(
            self.local_nxdrive_folder_1,
            self.nuxeo_url,
            self.user_1,
            password=self.password_1,
            start_engine=False,
        )

        self.engine_1.start()
        self.engine_1.stop()


class TestLongFileName(OneUserTest):
    def test_long_file_name(self):
        def error(*_):
            nonlocal received
            received = True

        received = False
        remote = self.remote_document_client_1

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)

        with patch.object(
            self.manager_1.notification_service, "_longPathError", new_callable=error
        ):
            remote.make_file(self.workspace, FILE, content=b"Sample Content")
            self.wait_sync(wait_for_async=True, timeout=5, fail_if_timeout=False)

            assert received
            assert not self.local_1.exists(f"/{FILE}")
