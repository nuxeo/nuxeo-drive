"""
Pytest plugin to mitigate random failures.
Adapted from github.com/pytest-dev/pytest-rerunfailures
"""

import os

import pytest
from _pytest.runner import runtestprotocol


def get_random(item):
    for random in item.iter_markers("randombug"):
        if random.kwargs.get("condition", True):
            return random
    return None


def get_repeat(item):
    random = get_random(item)
    return random.kwargs.get("repeat", 10) if random else None


def get_mode(item):
    random = get_random(item)
    mode = (
        (item.config.default_mode or random.kwargs.get("mode", "RELAX"))
        if random
        else None
    )
    if mode not in {"RELAX", "STRICT", "BYPASS"}:
        mode = "RELAX"
    return mode


def get_condition(item):
    random = get_random(item)
    return random.kwargs.get("condition", True) if random else False


def pytest_configure(config):
    """Set the default mode upon pytest loading."""
    config.default_mode = os.environ.get("RANDOM_BUG_MODE", None)
    if config.default_mode not in {"RELAX", "STRICT", "BYPASS"}:
        config.default_mode = None
    config.addinivalue_line(
        "markers",
        'randombug(reason, condition=True, mode="RELAX", repeat=10): Random failures management.'
        "\nIf the *condition* is False, the test runs normally. Else the behavior is driven by the *mode*:"
        "\n  - BYPASS: Skip the test."
        "\n  - RELAX: Run the test until it succeeds or "
        "has ran <repeat> times."
        "\n  - STRICT: Run the test until it fails or "
        "has ran <repeat> times. Will fail in case of no failure.",
    )


def pytest_collection_modifyitems(items):
    """Once tests have been collected, skip the ones marked BYPASS."""
    for item in items:
        marker = get_random(item)
        if not marker:
            continue
        mode = get_mode(item)
        if mode == "BYPASS":
            reason = marker.args[0] if marker.args else ""
            item.add_marker(pytest.mark.skip(reason=reason))


def pytest_runtest_protocol(item, nextitem):
    """runtest_setup/call/teardown protocol implementation."""
    condition = get_condition(item)
    if not condition:
        # The test doesn't have the random marker or doesn't
        # fulfill the condition, so we run the test normally
        return

    repeat = get_repeat(item)
    mode = get_mode(item)

    for i in range(repeat):
        item.ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)
        reports = runtestprotocol(item, nextitem=nextitem, log=False)

        for report in reports:  # 3 reports: setup, call, teardown
            report.total_repeat = repeat
            report.repeat = i

            if mode == "RELAX":
                condition = not report.failed or hasattr(report, "wasxfail")
            elif mode == "STRICT":
                condition = report.failed or report.skipped

            # we only mess with the report if it's a call report
            if i == repeat - 1 or condition or report.when != "call":
                # last run or no failure detected
                if mode == "STRICT" and i == repeat - 1 and report.when == "call":
                    # in STRICT mode, if the it never fails, then fail completely
                    report.outcome = "failed"
                    report.sections.append(
                        ("", f"The test {item.nodeid!r} is no more instable.")
                    )

                # log normally
                item.ihook.pytest_runtest_logreport(report=report)
            else:
                # failure detected and repeat not exhausted, since i < repeat
                report.outcome = "repeat"
                item.ihook.pytest_runtest_logreport(report=report)

                break  # trigger repeat
        else:
            return True  # no need to repeat
    return True


def pytest_report_teststatus(report):
    if report.outcome == "repeat":
        return (
            "repeated",
            "R",
            (
                f"REPEATED {report.repeat + 1:2d}/{report.total_repeat}",
                {"yellow": True},
            ),
        )
