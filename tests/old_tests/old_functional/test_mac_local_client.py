from ..markers import mac_only
from .common import OneUserTest

try:
    import xattr
except ImportError:
    pass


@mac_only
class TestMacSpecific(OneUserTest):
    def test_finder_in_use(self):
        """Test that if Finder is using the file we postpone the sync."""

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.local_1.make_file("/", "File.txt", content=b"Some Content 1")

        # Emulate the Finder in use flag
        key = [0] * 32  # OSX_FINDER_INFO_ENTRY_SIZE
        key[:8] = 0x62, 0x72, 0x6F, 0x6B, 0x4D, 0x41, 0x43, 0x53

        xattr.setxattr(
            str(self.local_1.abspath("/File.txt")),
            xattr.XATTR_FINDERINFO_NAME,
            bytes(bytearray(key)),
        )

        # The file should not be synced and there have no remote id
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        assert not self.local_1.get_remote_id("/File.txt")

        # Remove the Finder flag
        self.local_1.remove_remote_id("/File.txt", name=xattr.XATTR_FINDERINFO_NAME)

        # The sync process should now handle the file and sync it
        self.wait_sync(wait_for_async=True, fail_if_timeout=False)
        assert self.local_1.get_remote_id("/File.txt")
