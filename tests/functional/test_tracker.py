from time import monotonic_ns

import pytest

from nxdrive.engine.tracker import Tracker
from nxdrive.options import Options


@Options.mock()
def test_tracker_instance_and_attrs(manager_factory):
    """Naive checks to ensure the class and principal methods are functional."""

    Options.is_frozen = True
    Options.use_analytics = True

    with manager_factory(with_engine=False) as manager:
        tracker = Tracker(manager, uid="")
        assert repr(tracker)


@pytest.mark.parametrize(
    "is_frozen, use_analytics, metrics_shared",
    [
        (False, False, False),
        (False, True, False),
        (True, False, False),
        (True, True, True),
    ],
)
@pytest.mark.parametrize(
    "method, arguments",
    [
        ("send_directedit_open", ("Jean-Michel Jarre - Oxygen", 42)),
        ("send_directedit_open", ("Jean-Michel Jarre - Oxygen.ogg", 42)),
        ("send_directedit_edit", ("Jean-Michel Jarre - Oxygen", 42)),
        ("send_directedit_edit", ("Jean-Michel Jarre - Oxygen.ogg", 42)),
        ("send_direct_transfer", (True, 0)),
        ("send_direct_transfer", (False, 42)),
        (
            "send_sync_event",
            ({"start_ns": monotonic_ns(), "handler": "locally_created"},),
        ),
    ],
)
@Options.mock()
def test_tracker_send_methods(
    is_frozen,
    use_analytics,
    metrics_shared,
    method,
    arguments,
    manager_factory,
    monkeypatch,
):
    def post(*args, **kwargs):
        nonlocal checkpoint
        checkpoint = True

    # We need an engine to test custom dimensions (here it is unused and so we use "_")
    manager, _ = manager_factory()

    Options.is_frozen = is_frozen
    Options.use_analytics = use_analytics
    checkpoint = False

    with manager:
        tracker = Tracker(manager, uid="")
        monkeypatch.setattr(tracker._session, "post", post)
        getattr(tracker, method)(*arguments)

    assert checkpoint is metrics_shared


@pytest.mark.parametrize(
    "is_frozen, use_analytics, metrics_shared",
    [
        (False, False, False),
        (False, True, False),
        (True, False, True),
        (True, True, True),
    ],
)
@pytest.mark.parametrize("method", ["send_hello", "_poll"])
@Options.mock()
def test_tracker_method_without_args(
    is_frozen, use_analytics, metrics_shared, method, manager_factory, monkeypatch
):
    def post(*args, **kwargs):
        nonlocal checkpoint
        checkpoint = True

    # We need an engine to test custom dimensions (here it is unused and so we use "_")
    manager, _ = manager_factory()

    Options.is_frozen = is_frozen
    Options.use_analytics = use_analytics
    checkpoint = False

    with manager:
        tracker = Tracker(manager, uid="")
        monkeypatch.setattr(tracker._session, "post", post)
        getattr(tracker, method)()

    assert checkpoint is metrics_shared
