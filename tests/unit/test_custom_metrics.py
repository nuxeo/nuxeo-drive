import re
from time import monotonic_ns
from unittest.mock import patch

import pytest

from nxdrive.constants import MAC, WINDOWS
from nxdrive.exceptions import ThreadInterrupt
from nxdrive.metrics.poll_metrics import CustomPollMetrics
from nxdrive.metrics.utils import current_os, user_agent
from nxdrive.options import Options


class MockedClient:
    request = None


class MockedRemote:
    def __init__(self) -> None:
        self.client = MockedClient


@pytest.fixture
def my_remote():
    return MockedRemote()


def test_without_errors(my_remote):
    """A normal run test, all metrics should be sent."""

    called_count = 0

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request"""
        nonlocal called_count
        called_count += 1

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        metrics.send({"test": "data"})
        metrics.send({"test": "data"})
        metrics.push_sync_event({"handler": "data", "start_ns": monotonic_ns()})
        assert metrics._poll()
        assert called_count == 3
        assert metrics._metrics_queue.empty()


def test_with_some_errors(my_remote):
    """A few exceptions are thrown, ensure metrics are _not_ pushed back in the queue."""

    called_count = 0

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request that raise an Exception"""
        nonlocal called_count
        called_count += 1
        if called_count % 2 == 0:  # even number
            raise Exception("Mock'ed")

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        for _ in range(0, 12):
            metrics.send({"test": "data"})
        assert metrics._poll()
        assert called_count == 12
        assert metrics._metrics_queue.empty()


def test_thread_interrupt(my_remote):
    """A ThreadInterrupt exception is thrown, stopping the poll."""

    called_count = 0

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request that raise a ThreadInterrupt"""
        nonlocal called_count
        called_count += 1
        if called_count == 3:
            raise ThreadInterrupt("Mock'ed")

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        for _ in range(0, 12):
            metrics.send({"test": "data"})
        with pytest.raises(ThreadInterrupt, match="Mock'ed"):
            metrics._poll()
        assert called_count == 3
        assert not metrics._metrics_queue.empty()
        assert metrics._metrics_queue.qsize() == 9


@Options.mock()
def test_disabled_metrics(my_remote):
    """Custom metrics are disabled, nothing is sent."""

    called_count = 0
    Options.custom_metrics = False

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request"""
        nonlocal called_count
        called_count += 1

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        for _ in range(0, 12):
            metrics.send({"test": "data"})
        metrics._poll()
        assert called_count == 0
        assert metrics._metrics_queue.empty()
        assert metrics._metrics_queue.qsize() == 0


def test_current_os():
    if MAC:
        expected = re.compile(r"^macOS \d{2}\.\d{1,2}$")
    elif WINDOWS:
        expected = re.compile(r"^Windows \d{1,2}\.\d{1,2}$")
    else:
        expected = re.compile(r"^\w+ \d{1,2}\.\d{1,2}$")
    assert expected.fullmatch(current_os())


def test_current_os_full():
    if MAC:
        expected = r"^macOS \d{2}\.\d{1,2}\.\d{1,2}$"
    elif WINDOWS:
        expected = r"^Windows \d{1,2}\.\d{1,2}\.\d+$"
    else:
        expected = r"^\w+ \d{1,2}\.\d{1,2}\.\d{1,2}$"
    assert re.fullmatch(expected, current_os(full=True))


def test_user_agent():
    if MAC:
        expected = r"^Nuxeo-Drive/\d{1,2}\.\d{1,2}\.\d{1,2} \(macOS \d{2}\.\d{1,2}\)$"
    elif WINDOWS:
        expected = (
            r"^Nuxeo-Drive/\d{1,2}\.\d{1,2}\.\d{1,2} \(Windows \d{1,2}\.\d{1,2}\)$"
        )
    else:
        expected = r"^Nuxeo-Drive/\d{1,2}\.\d{1,2}\.\d{1,2} \(\w+ \d{1,2}\.\d{1,2}\)$"
    assert re.fullmatch(expected, user_agent())
