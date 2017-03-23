# coding: utf-8
""" Simple tests that must be launched first. """

from datetime import datetime
from time import sleep


def test_time_sleep(capsys):
    """ Simple test to check accurancy of time.sleep(). """

    def check_sleep(amount):
        start = datetime.now()
        sleep(amount)
        end = datetime.now()
        delta = end - start
        return delta.seconds + delta.microseconds / 1000000.0

    error = sum(abs(check_sleep(0.1) - 0.1) for _ in range(100)) * 10

    with capsys.disabled():
        print('check: time.sleep() average error is {:0.2}ms'.format(error))
