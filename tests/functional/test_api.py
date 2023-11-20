from collections import namedtuple
from unittest.mock import patch

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


def test_generate_report(manager_factory):
    manager = manager_factory(with_engine=False)
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def func(*args):
        return 1 / 0

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "generate_report", new=func):
            returned_val = drive_api.generate_report()
            assert not returned_val


def test_get_disk_space_info_to_width(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def func(*args):
        return 100, 200

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog",
        defaults=(manager, mocked_open_authentication_dialog),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "disk_space", new=func):
            returned_val = drive_api.get_disk_space_info_to_width()
            assert not returned_val
