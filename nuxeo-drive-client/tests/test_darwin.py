# coding: utf-8
import unittest

from nxdrive.osi import AbstractOSIntegration


class DarwinTest(unittest.TestCase):
    if AbstractOSIntegration.is_mac() and not AbstractOSIntegration.os_version_below("10.10"):
        def test_folder_registration(self):

            try:
                name = "TestCazz"

                # Unregister first; to ensure favorite bar is cleaned.
                os = AbstractOSIntegration.get(None)
                os.unregister_folder_link(name)
                self.assertFalse(self._is_folder_registered(name))

                os.register_folder_link(".", name)
                self.assertTrue(self._is_folder_registered(name))

                os.unregister_folder_link(name)
                self.assertFalse(self._is_folder_registered(name))

                assert 1
            except ImportError:
                # Sometimes you cannot import LSSharedFileListCreate
                pass

        # Others test can be written here.

        # Utils methods
        def _is_folder_registered(self, name):

            os = AbstractOSIntegration.get(None)
            lst = os._get_favorite_list()
            return os._find_item_in_list(lst, name) is not None

    else:
        @unittest.skip('Skipped test suite on another system than OSX.')
        def test_darwin(self):
            assert 0
