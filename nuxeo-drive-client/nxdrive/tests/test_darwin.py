import unittest
import sys


class DarwinTest(unittest.TestCase):
    if sys.platform == "darwin":
        def test_folder_registration(self):
            from nxdrive.osi import AbstractOSIntegration
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

        # Others test can be written here.

        # Utils methods
        def _is_folder_registered(self, name):
            from nxdrive.osi import AbstractOSIntegration

            os = AbstractOSIntegration.get(None)
            lst = os._get_favorite_list()
            return os._find_item_in_list(lst, name) is not None

    else:
        @unittest.skip('Skipped test suite on another system than OSX.')
        def test_darwin(self):
            assert 0
