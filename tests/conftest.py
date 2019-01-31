# coding: utf-8
from contextlib import suppress
from shutil import rmtree

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
        rmtree(tmp_path)


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
