"""Coverage for shared logging, path utilities, and local-client fallbacks."""

import errno
import http.client
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, Mock, call
from zipfile import ZipFile

import pytest

from nxdrive.drive import logging_config
from nxdrive.drive import utils as drive_utils
from nxdrive.drive.client.local import base as local_base
from nxdrive.drive.client.local.base import FileInfo, LocalClientMixin


@pytest.fixture
def rotating_handler(tmp_path):
    handler = logging_config.TimedCompressedRotatingFileHandler(
        str(tmp_path / "drive.log"), "midnight", 2
    )
    yield handler
    handler.close()


def test_rotated_file_discovery_and_compression(rotating_handler, tmp_path):
    rotated = tmp_path / "drive.log.2026-08-01"
    rotated.write_bytes(b"rotated log")

    assert rotated in list(rotating_handler.find_rotated_files())
    rotating_handler.compress(rotated)

    archive = Path(f"{rotated}.zip")
    assert not rotated.exists()
    with ZipFile(archive) as zipped:
        assert zipped.read(rotated.name) == b"rotated log"


def test_compress_all_skips_archives_and_ignores_os_errors(rotating_handler, tmp_path):
    first = tmp_path / "drive.log.2026-08-01"
    second = tmp_path / "drive.log.2026-08-02"
    archive = tmp_path / "drive.log.2026-08-03.zip"
    compress = Mock(side_effect=[None, OSError("busy")])
    rotating_handler.find_rotated_files = Mock(return_value=[first, archive, second])
    rotating_handler.compress = compress

    rotating_handler.compress_all()

    assert compress.call_args_list == [call(first), call(second)]


def test_remove_old_files_purges_only_old_archives(rotating_handler, tmp_path):
    rotating_handler.backupCount = 1
    oldest = tmp_path / "drive.log.2026-08-01.zip"
    middle = tmp_path / "drive.log.2026-08-02.zip"
    newest = tmp_path / "drive.log.2026-08-03.zip"
    for path in (oldest, middle, newest):
        path.touch()

    rotating_handler.remove_old_files()

    assert newest.exists()
    assert not middle.exists()
    assert not oldest.exists()


def test_rollover_runs_compression_cleanup(rotating_handler):
    rotating_handler.stream.write("before rollover\n")
    rotating_handler.stream.flush()
    rotating_handler.compress_and_purge = Mock()

    rotating_handler.doRollover()

    rotating_handler.compress_and_purge.assert_called_once_with()


def test_configure_updates_existing_file_handler_and_debug_http(monkeypatch):
    memory = Mock()
    console = Mock()
    file_handler = Mock()
    handlers = {
        "memory": memory,
        "nxdrive_console": console,
        "nxdrive_file": file_handler,
    }
    monkeypatch.setattr(logging_config, "is_logging_configured", False)
    monkeypatch.setattr(logging_config, "get_handler", handlers.get)
    monkeypatch.setenv("LOG_EVERYTHING", "1")
    monkeypatch.setattr(http.client.HTTPConnection, "debuglevel", 0)

    root = logging.getLogger()
    original_level = root.level
    try:
        logging_config.configure(log_filename=None, file_level="INFO")
    finally:
        root.setLevel(original_level)

    file_handler.setLevel.assert_called_once_with("INFO")
    assert http.client.HTTPConnection.debuglevel == 1


def test_get_level_warns_and_uses_default_for_invalid_input():
    assert logging_config.get_level("VERBOSE", "WARNING") == "WARNING"


def test_host_env_restores_original_loader_values(monkeypatch):
    monkeypatch.setattr(drive_utils, "_HOST_ENV_CACHE", None)
    monkeypatch.setenv("LD_LIBRARY_PATH", "/bundled")
    monkeypatch.setenv("LD_LIBRARY_PATH_ORIG", "/host")
    monkeypatch.setenv("PYTHONHOME", "/bundled-python")
    monkeypatch.delenv("PYTHONHOME_ORIG", raising=False)

    result = drive_utils.host_env()

    assert result["LD_LIBRARY_PATH"] == "/host"
    assert "LD_LIBRARY_PATH_ORIG" not in result
    assert "PYTHONHOME" not in result


def test_unc_direct_edit_uses_a_temporary_local_directory(monkeypatch, tmp_path):
    monkeypatch.setattr(drive_utils, "path_is_unc_name", Mock(return_value=True))
    monkeypatch.setattr(drive_utils, "gettempdir", Mock(return_value=str(tmp_path)))

    result = drive_utils.find_suitable_direct_edit_dir(Path("shared"))

    assert result.parent == tmp_path
    assert result.name.startswith("direct-edit-")


def test_windows_default_folder_falls_back_when_shell_lookup_fails(
    monkeypatch, tmp_path
):
    shell_package = ModuleType("win32com.shell")
    shell_package.shell = SimpleNamespace(
        SHGetFolderPath=Mock(side_effect=RuntimeError("access denied"))
    )
    shell_package.shellcon = SimpleNamespace(CSIDL_PERSONAL=5)
    win32com = ModuleType("win32com")
    win32com.shell = shell_package
    monkeypatch.setitem(sys.modules, "win32com", win32com)
    monkeypatch.setitem(sys.modules, "win32com.shell", shell_package)
    monkeypatch.setattr(drive_utils, "WINDOWS", True)
    monkeypatch.setattr(
        drive_utils,
        "Options",
        SimpleNamespace(home=tmp_path),
    )

    result = drive_utils.get_default_local_folder("Shared Drive")

    assert result == tmp_path / "Documents" / "Shared Drive"


def test_safe_long_path_normalizes_windows_unc_paths(monkeypatch):
    normalized = Path("normalized-share")
    normalize = Mock(return_value=normalized)
    monkeypatch.setattr(drive_utils, "WINDOWS", True)
    monkeypatch.setattr(drive_utils, "normalized_path", normalize)
    path = Path(r"\\server\share")

    assert drive_utils.safe_long_path(path) == normalized
    normalize.assert_called_once_with(path)


def test_safe_rename_reraises_when_destination_is_not_a_file():
    source = Mock()
    destination = Mock()
    source.rename.side_effect = FileExistsError("collision")
    destination.is_file.return_value = False

    with pytest.raises(FileExistsError):
        drive_utils.safe_rename(source, destination)


def test_client_certificate_returns_configured_pair(monkeypatch, tmp_path):
    certificate = tmp_path / "client.crt"
    key = tmp_path / "client.key"
    monkeypatch.setattr(
        drive_utils,
        "Options",
        SimpleNamespace(ssl_no_verify=False, cert_file=certificate, cert_key_file=key),
    )

    assert drive_utils.client_certificate() == (certificate, key)


def test_default_direct_transfer_path_parser_and_invalid_value(monkeypatch):
    config = SimpleNamespace(parse_direct_transfer_remote_path=None)
    monkeypatch.setattr(
        drive_utils, "_active_server_type_config", Mock(return_value=config)
    )

    assert (
        drive_utils._extract_direct_transfer_remote_path(
            " https/example.invalid/folder%20name "
        )
        == "/folder name"
    )
    with pytest.raises(ValueError, match="Invalid direct-transfer URL"):
        drive_utils._extract_direct_transfer_remote_path("https/example.invalid")


def test_default_download_server_normalizer_trims_slashes(monkeypatch):
    config = SimpleNamespace(normalize_download_server_path=None)
    monkeypatch.setattr(
        drive_utils, "_active_server_type_config", Mock(return_value=config)
    )

    assert drive_utils._normalize_download_server_path(
        "https://example.invalid///"
    ) == ("https://example.invalid")


def test_protocol_url_applies_registered_normalizer(monkeypatch):
    config = SimpleNamespace(
        normalize_protocol_url=Mock(return_value="unsupported"),
        protocol_token_pattern="",
    )
    monkeypatch.setattr(
        drive_utils, "_active_server_type_config", Mock(return_value=config)
    )
    drive_utils.parse_protocol_url.cache_clear()

    assert drive_utils.parse_protocol_url("malformed") is None
    config.normalize_protocol_url.assert_called_once_with("malformed")


def test_unlock_path_unlocks_parent_and_file(monkeypatch, tmp_path):
    path = tmp_path / "file.txt"
    path.write_text("data", encoding="utf-8")
    unset = Mock()
    monkeypatch.setattr(drive_utils.os, "access", Mock(return_value=False))
    monkeypatch.setattr(drive_utils, "unset_path_readonly", unset)

    assert drive_utils.unlock_path(path) == 3
    assert unset.call_args_list == [call(tmp_path), call(path)]


def test_lock_path_locks_the_parent(monkeypatch, tmp_path):
    path = tmp_path / "file.txt"
    set_readonly = Mock()
    monkeypatch.setattr(drive_utils, "set_path_readonly", set_readonly)

    drive_utils.lock_path(path, 2)

    set_readonly.assert_called_once_with(tmp_path)


def test_url_returns_connection_error_for_non_success_response(monkeypatch):
    response = MagicMock(status_code=500)
    response.__enter__.return_value = response
    response.raise_for_status.return_value = None
    monkeypatch.setattr("requests.get", Mock(return_value=response))
    monkeypatch.setattr(drive_utils, "requests_verify", Mock(return_value=True))
    monkeypatch.setattr(drive_utils, "client_certificate", Mock(return_value=None))

    assert drive_utils.test_url("https://example.invalid") == "CONNECTION_ERROR"


def test_get_verify_reads_ssl_override_from_config(monkeypatch, tmp_path):
    config = tmp_path / "config.ini"
    config.write_text(
        "[DEFAULT]\nenv = settings\n[settings]\nssl-no-verify = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        drive_utils,
        "Options",
        SimpleNamespace(ssl_no_verify=False, ca_bundle=None),
    )
    monkeypatch.setattr(drive_utils, "requests_verify", Mock(return_value=True))
    monkeypatch.setattr(drive_utils, "get_config_path", Mock(return_value=config))

    assert drive_utils.get_verify() is False


def test_find_real_office_file_returns_empty_when_no_candidate_exists(tmp_path):
    lock_file = tmp_path / "~$missing.docx"
    lock_file.touch()
    assert drive_utils.find_real_office_file(str(lock_file)) == ("", "")


def test_file_info_normalizes_non_normalized_path(monkeypatch, tmp_path):
    decomposed = Path("e\u0301.txt")
    (tmp_path / decomposed).write_text("data", encoding="utf-8")
    rename = Mock()
    monkeypatch.setattr(local_base, "MAC", False)
    monkeypatch.setattr(local_base, "safe_rename", rename)

    FileInfo(
        tmp_path,
        decomposed,
        False,
        datetime.now(tz=timezone.utc),
    )

    rename.assert_called_once()


def test_local_client_repr_contains_cached_case_sensitivity(tmp_path):
    client = SimpleNamespace(base_folder=tmp_path, _case_sensitive=False)
    result = LocalClientMixin.__repr__(client)
    assert "is_case_sensitive=False" in result


def test_case_sensitivity_falls_back_when_temp_creation_fails(monkeypatch):
    client = SimpleNamespace(_case_sensitive=None)
    monkeypatch.setattr(local_base, "mkdtemp", Mock(side_effect=OSError("denied")))

    assert LocalClientMixin.is_case_sensitive(client) is False
    assert client._case_sensitive is False


@pytest.mark.parametrize(
    "callable_",
    [
        lambda: LocalClientMixin.remove_remote_id_impl(SimpleNamespace(), Path("x")),
        lambda: LocalClientMixin.has_folder_icon(SimpleNamespace(), Path("x")),
        lambda: LocalClientMixin.set_folder_icon(
            SimpleNamespace(), Path("x"), Path("icon")
        ),
        lambda: LocalClientMixin.set_path_remote_id(Path("x"), b"id"),
        lambda: LocalClientMixin.get_path_remote_id(Path("x")),
        lambda: LocalClientMixin.trash(SimpleNamespace(), Path("x")),
    ],
)
def test_local_client_abstract_operations_raise(callable_):
    with pytest.raises(NotImplementedError):
        callable_()


def test_remove_remote_id_reraises_unrecognized_os_errors(monkeypatch, tmp_path):
    error = OSError(errno.EACCES, "denied")
    client = SimpleNamespace(
        abspath=Mock(return_value=tmp_path / "file"),
        remove_remote_id_impl=Mock(side_effect=error),
    )
    monkeypatch.setattr(local_base, "unlock_path", Mock(return_value=0))
    monkeypatch.setattr(local_base, "lock_path", Mock())

    with pytest.raises(OSError) as exc_info:
        LocalClientMixin.remove_remote_id(client, Path("file"))

    assert exc_info.value is error


def test_delete_copies_windows_return_code_to_error(monkeypatch, tmp_path):
    path = tmp_path / "file.txt"
    path.touch()
    error = OSError("delete failed")
    error.args = (None, None, str(path), 32)
    client = SimpleNamespace(
        abspath=Mock(return_value=path),
        unlock_ref=Mock(return_value=3),
        trash=Mock(side_effect=OSError("trash failed")),
        delete_final=Mock(side_effect=error),
        lock_ref=Mock(),
    )

    with pytest.raises(OSError) as exc_info:
        LocalClientMixin.delete(client, Path("file.txt"))

    assert exc_info.value.winerror == 32
    assert exc_info.value.trash_issue is True
    client.lock_ref.assert_called_once_with(path, 2, is_abs=True)


def test_delete_final_reraises_first_tree_error(monkeypatch, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    error = OSError("cannot remove child")

    def failed_tree_delete(path, onerror):
        onerror(None, path, (OSError, error, None))
        onerror(None, path, (OSError, OSError("later"), None))

    client = SimpleNamespace(
        unlock_ref=Mock(return_value=1),
        unset_readonly=Mock(),
        abspath=Mock(return_value=folder),
        lock_ref=Mock(),
    )
    monkeypatch.setattr(local_base.shutil, "rmtree", failed_tree_delete)

    with pytest.raises(OSError) as exc_info:
        LocalClientMixin.delete_final(client, Path("folder"))

    assert exc_info.value is error
    client.lock_ref.assert_called_once_with(Path("."), 1)
