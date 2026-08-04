"""Focused tests for the server-agnostic Direct Edit worker."""

import errno
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest
from requests.exceptions import ConnectionError
from watchdog.events import FileCreatedEvent, FileDeletedEvent, FileMovedEvent

from nxdrive.drive.direct_edit import APP_NAME, DirectEdit
from nxdrive.drive.exceptions import NoAssociatedSoftware, NotFound, ThreadInterrupt
from nxdrive.drive.feature import Feature
from nxdrive.drive.objects import DirectEditDetails


@pytest.fixture()
def manager():
    manager = Mock()
    manager.engines = {}
    manager.dao = Mock()
    manager.osi = Mock()
    manager.directEdit = Mock()
    manager.autolock_service = Mock()
    manager.notification_service = Mock()
    manager.get_direct_edit_auto_lock.return_value = True
    return manager


@pytest.fixture()
def direct_edit(manager, tmp_path):
    folder = tmp_path / "edit"
    folder.mkdir()
    return DirectEdit(manager, folder)


def _engine(url="https://example.test/nuxeo/", user="User", *, invalid=False):
    engine = Mock()
    engine.get_binder.return_value = SimpleNamespace(server_url=url, username=user)
    engine.has_invalid_credentials.return_value = invalid
    engine.hostname = "example.test"
    engine.dao = Mock()
    engine.local_folder = Path("/sync")
    return engine


def _child(name, *, folderish=True, path=None, filepath=None):
    return SimpleNamespace(
        name=name,
        folderish=folderish,
        path=path or Path(name),
        filepath=filepath or Path("/edit") / name,
    )


def _details(engine, *, digest="same"):
    return DirectEditDetails(
        uid="doc-id",
        engine=engine,
        digest_func="md5",
        digest=digest,
        xpath="file:content",
        editing=False,
    )


def test_construction_wires_services_and_initializes_queues(direct_edit, manager):
    assert direct_edit._manager is manager
    assert direct_edit._stop is False
    assert direct_edit._observer is None
    assert direct_edit._metrics == {"edit_files": 0}
    assert direct_edit._upload_queue.empty()
    assert direct_edit._lock_queue.empty()
    manager.directEdit.connect.assert_called_once_with(direct_edit.edit)
    manager.autolock_service.orphanLocks.connect.assert_called_once_with(
        direct_edit._autolock_orphans
    )
    manager.notification_service._directEditStarting.assert_not_called()


def test_base_hooks_are_explicit_and_stop_client_interrupts(direct_edit):
    with pytest.raises(NotImplementedError):
        direct_edit._download(None, None, Path("in"), Path("out"), None, "content")
    with pytest.raises(NotImplementedError):
        direct_edit._get_info(None, "doc")
    with pytest.raises(NotImplementedError):
        direct_edit._lock(None, "doc")
    with pytest.raises(NotImplementedError):
        direct_edit._unlock(None, "doc", Path("ref"))
    with pytest.raises(NotImplementedError):
        direct_edit._handle_upload_queue()
    with pytest.raises(NotImplementedError):
        direct_edit._handle_lock_queue()

    direct_edit.stop_client()
    direct_edit._stop = True
    with pytest.raises(ThreadInterrupt):
        direct_edit.stop_client()


def test_engine_resolution_exact_casefold_missing_and_invalid(direct_edit, manager):
    errors = []
    direct_edit.directEditError[str, list].connect(
        lambda label, values: errors.append((label, values))
    )
    exact = _engine(user="Exact")
    folded = _engine(user="MixedCase")
    manager.engines = {"exact": exact}
    assert direct_edit._get_engine("https://example.test/nuxeo", user="Exact") is exact

    manager.engines = {"folded": folded}
    assert (
        direct_edit._get_engine("https://example.test/nuxeo/", user="mixedcase")
        is folded
    )

    manager.engines = {}
    assert direct_edit._get_engine("https://missing.test", user="Nobody") is None
    assert errors == [
        (
            "DIRECT_EDIT_CANT_FIND_ENGINE",
            ["Nobody", "https://missing.test", APP_NAME],
        )
    ]

    invalid = _engine(invalid=True)
    manager.engines = {"invalid": invalid}
    assert direct_edit._get_engine("https://example.test/nuxeo", user="User") is None
    invalid.invalidAuthentication.emit.assert_called_once_with()


def test_extract_edit_info_validates_metadata_and_returns_details(direct_edit, manager):
    engine = _engine()
    manager.engines = {"engine": engine}
    ref = Path("doc/file.txt")
    metadata = {
        "nxdirectedit": "https://example.test/nuxeo/",
        "nxdirectedituser": "User",
        None: "doc-id",
        "nxdirecteditdigestalgorithm": "sha256",
        "nxdirecteditdigest": "digest",
        "nxdirecteditxpath": "file:content",
        "nxdirecteditlock": "1",
    }
    direct_edit.local.get_remote_id = Mock(
        side_effect=lambda _path, name=None: metadata[name]
    )

    details = direct_edit._extract_edit_info(ref)

    assert details == DirectEditDetails(
        "doc-id", engine, "sha256", "digest", "file:content", True
    )

    for missing_key, message in (
        ("nxdirectedit", "server url"),
        (None, "uid"),
    ):
        values = dict(metadata)
        values[missing_key] = None
        direct_edit.local.get_remote_id.side_effect = (
            lambda _path, name=None, values=values: values[name]
        )
        with pytest.raises(NotFound, match=message):
            direct_edit._extract_edit_info(ref)

    values = dict(metadata)
    values["nxdirectedit"] = "https://unknown.test"
    direct_edit.local.get_remote_id.side_effect = lambda _path, name=None: values[name]
    with pytest.raises(NotFound, match="engine"):
        direct_edit._extract_edit_info(ref)


def test_notifications_and_sync_status_use_matching_engine(direct_edit, manager):
    state = SimpleNamespace(local_path=Path("folder/file.txt"))
    missing = _engine()
    matching = _engine()
    missing.dao.get_normal_state_from_remote.return_value = None
    matching.dao.get_normal_state_from_remote.return_value = state
    manager.engines = {"missing": missing, "matching": matching}

    direct_edit.send_notification(Path("folder/file.txt"))

    manager.osi.send_sync_status.assert_called_once_with(
        state, matching.local_folder / state.local_path
    )
    direct_edit.autolock.documentLocked.emit.assert_called_once_with("file.txt")


def test_cleanup_handles_structural_and_error_paths(direct_edit):
    uid = "12345678-1234-1234-1234-123456789abc"
    file_child = _child("loose.txt", folderish=False)
    invalid = _child("not-a-direct-edit-folder")
    empty = _child(f"{uid}_empty")
    no_name = _child(f"{uid}_no-name")
    no_match = _child(f"{uid}_no-match")
    orphan = _child(f"{uid}_orphan")
    digest_error = _child(f"{uid}_digest-error")
    modified = _child(f"{uid}_modified")
    extra = _child(f"{uid}_extra")
    locked = _child(f"{uid}_locked")
    clean = _child(f"{uid}_clean")
    roots = [
        file_child,
        invalid,
        empty,
        no_name,
        no_match,
        orphan,
        digest_error,
        modified,
        extra,
        locked,
        clean,
    ]
    files = {
        no_name.path: [
            _child("file.txt", folderish=False, path=no_name.path / "file.txt")
        ],
        no_match.path: [
            _child("other.txt", folderish=False, path=no_match.path / "other.txt")
        ],
        orphan.path: [
            _child("file.txt", folderish=False, path=orphan.path / "file.txt")
        ],
        digest_error.path: [
            _child("file.txt", folderish=False, path=digest_error.path / "file.txt")
        ],
        modified.path: [
            _child("file.txt", folderish=False, path=modified.path / "file.txt")
        ],
        extra.path: [
            _child("file.txt", folderish=False, path=extra.path / "file.txt"),
            _child("sidecar.txt", folderish=False, path=extra.path / "sidecar.txt"),
        ],
        locked.path: [
            _child("file.txt", folderish=False, path=locked.path / "file.txt")
        ],
        clean.path: [_child("file.txt", folderish=False, path=clean.path / "file.txt")],
    }
    names = {child.path: "file.txt" for child in roots}
    names[no_name.path] = None
    engine = _engine()

    direct_edit.local.exists = Mock(return_value=True)
    direct_edit.local.get_children_info = Mock(
        side_effect=lambda ref: roots if ref == Path() else files.get(ref, [])
    )
    direct_edit.local.get_remote_id = Mock(side_effect=lambda ref, **_: names[ref])
    direct_edit.local.abspath = Mock(side_effect=lambda ref: direct_edit._folder / ref)

    def extract(ref):
        if ref.parent == orphan.path:
            raise NotFound()
        return _details(engine)

    def get_info(ref):
        if ref.parent == digest_error.path:
            raise OSError("digest unavailable")
        digest = "changed" if ref.parent == modified.path else "same"
        return SimpleNamespace(get_digest=Mock(return_value=digest))

    direct_edit._extract_edit_info = Mock(side_effect=extract)
    direct_edit.local.get_info = Mock(side_effect=get_info)
    locked_file = locked.filepath / "file.txt"
    direct_edit._manager.dao.get_locked_paths.return_value = [locked_file]

    with patch("nxdrive.drive.direct_edit.shutil.rmtree") as rmtree:
        direct_edit._cleanup()

    purged = {args[0] for args, _kwargs in rmtree.call_args_list}
    assert direct_edit._folder / empty.path in purged
    assert direct_edit._folder / orphan.path in purged
    assert direct_edit._folder / clean.path in purged
    assert direct_edit._folder / locked.path not in purged
    assert direct_edit._upload_queue.get_nowait() == modified.path / "file.txt"


def test_prepare_edit_persists_metadata_and_moves_download(
    direct_edit, manager, tmp_path
):
    engine = _engine()
    manager.engines = {"engine": engine}
    info = Mock(doc_type="File", path="/document")
    blob = SimpleNamespace(
        name="report.txt", digest="abc123", digest_algorithm="sha256"
    )
    info.get_blob.return_value = blob
    downloaded = tmp_path / "downloaded.tmp"
    downloaded.write_text("payload", encoding="utf-8")
    direct_edit._get_info = Mock(return_value=info)
    direct_edit._download = Mock(return_value=downloaded)
    direct_edit.local.set_remote_id = Mock()

    result = direct_edit._prepare_edit(
        "https://example.test/nuxeo",
        "doc-id",
        user="User",
        download_url="nxfile/default/doc-id/file:content/report.txt?token=1",
        callback=Mock(),
    )

    assert result == direct_edit._folder / "doc-id_file-content" / "report.txt"
    assert result.read_text(encoding="utf-8") == "payload"
    assert direct_edit.local.set_remote_id.call_args_list == [
        call(Path("doc-id_file-content"), "doc-id"),
        call(
            Path("doc-id_file-content"),
            "https://example.test/nuxeo",
            name="nxdirectedit",
        ),
        call(Path("doc-id_file-content"), "User", name="nxdirectedituser"),
        call(Path("doc-id_file-content"), "file:content", name="nxdirecteditxpath"),
        call(Path("doc-id_file-content"), "abc123", name="nxdirecteditdigest"),
        call(
            Path("doc-id_file-content"),
            b"sha256",
            name="nxdirecteditdigestalgorithm",
        ),
        call(Path("doc-id_file-content"), "report.txt", name="nxdirecteditname"),
    ]


def test_prepare_edit_short_circuits_for_missing_blob_download_and_connection(
    direct_edit,
):
    engine = _engine()
    direct_edit._get_engine = Mock(return_value=engine)
    direct_edit._get_info = Mock(return_value=Mock(doc_type="File", path="/doc"))
    direct_edit._get_info.return_value.get_blob.return_value = None
    assert direct_edit._prepare_edit("https://server", "doc") is None

    blob = SimpleNamespace(name="file.txt", digest="d", digest_algorithm="md5")
    direct_edit._get_info.return_value.get_blob.return_value = blob
    direct_edit._download = Mock(return_value=None)
    assert direct_edit._prepare_edit("https://server", "doc") is None

    direct_edit._download.side_effect = ConnectionError("offline")
    assert direct_edit._prepare_edit("https://server", "doc") is None


def test_edit_feature_open_and_error_paths(direct_edit, manager, tmp_path):
    errors = []
    direct_edit.directEditError[str, list].connect(
        lambda label, values: errors.append((label, values))
    )
    original = Feature.direct_edit
    try:
        Feature.direct_edit = False
        direct_edit.edit("server", "doc", None, None)
        assert errors[-1] == ("DIRECT_EDIT_NOT_ENABLED", [])

        Feature.direct_edit = True
        target = tmp_path / "document.txt"
        direct_edit._prepare_edit = Mock(return_value=target)
        direct_edit.edit("server", "doc", "user", "download")
        manager.open_local_file.assert_called_with(target)

        direct_edit._prepare_edit.side_effect = NoAssociatedSoftware(target)
        direct_edit.edit("server", "doc", None, None)
        assert errors[-1] == (
            "DIRECT_EDIT_NO_ASSOCIATED_SOFTWARE",
            ["document.txt", "text/plain"],
        )

        fallback = tmp_path / "fallback.txt"
        direct_edit._prepare_edit.side_effect = OSError(
            errno.EACCES, "locked", fallback
        )
        direct_edit.edit("server", "doc", None, None)
        manager.open_local_file.assert_called_with(fallback)

        direct_edit._prepare_edit.side_effect = OSError(errno.EIO, "disk error")
        with pytest.raises(OSError) as exc:
            direct_edit.edit("server", "doc", None, None)
        assert exc.value.errno == errno.EIO
    finally:
        Feature.direct_edit = original


def test_handle_queues_releases_delayed_items_in_order(direct_edit):
    direct_edit._handle_lock_queue = Mock()
    direct_edit._handle_upload_queue = Mock()
    direct_edit._error_queue = Mock()
    direct_edit._error_queue.get.return_value = [
        SimpleNamespace(path=Path("retry.txt"))
    ]

    direct_edit._handle_queues()

    direct_edit._handle_lock_queue.assert_called_once_with()
    assert direct_edit._upload_queue.get_nowait() == Path("retry.txt")
    direct_edit._handle_upload_queue.assert_called_once_with()


def test_execute_retries_recoverable_errors_and_always_stops_watchdog(direct_edit):
    direct_edit._cleanup = Mock()
    direct_edit._setup_watchdog = Mock()
    direct_edit._stop_watchdog = Mock()
    direct_edit._interact = Mock(side_effect=[None, None, ThreadInterrupt()])
    direct_edit._handle_queues = Mock(side_effect=[NotFound(), RuntimeError("boom")])

    with pytest.raises(ThreadInterrupt):
        direct_edit._execute()

    direct_edit._cleanup.assert_called_once_with()
    direct_edit._setup_watchdog.assert_called_once_with()
    assert direct_edit._handle_queues.call_count == 2
    direct_edit._stop_watchdog.assert_called_once_with()


def test_watchdog_setup_stop_and_metrics(direct_edit):
    observer = Mock()
    handler = Mock(counter=7)
    with (
        patch("nxdrive.drive.direct_edit.Observer", return_value=observer),
        patch("nxdrive.drive.direct_edit.DriveFSEventHandler", return_value=handler),
    ):
        direct_edit._setup_watchdog()

    observer.schedule.assert_called_once_with(
        handler, str(direct_edit._folder), recursive=True
    )
    observer.start.assert_called_once_with()
    assert direct_edit.get_metrics()["fs_events"] == 7

    direct_edit._stop_watchdog()
    observer.stop.assert_called_once_with()
    observer.join.assert_called_once_with()
    assert direct_edit._observer is None

    direct_edit._observer = Mock()
    direct_edit._observer.stop.side_effect = RuntimeError("already stopped")
    direct_edit._stop_watchdog()
    assert direct_edit._observer is None


def test_watchdog_ignores_directories_temp_and_missing_metadata(direct_edit, tmp_path):
    folder = tmp_path / "folder"
    folder.mkdir()
    direct_edit.handle_watchdog_event(FileCreatedEvent(str(folder)))

    file_path = tmp_path / "file.txt"
    direct_edit.local.is_temp_file = Mock(return_value=True)
    direct_edit.handle_watchdog_event(FileCreatedEvent(str(file_path)))

    direct_edit.local.is_temp_file.return_value = False
    direct_edit.local.get_path = Mock(return_value=Path("ref/file.txt"))
    direct_edit.local.get_remote_id = Mock(return_value=None)
    direct_edit.handle_watchdog_event(FileCreatedEvent(str(file_path)))
    assert direct_edit._upload_queue.empty()


def test_watchdog_moved_lock_and_document_actions(direct_edit, tmp_path):
    parent = tmp_path / "doc"
    parent.mkdir()
    destination = parent / "file.txt"
    direct_edit.local.is_temp_file = Mock(return_value=False)
    direct_edit.local.get_path = Mock(
        side_effect=lambda value: (
            Path("doc") if value == parent else Path("doc/file.txt")
        )
    )

    metadata = {"nxdirecteditname": "file.txt", "nxdirecteditlock": None}
    direct_edit.local.get_remote_id = Mock(
        side_effect=lambda _path, name=None: metadata[name]
    )
    direct_edit.handle_watchdog_event(
        FileMovedEvent(str(parent / "old.txt"), str(destination))
    )
    direct_edit.autolock.set_autolock.assert_called_with(destination, direct_edit)
    assert direct_edit._upload_queue.get_nowait() == Path("doc/file.txt")

    lock_file = parent / "~$file.txt"
    direct_edit.handle_watchdog_event(FileCreatedEvent(str(lock_file)))
    direct_edit.autolock.set_autolock.assert_called_with(destination, direct_edit)

    with patch.object(direct_edit.local, "remove_remote_id") as remove_remote_id:
        direct_edit.handle_watchdog_event(FileDeletedEvent(str(lock_file)))
        remove_remote_id.assert_called_with(Path("doc"), name="nxdirecteditlock")

    metadata["nxdirecteditlock"] = "1"
    direct_edit.handle_watchdog_event(FileDeletedEvent(str(destination)))
    assert direct_edit._upload_queue.empty()
