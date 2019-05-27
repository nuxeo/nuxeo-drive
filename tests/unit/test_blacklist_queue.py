# coding: utf-8
from time import monotonic, sleep

from nxdrive.engine.blacklist_queue import BlacklistItem, BlacklistQueue


def increase(item: BlacklistItem, next_try: int = None) -> None:
    item.count += 1
    cur_time = monotonic()
    if next_try is not None:
        item._next_try = next_try + cur_time
    else:
        item._next_try = item.count * item._interval + cur_time


def repush(
    queue: BlacklistQueue, item: BlacklistItem, increase_wait: bool = True
) -> None:
    if increase_wait:
        increase(item)
    else:
        increase(item, next_try=queue._delay)

    with queue._lock:
        queue._queue[item.uid] = item


def test_delay():
    sleep_time = 3

    # Push two items with a delay of 2s
    queue = BlacklistQueue(delay=2)
    queue.push("1", "Item1")
    queue.push("2", "Item2")

    # Verify no item is returned back before 2s
    assert not list(queue.get())
    sleep(sleep_time)

    # Verfiy we get the two items now
    item = next(queue.get())
    assert item.get() == "Item1"
    assert item.uid == "1"
    item = next(queue.get())
    assert item.get() == "Item2"
    assert item.uid == "2"
    assert item.count == 1

    # Repush item without increasing delay
    repush(queue, item, increase_wait=False)
    assert not list(queue.get())
    sleep(sleep_time)

    # We should get the repushed item after 2s wait
    item = next(queue.get())
    assert item.get() == "Item2"
    assert item.uid == "2"
    assert item.count == 2

    # Repush item with increase
    repush(queue, item, increase_wait=True)
    sleep(sleep_time)
    assert not list(queue.get())
    sleep(sleep_time)
    item = next(queue.get())
    assert item.get() == "Item2"
    assert item.uid == "2"
    assert item.count == 3
    assert not list(queue.get())
