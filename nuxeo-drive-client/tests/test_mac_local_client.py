# coding: utf-8
from unittest import skipIf

from nxdrive.osi import AbstractOSIntegration
from tests.common_unit_test import UnitTestCase


@skipIf(not AbstractOSIntegration.is_mac(),
        'Not relevant on GNU/Linux nor Windows')
class TestMacSpecific(UnitTestCase):

    def test_finder_in_use(self):
        """ Test that if Finder is using the file we postpone the sync. """

        self.engine_1.start()
        self.wait_sync(wait_for_async=True)
        self.local_client_1.make_file('/', u'File.txt',
                                      content=u'Some Content 1'.encode('utf-8'))

        # Emulate the Finder in use flag
        OSX_FINDER_INFO_ENTRY_SIZE = 32
        key = (OSX_FINDER_INFO_ENTRY_SIZE)*[0]
        key[0] = 0x62
        key[1] = 0x72
        key[2] = 0x6F
        key[3] = 0x6B
        key[4] = 0x4D
        key[5] = 0x41
        key[6] = 0x43
        key[7] = 0x53
        import xattr
        xattr.setxattr(self.local_client_1.abspath(u'/File.txt'), xattr.XATTR_FINDERINFO_NAME, bytes(bytearray(key)))

        # The file should not be synced and there have no remote id
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, timeout=10)
        info = self.local_client_1.get_remote_id(u'/File.txt')
        self.assertIsNone(info)

        # Remove the Finder flag
        self.local_client_1.remove_remote_id(u'/File.txt', xattr.XATTR_FINDERINFO_NAME)

        # The sync process should now handle the file and sync it
        self.wait_sync(wait_for_async=True, fail_if_timeout=False, timeout=10)
        info = self.local_client_1.get_remote_id(u'/File.txt')
        self.assertIsNotNone(info)