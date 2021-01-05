def test_simple_filter(engine_dao):
    with engine_dao("manager_migration.db") as dao:

        # Save of one filter
        dao.add_filter("/Test/Plop")
        assert len(dao.get_filters()) == 1

        # Save of second filter
        dao.add_filter("/Test/Plop2")
        assert len(dao.get_filters()) == 2

        # Save of a filter already filtered
        dao.add_filter("/Test/Plop2/SubFolder")
        assert len(dao.get_filters()) == 2

        # Remove non existing filter
        dao.remove_filter("/Test/Plop2/SubFor")
        assert len(dao.get_filters()) == 2

        # Adding a more generic filter should resolve of only one filter
        dao.add_filter("/Test")
        assert len(dao.get_filters()) == 1

        # Remove existing filter
        dao.remove_filter("/Test")
        assert not dao.get_filters()

        # Removing a non existing parent folder filter should clear
        # all subfilters
        dao.add_filter("/Test/Plop")
        dao.add_filter("/Test/Plop2")
        dao.add_filter("/Test2/Plop")
        dao.remove_filter("/Test")
        assert len(dao.get_filters()) == 1
