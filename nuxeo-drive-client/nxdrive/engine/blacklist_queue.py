# coding: utf-8
import time
from threading import Lock


class BlacklistItem(object):

    def __init__(self, item_id, item, next_try=30):
        self._count = 1
        self._next_try = None
        self._item = item
        self._item_id = item_id
        self._interval = next_try
        self._next_try = next_try + int(time.time())

    def check(self, cur_time=None):
        if cur_time is None:
            cur_time = int(time.time())
        return cur_time > self._next_try

    def get_id(self):
        return self._item_id

    def get(self):
        return self._item

    def increase(self, next_try=None):
        cur_time = int(time.time())
        self._count += 1
        if next_try is not None:
            self._next_try = next_try + cur_time
        else:
            self._next_try = self._count * self._interval + cur_time


class BlacklistQueue(object):

    def __init__(self, delay=30):
        self._queue = dict()
        self._lock = Lock()
        self._delay = delay

    def push(self, id_obj, obj):
        item = BlacklistItem(item_id=id_obj, item=obj, next_try=self._delay)
        with self._lock:
            self._queue[item.get_id()] = item

    def repush(self, item, increase_wait=True):
        if not isinstance(item, BlacklistItem):
            raise ValueError('Illegal argument')

        if increase_wait:
            item.increase()
        else:
            item.increase(next_try=self._delay)
        with self._lock:
            self._queue[item.get_id()] = item

    def get(self):
        cur_time = int(time.time())
        with self._lock:
            for item in self._queue.values():
                if item.check(cur_time=cur_time):
                    del self._queue[item.get_id()]
                    yield item
