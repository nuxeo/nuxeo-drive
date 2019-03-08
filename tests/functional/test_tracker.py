from nuxeo.models import Blob
from nxdrive.engine.tracker import Tracker


def test_tracker_instance_and_attrs(manager_factory):
    """Naive checks to ensure the class and principal methods are functional."""

    with manager_factory(with_engine=False) as manager:
        tracker = Tracker(manager, uid="")
        assert repr(tracker)

        assert tracker.current_locale
        assert tracker.user_agent


def test_tracker_send_methods(manager_factory, monkeypatch):
    def send(**kwargs):
        pass

    # We need an engine to test custom dimensions (here it is unused and so we use "_")
    manager, _ = manager_factory()

    metrics = {
        "start_time": 0,
        "end_time": 42,
        "speed": 42,
        "handler": "test_tracker_send_methods",
    }
    blob = Blob(
        uploaded=False, name="Jean-Michel Jarre - Oxygen", size=42, mimetype="audio/ogg"
    )

    with manager:
        tracker = Tracker(manager, uid="")
        monkeypatch.setattr(tracker._tracker, "send", send)

        tracker._send_directedit_open(blob)
        tracker._send_directedit_edit(blob)
        tracker._send_sync_event(metrics)
        tracker._send_stats()
