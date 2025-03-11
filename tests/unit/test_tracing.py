import pytest
from sentry_sdk import (
    Client,
    scope,
    transport,
)

import nxdrive.tracing

#
# Start Sentry internals.
# See https://github.com/getsentry/sentry-python/blob/0.20.3/tests/conftest.py
#
# This is OK because we need to test Event objects and not the Transport or Hub, or whatever.
#


sc = scope.Scope()

class CustomTransport(transport.Transport):
    def __init__(self):
        super().__init__()
        self._queue = None
        print(f">>>> self._queue: {self._queue!r}")

    def capture_envelope(self):
        print("Returning...")
        return


@pytest.fixture(scope="function")
def sentry_init_custom(monkeypatch):
    def inner(*a, **kw):
        print(f">>>> a: {a!r}")
        print(f">>>> kw: {kw!r}")
        # sc = scope.Scope()
        print(f">>>> sc: {sc!r}")
        client = Client(*a, **kw)
        # client.init()
        print(f">>>> client: {client!r}")
        sc.set_client(client)
        print(f">>>> sc.get_client(): {sc.get_client()!r}")
        monkeypatch.setattr(sc.get_client(), "transport", CustomTransport())

    yield inner


#
# End Sentry internals.
#


def test_flooding_prevention(sentry_init_custom):
    """Ensure that an infinite synchronization due to a unhandled error
    will not explode the Sentry quota.
    """

    def whoopsy(sc):
        """Problematic function ..."""
        print(f">>>>1 sc: {sc!r}")
        try:
            raise ValueError("Mock'ed error")
        except Exception:
            print("EXCP 1")
            sc.capture_exception()

    def whoopsy2():
        """Problematic function ..."""
        try:
            raise ValueError("Mock'ed error")
        except Exception:
            print("EXCP 2")
            sc.capture_exception()

    sentry_init_custom(before_send=nxdrive.tracing.before_send)

    # Ensure there is no event by default
    assert not nxdrive.tracing._EVENTS

    # The first event of an error should be sent
    whoopsy()
    assert len(nxdrive.tracing._EVENTS) == 1

    # Further events on the same error should not be sent
    whoopsy()
    whoopsy()
    assert len(nxdrive.tracing._EVENTS) == 1

    # A new error happens
    whoopsy2()
    assert len(nxdrive.tracing._EVENTS) == 2

    # Again and again ...
    whoopsy2()
    whoopsy2()
    assert len(nxdrive.tracing._EVENTS) == 2
