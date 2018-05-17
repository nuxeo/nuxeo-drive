# coding: utf-8
""" Pytest plugin to mitigate random failures.

    Adapted from github.com/pytest-dev/pytest-rerunfailures
"""

import os

import pytest
from _pytest.runner import runtestprotocol


def get_random(item):
    random = item.get_marker('randombug')
    if random:
        for mark in random._marks:
            if mark.kwargs.get('condition', True):
                return mark
    return None


def get_repeat(item):
    random = get_random(item)
    return random.kwargs.get('repeat', 10) if random else None


def get_mode(item):
    random = get_random(item)
    mode = (item.config.default_mode
            or random.kwargs.get('mode', 'RELAX')) if random else None
    return mode


def get_condition(item):
    random = get_random(item)
    return random.kwargs.get('condition', True) if random else False


def pytest_configure(config):
    """ Set the default mode upon pytest loading. """
    config.default_mode = os.environ.get('RANDOM_BUG_MODE', None)
    config.addinivalue_line(
        "markers",
        "randombug(reason, condition=True, mode='RELAX', repeat=10): "
        "if condition is False, test runs normally, else: "
        "if mode is BYPASS, skip test. "
        "If mode is RELAX, run test until it succeeds or "
        "has ran <repeat> times. "
        "If mode is STRICT, run test until it fails or "
        "has ran <repeat> times. ")


def pytest_collection_modifyitems(items):
    """ Once tests have been collected, skip the ones marked BYPASS. """
    for item in items:
        marker = get_random(item)
        if not marker:
            continue
        mode = get_mode(item)
        if mode == 'BYPASS':
            reason = marker.args[0] if marker.args else ''
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_runtest_protocol(item, nextitem):
    """ runtest_setup/call/teardown protocol implementation. """
    condition = get_condition(item)
    if not condition:
        # The test doesn't have the random marker or doesn't
        # fulfill the condition, so we run the test normally
        return

    repeat = get_repeat(item)
    mode = get_mode(item)

    for i in range(repeat):
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid,
                                           location=item.location)
        reports = runtestprotocol(item, nextitem=nextitem, log=False)

        for report in reports:  # 3 reports: setup, call, teardown
            report.repeat = i

            if mode == 'RELAX':
                condition = not report.failed or hasattr(report, 'wasxfail')
            elif mode == 'STRICT':
                condition = report.failed or report.skipped

            # we only mess with the report if it's a call report
            if i == repeat - 1 or condition or not report.when == 'call':
                # last run or no failure detected, log normally
                item.ihook.pytest_runtest_logreport(report=report)
            else:
                # failure detected and repeat not exhausted, since i < repeat
                report.outcome = 'repeat'
                item.ihook.pytest_runtest_logreport(report=report)

                break  # trigger repeat
        else:
            return True  # no need to repeat
    return True


def pytest_report_teststatus(report):
    if report.outcome == 'repeat':
        return 'repeated', 'R', ('REPEAT', {'yellow': True})
