from pathlib import Path
from time import sleep

import pytest

from nxdrive.engine.blocklist_queue import BlocklistItem, BlocklistQueue


@pytest.mark.randombug("Slow OS")
def test_delay():
    sleep_time = 3

    # Push two items with a delay of 1s
    queue = BlocklistQueue(delay=1)
    queue.push(Path("Item1"))
    queue.push(Path("Item2"))

    # Verify no item is returned back before 1s
    assert not list(queue.get())
    sleep(sleep_time)

    # Verfiy we get the two items now
    item = next(queue.get())
    assert isinstance(item, BlocklistItem)
    assert item.path == Path("Item1")
    item = next(queue.get())
    assert item.path == Path("Item2")
    assert item.count == 1

    # Repush item without increasing delay
    queue.repush(item, increase_wait=False)
    assert not list(queue.get())
    sleep(sleep_time)

    # We should get the repushed item after 1s wait
    item = next(queue.get())
    assert item.path == Path("Item2")
    assert item.count == 2

    # Repush item with increase
    queue.repush(item, increase_wait=True)
    sleep(sleep_time)
    assert not list(queue.get())

    sleep(sleep_time)
    item = next(queue.get())
    assert item.path == Path("Item2")
    assert item.count == 3
    assert not list(queue.get())
