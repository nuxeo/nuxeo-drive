from collections import namedtuple
from copy import deepcopy
from unittest.mock import Mock, patch

from nxdrive.gui.api import QMLDriveApi
from nxdrive.translator import Translator
from nxdrive.utils import find_resource

from ..markers import mac_only


def test_web_authentication(manager_factory, nuxeo_url):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    def func(*args):
        return True

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()

    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "check_local_folder_available", new=func):
            url = f"{nuxeo_url}/login.jsp?requestedUrl=ui%2F"
            returned_val = drive_api.web_authentication(
                url,
                "/dummy-path",
                True,
            )
            assert not returned_val


def test_get_features_list(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_features_list()
        assert returned_val


def test_balance_percents(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api._balance_percents(
            {"key_1": 10.1, "key_2": 20, "key_3": 20.5}
        )
        assert returned_val


def test_get_text(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_text("{'id': '1', \"price\": '2000'}", "price")
        assert returned_val == "2000"
        returned_val = drive_api.get_text("dummy_text", "dummy")
        assert returned_val == ""


def test_text_red(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""
    Translator(find_resource("i18n"), lang="en")

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.text_red("Dummy sentence.")
        assert not returned_val


def test_open_tasks_window(manager_factory):
    manager, engine = manager_factory()

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args, **kwargs):
        return

    def mocked_show_tasks_window(*args, **kwargs):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray, show_tasks_window",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            mocked_hide_systray,
            mocked_show_tasks_window,
        ),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)
    manager.application = app

    with manager:
        returned_val = drive_api.open_tasks_window("dummy_uid")
        assert returned_val is None


def test_close_tasks_window(manager_factory):
    manager, engine = manager_factory()

    def mocked_open_authentication_dialog():
        return

    def mocked_close_tasks_window(*args, **kwargs):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, close_tasks_window",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            mocked_close_tasks_window,
        ),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)
    manager.application = app

    with manager:
        returned_val = drive_api.close_tasks_window()
        assert returned_val is None


def test_get_tasks_list(manager_factory):
    manager, engine = manager_factory()
    Translator(find_resource("i18n"), lang="en")

    dummy_task = Mock()
    dummy_task.actors = [{"id": "user:Administrator"}]
    dummy_task.created = "2024-04-04T08:31:04.366Z"
    dummy_task.directive = "wf.serialDocumentReview.AcceptReject"
    dummy_task.dueDate = "2024-04-09T08:31:04.365Z"
    dummy_task.id = "e7fc7a3a-5c39-479f-8382-65ed08e8116d"
    dummy_task.name = "wf.serialDocumentReview.DocumentValidation"
    dummy_task.targetDocumentIds = [{"id": "5b77e4dd-c155-410b-9d4d-e72f499638b8"}]
    dummy_task.workflowInstanceId = "81133cf7-38d9-483c-9a0b-c98fc02822a0"
    dummy_task.workflowModelName = "SerialDocumentReview"
    dummy_task1 = deepcopy(dummy_task)
    dummy_task1.directive = "wf.pleaseSelect"
    dummy_task2 = deepcopy(dummy_task)
    dummy_task2.directive = "wf.give_opinion"
    dummy_task3 = deepcopy(dummy_task)
    dummy_task3.directive = "wf.consolidate"
    dummy_task4 = deepcopy(dummy_task)
    dummy_task4.directive = "wf.updateRequest"
    dummy_task5 = deepcopy(dummy_task)
    dummy_task5.targetDocumentIds = 0
    dummy_task_list = [
        dummy_task,
        dummy_task1,
        dummy_task2,
        dummy_task3,
        dummy_task4,
        dummy_task5,
    ]

    def mocked_open_authentication_dialog():
        return

    def fetch_pending_tasks_(*args, **kwargs):
        return dummy_task_list

    def show_hide_refresh_button_(*args, **kwargs):
        return

    def get_info_(*args, **kwargs):
        doc_info = Mock()
        doc_info.name = "dummy_doc_name"
        return doc_info

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, fetch_pending_tasks, show_hide_refresh_button ",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            fetch_pending_tasks_,
            show_hide_refresh_button_,
        ),
    )

    app = Mocked_App()
    manager.application = app

    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine.remote, "get_info", new=get_info_):
            returned_val = drive_api.get_Tasks_list(engine.uid, True, True)
            assert isinstance(returned_val, list)
            assert isinstance(returned_val[0], Mock)


def test_get_username(manager_factory):
    manager, engine = manager_factory()
    engine.remote_user = "dummy user"
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_username(engine.uid)
        assert returned_val == "dummy user"


def test_on_clicked_open_task(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_open_task(*args, **kwargs):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, open_task",
        defaults=(manager, mocked_open_authentication_dialog, mocked_open_task),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.on_clicked_open_task(engine.uid, "dummy_task_id")
        assert not returned_val


def test_get_last_files(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_get_last_files(*args, **kwargs):
        return []

    for engine_ in manager.engines.copy().values():
        engine_.dao = Mock()
        engine_.dao.get_last_files = mocked_get_last_files

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_last_files(engine.uid, 1)
        assert not returned_val


def test_get_last_files_count(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_get_last_files_count(*args, **kwargs):
        return 25

    for engine_ in manager.engines.copy().values():
        engine_.dao = Mock()
        engine_.dao.get_last_files_count = mocked_get_last_files_count

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_last_files_count(engine.uid)
        assert returned_val == 25


def test_export_formatted_state(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    DocPair = namedtuple(
        "DocPair",
        "error_count, local_state, pair_state, processor",
        defaults=(0, "", "", 0),
    )
    doc_pair = DocPair()

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api._export_formatted_state("dummy_uid", state=doc_pair)
        assert not returned_val


def test_get_active_sessions_count(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_active_sessions_count("dummy_uid")
        assert returned_val == 0


def test_get_completed_sessions_count(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_completed_sessions_count("dummy_uid")
        assert returned_val == 0


def test_show_metadata(manager_factory, tmp):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray():
        return

    def mocked_show_metadata(*args):
        return

    def mocked_ffetch_pending_tasks(*args):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray, show_metadata",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            mocked_hide_systray,
            mocked_show_metadata,
        ),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.show_metadata("dummy_uid", "dummy")
        assert not returned_val
        with patch.object(
            drive_api, "fetch_pending_tasks", new=mocked_ffetch_pending_tasks
        ):
            returned_val = drive_api.show_metadata(engine.uid, str(tmp()))
            assert not returned_val


def test_get_unsynchronizeds(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_unsynchronizeds("dummy_uid")
        assert not returned_val


def test_get_engine(manager_factory, tmp):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray():
        return

    def mocked_fetch_pending_task_list(*args, **kwargs):
        return

    def mocked__fetch_tasks(*args, **kwargs):
        task = Mock()
        task.id = "dummy_id"
        return [task]

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)
    engine.fetch_pending_task_list = mocked_fetch_pending_task_list

    with manager:
        assert not drive_api.get_conflicts("dummy_uid")
        assert not drive_api.get_errors("dummy_uid")
        assert not drive_api.open_direct_transfer("dummy_uid")
        assert not drive_api.open_server_folders("dummy_uid")
        assert not drive_api.open_remote_server("dummy_uid")
        assert not drive_api.open_local("dummy_uid", str(tmp()))
        assert not drive_api.show_conflicts_resolution("dummy_uid")
        assert not drive_api.open_remote_server("dummy_uid")
        assert not drive_api.tasks_remaining("dummy_uid")
        with patch.object(drive_api, "_fetch_tasks", new=mocked__fetch_tasks):
            assert drive_api.tasks_remaining(engine.uid) == 1
            assert not drive_api.fetch_pending_tasks(engine)
        assert not drive_api.get_document_details("dummy_uid", "dummy_doc_id")
        assert not drive_api.web_update_token("dummy_uid")
        assert not drive_api.get_disk_space_info_to_width("dummy_uid", str(tmp()), 1)
        assert not drive_api.get_drive_disk_space("dummy_uid")
        assert not drive_api.get_used_space_without_synced("dummy_uid", str(tmp()))
        assert not drive_api.filters_dialog("dummy_uid")
        assert not drive_api.set_server_ui("dummy_uid", "dummy_server_ui")
        assert not drive_api.has_invalid_credentials("dummy_uid")
        assert not drive_api.handle_token(None, "dummy_user")
        drive_api.callback_params = ""
        assert not drive_api.handle_token(None, "dummy_user")
        assert drive_api.get_syncing_count("dummy_uid") == 0
        assert not drive_api.resolve_with_local("dummy_uid", 0)
        assert not drive_api.resolve_with_remote("dummy_uid", 0)
        assert not drive_api.retry_pair("dummy_uid", 0)
        assert not drive_api.ignore_pair("dummy_uid", 0, "none")
        assert not drive_api.open_remote("dummy_uid", "remote_ref", "remote_name")
        assert not drive_api.open_remote_document(
            "dummy_uid", "remote_ref", "remote_path"
        )
        assert not drive_api.get_remote_document_url("dummy_uid", "remote_ref")
        assert not drive_api.on_clicked_open_task("dummy_uid", "dummy_task_id")


@mac_only
def test_open_server_folders(manager_factory):

    from PyQt5.QtCore import QObject

    from nxdrive.gui.application import Application

    from .test_direct_transfer_path import Mock_Qt

    manager, engine = manager_factory()
    mock_qt = Mock_Qt()
    with patch(
        "PyQt5.QtQml.QQmlApplicationEngine.rootObjects"
    ) as mock_root_objects, patch(
        "PyQt5.QtCore.QObject.findChild"
    ) as mock_find_child, patch(
        "nxdrive.gui.application.Application.init_nxdrive_listener"
    ) as mock_listener, patch(
        "nxdrive.gui.application.Application.show_metrics_acceptance"
    ) as mock_show_metrics, patch(
        "nxdrive.engine.activity.FileAction.__repr__"
    ) as mock_download_repr, patch(
        "nxdrive.gui.application.Application.create_custom_window_for_task_manager"
    ) as mock_task_manager, patch(
        "nxdrive.gui.api.QMLDriveApi._get_engine"
    ) as mock_engine, patch(
        "nxdrive.gui.application.Application.hide_systray"
    ) as mock_hide, patch(
        "nxdrive.engine.workers.PollWorker._execute"
    ) as mock_execute, patch(
        "nxdrive.engine.workers.Worker.run"
    ) as mock_run, patch(
        "PyQt5.QtWidgets.QDialog.exec_"
    ) as mock_exec:
        mock_root_objects.return_value = [QObject()]
        mock_find_child.return_value = mock_qt
        mock_listener.return_value = None
        mock_show_metrics.return_value = None
        mock_download_repr.return_value = "Nuxeo Drive"
        mock_task_manager.return_value = None
        mock_execute.return_value = None
        mock_run.return_value = None
        mock_exec.return_value = None
        app = Application(manager)
        drive_api = QMLDriveApi(app)
        mock_engine.return_value = engine
        mock_hide.return_value = None
        assert drive_api.open_server_folders("engine.uid") is None
        app.exit(0)
        del app
