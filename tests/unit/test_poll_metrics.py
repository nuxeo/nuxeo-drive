from time import monotonic_ns
from unittest.mock import patch

import pytest

from nxdrive.exceptions import ThreadInterrupt
from nxdrive.metrics.poll_metrics import CustomPollMetrics
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
    """A few exceptions are thrown, some metrics are pushed back in the queue."""

    called_count = 0

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request that raise an Exception"""
        nonlocal called_count
        called_count += 1
        if called_count % 2 == 0:  # Is a pair number
            raise Exception("Mock'ed")

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        for _ in range(0, 12):
            metrics.send({"test": "data"})
        assert metrics._poll()
        assert called_count == 12
        assert not metrics._metrics_queue.empty()
        assert metrics._metrics_queue.qsize() == 6


def test_thread_interrupt(my_remote):
    """A ThreadInterrupt exception is thrown, stopping the _poll."""

    called_count = 0

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request that raise a ThreadInterrupt"""
        nonlocal called_count
        called_count += 1
        if called_count == 3:  # Is a pair number
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

    options = {"custom_metrics": False}
    Options.update(options, setter="local")

    def fake_client_request(self, *_, **__):
        """Mocked'ed client request"""
        nonlocal called_count
        called_count += 1

    with patch.object(my_remote.client, "request", new=fake_client_request):
        metrics = CustomPollMetrics(my_remote)
        for _ in range(0, 12):
            metrics.send({"test": "data"})
        assert not metrics._poll()
        assert called_count == 0
        assert metrics._metrics_queue.empty()
        assert metrics._metrics_queue.qsize() == 0
