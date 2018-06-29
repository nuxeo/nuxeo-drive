# coding: utf-8
import time
from threading import Lock

__all__ = ('BlacklistQueue',)


class BlacklistItem:

    def __init__(self, item_id, item, next_try=30):
        self.uid = item_id
        self._item = item
        self._interval = next_try

        self._next_try = self._interval + int(time.time())
        self.count = 1

    def check(self, cur_time):
        return cur_time > self._next_try

    def get(self):
        return self._item

    def increase(self, next_try=None):
        self.count += 1
        cur_time = int(time.time())
        if next_try is not None:
            self._next_try = next_try + cur_time
        else:
            self._next_try = self.count * self._interval + cur_time


class BlacklistQueue:

    def __init__(self, delay=30):
        self._delay = delay

        self._queue = dict()
        self._lock = Lock()

    def push(self, id_obj, obj):
        item = BlacklistItem(item_id=id_obj, item=obj, next_try=self._delay)
        with self._lock:
            self._queue[item.uid] = item

    def repush(self, item, increase_wait=True):
        if increase_wait:
            item.increase()
        else:
            item.increase(next_try=self._delay)

        with self._lock:
            self._queue[item.uid] = item

    def get(self):
        cur_time = int(time.time())
        with self._lock:
            for item in self._queue.values():
                if item.check(cur_time):
                    del self._queue[item.uid]
                    yield item
