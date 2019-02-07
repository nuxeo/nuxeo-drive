# coding: utf-8
import os
import sys

import pytest

pytest_plugins = "tests.pytest_random"


# pytest marker to skip tests based on data coming from Jenkins (not public)
jenkins_only = pytest.mark.skipif(
    "JENKINS_URL" not in os.environ, reason="Must be ran from Jenkins."
)


@pytest.hookimpl(trylast=True, hookwrapper=True)
def pytest_runtest_makereport():
    """
    Delete captured logs if the test is not in failure.
    It will help keeping the memory usage at a descent level.
    """

    # Execute the test
    outcome = yield

    # Get the report
    report = outcome.get_result()

    if report.passed:
        # Remove captured logs to free memory
        report.sections = []
        outcome.force_result(report)


@pytest.fixture(autouse=True)
def cleanup_attrs(request):
    """
    Delete any attribute added in the test.
    It will help keeping the memory usage at a descent level.
    """
    if not request.instance:
        yield
    else:
        attr_orig = set(request.instance.__dict__.keys())
        yield
        for attr in set(request.instance.__dict__.keys()) - attr_orig:
            if attr.startswith("engine_"):
                engine = getattr(request.instance, attr)
                if engine.remote:
                    engine.remote.client._session.close()
            delattr(request.instance, attr)


@pytest.fixture(autouse=True)
def no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)
        # ImportWarning: Not importing directory '...' missing __init__(.py)
        if not (
            isinstance(warning.message, ImportWarning)
            and message.startswith("Not importing directory ")
            and " missing __init__" in message
            and "sentry_sdk" in message
        ):
            warnings.append(f"{warning.filename}:{warning.lineno} {message}")
    assert not warnings


@pytest.fixture(autouse=True)
def ensure_no_exception(request):
    """No exception must pass under the radar!"""

    def error(type_, value, traceback) -> None:
        """ Install an exception hook to catch any error. """
        nonlocal received
        received = True
        print(type_)
        print(value)
        print(repr(traceback))

    received = False
    excepthook, sys.excepthook = sys.excepthook, error

    try:
        yield 2
    finally:
        sys.excepthook = excepthook
        assert not received, "Unhandled exception raised!"
