"""Native-free coverage for Application orchestration methods."""

from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, call, patch

from nxdrive.drive.gui import application as application_module
from nxdrive.drive.gui.application import Application
from nxdrive.drive.options import Options
from nxdrive.drive.qt import constants as qt


class ApplicationMethodHost:
    def __getattr__(self, name):
        attribute = getattr(Application, name)
        descriptor = getattr(attribute, "__get__", None)
        return descriptor(self, type(self)) if descriptor else attribute


def make_application(**attributes):
    application = ApplicationMethodHost()
    for name, value in attributes.items():
        setattr(application, name, value)
    return application


def test_small_window_translation_and_dialog_helpers(monkeypatch):
    window = Mock()
    manager = Mock()
    manager.get_config.return_value = "fr"
    application = make_application(
        manager=manager,
        osi=Mock(),
        icon=object(),
        installTranslator=Mock(),
        _handle_language_change=Mock(),
    )

    application._show_window(window)
    assert application._window_root(window) is window
    window.show.assert_called_once_with()
    window.raise_.assert_called_once_with()
    window.requestActivate.assert_called_once_with()

    translator = MagicMock()
    translator.get.return_value = "translated"
    translator.singleton = object()
    monkeypatch.setattr(application_module, "Translator", translator)
    monkeypatch.setattr(application_module, "find_resource", lambda *_args: "i18n")

    application._init_translator()
    translator.assert_called_once_with("i18n", lang="fr")
    translator.on_change.assert_called_once_with(application._handle_language_change)
    application.osi.register_contextual_menu.assert_called_once_with()
    application.installTranslator.assert_called_once_with(translator.singleton)
    assert application.translate("MESSAGE", values=["value"]) == "translated"

    message_box = Mock()
    monkeypatch.setattr(
        application_module, "QMessageBox", Mock(return_value=message_box)
    )
    result = application._msgbox(
        icon=qt.Warning,
        title="Title",
        header="Header",
        message="Message",
        details="Details",
    )
    assert result is message_box
    message_box.setText.assert_called_once_with("Header")
    message_box.setInformativeText.assert_called_once_with("Message")
    message_box.setDetailedText.assert_called_once_with("Details")
    message_box.exec.assert_called_once_with()


def test_display_helpers_and_question_delegate_to_msgbox():
    application = make_application(
        translate=Mock(return_value="translated"),
        _msgbox=Mock(return_value="box"),
    )

    application.display_info("Info", "MESSAGE", ["one"])
    warning = application.display_warning(
        "Warning", "MESSAGE", ["two"], details="details", execute=False
    )
    question = application.question("Header", "Question", icon=qt.Warning)

    assert warning == "box"
    assert question == "box"
    assert application._msgbox.call_args_list == [
        call(title="Info", message="translated"),
        call(
            icon=qt.Warning,
            title="Warning",
            message="translated",
            details="details",
            execute=False,
        ),
        call(
            icon=qt.Warning,
            header="Header",
            message="Question",
            execute=False,
        ),
    ]


def test_exit_center_and_engine_list_helpers(monkeypatch):
    good_widget = Mock()
    bad_widget = Mock()
    bad_widget.close.side_effect = RuntimeError
    window = Mock()
    screen = Mock()
    geometry = object()
    application = make_application(
        topLevelWidgets=Mock(return_value=[good_widget, bad_widget]),
        quit=Mock(),
        _show_window=Mock(),
        engine_model=Mock(),
    )

    with patch.object(application_module.State, "about_to_quit", False):
        application.exit_app()
        assert application_module.State.about_to_quit is True
    good_widget.close.assert_called_once_with()
    application.quit.assert_called_once_with()

    monkeypatch.setattr(
        application_module.QApplication, "screenAt", Mock(return_value=screen)
    )
    monkeypatch.setattr(application_module.QCursor, "pos", Mock(return_value=object()))
    monkeypatch.setattr(
        application_module.QStyle, "alignedRect", Mock(return_value=geometry)
    )
    application._center_on_screen(window)
    assert application._show_window.call_count == 2
    window.setGeometry.assert_called_once_with(geometry)

    first = SimpleNamespace(uid="one")
    second = SimpleNamespace(uid="two")
    application.add_engines([])
    application.add_engines(first)
    application.add_engines([second])
    assert application.engine_model.addEngine.call_args_list == [
        call("one"),
        call("two"),
    ]


def test_update_workflow_success_and_attribute_error(monkeypatch):
    first = SimpleNamespace(uid="one")
    second = SimpleNamespace(uid="two")
    workflow = Mock()
    application = make_application(
        manager=SimpleNamespace(engines={"one": first, "two": second}),
        workflow=workflow,
        added_user_engine_list=["one"],
        update_workflow_user_engine_list=Mock(),
    )
    monkeypatch.setattr(application_module.Feature, "tasks_management", True)

    application.update_workflow()
    application.update_workflow_user_engine_list.assert_called_once_with(False, "two")
    workflow.get_pending_tasks.assert_called_once_with(second)

    workflow.get_pending_tasks.side_effect = AttributeError
    application.added_user_engine_list = []
    with patch.object(application_module.log, "debug") as log_debug:
        application.update_workflow()
    log_debug.assert_called_once_with("Unable to fetch the TASKS")


def test_conflict_and_direct_transfer_window_helpers(monkeypatch):
    engine = SimpleNamespace(uid="engine")
    old_dialog = Mock()
    dialog = Mock()
    dialog.engine = engine
    application = make_application(
        filters_dlg=old_dialog,
        destroyed_filters_dialog=Mock(),
        direct_transfer_window=Mock(),
        _window_root=Mock(),
        _center_on_screen=Mock(),
        show_direct_transfer_window=Mock(),
    )
    monkeypatch.setattr(application_module, "FoldersDialog", Mock(return_value=dialog))

    application.show_server_folders(engine, None, "/folder")
    old_dialog.close.assert_called_once_with()
    dialog.accepted.connect.assert_called_once_with(
        application._show_direct_transfer_window
    )
    dialog.destroyed.connect.assert_called_once_with(
        application.destroyed_filters_dialog
    )
    dialog.show.assert_called_once_with()

    application._show_direct_transfer_window()
    application.show_direct_transfer_window.assert_called_once_with("engine")

    root = Mock()
    application._window_root.return_value = root
    application.show_direct_transfer_window = (
        Application.show_direct_transfer_window.__get__(application, type(application))
    )
    application.show_direct_transfer_window("engine")
    root.setEngine.emit.assert_called_once_with("engine")
    application._center_on_screen.assert_called_once_with(
        application.direct_transfer_window
    )


def test_direct_download_window_selection_paths():
    first = SimpleNamespace(uid="one")
    second = SimpleNamespace(uid="two")
    root = Mock()
    application = make_application(
        manager=SimpleNamespace(engines={}),
        direct_transfer_window=Mock(),
        _window_root=Mock(return_value=root),
        _center_on_screen=Mock(),
        _select_account=Mock(return_value=second),
    )

    assert application.show_direct_download_window() is None
    application.manager.engines = {"one": first}
    assert application.show_direct_download_window() is first
    application.manager.engines = {"one": first, "two": second}
    assert application.show_direct_download_window() is second
    application._select_account.assert_called_once_with([first, second])
    assert root.setEngine.emit.call_args_list == [call("one"), call("two")]
    assert root.switchToTab.emit.call_args_list == [call(0), call(0)]


def test_duplicate_warning_and_cancel_confirmations(monkeypatch):
    layout = Mock()
    message = Mock()
    message.layout.return_value = layout
    continued = object()
    cancel = object()
    message.addButton.side_effect = [continued, cancel, continued, cancel]
    message.clickedButton.return_value = continued
    engine = Mock()
    application = make_application(
        manager=SimpleNamespace(engines={"engine": engine}),
        api=Mock(),
        display_warning=Mock(return_value=message),
        question=Mock(return_value=message),
    )
    monkeypatch.setattr(
        application_module.Translator, "get", lambda message, values=None: message
    )
    monkeypatch.setattr(application_module, "QSpacerItem", Mock(return_value="spacer"))

    application.folder_duplicate_warning(
        ["one", "two", "three", "four", "five"], "/remote", "https://server"
    )
    warning_values = application.display_warning.call_args.args[2]
    assert "<li>…</li>" in warning_values[2]
    layout.addItem.assert_called_once()

    application.confirm_cancel_transfer("engine", 42, "file")
    engine.cancel_upload.assert_called_once_with(42)
    assert application.confirm_cancel_session("engine", 7, "folder", 3) is True
    application.api.cancel_session.assert_called_once_with("engine", 7)


@Options.mock()
def test_authentication_frozen_and_debug_handler(monkeypatch):
    application = make_application(
        api=Mock(), manager=Mock(), _web_auth_not_frozen=Mock()
    )
    params = {"server_url": "https://server"}

    Options.set("is_frozen", True, setter="local")
    monkeypatch.setattr(application_module, "LINUX", False)
    with (
        patch.object(application_module.webbrowser, "open_new_tab") as open_tab,
        patch.object(
            application_module.QApplication, "setOverrideCursor"
        ) as set_cursor,
        patch.object(
            application_module.QApplication, "restoreOverrideCursor"
        ) as restore_cursor,
    ):
        application.open_authentication_dialog("https://login", params)
    assert application.api.callback_params is params
    open_tab.assert_called_once_with("https://login")
    set_cursor.assert_called_once_with(qt.WaitCursor)
    restore_cursor.assert_called_once_with()

    Options.set("is_frozen", False, setter="local")
    application.open_authentication_dialog("https://login", params)
    application._web_auth_not_frozen.assert_called_once_with("https://server", params)

    application._web_auth_not_frozen = Application._web_auth_not_frozen.__get__(
        application, type(application)
    )
    config = SimpleNamespace(key="server", debug_auth_handler=Mock())
    with patch.object(application_module._st, "detect_by_url", return_value=config):
        application._web_auth_not_frozen("https://server", params)
    config.debug_auth_handler.assert_called_once_with(
        "https://server", application.manager, application.api
    )

    config.debug_auth_handler = None
    with (
        patch.object(application_module._st, "detect_by_url", return_value=config),
        patch.object(application_module.log, "warning") as log_warning,
    ):
        application._web_auth_not_frozen("https://server", params)
    log_warning.assert_called_once()


@Options.mock()
def test_authentication_frozen_linux_uses_xdg_open(monkeypatch):
    application = make_application(api=Mock(), manager=Mock())
    params = {"server_url": "https://server"}
    environment = {"PATH": "/usr/bin"}

    Options.set("is_frozen", True, setter="local")
    monkeypatch.setattr(application_module, "LINUX", True)
    with (
        patch("subprocess.Popen") as popen,
        patch(
            "nxdrive.drive.utils.host_env", return_value=environment
        ) as host_environment,
        patch.object(application_module.webbrowser, "open_new_tab") as open_tab,
        patch.object(
            application_module.QApplication, "setOverrideCursor"
        ) as set_cursor,
        patch.object(
            application_module.QApplication, "restoreOverrideCursor"
        ) as restore_cursor,
    ):
        application.open_authentication_dialog("https://login", params)

    assert application.api.callback_params is params
    host_environment.assert_called_once_with()
    popen.assert_called_once_with(["xdg-open", "https://login"], env=environment)
    open_tab.assert_not_called()
    set_cursor.assert_called_once_with(qt.WaitCursor)
    restore_cursor.assert_called_once_with()


@Options.mock()
def test_authentication_frozen_linux_handles_missing_xdg_open(monkeypatch):
    application = make_application(api=Mock(), manager=Mock())
    params = {"server_url": "https://server"}
    environment = {"PATH": "/usr/bin"}

    Options.set("is_frozen", True, setter="local")
    monkeypatch.setattr(application_module, "LINUX", True)
    with (
        patch("subprocess.Popen", side_effect=FileNotFoundError) as popen,
        patch("nxdrive.drive.utils.host_env", return_value=environment),
        patch.object(application_module.log, "exception") as log_exception,
        patch.object(application_module.webbrowser, "open_new_tab") as open_tab,
        patch.object(
            application_module.QApplication, "setOverrideCursor"
        ) as set_cursor,
        patch.object(
            application_module.QApplication, "restoreOverrideCursor"
        ) as restore_cursor,
    ):
        application.open_authentication_dialog("https://login", params)

    popen.assert_called_once_with(["xdg-open", "https://login"], env=environment)
    log_exception.assert_called_once_with(
        "Failed to open authentication dialog: %s", exc_info=True
    )
    open_tab.assert_not_called()
    set_cursor.assert_called_once_with(qt.WaitCursor)
    restore_cursor.assert_called_once_with()


def test_open_task_uses_platform_launcher(monkeypatch):
    application = make_application()
    engine = SimpleNamespace(server_url="https://server")
    environment = {"PATH": "/usr/bin"}
    expected_url = "https://server/ui/#!/tasks/task-1"

    monkeypatch.setattr(application_module, "LINUX", True)
    with (
        patch.object(application_module.subprocess, "Popen") as popen,
        patch(
            "nxdrive.drive.utils.host_env", return_value=environment
        ) as host_environment,
        patch.object(application_module.webbrowser, "open") as open_browser,
    ):
        application.open_task(engine, "task-1")

    host_environment.assert_called_once_with()
    popen.assert_called_once_with(["xdg-open", expected_url], env=environment)
    open_browser.assert_not_called()

    monkeypatch.setattr(application_module, "LINUX", False)
    with (
        patch.object(application_module.subprocess, "Popen") as popen,
        patch.object(application_module.webbrowser, "open") as open_browser,
    ):
        application.open_task(engine, "task-1")

    popen.assert_not_called()
    open_browser.assert_called_once_with(expected_url)


def test_icon_conflict_and_systray_setup(monkeypatch):
    tray = Mock()
    tray.isSystemTrayAvailable.return_value = True
    application = make_application(
        icon_state="idle",
        icons={"idle": "idle-icon", "disabled": "disabled-icon"},
        tray_icon=tray,
        default_tooltip="Drive",
        get_tooltip=Mock(return_value="tooltip"),
        manager=Mock(),
        load_icons_set=Mock(),
        initial_icons_set=Mock(return_value=False),
    )

    assert application.set_icon_state("idle") is False
    assert application.set_icon_state("idle", force=True) is True
    tray.setToolTip.assert_called_with("tooltip")
    tray.setIcon.assert_called_once_with("idle-icon")

    conflicts = Mock()
    errors = Mock()
    ignored = Mock()
    application.api = Mock()
    application.conflicts_model = conflicts
    application.errors_model = errors
    application.ignoreds_model = ignored
    application.refresh_conflicts("uid")
    conflicts.add_files.assert_called_once_with(application.api.get_conflicts("uid"))
    errors.add_files.assert_called_once_with(application.api.get_errors("uid"))
    ignored.add_files.assert_called_once_with(
        application.api.get_unsynchronizeds("uid")
    )

    monkeypatch.setattr(application_module, "DriveSystrayIcon", Mock(return_value=tray))
    application.setup_systray()
    application.load_icons_set.assert_called_once_with(False)
    assert call(application_module.APP_NAME) in tray.setToolTip.call_args_list
    tray.show.assert_called_once_with()
