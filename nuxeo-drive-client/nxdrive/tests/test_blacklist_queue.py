'''
Created on 2 juil. 2015

@author: Remi Cattiau
'''
import unittest
from nxdrive.engine.blacklist_queue import BlacklistQueue
from time import sleep


class BlacklistQueueTest(unittest.TestCase):

    def testDelay(self):
        # Push two items with a delay of 1s
        queue = BlacklistQueue(delay=1)
        queue.push(1, "Item1")
        queue.push(2, "Item2")
        # Verify no item is returned back before 1s
        item = queue.get()
        self.assertIsNone(item)
        sleep(2)
        # Verfiy we get the two items now
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item1")
        self.assertEquals(item.get_id(), 1)
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item2")
        self.assertEquals(item.get_id(), 2)
        self.assertEquals(item._count, 1)
        # Repush item without increasing delay
        queue.repush(item, increase_wait=False)
        item = queue.get()
        self.assertIsNone(item)
        sleep(2)
        # We should get the repushed item after 1s wait
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item2")
        self.assertEquals(item.get_id(), 2)
        self.assertEquals(item._count, 2)
        # Repush item with increase
        queue.repush(item, increase_wait=True)
        sleep(2)
        item = queue.get()
        self.assertIsNone(item)
        sleep(2)
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item2")
        self.assertEquals(item.get_id(), 2)
        self.assertEquals(item._count, 3)
        item = queue.get()
        self.assertIsNone(item)
