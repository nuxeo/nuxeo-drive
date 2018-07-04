# coding: utf-8
from .common import UnitTestCase


class TestModelFilter(UnitTestCase):
    def test_simple_filter(self):
        dao = self.engine_1.get_dao()

        # Save of one filter
        self.engine_1.add_filter("/Test/Plop")
        assert len(dao.get_filters()) == 1

        # Save of second filter
        self.engine_1.add_filter("/Test/Plop2")
        assert len(dao.get_filters()) == 2

        # Save of a filter already filtered
        self.engine_1.add_filter("/Test/Plop2/SubFolder")
        assert len(dao.get_filters()) == 2

        # Remove non existing filter
        self.engine_1.remove_filter("/Test/Plop2/SubFor")
        assert len(dao.get_filters()) == 2

        # Adding a more generic filter should resolve of only one filter
        self.engine_1.add_filter("/Test")
        assert len(dao.get_filters()) == 1

        # Remove existing filter
        self.engine_1.remove_filter("/Test")
        assert not (dao.get_filters())

        # Removing a non existing parent folder filter should clear
        # all subfilters
        self.engine_1.add_filter("/Test/Plop")
        self.engine_1.add_filter("/Test/Plop2")
        self.engine_1.add_filter("/Test2/Plop")
        self.engine_1.remove_filter("/Test")
        assert len(dao.get_filters()) == 1
