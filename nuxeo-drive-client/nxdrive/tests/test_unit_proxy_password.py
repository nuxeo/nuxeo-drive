__author__ = 'jowensla'

import unittest

from nxdrive.tests.mocks_for_unit_tests import MockCommandLine
from nxdrive.controller import ProxyPassword
from nxdrive.controller import MissingToken


class ProxyPasswordTest(unittest.TestCase):
    def setUp(self):
        super(ProxyPasswordTest, self).setUp()
        self.cmdline = MockCommandLine()

    def tearDown(self):
        super(ProxyPasswordTest, self).tearDown()
        self.cmdline = None

    def test_happy_path(self):
        """Test the class in its happy path"""
        pp = ProxyPassword(self.cmdline.controller)
        encryptedp = pp.encrypt('halellujah')
        decryptedp = pp.decrypt(encryptedp)
        self.assertEqual(decryptedp, 'halellujah')

    def test_exception(self):
        """Test the class when it throws an exception in the _get_secret method"""
        self.cmdline.controller.mock_server_binding.remote_token = None
        pp = ProxyPassword(self.cmdline.controller)
        with self.assertRaises(Exception) as MissingToken:
            encryptedp = pp.encrypt('halellujah')


if __name__ == "__main__":
    unittest.main()
