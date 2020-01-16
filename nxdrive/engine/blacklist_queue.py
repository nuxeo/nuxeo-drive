# coding: utf-8
from time import monotonic
from logging import getLogger
from pathlib import Path
from threading import Lock
from typing import Dict, Generator

__all__ = ("BlacklistQueue",)
log = getLogger(__name__)


class BlacklistItem:
    def __init__(self, path: Path, next_try: int = 30) -> None:
        self.path = path
        self._interval = next_try

        self._next_try = self._interval + int(monotonic())
        self.count = 1

    def __repr__(self) -> str:
        return f"<{type(self).__name__} path={self.path!r}, count={self.count}>"

    def __str__(self) -> str:
        return repr(self)

    def check(self, cur_time: int) -> bool:
        return cur_time > self._next_try

    def increase(self, next_try: int = None) -> None:
        # Only used in tests, but it is more practical to keep there.
        self.count += 1
        cur_time = int(monotonic())
        if next_try is not None:
            self._next_try = next_try + cur_time
        else:
            self._next_try = self.count * self._interval + cur_time


class BlacklistQueue:
    def __init__(self, delay: int = 30) -> None:
        self._delay = delay

        self._queue: Dict[Path, BlacklistItem] = {}
        self._lock = Lock()

    def __repr__(self) -> str:
        return f"<{type(self).__name__} queue_size={len(self._queue)}>"

    def __str__(self) -> str:
        return repr(self)

    def push(self, path: Path) -> None:
        with self._lock:
            item = BlacklistItem(path, next_try=self._delay)
            log.debug(f"Blacklisting {item!r}")
            self._queue[path] = item

    def repush(self, item: BlacklistItem, increase_wait: bool = True) -> None:
        # Only used in tests, but it is more practical to keep there.
        with self._lock:
            item.increase(next_try=None if increase_wait else self._delay)
            self._queue[item.path] = item

    def get(self) -> Generator[BlacklistItem, None, None]:
        with self._lock:
            cur_time = int(monotonic())
            for item in self._queue.copy().values():
                if not item.check(cur_time):
                    continue

                log.debug(f"Whitelisting {item!r}")
                yield self._queue.pop(item.path)
