def test_simple_filter(engine_dao):
    with engine_dao("engine_migration.db") as dao:
        # There is already 2 tests filters
        assert len(dao.get_filters()) == 2

        # Save of one more filter
        dao.add_filter("/Test/Plop")
        assert len(dao.get_filters()) == 3

        # Save of second filter
        dao.add_filter("/Test/Plop2")
        assert len(dao.get_filters()) == 4

        # Save of a filter already filtered
        dao.add_filter("/Test/Plop2/SubFolder")
        assert len(dao.get_filters()) == 4

        # Remove non existing filter
        dao.remove_filter("/Test/Plop2/SubFor")
        assert len(dao.get_filters()) == 4

        # Adding a more generic filter should resolve of only one filter
        dao.add_filter("/Test")
        assert len(dao.get_filters()) == 3

        # Remove existing filter
        dao.remove_filter("/Test")
        assert dao.get_filters() == ["/fakeFilter/Test_Parent/", "/fakeFilter/Retest/"]

        # Removing a non existing parent folder filter should clear
        # all subfilters
        dao.add_filter("/Test/Plop")
        dao.add_filter("/Test/Plop2")
        dao.add_filter("/Test2/Plop")
        dao.remove_filter("/Test")
        assert len(dao.get_filters()) == 3
        assert dao.get_filters() == [
            "/fakeFilter/Test_Parent/",
            "/fakeFilter/Retest/",
            "/Test2/Plop/",
        ]
