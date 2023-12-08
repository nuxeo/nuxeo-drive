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
        return "Report"

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
            assert returned_val


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
        from nxdrive import utils

        with patch.object(utils, "disk_space", new=func):
            returned_val = drive_api.get_disk_space_info_to_width(
                "001", "dummy_path", 100
            )
            assert returned_val


def test_open_local(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def func(*args):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "open_local_file", new=func):
            returned_val = drive_api.open_local(None, "dummy_path")
            assert not returned_val


def test_open_document(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.open_document("engine_uid", 1)
        assert not returned_val


def test_open_remote_document(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_open_remote(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_remote", new=mocked_open_remote):
            returned_val = drive_api.open_remote_document(
                "dummy_uid", "dummy_remote_ref", "dummy_remote_path"
            )
            assert not returned_val


def test_get_remote_document_url(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_open_remote(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_remote", new=mocked_open_remote):
            returned_val = drive_api.get_remote_document_url(
                "dummy_uid", "dummy_remote_ref"
            )
            assert not returned_val


def test_open_remote(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_open_edit(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_open_edit):
            returned_val = drive_api.open_remote(
                "dummy_uid", "dummy_remote_ref", "dummy_remote_name"
            )
            assert not returned_val


def test_ignore_pair(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_ignore_pair(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_ignore_pair):
            returned_val = drive_api.ignore_pair(
                "dummy_uid", "dummy_state_id", "dummy_reason"
            )
            assert not returned_val


def test_retry_pair(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_retry_pair(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_retry_pair):
            returned_val = drive_api.retry_pair("dummy_uid", "dummy_state_id")
            assert not returned_val


def test_resolve_with_remote(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_resolve_with_remote(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_resolve_with_remote):
            returned_val = drive_api.resolve_with_remote("dummy_uid", "dummy_state_id")
            assert not returned_val


def test_resolve_with_local(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_resolve_with_local(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_resolve_with_local):
            returned_val = drive_api.resolve_with_local("dummy_uid", "dummy_state_id")
            assert not returned_val


def test_get_syncing_count(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_syncing_count(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_get_syncing_count):
            returned_val = drive_api.get_syncing_count("dummy_uid")
            assert type(returned_val) is int


def test_is_paused(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_is_paused(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.is_paused = mocked_is_paused

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        # with patch.object(manager, "is_paused", new=mocked_is_paused):
        returned_val = drive_api.is_paused()
        assert returned_val is mocked_is_paused


def test_suspend(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_resolve_with_local(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_resume(*args):
        return

    def mocked_suspend(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.resume = mocked_resume
    manager.suspend = mocked_suspend

    def func(*args):
        return True

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_resolve_with_local):
            returned_val = drive_api.suspend(True)
            assert not returned_val
            returned_val = drive_api.suspend(False)
            assert not returned_val


def test_restart_needed(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_resolve_with_local(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    def func(*args):
        return True

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_resolve_with_local):
            returned_val = drive_api.restart_needed()
            assert returned_val is mocked_restart_needed


def test_has_invalid_credentials(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_has_invalid_credentials(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(engine, "open_edit", new=mocked_has_invalid_credentials):
            returned_val = drive_api.has_invalid_credentials("dummy_uid")
            assert not returned_val


def test_get_deletion_behavior(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.get_deletion_behavior()
        assert returned_val


def test_set_deletion_behavior(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    def mocked_set_config(*args):
        return True

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "set_config", new=mocked_set_config):
            returned_val = drive_api.set_deletion_behavior("deletion_behavior")
            assert not returned_val


def test_set_proxy_settings(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_proxy(*args):
        return "dummy_proxy"

    def mocked_set_proxy(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray",
        defaults=(manager, mocked_open_authentication_dialog, mocked_hide_systray),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        with patch.object(manager, "set_proxy", new=mocked_set_proxy):
            returned_val = drive_api.set_proxy_settings(
                "Manual", "dummy_url", "dummy_pac_url"
            )
            assert returned_val


def test_open_direct_transfer(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    def mocked_refresh_direct_transfer_items(*args):
        return

    def mocked_refresh_active_sessions_items(*args):
        return

    def mocked_refresh_completed_sessions_items(*args):
        return

    def mocked_show_direct_transfer_window(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray, refresh_direct_transfer_items, \
            refresh_active_sessions_items, refresh_completed_sessions_items, show_direct_transfer_window,",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            mocked_hide_systray,
            mocked_refresh_direct_transfer_items,
            mocked_refresh_active_sessions_items,
            mocked_refresh_completed_sessions_items,
            mocked_show_direct_transfer_window,
        ),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.open_direct_transfer("dummy_uid")
        assert not returned_val


def test_open_server_folders(manager_factory):
    manager, engine = manager_factory()
    manager.application = ""
    engine.uid = "dummy_uid"

    def mocked_open_authentication_dialog():
        return

    def mocked_hide_systray(*args):
        return

    def mocked_get_metadata_url(*args):
        return

    def mocked_restart_needed(*args):
        return

    def mocked_show_server_folders(*args):
        return

    engine.get_metadata_url = mocked_get_metadata_url  # .__get__(engine)
    manager.restart_needed = mocked_restart_needed

    Mocked_App = namedtuple(
        "app",
        "manager, open_authentication_dialog, hide_systray, show_server_folders",
        defaults=(
            manager,
            mocked_open_authentication_dialog,
            mocked_hide_systray,
            mocked_show_server_folders,
        ),
    )
    app = Mocked_App()
    drive_api = QMLDriveApi(app)

    with manager:
        returned_val = drive_api.open_server_folders("dummy_uid")
        assert not returned_val
