'''
Created on 20 mai 2014

@author: Remi Cattiau
'''
from nxdrive.tests.common import IntegrationTestCase
from nxdrive.engine.dao.model import Filter, ServerBinding


class TestModelFilter(IntegrationTestCase):

    def testSimpleFilter(self):
        session = self.controller_1.get_session()
        server_binding = ServerBinding(self.local_test_folder_1,
                                       self.nuxeo_url, self.admin_user)
        Filter.add(session, server_binding, "/Test/Plop")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 1,
                         "Save of one filter has failed")
        # On purpose to verify that filter not messup if starts with the
        # same value
        Filter.add(session, server_binding, "/Test/Plop2")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 2,
                         "Save of second filter has failed")
        Filter.add(session, server_binding, "/Test/Plop2/SubFolder")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 2,
                         "Save of a filter already filtered has failed")
        Filter.remove(session, server_binding, "/Test/Plop2/SubFor")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 2,
                         "Remove non existing filter has failed")
        Filter.add(session, server_binding, "/Test")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 1,
                         "Adding a more generic filter should resolve of only"
                         " one filter")
        Filter.remove(session, server_binding, "/Test")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 0,
                         "Remove existing filter has failed")
        Filter.add(session, server_binding, "/Test/Plop")
        Filter.add(session, server_binding, "/Test/Plop2")
        Filter.add(session, server_binding, "/Test2/Plop")
        Filter.remove(session, server_binding, "/Test")
        self.assertEqual(len(Filter.getAll(session, server_binding)), 1,
                         "Removing a non existing parent folder filter should"
                         " clear all subfilters")
