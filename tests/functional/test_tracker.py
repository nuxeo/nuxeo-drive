from time import monotonic_ns

from nxdrive.engine.tracker import Tracker


def test_tracker_instance_and_attrs(manager_factory):
    """Naive checks to ensure the class and principal methods are functional."""

    with manager_factory(with_engine=False) as manager:
        tracker = Tracker(manager, uid="")
        assert repr(tracker)

        assert tracker.current_locale
        assert tracker.user_agent


def test_tracker_send_methods(manager_factory, monkeypatch):
    def post(*args, **kwargs):
        pass

    # We need an engine to test custom dimensions (here it is unused and so we use "_")
    manager, _ = manager_factory()

    metrics = {"start_ns": monotonic_ns(), "handler": "locally_created"}

    with manager:
        tracker = Tracker(manager, uid="")
        monkeypatch.setattr(tracker._session, "post", post)

        tracker.send_directedit_open("Jean-Michel Jarre - Oxygen", 42)
        tracker.send_directedit_open("Jean-Michel Jarre - Oxygen.ogg", 42)
        tracker.send_directedit_edit("Jean-Michel Jarre - Oxygen", 42)
        tracker.send_directedit_edit("Jean-Michel Jarre - Oxygen.ogg", 42)
        tracker.send_direct_transfer(True, 0)
        tracker.send_direct_transfer(False, 42)
        tracker.send_sync_event(metrics)
        tracker._poll()
