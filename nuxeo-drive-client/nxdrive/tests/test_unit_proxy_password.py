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


if __name__ == "__main__":
    unittest.main()
