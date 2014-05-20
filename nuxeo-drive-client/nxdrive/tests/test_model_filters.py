'''
Created on 20 mai 2014

@author: Remi Cattiau
'''
from nxdrive.tests.common import IntegrationTestCase
from nxdrive.model import Filter

class TestModelFilter(IntegrationTestCase):


    def testSimpleFilter(self):
        session = self.controller_1.get_session()
        local_folder=''
        Filter.add(session, local_folder, "/Test/Plop")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 1, "Save of one filter has failed")
        # On purpose to verify that filter not messup if starts with the same value
        Filter.add(session, local_folder, "/Test/Plop2")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 2, "Save of second filter has failed")
        Filter.add(session, local_folder, "/Test/Plop2/SubFolder")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 2, "Save of a filter already filtered has failed")
        Filter.remove(session, local_folder, "/Test/Plop2/SubFor")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 2, "Remove non existing filter has failed")
        Filter.add(session, local_folder, "/Test")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 1, "Adding a more generic filter should resolve of only one filter")
        Filter.remove(session, local_folder, "/Test")
        self.assertEqual(len(Filter.getAll(session, local_folder)), 0, "Remove existing filter has failed")