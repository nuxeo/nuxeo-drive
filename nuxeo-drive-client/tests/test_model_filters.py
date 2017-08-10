# coding: utf-8
from tests.common_unit_test import UnitTestCase


class TestModelFilter(UnitTestCase):

    def testSimpleFilter(self):
        dao = self.engine_1.get_dao()
        self.engine_1.add_filter("/Test/Plop")
        self.assertEqual(len(dao.get_filters()), 1, "Save of one filter has failed")
        # On purpose to verify that filter not messup if starts with the
        # same value
        self.engine_1.add_filter("/Test/Plop2")
        self.assertEqual(len(dao.get_filters()), 2,
                         "Save of second filter has failed")
        self.engine_1.add_filter("/Test/Plop2/SubFolder")
        self.assertEqual(len(dao.get_filters()), 2,
                         "Save of a filter already filtered has failed")
        self.engine_1.remove_filter("/Test/Plop2/SubFor")
        self.assertEqual(len(dao.get_filters()), 2,
                         "Remove non existing filter has failed")
        self.engine_1.add_filter("/Test")
        self.assertEqual(len(dao.get_filters()), 1,
                         "Adding a more generic filter should resolve of only"
                         " one filter")
        self.engine_1.remove_filter("/Test")
        self.assertEqual(len(dao.get_filters()), 0,
                         "Remove existing filter has failed")
        self.engine_1.add_filter("/Test/Plop")
        self.engine_1.add_filter("/Test/Plop2")
        self.engine_1.add_filter("/Test2/Plop")
        self.engine_1.remove_filter("/Test")
        self.assertEqual(len(dao.get_filters()), 1,
                         "Removing a non existing parent folder filter should"
                         " clear all subfilters")
