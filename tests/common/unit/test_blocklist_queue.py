"""Unit tests for nxdrive.drive.engine.blocklist_queue module."""

import time
from pathlib import Path

from nxdrive.drive.engine.blocklist_queue import BlocklistItem, BlocklistQueue


class TestBlocklistItem:
    def test_creation(self):
        item = BlocklistItem(Path("/tmp/f.txt"), next_try=10)
        assert item.path == Path("/tmp/f.txt")
        assert item.count == 1

    def test_repr(self):
        item = BlocklistItem(Path("file.txt"))
        assert "file.txt" in repr(item)
        assert "count=1" in repr(item)

    def test_str_same_as_repr(self):
        item = BlocklistItem(Path("file.txt"))
        assert str(item) == repr(item)

    def test_check_before_interval(self):
        item = BlocklistItem(Path("f.txt"), next_try=9999)
        assert item.check(0) is False

    def test_check_after_interval(self):
        item = BlocklistItem(Path("f.txt"), next_try=0)
        # After creation with next_try=0, _next_try = monotonic()
        # So any time far in the future should pass
        assert item.check(int(time.monotonic()) + 100) is True

    def test_increase_increments_count(self):
        item = BlocklistItem(Path("f.txt"), next_try=5)
        item.increase()
        assert item.count == 2
        item.increase()
        assert item.count == 3

    def test_increase_with_explicit_next_try(self):
        item = BlocklistItem(Path("f.txt"), next_try=5)
        item.increase(next_try=0)
        assert item.count == 2
        # Should be checkable almost immediately
        assert item.check(int(time.monotonic()) + 1) is True


class TestBlocklistQueue:
    def test_empty_on_creation(self):
        q = BlocklistQueue(delay=30)
        assert q.empty() is True

    def test_repr(self):
        q = BlocklistQueue()
        assert "queue_size=0" in repr(q)

    def test_push_makes_non_empty(self):
        q = BlocklistQueue(delay=30)
        q.push(Path("/tmp/f.txt"))
        assert q.empty() is False

    def test_get_empty_queue(self):
        q = BlocklistQueue(delay=30)
        items = list(q.get())
        assert items == []

    def test_get_before_delay_returns_nothing(self):
        q = BlocklistQueue(delay=9999)
        q.push(Path("/tmp/f.txt"))
        items = list(q.get())
        assert items == []

    def test_get_after_delay_returns_item(self):
        q = BlocklistQueue(delay=0)
        q.push(Path("/tmp/f.txt"))
        # delay=0 means _next_try = 0 + int(monotonic()) which is current time
        # We need cur_time > _next_try, so wait a moment
        time.sleep(0.05)
        items = list(q.get())
        # With delay=0, _next_try equals the monotonic time at push.
        # get() checks cur_time > _next_try (strict >), so we need
        # at least 1 second to pass. Instead, manipulate the item directly.
        if not items:
            # Access internal queue and force the item to be ready
            with q._lock:
                for item in q._queue.values():
                    item._next_try = 0
            items = list(q.get())
        assert len(items) == 1
        assert items[0].path == Path("/tmp/f.txt")
        assert q.empty() is True

    def test_repush(self):
        q = BlocklistQueue(delay=0)
        q.push(Path("/tmp/f.txt"))
        # Force the item to be retrievable
        with q._lock:
            for item in q._queue.values():
                item._next_try = 0
        items = list(q.get())
        assert len(items) == 1
        q.repush(items[0], increase_wait=False)
        assert q.empty() is False
