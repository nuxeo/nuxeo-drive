"""
Functional test for nxdrive/engine/watcher/local_watcher.py
"""

from unittest.mock import patch

import pytest

from nxdrive.engine.watcher.local_watcher import LocalWatcher


def test_execute(manager_factory):
    """
    watchdog_queue is empty
    """
    from nxdrive.exceptions import ThreadInterrupt

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    with patch(
        "nxdrive.client.local.base.LocalClientMixin.exists"
    ) as mock_exists, patch("nxdrive.engine.workers.Worker._interact") as mock_interact:
        mock_exists.return_value = True
        mock_interact.return_value = True
        mock_interact.side_effect = ThreadInterrupt("dummy_interrupt_process")
        local_watcher.watchdog_queue.put(item="data", block=False, timeout=1.0)
        with pytest.raises(ThreadInterrupt) as ex:
            local_watcher._execute()
        assert (
            ex.exconly()
            == "nxdrive.exceptions.ThreadInterrupt: dummy_interrupt_process"
        )


# def test_execute_watchdog(manager_factory):
#     # This test needs to be completed after sometime, to avoid triggering infinite loop
#     '''
#     watchdog_queue is NOT empty
#     '''
#     from nxdrive.exceptions import ThreadInterrupt

#     manager, engine = manager_factory()
#     print(manager_factory())
#     remote = engine.remote
#     dao = remote.dao
#     local_watcher = LocalWatcher(engine, dao)
#     with patch("nxdrive.client.local.base.LocalClientMixin.exists") as mock_exists,\
#         patch("nxdrive.engine.workers.Worker._interact") as mock_interact,\
#         patch("nxdrive.engine.watcher.local_watcher.LocalWatcher.handle_watchdog_event") as mock_handle:
#         mock_exists.return_value = True
#         mock_interact.return_value = True
#         mock_interact.side_effect = ThreadInterrupt("dummy_interrupt_process")
#         mock_handle.return_value = None
#         local_watcher.watchdog_queue.put(item="data",block=False,timeout=1.0)
#         with pytest.raises(ThreadInterrupt) as ex:
#             local_watcher._execute()
#         assert ex.exconly() == 'nxdrive.exceptions.ThreadInterrupt: dummy_interrupt_process'


def test_update_local_status(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher._update_local_status() is None


def test_win_queue_empty(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.win_queue_empty() is True


def test_get_win_queue_size(manager_factory):
    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    assert local_watcher.get_win_queue_size() == 0


def test_win_delete_check(manager_factory):
    from time import time

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._win_delete_interval = int(round(time() * 1000) - 20000)
    assert local_watcher._win_delete_check() is None


def test_win_dequeue_delete(manager_factory):
    from time import time

    manager, engine = manager_factory()
    remote = engine.remote
    dao = remote.dao
    local_watcher = LocalWatcher(engine, dao)
    local_watcher._win_delete_interval = int(round(time() * 1000) + 20000)
    assert local_watcher._win_delete_check() is None
