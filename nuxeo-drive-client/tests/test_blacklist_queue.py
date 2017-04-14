'''
Created on 2 juil. 2015

@author: Remi Cattiau
'''
import unittest
from nxdrive.engine.blacklist_queue import BlacklistQueue
from tests.common_unit_test import RandomBug
from time import sleep


class BlacklistQueueTest(unittest.TestCase):

    @RandomBug('NXDRIVE-767', target='mac', mode='BYPASS')
    def test_delay(self):
        sleep_time = 3
        # Push two items with a delay of 1s
        queue = BlacklistQueue(delay=1)
        queue.push(1, "Item1")
        queue.push(2, "Item2")

        # Verify no item is returned back before 1s
        item = queue.get()
        self.assertIsNone(item)
        sleep(sleep_time)

        # Verfiy we get the two items now
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEqual(item.get(), "Item1")
        self.assertEqual(item.get_id(), 1)
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEqual(item.get(), "Item2")
        self.assertEqual(item.get_id(), 2)
        self.assertEqual(item._count, 1)

        # Repush item without increasing delay
        queue.repush(item, increase_wait=False)
        item = queue.get()
        self.assertIsNone(item)
        sleep(sleep_time)

        # We should get the repushed item after 1s wait
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEqual(item.get(), "Item2")
        self.assertEqual(item.get_id(), 2)
        self.assertEqual(item._count, 2)

        # Repush item with increase
        queue.repush(item, increase_wait=True)
        sleep(sleep_time)
        item = queue.get()
        self.assertIsNone(item)
        sleep(sleep_time)
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEqual(item.get(), "Item2")
        self.assertEqual(item.get_id(), 2)
        self.assertEqual(item._count, 3)
        item = queue.get()
        self.assertIsNone(item)
