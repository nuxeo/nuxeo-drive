'''
Created on 2 juil. 2015

@author: Remi Cattiau
'''
import unittest
from nxdrive.engine.blacklist_queue import BlacklistQueue
from time import sleep
from nxdrive.tests.common_unit_test import log


class BlacklistQueueTest(unittest.TestCase):

    def test_delay(self):
        sleep_time = 3
        # Push two items with a delay of 1s
        queue = BlacklistQueue(delay=1)
        interval1 = queue.push(1, "Item1")
        interval2 = queue.push(2, "Item2")
        log.debug('interval1=%d', interval1)
        log.debug('interval2=%d', interval2)
        log.debug('queue:\n%s', str(queue))

        # Verify no item is returned back before 1s
        item = queue.get()
        self.assertIsNone(item)
        sleep(sleep_time)
        # Verify we get the two items now
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
        sleep(sleep_time)
        # We should get the repushed item after 1s wait
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item2")
        self.assertEquals(item.get_id(), 2)
        self.assertEquals(item._count, 2)

        # Repush item with increase
        interval3 = queue.push(3, "Item3")
        log.debug('interval3=%d', interval3)
        item = queue.get()
        self.assertIsNone(item)
        sleep(sleep_time)
        # Verify we get the item now
        item = queue.get()
        self.assertIsNotNone(item)
        self.assertEquals(item.get(), "Item3")
        self.assertEquals(item.get_id(), 3)
        log.debug('queue:\n%s', str(queue))

        for i in range(1, 3):
            queue.repush(item, increase_wait=True)
            log.debug('item after repush:\n%s', str(item))
            log.debug('queue after repush:\n%s', str(queue))
            # sleep time should be at least 2 ** i + 20%
            min_sleep_time = int(0.8 * 2 ** i) - 1
            max_sleep_time = int(1.2 * 2 ** i) + 2
            if min_sleep_time < 0:
                min_sleep_time = 0

            log.debug('min sleep time=%d', min_sleep_time)
            log.debug('max sleep time=%d', max_sleep_time)
            if min_sleep_time > 0:
                log.debug('sleep %d', min_sleep_time)
                sleep(min_sleep_time)
                max_sleep_time -= min_sleep_time
            item = queue.get()
            self.assertIsNone(item)
            log.debug('sleep %d', max_sleep_time)
            sleep(max_sleep_time)
            item = queue.get()
            self.assertIsNotNone(item)
            self.assertEquals(item.get(), "Item3")
            self.assertEquals(item.get_id(), 3)
            self.assertEquals(item._count, i + 1)

    def test_looping(self):
        # Push several items with a delay of 1s
        queue = BlacklistQueue(delay=1)
        queue.push(1, "Item1")
        queue.push(2, "Item2")
        queue.push(3, "Item3")
        queue.push(4, "Item4")
        queue.push(5, "Item5")
        queue.push(6, "Item6")
        queue.push(7, "Item7")
        log.debug('queue:\n%s', str(queue))

        count = 0
        for item in queue.process_items():
            if item:
                log.debug('item: %s', item.get_id())
                count += 1

        self.assertEqual(queue.size(), 7, "queue size has changed")
        self.assertEqual(count, 0, "no item should have been ready for processing")

        sleep_time = 3
        sleep(sleep_time)
        for item in queue.process_items():
            if item:
                log.debug('item: %s', item.get_id())
                count += 1
                queue.repush(item)

        self.assertEqual(queue.size(), 7, "queue size has changed")
        self.assertEqual(count, 7, "all items should have been ready for processing")

        log.debug('queue:\n%s', str(queue))
        count = 0
        for item in queue.process_items():
            if item:
                log.debug('item: %s', item.get_id())
                count += 1

        self.assertEqual(queue.size(), 7, "queue size has changed")
        self.assertEqual(count, 0, "no item should have been ready for processing after repush")

        sleep_time = 4
        sleep(sleep_time)
        log.debug('queue:\n%s', str(queue))
        count = 0
        for item in queue.process_items():
            if item:
                log.debug('item: %s', item.get_id())
                count += 1

        self.assertEqual(queue.size(), 7, "queue size has changed")
        self.assertEqual(count, 7, "all items should have been ready for processing after repush")

        for item in queue.process_items(remove=True):
            log.debug('item: %s', item.get_id())

        self.assertTrue(queue.is_empty(), 'queue is not empty')