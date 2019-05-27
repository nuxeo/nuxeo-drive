# coding: utf-8
import time
from logging import getLogger
from threading import Lock
from typing import Dict, Generator

__all__ = ("BlacklistQueue",)
log = getLogger(__name__)


class BlacklistItem:
    def __init__(self, item_id: str, item: str, next_try: int = 30) -> None:
        self.uid = item_id
        self._item = item
        self._interval = next_try

        self._next_try = self._interval + time.monotonic()
        self.count = 1

    def check(self, cur_time: float) -> bool:
        return cur_time > self._next_try

    def get(self):
        return self._item


class BlacklistQueue:
    def __init__(self, delay: int = 30) -> None:
        self._delay = delay

        self._queue: Dict[str, BlacklistItem] = dict()
        self._lock = Lock()

    def push(self, id_obj: str, obj: str) -> None:
        log.debug(f"Blacklisting {obj!r}")
        item = BlacklistItem(item_id=id_obj, item=obj, next_try=self._delay)
        with self._lock:
            self._queue[item.uid] = item

    def get(self) -> Generator[BlacklistItem, None, None]:
        cur_time = time.monotonic()
        with self._lock:
            for item in self._queue.copy().values():
                if item.check(cur_time):
                    del self._queue[item.uid]
                    yield item
