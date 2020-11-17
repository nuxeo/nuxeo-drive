from unittest.mock import patch

import pytest


@pytest.fixture
def get_changes():
    """Initialize last event log id (lower bound)."""

    def inner(engine, last_root_definitions="", last_event_log_id=0):
        summary = engine.remote.get_changes(
            last_root_definitions, log_id=last_event_log_id
        )
        if "upperBound" in summary:
            last_event_log_id = summary["upperBound"]
        last_root_definitions = summary["activeSynchronizationRootDefinitions"]
        return summary, last_root_definitions, last_event_log_id

    return inner


@pytest.mark.randombug("NXDRIVE-1565: Needed for the server is lagging")
def test_changes_without_active_roots(get_changes, manager_factory):
    manager, engine = manager_factory()
    with manager:
        summary, last_root_definitions, last_event_log_id = get_changes(engine)
        assert not summary["hasTooManyChanges"]
        assert "fileSystemChanges" in summary
        assert "activeSynchronizationRootDefinitions" in summary
        first_timestamp = summary["syncDate"]
        assert first_timestamp > 0
        first_event_log_id = 0
        if "upperBound" in summary:
            first_event_log_id = summary["upperBound"]
            assert first_event_log_id >= 0

        summary, *_ = get_changes(
            engine,
            last_root_definitions=last_root_definitions,
            last_event_log_id=last_event_log_id,
        )
        assert not summary["hasTooManyChanges"]
        assert not summary["fileSystemChanges"]
        assert not summary["activeSynchronizationRootDefinitions"]
        second_timestamp = summary["syncDate"]
        assert second_timestamp >= first_timestamp
        if "upperBound" in summary:
            second_event_log_id = summary["upperBound"]
            assert second_event_log_id >= first_event_log_id


@pytest.mark.parametrize("bad_data", ["not a dict", {"wrong": "dict"}])
def test_wrong_server_reply(bad_data, manager_factory):
    """
    A response that is not a dictionary or that does not contain
    the right entries should not raise an exception.
    It should not modify the attributes we use to track the last
    synchronization either.
    """

    def bad_get_changes(*args, **kwargs):
        return bad_data

    manager, engine = manager_factory()
    sync_date = engine._remote_watcher._last_sync_date
    with manager:
        with patch.object(engine.remote, "get_changes", new=bad_get_changes):
            assert not engine._remote_watcher._get_changes()
            assert engine._remote_watcher._last_sync_date == sync_date
