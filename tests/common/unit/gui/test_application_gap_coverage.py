"""Focused coverage tests for small Application GUI branches."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import pytest

from nxdrive.drive.gui import application as application_module
from nxdrive.drive.gui.application import Application
from nxdrive.drive.qt.imports import Qt


def make_application(**attributes):
    """Build an Application without running its process-wide constructor."""
    application = Application.__new__(Application)
    application.tasks_management_feature_model = Mock()
    for name, value in attributes.items():
        setattr(application, name, value)
    return application


@pytest.mark.parametrize(
    ("scheme", "expected"),
    [
        (Qt.ColorScheme.Dark, True),
        (Qt.ColorScheme.Light, False),
        (Qt.ColorScheme.Unknown, False),
    ],
)
def test_dark_mode_detection_and_change_signal(scheme, expected):
    application = make_application(dark_mode_signal=Mock())
    hints = Mock()
    hints.colorScheme.return_value = scheme

    with (
        patch.object(Application, "styleHints", return_value=hints),
        patch.object(application_module.log, "error") as log_error,
    ):
        assert application.is_dark_mode() is expected
        application._on_color_scheme_changed(scheme)

    application.dark_mode_signal.emit.assert_called_once_with(expected)
    assert log_error.call_count == (2 if scheme == Qt.ColorScheme.Unknown else 0)


def test_dark_mode_without_style_hints_is_light():
    application = make_application()
    with patch.object(Application, "styleHints", return_value=None):
        assert application.is_dark_mode() is False


def test_workflow_engine_list_feature_guard_and_registered_workflow():
    manager = Mock()
    application = make_application(
        manager=manager,
        added_user_engine_list=["one"],
        known_feature_model=SimpleNamespace(enabled=False, restart_needed=False),
    )

    application.update_workflow_user_engine_list(True, "missing")
    application.update_workflow_user_engine_list(True, "one")
    application.update_workflow_user_engine_list(False, "two")
    assert application.added_user_engine_list == ["two"]

    application.absent_feature_model = None
    application._update_feature_state("absent", True)
    manager.reload_client_global_headers.assert_not_called()

    workflow = SimpleNamespace(user_task_list={"task": object()})
    tasks = SimpleNamespace(enabled=True, restart_needed=False)
    application.tasks_management_feature_model = tasks
    application._workflow_cls = workflow
    application._update_feature_state("tasks_management", False)

    assert workflow.user_task_list == {}
    manager.stop_workflow_worker.assert_called_once_with()


def test_fill_qml_context_includes_admin_special_versions(monkeypatch):
    context = Mock()
    manager = Mock()
    manager.updater = object()
    manager.device_id = "device-123"
    manager.get_metrics.return_value = {
        "python_version": "3.13",
        "qt_version": "6.8",
        "python_client_version": "9.9",
    }
    application = make_application(
        manager=manager,
        osi=object(),
        point_size=10.0,
        api=object(),
        today_is_special=True,
    )
    model_names = (
        "active_direct_download_model",
        "active_session_model",
        "completed_direct_download_model",
        "completed_session_model",
        "conflicts_model",
        "direct_download_monitoring_model",
        "direct_transfer_model",
        "errors_model",
        "engine_model",
        "transfer_model",
        "file_model",
        "ignoreds_model",
        "language_model",
        "tasks_model",
        "auto_update_feature_model",
        "direct_edit_feature_model",
        "direct_transfer_feature_model",
        "document_type_selection_feature_model",
        "synchronization_feature_model",
    )
    for name in model_names:
        setattr(application, name, object())
    application.current_language = Mock(return_value="English")
    application._resolve_server_qml_url = Mock(side_effect=["new-url", "login-url"])

    monkeypatch.setattr(application_module, "choice", lambda _values: "🎄")
    monkeypatch.setattr(application_module._st, "all_keys", lambda: ("server",))
    monkeypatch.setattr(application_module._st, "get_default_key", lambda: "server")
    options = type(application_module.Options).options
    original_system_wide = options["system_wide"]
    options["system_wide"] = (True, "test")
    try:
        application._fill_qml_context(context)
    finally:
        options["system_wide"] = original_system_wide

    properties = dict(call_.args for call_ in context.setContextProperty.call_args_list)
    assert properties["serverNewAccountPopupUrl"] == "new-url"
    assert properties["serverReloginPopupUrl"] == "login-url"
    assert properties["modulesVersionText"].endswith("[admin] 🎄")
    assert properties["deviceIdText"] == "Device ID: device-123"


def _server_config(new_account_path="", relogin_path=""):
    return SimpleNamespace(
        key="server",
        new_account_popup_qml_path=new_account_path,
        relogin_popup_qml_path=relogin_path,
    )


def test_resolve_server_qml_url_missing_new_account_has_no_fallback(monkeypatch):
    application = make_application()
    monkeypatch.setattr(
        application_module._st,
        "get",
        lambda _key: _server_config("missing/New.qml", ""),
    )
    with patch.object(Path, "is_file", return_value=False):
        assert application._resolve_server_qml_url("new_account") == ""


def test_resolve_server_qml_url_uses_relogin_fallback(monkeypatch, tmp_path):
    application = make_application()
    fallback = tmp_path / "ReLoginPopup.qml"
    fallback.write_text("fallback", encoding="utf-8")
    monkeypatch.setattr(
        application_module._st,
        "get",
        lambda _key: _server_config("", "missing/ReLogin.qml"),
    )
    monkeypatch.setattr(application_module, "find_resource", lambda *_a, **_k: fallback)
    with patch.object(Path, "is_file", return_value=False):
        url = application._resolve_server_qml_url("relogin")
    assert url.startswith("file:")
    assert url.endswith("ReLoginPopup.qml")


def test_resolve_server_qml_url_uses_existing_configured_file(monkeypatch):
    application = make_application()
    monkeypatch.setattr(
        application_module._st,
        "get",
        lambda _key: _server_config("custom/New.qml", ""),
    )
    with patch.object(Path, "is_file", return_value=True):
        url = application._resolve_server_qml_url("new_account")
    assert url.startswith("file:")
    assert url.endswith("custom/New.qml")


def test_direct_edit_callbacks_and_simple_warning_slots():
    manager = Mock()
    manager.direct_edit = Mock()
    application = make_application(
        manager=manager,
        _conflicts_modals={"busy.txt": True},
        display_warning=Mock(),
    )

    application._direct_edit_conflict("busy.txt", Path("ref"), "digest")
    manager.direct_edit.force_update.assert_not_called()

    application._direct_edit_error("MESSAGE", ["value"], "details")
    application._no_space_left()
    assert application.display_warning.call_args_list == [
        call(
            f"Direct Edit - {application_module.APP_NAME}",
            "MESSAGE",
            ["value"],
            details="details",
        ),
        call(application_module.APP_NAME, "NO_SPACE_LEFT_ON_DEVICE", []),
    ]


def test_direct_edit_conflict_logs_unexpected_dialog_failure():
    application = make_application(
        _conflicts_modals={}, question=Mock(side_effect=OSError)
    )
    with patch.object(application_module.log, "exception") as log_exception:
        application._direct_edit_conflict("file.txt", Path("ref"), "digest")
    log_exception.assert_called_once()


def test_confirm_deletion_cancel_and_file_replace_paths(tmp_path):
    manager = Mock()
    manager.get_deletion_behavior.return_value = application_module.DelAction.UNSYNC
    message = Mock()
    message.addButton.side_effect = [Mock(), Mock()]
    message.clickedButton.return_value = object()
    checkbox = Mock()
    checkbox.isChecked.return_value = False
    application = make_application(manager=manager, question=Mock(return_value=message))

    with (
        patch.object(application_module, "QCheckBox", return_value=checkbox),
        patch.object(
            application_module.Translator,
            "get",
            side_effect=lambda key, **_kwargs: key,
        ),
    ):
        result = application.confirm_deletion(tmp_path / "item")
    assert result is application_module.DelAction.ROLLBACK

    old_path = tmp_path / "old.txt"
    new_path = tmp_path / "new.txt"
    old_path.write_text("old", encoding="utf-8")
    new_path.write_text("new", encoding="utf-8")
    replace_message = Mock()
    replace = Mock()
    replace_message.addButton.side_effect = [replace, Mock()]
    replace_message.clickedButton.return_value = replace
    application.question.return_value = replace_message
    with (
        patch.object(application_module, "normalize_event_filename") as normalize,
        patch.object(
            application_module.Translator,
            "get",
            side_effect=lambda key, **_kwargs: key,
        ),
    ):
        application._file_already_exists(old_path, new_path)
    assert not old_path.exists()
    normalize.assert_called_once_with(new_path)


def test_engine_removal_drop_state_clear_and_simple_slots():
    engine_model = Mock()
    file_model = Mock()
    application = make_application(
        engine_model=engine_model,
        file_model=file_model,
        refresh_conflicts=Mock(),
        change_systray_icon=Mock(),
        sender=Mock(return_value=object()),
        systray_window=Mock(),
        direct_transfer_window=Mock(),
        manager=Mock(),
    )

    application.remove_engine("uid")
    application.dropped_engine(object())
    application._on_engine_state_cleared()
    application.hide_systray()
    application.open_help()
    application.close_direct_transfer_window()

    engine_model.removeEngine.assert_called_once_with("uid")
    assert file_model.add_files.call_args_list == [call([]), call([]), call([])]
    application.refresh_conflicts.assert_not_called()
    assert application.change_systray_icon.call_count == 2
    application.systray_window.hide.assert_called_once_with()
    application.manager.open_help.assert_called_once_with()
    application.direct_transfer_window.close.assert_called_once_with()


def test_pending_filter_dialog_replacement_acceptance_and_queue(monkeypatch):
    old_dialog = Mock()
    new_dialog = Mock()
    engine = Mock()
    application = make_application(filters_dlg=old_dialog, _show_window=Mock())
    monkeypatch.setattr(
        application_module, "DocumentsDialog", Mock(return_value=new_dialog)
    )

    application._show_pending_filters(engine)

    old_dialog.close.assert_called_once_with()
    new_dialog.destroyed.connect.assert_has_calls(
        [
            call(application.destroyed_filters_dialog),
            call(application._show_next_pending_filter),
        ]
    )
    accepted_callback = new_dialog.accepted.connect.call_args.args[0]
    accepted_callback()
    engine.mark_filters_configured.assert_called_once_with()
    application._show_window.assert_called_once_with(new_dialog)

    first, second = Mock(), Mock()
    application._pending_filter_engines = [first, second]
    application._show_pending_filters = Mock()
    application._show_next_pending_filter()
    application._show_pending_filters.assert_called_once_with(first)
    assert application._pending_filter_engines == [second]


def test_simple_status_notification_tooltip_and_metadata_slots():
    notification_service = Mock()
    application = make_application(
        manager=SimpleNamespace(
            notification_service=notification_service,
            ctx_edit_metadata=Mock(),
        ),
        current_notification=SimpleNamespace(uid="notice"),
        default_tooltip="Drive",
    )

    application.message_clicked()
    notification_service.trigger_notification.assert_called_once_with("notice")
    application.show_metadata(Path("metadata.txt"))
    application.manager.ctx_edit_metadata.assert_called_once_with(Path("metadata.txt"))

    with patch.object(application_module.Action, "get_actions", return_value={}):
        assert application.get_tooltip() == "Drive"

    hidden = SimpleNamespace(type="_internal")
    visible = SimpleNamespace(type="upload", __repr__=lambda self: "upload")
    with patch.object(
        application_module.Action,
        "get_actions",
        return_value={"hidden": hidden, "visible": visible},
    ):
        assert application.get_tooltip().startswith("Drive - ")

    with patch.object(
        application_module.Action,
        "get_actions",
        return_value={"hidden": hidden},
    ):
        assert application.get_tooltip() == "Drive"


def test_icon_loading_initial_selection_and_systray_unavailable(monkeypatch):
    manager = Mock()
    application = make_application(
        manager=manager,
        use_light_icons=False,
        today_is_special=True,
        icons={},
        icon_state="idle",
        set_icon_state=Mock(),
    )
    monkeypatch.setattr(
        application_module, "find_icon", lambda name: Path("icons") / name
    )
    monkeypatch.setattr(application_module, "MAC", False)

    application.load_icons_set(False)
    manager.set_config.assert_not_called()

    application.load_icons_set(True)
    assert set(application.icons) == {
        "conflict",
        "disabled",
        "error",
        "idle",
        "notification",
        "paused",
        "syncing",
        "update",
    }
    manager.set_config.assert_called_once_with("light_icons", True)
    application.set_icon_state.assert_called_once_with("idle", force=True)

    manager.get_config.return_value = "1"
    assert application.initial_icons_set() is True

    tray = Mock()
    tray.isSystemTrayAvailable.return_value = False
    application.load_icons_set = Mock()
    application.initial_icons_set = Mock(return_value=False)
    monkeypatch.setattr(application_module, "DriveSystrayIcon", Mock(return_value=tray))
    with patch.object(application_module.log, "critical") as critical:
        application.setup_systray()
    critical.assert_called_once()


def test_restart_protocol_and_listener_error_paths(monkeypatch):
    application = make_application(display_warning=Mock(), manager=Mock())
    application.show_msgbox_restart_needed()
    application.display_warning.assert_called_once_with(
        application_module.APP_NAME, "RESTART_NEEDED_MSG", [application_module.APP_NAME]
    )

    monkeypatch.setattr(
        application_module, "parse_protocol_url", Mock(side_effect=ValueError("bad"))
    )
    assert application._handle_nxdrive_url("invalid") is False

    config = SimpleNamespace(bundle_identifier="example.drive")
    monkeypatch.setattr(application_module._st, "get", lambda _key: config)
    server = Mock()
    server.listen.side_effect = OSError("busy")
    monkeypatch.setattr(application_module, "QLocalServer", Mock(return_value=server))
    application.aboutToQuit = Mock()
    application.init_nxdrive_listener()
    assert application._nxdrive_listener is server
    application.aboutToQuit.connect.assert_called_once_with(server.close)


def test_refresh_models_and_current_language():
    dao = object()
    api = Mock()
    application = make_application(
        api=api,
        transfer_model=SimpleNamespace(transfers=[], set_transfers=Mock()),
        active_session_model=SimpleNamespace(
            sessions=[], set_sessions=Mock(), update_sessions=Mock()
        ),
        active_direct_download_model=SimpleNamespace(
            downloads=[], set_downloads=Mock()
        ),
        completed_direct_download_model=SimpleNamespace(
            downloads=[], set_downloads=Mock()
        ),
        direct_download_monitoring_model=SimpleNamespace(items=[], set_items=Mock()),
        completed_session_model=SimpleNamespace(sessions=[], set_sessions=Mock()),
        file_model=SimpleNamespace(files=[], add_files=Mock()),
        language_model=SimpleNamespace(languages=[("en", "English")]),
    )
    api.get_transfers.return_value = ["transfer"]
    api.get_active_sessions_items.return_value = ["session"]
    api.get_active_direct_downloads_items.return_value = ["active"]
    api.get_completed_direct_downloads_items.return_value = ["completed"]
    api.get_direct_downloads_for_monitoring.return_value = ["monitor"]
    api.get_completed_sessions_items.return_value = []
    api.get_last_files.return_value = ["file"]

    application.refresh_transfers(dao)
    application.refresh_active_sessions_items(dao)
    application.active_session_model.sessions = ["old"]
    application.refresh_active_sessions_items(dao)
    application.refresh_active_direct_downloads_items(dao)
    application.refresh_completed_direct_downloads_items(dao)
    application.refresh_direct_download_monitoring_items(dao)
    application.refresh_completed_sessions_items(dao, True)
    application.get_last_files("uid")

    application.transfer_model.set_transfers.assert_called_once_with(["transfer"])
    application.active_session_model.set_sessions.assert_called_once_with(["session"])
    application.active_session_model.update_sessions.assert_called_once_with(
        ["session"]
    )
    application.active_direct_download_model.set_downloads.assert_called_once_with(
        ["active"]
    )
    application.completed_direct_download_model.set_downloads.assert_called_once_with(
        ["completed"]
    )
    application.direct_download_monitoring_model.set_items.assert_called_once_with(
        ["monitor"]
    )
    application.completed_session_model.set_sessions.assert_called_once_with([])
    application.file_model.add_files.assert_called_once_with(["file"])

    with patch.object(application_module.Translator, "locale", return_value="en"):
        assert application.current_language() == "English"
    with patch.object(application_module.Translator, "locale", return_value="fr"):
        assert application.current_language() is None


def test_refresh_files_rejects_non_engine_sender(monkeypatch):
    application = make_application(
        _last_refresh_view=0.0, sender=Mock(return_value=object())
    )
    monkeypatch.setattr(application_module, "monotonic", lambda: 10.0)
    with patch.object(application_module.log, "error") as log_error:
        application.refresh_files({})
    log_error.assert_called_once()
