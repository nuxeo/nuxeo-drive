from types import SimpleNamespace
from unittest.mock import Mock, call, patch

from nxdrive.drive.metrics.sentry import SentryMetrics
from nxdrive.drive.options import Options


def make_worker(*engines):
    manager = SimpleNamespace(
        engines={str(index): engine for index, engine in enumerate(engines)}
    )
    return SentryMetrics(manager)


@Options.mock()
def test_metrics_are_disabled_without_advanced_analytics():
    engine = Mock()
    worker = make_worker(engine)

    with patch("nxdrive.drive.metrics.sentry.metrics") as metrics:
        worker.send_sync_event({"start_ns": 1, "handler": "upload"})
        worker.send_direct_edit_open("report.pdf", 12)
        worker.send_direct_transfer(False, 42)
        worker.send_stats()

    metrics.distribution.assert_not_called()
    metrics.gauge.assert_not_called()
    engine.get_metrics.assert_not_called()
    worker.stop()


@Options.mock()
def test_sync_timing_is_sent_as_distribution():
    Options.use_analytics = True
    worker = make_worker()

    with patch("nxdrive.drive.metrics.sentry.monotonic_ns", return_value=150), patch(
        "nxdrive.drive.metrics.sentry.metrics.distribution"
    ) as distribution:
        worker.send_sync_event({"start_ns": 100, "handler": "upload"})

    distribution.assert_called_once_with(
        "drive.sync.duration",
        50,
        unit="nanosecond",
        attributes={"handler": "upload"},
    )
    worker.stop()


@Options.mock()
def test_direct_edit_and_transfer_are_sent_as_distributions():
    Options.use_analytics = True
    worker = make_worker()

    with patch("nxdrive.drive.metrics.sentry.metrics.distribution") as distribution:
        worker.send_direct_edit_open("report.PDF", 125)
        worker.send_direct_edit_edit("README", 250)
        worker.send_direct_transfer(False, 2048)
        worker.send_direct_transfer(True, 0)

    assert distribution.call_args_list == [
        call(
            "drive.direct_edit.duration",
            125,
            unit="millisecond",
            attributes={"action": "open", "extension": ".pdf"},
        ),
        call(
            "drive.direct_edit.duration",
            250,
            unit="millisecond",
            attributes={"action": "edit", "extension": "unknown"},
        ),
        call(
            "drive.direct_transfer.size",
            2048,
            unit="byte",
            attributes={"type": "file"},
        ),
        call(
            "drive.direct_transfer.size",
            0,
            unit="byte",
            attributes={"type": "folder"},
        ),
    ]
    worker.stop()


@Options.mock()
def test_hourly_engine_statistics_are_sent_as_gauges():
    Options.use_analytics = True
    first = Mock()
    first.get_metrics.return_value = {
        "sync_files": 12,
        "files_size": 4096,
        "uid": "engine-one",
    }
    second = Mock()
    second.get_metrics.return_value = {"error_files": 2}
    worker = make_worker(first, second)

    with patch("nxdrive.drive.metrics.sentry.metrics.gauge") as gauge:
        assert worker._poll() is True

    assert gauge.call_args_list == [
        call("drive.engine.sync_files", 12),
        call("drive.engine.files_size", 4096),
        call("drive.engine.error_files", 2),
    ]
    worker.stop()
