"""Unit tests for LocalWatcher._execute() method."""

from pathlib import Path
from queue import Queue
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from nxdrive.constants import ROOT
from nxdrive.exceptions import ThreadInterrupt


def test_execute(tmp_path):
    """Test LocalWatcher._execute() method covering all code paths."""
    from nxdrive.engine.watcher.local_watcher import LocalWatcher

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_engine.manager.osi = Mock()
    mock_engine.queue_manager = Mock()

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)
    watcher.local = mock_local

    # Test Case 1: Root doesn't exist - should emit rootDeleted signal
    mock_local.exists.return_value = False
    signal_emitted = []
    watcher.rootDeleted.connect(lambda: signal_emitted.append(True))

    watcher._execute()

    assert mock_local.exists.called
    assert signal_emitted == [True]
    mock_local.exists.assert_called_once_with(ROOT)

    # Reset for next test
    mock_local.reset_mock()
    signal_emitted.clear()

    # Test Case 2: Normal flow with ThreadInterrupt (non-Windows, non-Linux)
    mock_local.exists.return_value = True

    # Mock the methods called in _execute
    watcher._setup_watchdog = Mock()
    watcher._scan = Mock()
    watcher._update_local_status = Mock()
    watcher._interact = Mock()
    watcher.handle_watchdog_event = Mock()
    watcher._stop_watchdog = Mock()
    watcher._win_delete_check = Mock()
    watcher._win_folder_scan_check = Mock()

    # Create a counter to throw ThreadInterrupt after a few iterations
    interact_call_count = [0]

    def interact_side_effect():
        interact_call_count[0] += 1
        if interact_call_count[0] >= 3:  # Throw after 3 calls
            raise ThreadInterrupt()

    watcher._interact.side_effect = interact_side_effect

    # Execute and expect ThreadInterrupt (patch OS to ensure non-Linux, non-Windows)
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", False
    ):
        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify the flow
        mock_local.exists.assert_called_once_with(ROOT)
        watcher._setup_watchdog.assert_called_once()
        watcher._scan.assert_called_once()
        assert watcher._interact.call_count >= 1
        watcher._stop_watchdog.assert_called_once()  # Finally block executed

    # Reset for next test
    mock_local.reset_mock()
    watcher._setup_watchdog.reset_mock()
    watcher._scan.reset_mock()
    watcher._interact.reset_mock()
    watcher._stop_watchdog.reset_mock()
    watcher._update_local_status.reset_mock()
    interact_call_count[0] = 0

    # Test Case 3: Linux-specific flow with _update_local_status
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", True), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", False
    ):

        def interact_side_effect_linux():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 2:
                raise ThreadInterrupt()

        watcher._interact.side_effect = interact_side_effect_linux

        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify Linux-specific method was called
        watcher._update_local_status.assert_called_once()
        watcher._stop_watchdog.assert_called()

    # Reset for next test
    mock_local.reset_mock()
    watcher._setup_watchdog.reset_mock()
    watcher._scan.reset_mock()
    watcher._update_local_status.reset_mock()
    watcher._interact.reset_mock()
    watcher._stop_watchdog.reset_mock()
    watcher._win_delete_check.reset_mock()
    watcher._win_folder_scan_check.reset_mock()
    interact_call_count[0] = 0

    # Test Case 4: Windows-specific flow with delete and folder scan checks
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", True
    ), patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:

        # Setup time mock to return incrementing values
        time_values = [1000, 1001, 1002, 1003, 1004, 1005]
        mock_time.side_effect = time_values

        # Add an event to the watchdog queue
        watcher.watchdog_queue = Queue()
        mock_event = Mock()
        watcher.watchdog_queue.put(mock_event)

        def interact_side_effect_windows():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 4:
                raise ThreadInterrupt()

        watcher._interact.side_effect = interact_side_effect_windows

        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify Windows-specific behavior
        watcher._setup_watchdog.assert_called_once()
        watcher._scan.assert_called_once()
        watcher.handle_watchdog_event.assert_called_once_with(mock_event)
        # Windows checks should be called multiple times
        assert watcher._win_delete_check.call_count >= 2
        assert watcher._win_folder_scan_check.call_count >= 2
        watcher._stop_watchdog.assert_called_once()

    # Reset for next test
    mock_local.reset_mock()
    watcher._setup_watchdog.reset_mock()
    watcher._scan.reset_mock()
    watcher._interact.reset_mock()
    watcher._stop_watchdog.reset_mock()
    watcher._win_delete_check.reset_mock()
    watcher._win_folder_scan_check.reset_mock()
    watcher.handle_watchdog_event.reset_mock()
    interact_call_count[0] = 0

    # Test Case 5: Multiple watchdog events processing on Windows
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", True
    ), patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:

        mock_time.side_effect = [2000, 2001, 2002, 2003, 2004, 2005, 2006]

        # Add multiple events to the watchdog queue
        watcher.watchdog_queue = Queue()
        mock_event1 = Mock()
        mock_event2 = Mock()
        mock_event3 = Mock()
        watcher.watchdog_queue.put(mock_event1)
        watcher.watchdog_queue.put(mock_event2)
        watcher.watchdog_queue.put(mock_event3)

        def interact_side_effect_multi_events():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 6:  # Allow processing of all events
                raise ThreadInterrupt()

        watcher._interact.side_effect = interact_side_effect_multi_events

        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify all events were processed
        assert watcher.handle_watchdog_event.call_count == 3
        watcher.handle_watchdog_event.assert_any_call(mock_event1)
        watcher.handle_watchdog_event.assert_any_call(mock_event2)
        watcher.handle_watchdog_event.assert_any_call(mock_event3)

        # Verify Windows checks were called after each event
        assert watcher._win_delete_check.call_count >= 3
        assert watcher._win_folder_scan_check.call_count >= 3

        # Verify _interact was called between events (for GUI responsiveness)
        assert watcher._interact.call_count >= 5

    # Reset for next test
    mock_local.reset_mock()
    watcher._setup_watchdog.reset_mock()
    watcher._scan.reset_mock()
    watcher._interact.reset_mock()
    watcher._stop_watchdog.reset_mock()
    watcher._win_delete_check.reset_mock()
    watcher._win_folder_scan_check.reset_mock()
    watcher.handle_watchdog_event.reset_mock()
    interact_call_count[0] = 0

    # Test Case 6: Finally block always executes even without ThreadInterrupt
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", False
    ):

        def interact_side_effect_generic_exception():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 2:
                raise ValueError("Test exception")

        watcher._interact.side_effect = interact_side_effect_generic_exception

        # Generic exceptions should be propagated, but finally should still run
        with pytest.raises(ValueError, match="Test exception"):
            watcher._execute()

        # Verify finally block executed
        watcher._stop_watchdog.assert_called_once()

    # Reset for next test
    mock_local.reset_mock()
    watcher._setup_watchdog.reset_mock()
    watcher._scan.reset_mock()
    watcher._interact.reset_mock()
    watcher._stop_watchdog.reset_mock()
    interact_call_count[0] = 0

    # Test Case 7: Empty queue flow (no events, just sleep cycles)
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", False
    ), patch("nxdrive.engine.watcher.local_watcher.sleep") as mock_sleep:

        watcher.watchdog_queue = Queue()  # Empty queue

        def interact_side_effect_empty_queue():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 3:
                raise ThreadInterrupt()

        watcher._interact.side_effect = interact_side_effect_empty_queue

        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify sleep was called in the main loop
        assert mock_sleep.call_count >= 1
        mock_sleep.assert_called_with(1)

        # Verify no events were handled
        watcher.handle_watchdog_event.assert_not_called()

        # Finally block should still execute
        watcher._stop_watchdog.assert_called_once()

    # Test Case 8: Windows checks after queue processing
    with patch("nxdrive.engine.watcher.local_watcher.LINUX", False), patch(
        "nxdrive.engine.watcher.local_watcher.WINDOWS", True
    ), patch(
        "nxdrive.engine.watcher.local_watcher.current_milli_time"
    ) as mock_time, patch(
        "nxdrive.engine.watcher.local_watcher.sleep"
    ):

        mock_time.side_effect = [3000, 3001, 3002, 3003]

        # Reset mocks
        watcher._win_delete_check.reset_mock()
        watcher._win_folder_scan_check.reset_mock()
        watcher._interact.reset_mock()
        watcher._stop_watchdog.reset_mock()
        interact_call_count[0] = 0

        watcher.watchdog_queue = Queue()  # Empty queue

        def interact_side_effect_windows_checks():
            interact_call_count[0] += 1
            if interact_call_count[0] >= 2:
                raise ThreadInterrupt()

        watcher._interact.side_effect = interact_side_effect_windows_checks

        with pytest.raises(ThreadInterrupt):
            watcher._execute()

        # Verify Windows-specific checks were called after the queue was empty
        assert watcher._win_delete_check.call_count >= 1
        assert watcher._win_folder_scan_check.call_count >= 1


def test_update_local_status(tmp_path):
    """Test LocalWatcher._update_local_status() method covering all code paths."""
    from nxdrive.engine.watcher.local_watcher import LocalWatcher

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_osi = Mock()
    mock_engine.manager.osi = mock_osi

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)
    watcher.local = mock_local
    watcher.dao = mock_dao

    # Test Case 1: Empty list (only ROOT)
    mock_dao.get_states_from_partial_local.return_value = [
        Mock(local_path=ROOT, remote_ref="root_ref")
    ]

    watcher._update_local_status()

    # Verify the method was called with ROOT
    mock_dao.get_states_from_partial_local.assert_called_once_with(ROOT)

    # Verify send_sync_status was NOT called (only ROOT in list, skipped)
    mock_osi.send_sync_status.assert_not_called()

    # Reset mocks
    mock_dao.reset_mock()
    mock_osi.reset_mock()
    mock_local.reset_mock()

    # Test Case 2: Multiple doc_pairs (ROOT + other files)
    root_doc_pair = Mock(local_path=ROOT, remote_ref="root_ref")
    doc_pair1 = Mock(local_path=Path("file1.txt"), remote_ref="ref1")
    doc_pair2 = Mock(local_path=Path("folder/file2.txt"), remote_ref="ref2")
    doc_pair3 = Mock(local_path=Path("another/file3.doc"), remote_ref="ref3")

    mock_dao.get_states_from_partial_local.return_value = [
        root_doc_pair,
        doc_pair1,
        doc_pair2,
        doc_pair3,
    ]

    # Setup abspath return values
    abs_path1 = tmp_path / "file1.txt"
    abs_path2 = tmp_path / "folder" / "file2.txt"
    abs_path3 = tmp_path / "another" / "file3.doc"

    mock_local.abspath.side_effect = [abs_path1, abs_path2, abs_path3]

    watcher._update_local_status()

    # Verify get_states_from_partial_local was called
    mock_dao.get_states_from_partial_local.assert_called_once_with(ROOT)

    # Verify abspath was called for each non-ROOT doc_pair
    assert mock_local.abspath.call_count == 3
    mock_local.abspath.assert_any_call(doc_pair1.local_path)
    mock_local.abspath.assert_any_call(doc_pair2.local_path)
    mock_local.abspath.assert_any_call(doc_pair3.local_path)

    # Verify send_sync_status was called for each non-ROOT doc_pair
    assert mock_osi.send_sync_status.call_count == 3
    mock_osi.send_sync_status.assert_any_call(doc_pair1, abs_path1)
    mock_osi.send_sync_status.assert_any_call(doc_pair2, abs_path2)
    mock_osi.send_sync_status.assert_any_call(doc_pair3, abs_path3)

    # Reset mocks
    mock_dao.reset_mock()
    mock_osi.reset_mock()
    mock_local.reset_mock()
    # Clear side_effect to use return_value
    mock_local.abspath.side_effect = None

    # Test Case 3: Single non-ROOT doc_pair
    single_doc_pair = Mock(local_path=Path("single.txt"), remote_ref="single_ref")

    mock_dao.get_states_from_partial_local.return_value = [
        root_doc_pair,
        single_doc_pair,
    ]

    abs_path_single = tmp_path / "single.txt"
    mock_local.abspath.return_value = abs_path_single

    watcher._update_local_status()

    # Verify the calls
    mock_dao.get_states_from_partial_local.assert_called_once_with(ROOT)
    mock_local.abspath.assert_called_once_with(single_doc_pair.local_path)
    mock_osi.send_sync_status.assert_called_once_with(single_doc_pair, abs_path_single)

    # Reset mocks
    mock_dao.reset_mock()
    mock_osi.reset_mock()
    mock_local.reset_mock()
    # Clear side_effect to use return_value
    mock_local.abspath.side_effect = None

    # Test Case 4: Verify iteration order and that first element is skipped
    doc_pairs_list = [
        Mock(local_path=ROOT, remote_ref="root"),  # This should be skipped
        Mock(local_path=Path("a.txt"), remote_ref="a"),
        Mock(local_path=Path("b.txt"), remote_ref="b"),
        Mock(local_path=Path("c.txt"), remote_ref="c"),
    ]

    mock_dao.get_states_from_partial_local.return_value = doc_pairs_list

    abs_paths = [
        tmp_path / "a.txt",
        tmp_path / "b.txt",
        tmp_path / "c.txt",
    ]

    mock_local.abspath.side_effect = abs_paths

    watcher._update_local_status()

    # Verify abspath and send_sync_status were called in correct order
    expected_abspath_calls = [
        call(doc_pairs_list[1].local_path),
        call(doc_pairs_list[2].local_path),
        call(doc_pairs_list[3].local_path),
    ]
    mock_local.abspath.assert_has_calls(expected_abspath_calls, any_order=False)

    expected_sync_calls = [
        call(doc_pairs_list[1], abs_paths[0]),
        call(doc_pairs_list[2], abs_paths[1]),
        call(doc_pairs_list[3], abs_paths[2]),
    ]
    mock_osi.send_sync_status.assert_has_calls(expected_sync_calls, any_order=False)


def test_win_delete_check(tmp_path):
    """Test LocalWatcher._win_delete_check() method covering all code paths."""
    from nxdrive.engine.watcher.local_watcher import (
        WIN_MOVE_RESOLUTION_PERIOD,
        LocalWatcher,
    )

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_engine.manager.osi = Mock()

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)
    watcher.local = mock_local
    watcher._win_dequeue_delete = Mock()

    # Test Case 1: Early return when _win_delete_interval >= elapsed
    # _win_delete_interval is recent enough that we shouldn't process
    with patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:
        current_time = 10000
        mock_time.return_value = current_time

        # Set _win_delete_interval to a time that is still within the waiting period
        # elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        # if _win_delete_interval >= elapsed, then return early
        elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        watcher._win_delete_interval = elapsed + 100  # Still within waiting period

        watcher._win_delete_check()

        # Verify that _win_dequeue_delete was NOT called (early return)
        watcher._win_dequeue_delete.assert_not_called()

        # Verify that _win_delete_interval was NOT updated
        assert watcher._win_delete_interval == elapsed + 100

    # Reset mock
    watcher._win_dequeue_delete.reset_mock()

    # Test Case 2: Process deletes when enough time has elapsed
    # _win_delete_interval is old enough that we should process
    with patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:
        current_time = 15000
        # First call for elapsed calculation, second call for updating _win_delete_interval
        mock_time.side_effect = [current_time, current_time + 10]

        # Set _win_delete_interval to a time that is older than the waiting period
        elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        watcher._win_delete_interval = elapsed - 100  # Old enough to process

        watcher._win_delete_check()

        # Verify that _win_dequeue_delete was called (processing happened)
        watcher._win_dequeue_delete.assert_called_once()

        # Verify that _win_delete_interval was updated
        assert watcher._win_delete_interval == current_time + 10

    # Reset mock
    watcher._win_dequeue_delete.reset_mock()

    # Test Case 3: Exact boundary condition (_win_delete_interval == elapsed)
    with patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:
        current_time = 20000
        mock_time.side_effect = [current_time, current_time + 5]

        elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        watcher._win_delete_interval = elapsed  # Exactly at the boundary

        watcher._win_delete_check()

        # At boundary, condition is _win_delete_interval >= elapsed, so should return early
        watcher._win_dequeue_delete.assert_not_called()

        # _win_delete_interval should NOT be updated
        assert watcher._win_delete_interval == elapsed

    # Reset mock
    watcher._win_dequeue_delete.reset_mock()

    # Test Case 4: Just past the boundary (_win_delete_interval < elapsed)
    with patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:
        current_time = 25000
        mock_time.side_effect = [current_time, current_time + 15]

        elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        watcher._win_delete_interval = elapsed - 1  # Just past the boundary

        watcher._win_delete_check()

        # Should process deletes
        watcher._win_dequeue_delete.assert_called_once()

        # _win_delete_interval should be updated
        assert watcher._win_delete_interval == current_time + 15

    # Reset mock
    watcher._win_dequeue_delete.reset_mock()

    # Test Case 5: Verify lock is used when processing (by patching the lock)
    with patch("nxdrive.engine.watcher.local_watcher.current_milli_time") as mock_time:
        current_time = 30000
        mock_time.side_effect = [current_time, current_time + 20]

        elapsed = current_time - WIN_MOVE_RESOLUTION_PERIOD
        watcher._win_delete_interval = elapsed - 1000  # Old enough to process

        # Replace lock with a MagicMock to track its usage (supports context manager)
        mock_lock = MagicMock()
        original_lock = watcher.lock
        watcher.lock = mock_lock

        watcher._win_delete_check()

        # Verify lock was used as a context manager
        mock_lock.__enter__.assert_called_once()
        mock_lock.__exit__.assert_called_once()

        # Verify _win_dequeue_delete was called
        watcher._win_dequeue_delete.assert_called_once()

        # Restore original lock
        watcher.lock = original_lock


def test_scan_pair(tmp_path):
    """Test LocalWatcher.scan_pair() method covering all code paths."""
    from nxdrive.engine.watcher.local_watcher import LocalWatcher

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_engine.manager.osi = Mock()
    mock_queue_manager = Mock()
    mock_engine.queue_manager = mock_queue_manager

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)
    watcher.local = mock_local
    watcher._suspend_queue = Mock()
    watcher._scan_recursive = Mock()
    watcher._scan_handle_deleted_files = Mock()

    # Test Case 1: Queue is NOT paused, folder exists
    # Should pause queue, scan, then resume
    mock_queue_manager.is_paused.return_value = False
    test_path = Path("test_folder")
    mock_file_info = Mock()
    mock_local.try_get_info.return_value = mock_file_info

    watcher.scan_pair(test_path)

    # Verify queue operations
    mock_queue_manager.is_paused.assert_called_once()
    watcher._suspend_queue.assert_called_once()
    mock_queue_manager.resume.assert_called_once()

    # Verify scanning operations
    mock_local.try_get_info.assert_called_once_with(test_path)
    watcher._scan_recursive.assert_called_once_with(mock_file_info, recursive=False)
    watcher._scan_handle_deleted_files.assert_called_once()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 2: Queue is already paused, folder exists
    # Should NOT pause/resume queue, but should scan
    mock_queue_manager.is_paused.return_value = True
    test_path2 = Path("another_folder")
    mock_file_info2 = Mock()
    mock_local.try_get_info.return_value = mock_file_info2

    watcher.scan_pair(test_path2)

    # Verify queue was NOT suspended or resumed
    mock_queue_manager.is_paused.assert_called_once()
    watcher._suspend_queue.assert_not_called()
    mock_queue_manager.resume.assert_not_called()

    # Verify scanning operations still happened
    mock_local.try_get_info.assert_called_once_with(test_path2)
    watcher._scan_recursive.assert_called_once_with(mock_file_info2, recursive=False)
    watcher._scan_handle_deleted_files.assert_called_once()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 3: Queue is NOT paused, folder does NOT exist (non-Windows)
    # Should pause/resume queue, skip scanning
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False):
        mock_queue_manager.is_paused.return_value = False
        test_path3 = Path("nonexistent_folder")
        mock_local.try_get_info.return_value = None  # Folder doesn't exist

        watcher.scan_pair(test_path3)

        # Verify queue operations
        mock_queue_manager.is_paused.assert_called_once()
        watcher._suspend_queue.assert_called_once()
        mock_queue_manager.resume.assert_called_once()

        # Verify scanning operations did NOT happen
        mock_local.try_get_info.assert_called_once_with(test_path3)
        watcher._scan_recursive.assert_not_called()
        watcher._scan_handle_deleted_files.assert_not_called()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 4: Queue is already paused, folder does NOT exist (non-Windows)
    # Should NOT pause/resume queue, skip scanning
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False):
        mock_queue_manager.is_paused.return_value = True
        test_path4 = Path("another_nonexistent")
        mock_local.try_get_info.return_value = None

        watcher.scan_pair(test_path4)

        # Verify queue was NOT suspended or resumed
        mock_queue_manager.is_paused.assert_called_once()
        watcher._suspend_queue.assert_not_called()
        mock_queue_manager.resume.assert_not_called()

        # Verify scanning operations did NOT happen
        mock_local.try_get_info.assert_called_once_with(test_path4)
        watcher._scan_recursive.assert_not_called()
        watcher._scan_handle_deleted_files.assert_not_called()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 5: Windows-specific - folder does NOT exist, remove from events
    # Should remove from _folder_scan_events
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", True):
        mock_queue_manager.is_paused.return_value = False
        test_path5 = Path("windows_nonexistent")
        mock_local.try_get_info.return_value = None

        # Pre-populate _folder_scan_events
        watcher._folder_scan_events = {
            test_path5: (1000, Mock()),
            Path("other_path"): (2000, Mock()),
        }

        watcher.scan_pair(test_path5)

        # Verify queue operations
        mock_queue_manager.is_paused.assert_called_once()
        watcher._suspend_queue.assert_called_once()
        mock_queue_manager.resume.assert_called_once()

        # Verify folder was removed from _folder_scan_events
        assert test_path5 not in watcher._folder_scan_events
        assert Path("other_path") in watcher._folder_scan_events

        # Verify scanning operations did NOT happen
        watcher._scan_recursive.assert_not_called()
        watcher._scan_handle_deleted_files.assert_not_called()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 6: Windows-specific - folder does NOT exist, path not in events
    # Should not fail when path not in _folder_scan_events
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", True):
        mock_queue_manager.is_paused.return_value = True
        test_path6 = Path("windows_path_not_in_events")
        mock_local.try_get_info.return_value = None

        # Ensure path is not in _folder_scan_events
        watcher._folder_scan_events = {Path("other_path"): (3000, Mock())}

        watcher.scan_pair(test_path6)

        # Verify queue was NOT suspended or resumed (already paused)
        watcher._suspend_queue.assert_not_called()
        mock_queue_manager.resume.assert_not_called()

        # Verify _folder_scan_events remains unchanged
        assert test_path6 not in watcher._folder_scan_events
        assert Path("other_path") in watcher._folder_scan_events

        # Verify scanning operations did NOT happen
        watcher._scan_recursive.assert_not_called()
        watcher._scan_handle_deleted_files.assert_not_called()

    # Reset mocks
    mock_queue_manager.reset_mock()
    watcher._suspend_queue.reset_mock()
    watcher._scan_recursive.reset_mock()
    watcher._scan_handle_deleted_files.reset_mock()
    mock_local.reset_mock()

    # Test Case 7: Verify recursive=False is passed to _scan_recursive
    mock_queue_manager.is_paused.return_value = False
    test_path7 = Path("verify_recursive_param")
    mock_file_info7 = Mock()
    mock_local.try_get_info.return_value = mock_file_info7

    watcher.scan_pair(test_path7)

    # Verify _scan_recursive was called with recursive=False
    watcher._scan_recursive.assert_called_once()
    call_args = watcher._scan_recursive.call_args
    assert call_args[0][0] == mock_file_info7  # positional arg
    assert call_args[1]["recursive"] is False  # keyword arg


def test_get_creation_time(tmp_path):
    """Test LocalWatcher.get_creation_time() method covering all code paths."""
    from nxdrive.engine.watcher.local_watcher import LocalWatcher

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_engine.manager.osi = Mock()

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)

    # Test Case 1: Windows - returns st_ctime as integer
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", True), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", False
    ):

        # Create a real temp file to get actual stat
        test_file = tmp_path / "windows_test.txt"
        test_file.write_text("test content")

        result = watcher.get_creation_time(test_file)

        # Verify result is an integer (converted from st_ctime)
        assert isinstance(result, int)
        assert result > 0

        # Verify it's approximately the current time (within reason)
        import time

        current_time = int(time.time())
        assert abs(result - current_time) < 3600  # Within an hour

    # Test Case 2: Mac with st_ino attribute - returns st_ino
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", True
    ):

        test_file2 = tmp_path / "mac_test.txt"
        test_file2.write_text("mac content")

        result = watcher.get_creation_time(test_file2)

        # Verify result is the inode number
        assert isinstance(result, int)
        assert result == test_file2.stat().st_ino
        assert result > 0

    # Test Case 3: Mac without st_ino attribute (mocked stat without st_ino)
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", True
    ):

        test_file3 = tmp_path / "mac_no_ino.txt"
        test_file3.write_text("mac no ino content")

        # Mock the stat to not have st_ino
        mock_stat = Mock()
        mock_stat.st_birthtime = 1234567890
        # Explicitly remove st_ino attribute
        del mock_stat.st_ino

        with patch.object(Path, "stat", return_value=mock_stat):
            result = watcher.get_creation_time(test_file3)

            # Should return st_birthtime
            assert result == 1234567890

    # Test Case 4: Non-Mac, non-Windows with st_birthtime - returns st_birthtime
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", False
    ):

        test_file4 = tmp_path / "other_os_test.txt"
        test_file4.write_text("other os content")

        # Mock stat with st_birthtime
        mock_stat = Mock()
        mock_stat.st_birthtime = 9876543210

        with patch.object(Path, "stat", return_value=mock_stat):
            result = watcher.get_creation_time(test_file4)

            # Should return st_birthtime
            assert result == 9876543210

    # Test Case 5: Non-Mac, non-Windows without st_birthtime - returns 0
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", False
    ):

        test_file5 = tmp_path / "no_birthtime.txt"
        test_file5.write_text("no birthtime content")

        # Mock stat without st_birthtime
        mock_stat = Mock(spec=["st_ctime", "st_mtime"])  # Only has ctime and mtime
        del mock_stat.st_birthtime  # Ensure it doesn't have st_birthtime

        with patch.object(Path, "stat", return_value=mock_stat):
            result = watcher.get_creation_time(test_file5)

            # Should return 0
            assert result == 0

    # Test Case 6: Mac with st_ino=0 (edge case)
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", False), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", True
    ):

        test_file6 = tmp_path / "mac_zero_ino.txt"
        test_file6.write_text("mac zero ino content")

        # Mock stat with st_ino=0
        mock_stat = Mock()
        mock_stat.st_ino = 0

        with patch.object(Path, "stat", return_value=mock_stat):
            result = watcher.get_creation_time(test_file6)

            # Should still return 0 (the actual st_ino value)
            assert result == 0

    # Test Case 7: Windows with fractional st_ctime - returns integer part
    with patch("nxdrive.engine.watcher.local_watcher.WINDOWS", True), patch(
        "nxdrive.engine.watcher.local_watcher.MAC", False
    ):

        test_file7 = tmp_path / "windows_fractional.txt"
        test_file7.write_text("fractional time")

        # Mock stat with fractional st_ctime
        mock_stat = Mock()
        mock_stat.st_ctime = 1234567890.123456

        with patch.object(Path, "stat", return_value=mock_stat):
            result = watcher.get_creation_time(test_file7)

            # Should return integer part only
            assert result == 1234567890
            assert isinstance(result, int)


def test_scan_recursive(tmp_path):
    """Test LocalWatcher._scan_recursive() method covering all code paths."""
    from datetime import datetime

    from nxdrive.client.local import FileInfo
    from nxdrive.engine.watcher.local_watcher import LocalWatcher

    # Create mocks
    mock_engine = Mock()
    mock_dao = Mock()
    mock_local = Mock()
    mock_engine.local = mock_local
    mock_engine.manager = Mock()
    mock_engine.manager.osi = Mock()

    # Initialize LocalWatcher
    watcher = LocalWatcher(mock_engine, mock_dao)
    watcher.local = mock_local
    watcher.dao = mock_dao
    watcher._interact = Mock()
    watcher.get_creation_time = Mock(return_value=1000)
    watcher.increase_error = Mock()
    watcher.remove_void_transfers = Mock()
    watcher._metrics = {"new_files": 0, "update_files": 0, "delete_files": 0}
    watcher._protected_files = {}
    watcher._delete_files = {}

    # Test Case 1: OSError when getting FS children (folder deleted)
    parent_info = Mock(spec=FileInfo)
    parent_info.path = Path("/parent")
    parent_info.folderish = True

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.side_effect = OSError("Folder deleted")

    # Should return early without error
    watcher._scan_recursive(parent_info, recursive=False)

    mock_dao.get_local_children.assert_called_once_with(parent_info.path)
    mock_local.get_children_info.assert_called_once_with(parent_info.path)

    # Reset mocks
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._interact.reset_mock()
    mock_local.get_children_info.side_effect = None

    # Test Case 2: New file without remote_id
    parent_info2 = Mock(spec=FileInfo)
    parent_info2.path = Path("/parent2")

    child_info = Mock(spec=FileInfo)
    child_info.path = Path("/parent2/newfile.txt")
    child_info.folderish = False
    child_info.last_modification_time = datetime.now()
    child_info.get_digest = Mock(return_value="abc123")

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.return_value = [child_info]
    mock_local.get_remote_id.side_effect = [None, None]  # parent, child
    mock_dao.get_new_remote_children.return_value = []

    watcher._scan_recursive(parent_info2, recursive=False)

    # Verify new file was inserted
    mock_dao.insert_local_state.assert_called_once_with(child_info, parent_info2.path)
    assert watcher._metrics["new_files"] == 1

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._metrics["new_files"] = 0
    watcher._interact.reset_mock()

    # Test Case 3: File with remote_id - potential move
    parent_info3 = Mock(spec=FileInfo)
    parent_info3.path = Path("/parent3")

    child_info3 = Mock(spec=FileInfo)
    child_info3.path = Path("/parent3/movedfile.txt")
    child_info3.folderish = False
    child_info3.last_modification_time = datetime.now()
    child_info3.get_digest = Mock(return_value="def456")

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.return_value = [child_info3]
    mock_local.get_remote_id.side_effect = [None, "remote123"]
    mock_dao.get_new_remote_children.return_value = []

    # doc_pair doesn't exist in DB
    mock_dao.get_normal_state_from_remote.return_value = None

    watcher._scan_recursive(parent_info3, recursive=False)

    # Should insert as new (locally_created)
    mock_dao.insert_local_state.assert_called_once()
    assert watcher._metrics["new_files"] == 1
    assert "remote123" in watcher._protected_files

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._metrics["new_files"] = 0
    watcher._protected_files = {}
    watcher._interact.reset_mock()

    # Test Case 4: Existing child - update case
    parent_info4 = Mock(spec=FileInfo)
    parent_info4.path = Path("/parent4")

    child_info4 = Mock(spec=FileInfo)
    child_info4.path = Path("/parent4/existingfile.txt")
    child_info4.folderish = False
    child_info4.last_modification_time = datetime(2025, 12, 10, 12, 0, 0)
    child_info4.get_digest = Mock(return_value="newdigest")

    existing_pair = Mock()
    existing_pair.local_name = "existingfile.txt"
    existing_pair.processor = 0
    existing_pair.last_local_updated = "2025-12-10 11:00:00.000"
    existing_pair.remote_ref = "remote456"
    existing_pair.local_path = child_info4.path
    existing_pair.local_digest = "olddigest"
    existing_pair.local_state = "synchronized"

    mock_dao.get_local_children.return_value = [existing_pair]
    mock_local.get_children_info.return_value = [child_info4]
    mock_local.get_remote_id.side_effect = [None, "remote456"]
    mock_dao.get_new_remote_children.return_value = []

    watcher._scan_recursive(parent_info4, recursive=False)

    # Should update the file
    assert watcher._metrics["update_files"] == 1
    assert existing_pair.local_state == "modified"
    assert existing_pair.local_digest == "newdigest"
    mock_dao.update_local_state.assert_called()

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._metrics["update_files"] = 0
    watcher._interact.reset_mock()

    # Test Case 5: Deleted file (in DB but not in FS)
    parent_info5 = Mock(spec=FileInfo)
    parent_info5.path = Path("/parent5")

    deleted_pair = Mock()
    deleted_pair.local_name = "deletedfile.txt"
    deleted_pair.local_path = Path("/parent5/deletedfile.txt")
    deleted_pair.remote_ref = "remote789"
    deleted_pair.pair_state = "synchronized"
    deleted_pair.remote_state = "synchronized"

    mock_dao.get_local_children.return_value = [deleted_pair]
    mock_local.get_children_info.return_value = []  # No FS children
    mock_local.get_remote_id.side_effect = None  # Reset side_effect
    mock_local.get_remote_id.return_value = None
    mock_dao.get_new_remote_children.return_value = []

    watcher._scan_recursive(parent_info5, recursive=False)  # Should mark as deleted
    assert watcher._metrics["delete_files"] == 1
    assert "remote789" in watcher._delete_files
    watcher.remove_void_transfers.assert_called_once_with(deleted_pair)

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._metrics["delete_files"] = 0
    watcher._delete_files = {}
    watcher.remove_void_transfers.reset_mock()
    watcher._interact.reset_mock()

    # Test Case 6: Recursive=True - should call _interact
    parent_info6 = Mock(spec=FileInfo)
    parent_info6.path = Path("/parent6")

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.return_value = []
    mock_local.get_remote_id.return_value = None
    mock_dao.get_new_remote_children.return_value = []

    watcher._scan_recursive(parent_info6, recursive=True)

    # Should call _interact when recursive=True
    watcher._interact.assert_called()

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._interact.reset_mock()

    # Test Case 7: Child in remote_children - skip it
    parent_info7 = Mock(spec=FileInfo)
    parent_info7.path = Path("/parent7")

    child_info7 = Mock(spec=FileInfo)
    child_info7.path = Path("/parent7/remotechild.txt")
    child_info7.folderish = False

    remote_pair = Mock()
    remote_pair.remote_name = "remotechild.txt"

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.return_value = [child_info7]
    mock_local.get_remote_id.side_effect = ["parent_remote", None]
    mock_dao.get_new_remote_children.return_value = [remote_pair]

    initial_new_files = watcher._metrics["new_files"]
    watcher._scan_recursive(parent_info7, recursive=False)

    # Should NOT insert (skip remote creation)
    mock_dao.insert_local_state.assert_not_called()
    assert watcher._metrics["new_files"] == initial_new_files

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._interact.reset_mock()

    # Test Case 8: Exception during child processing - should continue
    parent_info8 = Mock(spec=FileInfo)
    parent_info8.path = Path("/parent8")

    child_info8 = Mock(spec=FileInfo)
    child_info8.path = Path("/parent8/errorfile.txt")
    child_info8.folderish = False

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.return_value = [child_info8]
    mock_local.get_remote_id.side_effect = [None, Exception("Test error")]
    mock_dao.get_new_remote_children.return_value = []

    # Should not raise, just log and continue
    watcher._scan_recursive(parent_info8, recursive=False)

    # Method completed without raising exception
    mock_local.get_children_info.assert_called_once()

    # Reset
    mock_dao.reset_mock()
    mock_local.reset_mock()
    watcher._interact.reset_mock()

    # Test Case 9: Folder child - should be added to to_scan_new
    parent_info9 = Mock(spec=FileInfo)
    parent_info9.path = Path("/parent9")

    folder_child = Mock(spec=FileInfo)
    folder_child.path = Path("/parent9/newfolder")
    folder_child.folderish = True
    folder_child.get_digest = Mock(return_value="")

    # Return folder for parent, empty for child
    def get_children_side_effect(path):
        if path == parent_info9.path:
            return [folder_child]
        return []

    mock_dao.get_local_children.return_value = []
    mock_local.get_children_info.side_effect = get_children_side_effect
    mock_local.get_remote_id.side_effect = lambda path: None  # Always return None
    mock_dao.get_new_remote_children.return_value = []

    # For folders, we just verify insert was called
    watcher._scan_recursive(parent_info9, recursive=False)

    # Should have called insert for new folder
    mock_dao.insert_local_state.assert_called_once_with(folder_child, parent_info9.path)
