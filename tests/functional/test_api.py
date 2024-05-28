from collections import namedtuple
from unittest.mock import Mock, patch

from nxdrive.gui.api import QMLDriveApi


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
        returned_val = drive_api.get_text("{'id': '1', 'price': '2000'}", "price")
        assert returned_val == "2000"


def test_text_red(manager_factory):
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
    print("1")
    manager, engine = manager_factory()

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
    dummy_task1 = dummy_task
    dummy_task1.directive = "wf.pleaseSelect"
    dummy_task2 = dummy_task
    dummy_task2.directive = "wf.give_opinion"
    dummy_task3 = dummy_task
    dummy_task3.directive = "wf.consolidate"
    dummy_task4 = dummy_task
    dummy_task4.directive = "wf.updateRequest"
    dummy_task_list = [dummy_task, dummy_task1, dummy_task2, dummy_task3, dummy_task4]

    def mocked_open_authentication_dialog():
        return

    def fetch_pending_tasks_(*args, **kwargs):
        return dummy_task_list

    def get_info_(*args, **kwargs):
        doc_info = Mock()
        doc_info.name = "dummy_doc_name"
        return doc_info

    print("2")

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, fetch_pending_tasks",
        defaults=(manager, mocked_open_authentication_dialog, fetch_pending_tasks_),
    )

    app = Mocked_App()
    manager.application = app

    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine.remote, "get_info", new=get_info_):
            returned_val = drive_api.get_Tasks_list(engine.uid)
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
