'''
Created on 1 juil. 2015

@author: Remi Cattiau

Updated on Feb 17, 2016

@author: Michael Constantin
'''

from __future__ import division
from threading import RLock
import time
import random
import math


OFFSET_PERCENT = 20
DEFAULT_DELAY = 10


class BlacklistItem(object):

    def __init__(self, item_id, item, next_try=DEFAULT_DELAY, count=1):
        self._count = count
        self._next_try = None
        self._item = item
        self._item_id = item_id
        self._interval = next_try

        next_interval = self._interval * 2 ** (self._count - 1)
        # add a random number between -20% and +20% of the next_try value
        limit = int(math.ceil(next_interval * OFFSET_PERCENT/ 100))
        offset = random.randint(-limit, limit)
        self._next_interval = next_interval + offset
        self._next_try = self._next_interval + int(time.time())

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
            next_interval = self._interval * 2 ** (self._count - 1)
            # add a random number between -20% and +20% of the next_try value
            limit = int(math.ceil(next_interval * OFFSET_PERCENT/ 100))
            offset = random.randint(-limit, limit)
            self._next_interval = next_interval + offset
            self._next_try = self._next_interval + cur_time

    def __repr__(self):
        return 'id={}, item={}, count={}, interval={}, next interval={}'\
            .format(self._item_id, self._item, self._count, self._interval, self._next_interval)


class BlacklistQueue(object):

    def __init__(self, delay=DEFAULT_DELAY):
        self._queue = dict()
        self._lock = RLock()
        self._delay = delay

    def push(self, id_obj, obj, count=1):
        item = BlacklistItem(item_id=id_obj, item=obj, next_try=self._delay, count=count)
        self._lock.acquire()
        try:
            self._queue[item.get_id()] = item
            return item._next_interval
        finally:
            self._lock.release()

    def repush(self, item, increase_wait=True):
        if not isinstance(item, BlacklistItem):
            raise Exception("Illegal argument")
        if increase_wait:
            item.increase()
        else:
            item.increase(next_try=self._delay)
        self._lock.acquire()
        try:
            self._queue[item.get_id()] = item
            return item._next_interval
        finally:
            self._lock.release()

    def repush_by_id(self, item_id, increase_wait=True):
        item = None
        self._lock.acquire()
        try:
            item = self._queue[item_id]
        finally:
            self._lock.release()

        if item is not None:
            return self.repush(item, increase_wait=increase_wait)

    def get(self):
        cur_time = int(time.time())
        self._lock.acquire()
        try:
            for item in self._queue.values():
                if item.check(cur_time=cur_time):
                    del self._queue[item.get_id()]
                    return item
        finally:
            self._lock.release()

    def process_items(self, remove=True):
        cur_time = int(time.time())
        self._lock.acquire()
        try:
            for item in self._queue.values():
                if item.check(cur_time=cur_time):
                    if remove:
                        del self._queue[item.get_id()]
                    yield item
        finally:
            self._lock.release()

    def remove(self, item_id):
        try:
            del self._queue[item_id]
        except KeyError:
            pass

    def is_empty(self):
        self._lock.acquire()
        try:
            return not self._queue
        finally:
            self._lock.release()

    def exists(self, item_id):
        self._lock.acquire()
        try:
            return item_id in self._queue
        finally:
            self._lock.release()

    def size(self):
        self._lock.acquire()
        try:
            return len(self._queue)
        finally:
            self._lock.release()

    def items(self):
        self._lock.acquire()
        try:
            return self._queue.values()
        finally:
            self._lock.release()

    def __repr__(self):
        queue_data = '\n'.join(['\t' + str(item) for item in self._queue.values()])
        return 'delay={}\nqueue=\n{}'.format(self._delay, queue_data)
