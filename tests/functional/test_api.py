from unittest.mock import patch

from nxdrive.gui.api import QMLDriveApi
from nxdrive.gui.application import Application


def test_web_authentication(manager_factory):
    manager, engine = manager_factory()

    def func(val):
        return True

    app = Application(manager)
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "check_local_folder_available", new=func):
            returned_val = drive_api.web_authentication(
                "http://localhost:8080/nuxeo/login.jsp?requestedUrl=ui%2F",
                "/dummy-path",
                True,
            )
            assert not returned_val
