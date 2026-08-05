"""Focused tests for shared diagnostic report paths."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

import pytest

from nxdrive.drive import report as report_module
from nxdrive.drive import server_type
from nxdrive.drive.report import Report


def make_report(tmp_path):
    manager = SimpleNamespace(home=tmp_path, engines={}, dao=Mock())
    report = Report(manager, report_path=tmp_path / "reports" / "diagnostic")
    return report, manager


def test_copy_logs_returns_when_log_directory_is_missing(tmp_path):
    report, _ = make_report(tmp_path)
    archive = Mock()

    with patch.object(server_type, "all_configs", return_value={}):
        report.copy_logs(archive)

    archive.write.assert_not_called()


@pytest.mark.parametrize(
    "configs",
    [
        {"shared": SimpleNamespace(log_file="shared.log")},
        [SimpleNamespace(log_file="shared.log")],
    ],
)
def test_copy_logs_filters_files_and_selects_compression(tmp_path, configs):
    report, manager = make_report(tmp_path)
    logs = manager.home / "logs"
    logs.mkdir()
    (logs / "shared.log").write_text("shared log")
    (logs / "segfault.log").write_text("crash log")
    (logs / "rotated.zip").write_bytes(b"archived log")
    (logs / "ignored.txt").write_text("not a log")
    (logs / "nested.log").mkdir()
    archive_path = tmp_path / "logs.zip"

    with patch.object(server_type, "all_configs", return_value=configs), ZipFile(
        archive_path, "w"
    ) as archive:
        report.copy_logs(archive)

    with ZipFile(archive_path) as archive:
        assert set(archive.namelist()) == {
            "logs/shared.log",
            "logs/segfault.log",
            "logs/rotated.zip",
        }
        assert archive.getinfo("logs/shared.log").compress_type == ZIP_DEFLATED
        assert archive.getinfo("logs/segfault.log").compress_type == ZIP_DEFLATED
        assert archive.getinfo("logs/rotated.zip").compress_type == ZIP_STORED


def test_copy_logs_ignores_individual_write_failures(tmp_path):
    report, manager = make_report(tmp_path)
    logs = manager.home / "logs"
    logs.mkdir()
    log_path = logs / "shared.log"
    log_path.write_text("shared log")
    archive = Mock()
    archive.write.side_effect = RuntimeError("cannot add file")
    configs = {"shared": SimpleNamespace(log_file="shared.log")}

    with patch.object(server_type, "all_configs", return_value=configs):
        report.copy_logs(archive)

    archive.write.assert_called_once_with(
        str(log_path),
        str(log_path.relative_to(manager.home)),
        compress_type=ZIP_DEFLATED,
    )


def test_copy_db_checkpoints_and_adds_database(tmp_path):
    db = tmp_path / "shared.db"
    db.write_bytes(b"database")
    dao = SimpleNamespace(db=db, lock=MagicMock(), force_commit=Mock())
    archive_path = tmp_path / "database.zip"

    with ZipFile(archive_path, "w") as archive:
        Report.copy_db(archive, dao)

    dao.force_commit.assert_called_once_with()
    dao.lock.__enter__.assert_called_once_with()
    with ZipFile(archive_path) as archive:
        assert archive.read("shared.db") == b"database"
        assert archive.getinfo("shared.db").compress_type == ZIP_DEFLATED


def test_copy_db_ignores_checkpoint_or_write_failure(tmp_path):
    db = tmp_path / "shared.db"
    dao = SimpleNamespace(
        db=db,
        lock=MagicMock(),
        force_commit=Mock(side_effect=RuntimeError("checkpoint failed")),
    )
    archive = Mock()

    Report.copy_db(archive, dao)

    dao.force_commit.assert_called_once_with()
    archive.write.assert_not_called()


def test_export_logs_returns_nothing_without_memory_handler():
    with patch.object(report_module, "get_handler", return_value=None):
        assert list(Report.export_logs(5)) == []


def test_export_logs_encodes_text_bytes_and_formatting_errors():
    handler = Mock()
    handler.get_buffer.return_value = ["text-record", "bytes-record", "broken"]
    handler.format.side_effect = [
        "formatted text",
        b"formatted bytes",
        ValueError("bad formatter"),
    ]

    with patch.object(report_module, "get_handler", return_value=handler):
        result = list(Report.export_logs(3))

    handler.get_buffer.assert_called_once_with(3)
    assert result == [
        b"formatted text",
        b"formatted bytes",
        b"Logging record error: 'broken'",
    ]


def test_generate_copies_all_databases_and_writes_memory_log(tmp_path):
    report, manager = make_report(tmp_path)
    first_engine_dao = Mock()
    second_engine_dao = Mock()
    manager.engines = {
        "first": SimpleNamespace(dao=first_engine_dao),
        "second": SimpleNamespace(dao=second_engine_dao),
    }

    with patch.object(Report, "copy_db") as copy_db, patch.object(
        Report, "copy_logs"
    ) as copy_logs, patch.object(
        Report, "export_logs", return_value=iter([b"first", b"second"])
    ):
        report.generate()

    assert [args[0][1] for args in copy_db.call_args_list] == [
        manager.dao,
        first_engine_dao,
        second_engine_dao,
    ]
    copy_logs.assert_called_once()
    with ZipFile(report.get_path()) as archive:
        assert archive.read("debug.log") == b"first\nsecond"
        assert archive.getinfo("debug.log").compress_type == ZIP_DEFLATED


def test_generate_ignores_memory_log_export_failure(tmp_path):
    report, _ = make_report(tmp_path)

    with patch.object(Report, "copy_db"), patch.object(
        Report, "copy_logs"
    ), patch.object(
        Report, "export_logs", side_effect=RuntimeError("memory logger failed")
    ):
        report.generate()

    with ZipFile(report.get_path()) as archive:
        assert "debug.log" not in archive.namelist()
