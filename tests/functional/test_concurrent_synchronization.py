import time

from nxdrive.constants import WINDOWS

from .conftest import TwoUsersTest


class TestConcurrentSynchronization(TwoUsersTest):
    def create_docs(self, parent, number, name_pattern=None, delay=1.0):
        return self.root_remote.execute(
            command="NuxeoDrive.CreateTestDocuments",
            input_obj=f"doc:{parent}",
            namePattern=name_pattern,
            number=number,
            delay=int(delay * 1000),
        )

    def test_rename_local_folder(self):
        # Get local and remote clients
        local1 = self.local_1
        local2 = self.local_2

        # Launch first synchronization
        self.engine_1.start()
        self.engine_2.start()
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)

        # Test workspace should be created locally
        assert local1.exists("/")
        assert local2.exists("/")

        # Create a local folder in the test workspace and a file inside
        # this folder, then synchronize
        local1.make_folder("/", "Test folder")
        if WINDOWS:
            # Too fast folder create-then-rename are not well handled
            time.sleep(1)
        local1.rename("/Test folder", "Renamed folder")
        self.wait_sync(wait_for_async=True, wait_for_engine_2=True)
        assert local1.exists("/Renamed folder")
        assert local2.exists("/Renamed folder")
