from collections import namedtuple
from unittest.mock import patch  # Mock, patch

from nxdrive.gui.api import QMLDriveApi

# from nxdrive.gui.application import Application


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
