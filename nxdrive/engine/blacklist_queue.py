# coding: utf-8
import time
from logging import getLogger
from threading import Lock
from typing import Generator

__all__ = ("BlacklistQueue",)
log = getLogger(__name__)


class BlacklistItem:
    def __init__(self, item_id: str, item: str, next_try: int = 30) -> None:
        self.uid = item_id
        self._item = item
        self._interval = next_try

        self._next_try = self._interval + int(time.time())
        self.count = 1

    def check(self, cur_time: int) -> bool:
        return cur_time > self._next_try

    def get(self):
        return self._item

    def increase(self, next_try: int = None) -> None:
        self.count += 1
        cur_time = int(time.time())
        if next_try is not None:
            self._next_try = next_try + cur_time
        else:
            self._next_try = self.count * self._interval + cur_time


class BlacklistQueue:
    def __init__(self, delay: int = 30) -> None:
        self._delay = delay

        self._queue = dict()
        self._lock = Lock()

    def push(self, id_obj: str, obj: str) -> None:
        log.trace(f"Blacklisting {obj!r}")
        item = BlacklistItem(item_id=id_obj, item=obj, next_try=self._delay)
        with self._lock:
            self._queue[item.uid] = item

    def repush(self, item: BlacklistItem, increase_wait: bool = True) -> None:
        if increase_wait:
            item.increase()
        else:
            item.increase(next_try=self._delay)

        with self._lock:
            self._queue[item.uid] = item

    def get(self) -> Generator[BlacklistItem, None, None]:
        cur_time = int(time.time())
        with self._lock:
            for item in list(self._queue.values()):
                if item.check(cur_time):
                    del self._queue[item.uid]
                    yield item
