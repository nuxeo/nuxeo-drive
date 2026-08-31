"""Coverage for the process-wide Application constructor."""

from unittest.mock import MagicMock, patch

from nxdrive.drive.gui import application as application_module
from nxdrive.drive.gui.application import Application
from nxdrive.drive.options import Options
from nxdrive.drive.qt.imports import QApplication
from tests.markers import not_linux


_APPLICATIONS = []


@Options.mock()
@not_linux(reason="Linux session fixture already owns the QApplication singleton")
def test_application_constructor_initializes_services_and_optional_workers():
    assert QApplication.instance() is None

    manager = MagicMock()
    manager.preferences_metrics_chosen = False
    manager.direct_edit = MagicMock()
    manager.direct_download = MagicMock()
    manager.old_version = "1.0"
    manager.version = "2.0"
    Options.protocol_url = "nxdrive://test"

    with (
        patch.object(Application, "_init_translator") as init_translator,
        patch.object(Application, "show_metrics_acceptance") as show_metrics,
        patch.object(Application, "init_gui") as init_gui,
        patch.object(Application, "setup_systray") as setup_systray,
        patch.object(Application, "init_checks") as init_checks,
        patch.object(Application, "_setup_notification_center") as setup_notifications,
        patch.object(Application, "init_workflow") as init_workflow,
        patch.object(Application, "_show_release_notes") as show_release_notes,
        patch.object(Application, "init_nxdrive_listener") as init_listener,
        patch.object(Application, "_send_crash_metrics") as send_crash_metrics,
        patch.object(Application, "_handle_nxdrive_url") as handle_protocol_url,
        patch.object(application_module, "today_is_special", return_value=False),
    ):
        init_gui.side_effect = lambda: setattr(
            QApplication.instance(), "direct_download_monitoring_model", MagicMock()
        )
        application = Application(manager, ["nuxeo-drive-test"])

    _APPLICATIONS.append(application)

    assert manager.application is application
    assert application.manager is manager
    assert application.osi is manager.osi
    assert application.timer.isActive()
    assert application.applicationName() == application_module.APP_NAME
    assert application.quitOnLastWindowClosed() is False
    assert application.default_tooltip == application_module.APP_NAME
    assert application.added_user_engine_list == [str]
    assert application.workflow is None
    init_translator.assert_called_once_with()
    show_metrics.assert_called_once_with()
    init_gui.assert_called_once_with()
    setup_systray.assert_called_once_with()
    init_checks.assert_called_once_with()
    init_workflow.assert_called_once_with()
    show_release_notes.assert_called_once_with("1.0", "2.0")
    init_listener.assert_called_once_with()
    send_crash_metrics.assert_called_once_with()
    handle_protocol_url.assert_called_once_with("nxdrive://test")
    if application_module.MAC:
        setup_notifications.assert_called_once_with()
    else:
        setup_notifications.assert_not_called()

    manager.direct_edit.directEditConflict.connect.assert_called_once_with(
        application._direct_edit_conflict
    )
    manager.direct_download.downloadProgress.connect.assert_called_once_with(
        application.direct_download_monitoring_model.set_progress
    )

    application.timer.stop()
