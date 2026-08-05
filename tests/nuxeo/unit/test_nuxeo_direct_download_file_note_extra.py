"""Focused tests for Nuxeo direct file and note downloads."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from nxdrive.nuxeo.direct_download import DirectDownload

SERVER_HOST = "https://server.test"
SERVER_URL = f"{SERVER_HOST}/nuxeo"
DOWNLOAD_URL = "/nxfile/default/doc/file:content/content.bin"
MISSING = object()


def make_response(*chunks, status_code=200, content_length=MISSING):
    response = Mock()
    response.status_code = status_code
    response.headers = {}
    if content_length is not MISSING:
        response.headers["Content-Length"] = content_length
    response.iter_content.return_value = list(chunks)
    return response


@pytest.fixture()
def downloader(tmp_path):
    manager = Mock()
    manager.engines = {}
    worker = DirectDownload(manager, tmp_path)
    worker._get_download_record = Mock(return_value=None)
    worker._is_single_download_cancelled = Mock(return_value=False)
    worker._update_download_progress = Mock()
    yield worker
    worker.stop()


@pytest.fixture()
def engine():
    result = Mock()
    result.remote.client.host = SERVER_HOST
    result.remote.verification_needed = False
    return result


class TestDirectDownloadNote:
    def test_uses_file_written_by_remote_and_reports_size(
        self, downloader, engine, tmp_path
    ):
        content = b"remote note"

        def write_note(doc_id, *, file_out):
            assert doc_id == "note-id"
            file_out.write_bytes(content)
            return content

        engine.remote.get_note.side_effect = write_note

        downloader._download_note(
            engine,
            "note-id",
            "note.html",
            tmp_path,
            record_uid=17,
        )

        target = tmp_path / "note.html"
        assert target.read_bytes() == content
        engine.remote.get_note.assert_called_once_with("note-id", file_out=target)
        downloader._update_download_progress.assert_called_once_with(
            17, len(content), len(content)
        )

    def test_writes_content_returned_without_a_remote_file(
        self, downloader, engine, tmp_path
    ):
        engine.remote.get_note.return_value = b"inline note"

        downloader._download_note(engine, "note-id", "note.txt", tmp_path)

        target = tmp_path / "note.txt"
        assert target.read_bytes() == b"inline note"
        engine.remote.get_note.assert_called_once_with("note-id", file_out=target)
        downloader._update_download_progress.assert_not_called()

    def test_creates_empty_file_when_remote_returns_no_content(
        self, downloader, engine, tmp_path
    ):
        engine.remote.get_note.return_value = None

        downloader._download_note(engine, "empty-note", "empty.txt", tmp_path)

        assert (tmp_path / "empty.txt").read_bytes() == b""

    def test_propagates_remote_note_failure(self, downloader, engine, tmp_path):
        engine.remote.get_note.side_effect = RuntimeError("note unavailable")

        with pytest.raises(RuntimeError, match="note unavailable"):
            downloader._download_note(engine, "note-id", "note.txt", tmp_path)

        assert not (tmp_path / "note.txt").exists()
        downloader._update_download_progress.assert_not_called()


class TestDirectDownloadFile:
    def test_rejects_missing_download_url(self, downloader, engine, tmp_path):
        with pytest.raises(
            RuntimeError, match="No downloadable content found for 'missing.bin'"
        ):
            downloader._download_file(engine, SERVER_URL, "", "missing.bin", tmp_path)

        engine.remote.client.request.assert_not_called()

    def test_reuses_untracked_duplicate_without_network_request(
        self, downloader, engine, tmp_path
    ):
        target = tmp_path / "cached.bin"
        target.write_bytes(b"cached")

        downloader._download_file(
            engine, SERVER_URL, DOWNLOAD_URL, target.name, tmp_path
        )

        assert target.read_bytes() == b"cached"
        downloader._get_download_record.assert_not_called()
        engine.remote.client.request.assert_not_called()

    def test_reuses_complete_persisted_download(self, downloader, engine, tmp_path):
        target = tmp_path / "complete.bin"
        target.write_bytes(b"stored")
        downloader._get_download_record.return_value = SimpleNamespace(
            total_bytes=6,
            bytes_downloaded=6,
            is_folder=False,
        )

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            target.name,
            tmp_path,
            record_uid=21,
        )

        assert target.read_bytes() == b"stored"
        downloader._get_download_record.assert_called_once_with(21)
        engine.remote.client.request.assert_not_called()

    def test_resumes_partial_download_and_reports_progress(
        self, downloader, engine, tmp_path
    ):
        target = tmp_path / "resume.bin"
        target.write_bytes(b"old")
        downloader._get_download_record.return_value = SimpleNamespace(
            total_bytes=6,
            bytes_downloaded=3,
            is_folder=False,
        )
        response = make_response(b"", b"new", status_code=206, content_length="3")
        engine.remote.client.request.return_value = response

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            target.name,
            tmp_path,
            record_uid=22,
        )

        assert target.read_bytes() == b"oldnew"
        engine.remote.client.request.assert_called_once_with(
            "GET",
            f"/nuxeo{DOWNLOAD_URL}",
            ssl_verify=False,
            stream=True,
            headers={"Range": "bytes=3-"},
        )
        response.raise_for_status.assert_called_once_with()
        response.iter_content.assert_called_once_with(chunk_size=64 * 1024)
        downloader._is_single_download_cancelled.assert_called_once_with(22)
        downloader._update_download_progress.assert_called_once_with(
            22,
            6,
            6,
            filename=target.name,
            emitted_bytes_downloaded=6,
            emitted_total_bytes=6,
        )
        response.close.assert_called_once_with()

    def test_restarts_when_server_ignores_range_and_uses_persisted_total(
        self, downloader, engine, tmp_path
    ):
        target = tmp_path / "restart.bin"
        target.write_bytes(b"partial")
        downloader._get_download_record.return_value = SimpleNamespace(
            total_bytes=11,
            bytes_downloaded=7,
            is_folder=False,
        )
        response = make_response(b"replacement", status_code=200, content_length="11")
        engine.remote.client.request.return_value = response

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            target.name,
            tmp_path,
            record_uid=23,
        )

        assert target.read_bytes() == b"replacement"
        engine.remote.client.request.assert_called_once_with(
            "GET",
            f"/nuxeo{DOWNLOAD_URL}",
            ssl_verify=False,
            stream=True,
            headers={"Range": "bytes=7-"},
        )
        downloader._update_download_progress.assert_called_once_with(
            23,
            11,
            11,
            filename=target.name,
            emitted_bytes_downloaded=11,
            emitted_total_bytes=11,
        )
        response.close.assert_called_once_with()

    def test_folder_resume_reports_batch_and_child_progress(
        self, downloader, engine, tmp_path
    ):
        target = tmp_path / "folder-child.bin"
        target.write_bytes(b"old")
        downloader._get_download_record.return_value = SimpleNamespace(
            total_bytes=100,
            bytes_downloaded=23,
            is_folder=True,
        )
        response = make_response(b"++", status_code=206, content_length="2")
        engine.remote.client.request.return_value = response

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            target.name,
            tmp_path,
            record_uid=24,
        )

        assert target.read_bytes() == b"old++"
        downloader._update_download_progress.assert_called_once_with(
            24,
            25,
            100,
            filename=target.name,
            emitted_bytes_downloaded=5,
            emitted_total_bytes=5,
        )
        response.close.assert_called_once_with()

    def test_range_eof_reuses_existing_file_and_closes_response(
        self, downloader, engine, tmp_path
    ):
        target = tmp_path / "range-eof.bin"
        target.write_bytes(b"complete")
        response = make_response(status_code=416)
        engine.remote.client.request.return_value = response

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            target.name,
            tmp_path,
            record_uid=25,
        )

        assert target.read_bytes() == b"complete"
        engine.remote.client.request.assert_called_once_with(
            "GET",
            f"/nuxeo{DOWNLOAD_URL}",
            ssl_verify=False,
            stream=True,
            headers={"Range": "bytes=8-"},
        )
        response.raise_for_status.assert_not_called()
        response.iter_content.assert_not_called()
        response.close.assert_called_once_with()

    def test_invalid_content_length_streams_without_progress(
        self, downloader, engine, tmp_path
    ):
        response = make_response(b"payload", content_length="invalid")
        engine.remote.client.request.return_value = response

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            "unknown-size.bin",
            tmp_path,
            record_uid=26,
        )

        assert (tmp_path / "unknown-size.bin").read_bytes() == b"payload"
        downloader._is_single_download_cancelled.assert_called_once_with(26)
        downloader._update_download_progress.assert_not_called()
        response.close.assert_called_once_with()

    def test_cancelled_transfer_is_swallowed_and_response_is_closed(
        self, downloader, engine, tmp_path
    ):
        response = make_response(b"new", content_length="3")
        engine.remote.client.request.return_value = response
        downloader._is_single_download_cancelled.return_value = True

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            "cancelled.bin",
            tmp_path,
            record_uid=27,
        )

        assert (tmp_path / "cancelled.bin").read_bytes() == b""
        downloader._update_download_progress.assert_not_called()
        response.close.assert_called_once_with()

    def test_worker_stop_returns_immediately_during_cancelled_transfer(
        self, downloader, engine, tmp_path
    ):
        response = make_response(b"new", content_length="3")
        engine.remote.client.request.return_value = response
        downloader._is_single_download_cancelled.return_value = True
        downloader._stop = True

        downloader._download_file(
            engine,
            SERVER_URL,
            DOWNLOAD_URL,
            "stopped.bin",
            tmp_path,
            record_uid=28,
        )

        assert (tmp_path / "stopped.bin").read_bytes() == b""
        downloader._update_download_progress.assert_not_called()
        response.close.assert_called_once_with()

    def test_stream_integrity_runtime_error_propagates_and_closes_response(
        self, downloader, engine, tmp_path
    ):
        response = make_response(content_length="5")
        response.iter_content.side_effect = RuntimeError("integrity mismatch")
        engine.remote.client.request.return_value = response

        with pytest.raises(RuntimeError, match="integrity mismatch"):
            downloader._download_file(
                engine,
                SERVER_URL,
                DOWNLOAD_URL,
                "corrupt.bin",
                tmp_path,
            )

        assert (tmp_path / "corrupt.bin").read_bytes() == b""
        response.close.assert_called_once_with()

    def test_response_error_propagates_and_closes_response(
        self, downloader, engine, tmp_path
    ):
        response = make_response(content_length="5")
        response.raise_for_status.side_effect = OSError("connection lost")
        engine.remote.client.request.return_value = response

        with pytest.raises(OSError, match="connection lost"):
            downloader._download_file(
                engine,
                SERVER_URL,
                DOWNLOAD_URL,
                "failed.bin",
                tmp_path,
            )

        assert not (tmp_path / "failed.bin").exists()
        response.close.assert_called_once_with()
