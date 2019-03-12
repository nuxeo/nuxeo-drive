# coding: utf-8

import shutil
import sys
from contextlib import suppress

import pytest


pytest_plugins = "tests.pytest_random"


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


@pytest.fixture
def tmp(tmp_path):
    """Use the original *tmp_path* fixture with automatic clean-up."""

    created_folders = []
    n = 0

    def _make_folder():
        nonlocal n
        path = tmp_path / str(n)
        created_folders.append(path)
        n += 1
        return path

    yield _make_folder

    with suppress(OSError):
        shutil.rmtree(tmp_path)


@pytest.fixture(autouse=True)
def no_warnings(recwarn):
    """Fail on warning."""

    yield

    warnings = []
    for warning in recwarn:  # pragma: no cover
        message = str(warning.message)

        if "sentry_sdk" in warning.filename:
            continue

        warn = f"{warning.filename}:{warning.lineno} {message}"
        print(warn, file=sys.stderr)
        warnings.append(warn)

    assert not warnings


@pytest.fixture(autouse=True)
def cleanup_attrs(request):
    """
    Delete any attribute added in the test.
    It will help keeping the memory usage at a descent level.
    """

    # .instance for tests methods
    # .node     for tests functions
    test_case = request.instance or request.node
    attr_orig = set(test_case.__dict__.keys())

    yield

    # Note: if the test failed, this part will not be executed.

    attr_added = set(test_case.__dict__.keys()) - attr_orig
    if not attr_added:
        return

    for attr in attr_added:
        if attr.startswith("engine_"):
            engine = getattr(test_case, attr)
            if engine.remote:
                engine.remote.client._session.close()
        delattr(test_case, attr)
