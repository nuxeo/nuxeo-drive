from collections import namedtuple
from unittest.mock import patch
from uuid import uuid4

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


def test_display_pending_task(manager_factory):
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
        returned_val = drive_api.display_pending_task(
            str(uuid4()), str(uuid4()), "/doc_path"
        )
        assert returned_val is None
