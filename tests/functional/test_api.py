from collections import namedtuple
from unittest.mock import patch

from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application


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

    # app = Application(manager)
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "check_local_folder_available", new=func):
            url = nuxeo_url + "/login.jsp?requestedUrl=ui"
            returned_val = drive_api.web_authentication(
                url,
                "/dummy-path",
                True,
            )
            assert returned_val
