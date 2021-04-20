from io import BytesIO
from unittest.mock import patch

import pytest
import requests

from nxdrive import __version__
from nxdrive.feature import Feature
from nxdrive.options import Options
from nxdrive.poll_workers import ServerOptionsUpdater
from nxdrive.updater.base import BaseUpdater

# SHA256 of MockResponse.raw, see below
_checksum = "be9b795e95c7b4940cc40e023cfda1b4f22ed97d8c44d8ebc45625db532a2b12"

NEXT_VER = ".".join(f"{v + 1}" for v in map(int, __version__.split(".")))
VERSIONS = {
    __version__: {"type": "release", "min": "10.10"},
    NEXT_VER: {
        "type": "release",
        "min": "10.10",
        "checksum": {
            "algo": "sha256",
            "foo": _checksum,
        },
    },
    "4.4.0": {
        "type": "release",
        "min": "10.10",
        "checksum": {
            "algo": "sha256",
            "foo": _checksum,
        },
    },
    "4.5.0": {
        "type": "beta",
        "min": "10.10",
        "checksum": {
            "algo": "sha256",
            "foo": "bad_checksum",
        },
    },
}


class Updater(BaseUpdater):
    """Fake updater for our tests."""

    def __init__(self, *args):
        super().__init__(*args)

        self.ext = "foo"
        self.release_file = "nuxeo-drive-{version}.foo"

        self.checkpoint = False

    @property
    def server_ver(self):
        return "10.10"

    def install(self, filename: str) -> None:
        self.checkpoint = True

    def _fetch_versions(self):
        self.versions = VERSIONS


class MockResponse(requests.Response):
    """Mocked requests.Response to prevent downloading stuff."""

    def __init__(self):
        super().__init__()

        content_length = BaseUpdater.chunk_size * 4
        self.status_code = 200
        self.headers["Content-Length"] = str(content_length)
        self.raw = BytesIO(b"0" * content_length)


def mock_get(url, *_, **__):
    """Used by the monkeypatch fixture to patch requests.Response."""
    return MockResponse()


@pytest.fixture(scope="function")
def monkey_requests(monkeypatch):
    """Helper fixture to mimic requests.get() without actually downloading anything
    but still keeping all the logic present (like .raise_for_status() et al.).
    """
    monkeypatch.setattr(requests, "get", mock_get)
    try:
        yield
    finally:
        monkeypatch.undo()


def check_attrs(updater: Updater, enable: bool, checkpoint: bool, version: str) -> None:
    """Check Updater state before and after a forced recheck."""
    assert updater.enable is enable
    updater.refresh_status()
    assert updater.checkpoint is checkpoint
    assert updater.version == version


def test_not_frozen(manager_factory):
    """The application is not frozen."""
    Options.is_frozen = False

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen(manager_factory, monkey_requests):
    """The application is frozen."""
    Options.is_frozen = True

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)

        # The server config has not been fetched yet, no update possible then
        check_attrs(updater, True, False, "")

        # The server config has been fetched, the update can be done
        manager.server_config_updater.first_run = False
        check_attrs(updater, True, True, NEXT_VER)


@Options.mock()
def test_frozen_updates_disabled(manager_factory):
    """The application is frozen and auto-update disabled."""
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen_updates_disabled_centralized(manager_factory):
    """Scenario:
    - the application is frozen
    - auto-update disabled
    - channel set to centralized
    """
    Options.channel = "centralized"
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen_updates_disabled_centralized_client_version_invalid(manager_factory):
    """Scenario:
    - the application is frozen
    - auto-update disabled
    - channel set centralized
    - client_version is set to an invalid value
    """
    Options.channel = "centralized"
    Options.client_version = "4.0.0"
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)
        check_attrs(updater, False, False, "")


@Options.mock()
def test_frozen_updates_disabled_centralized_client_version(
    manager_factory, monkey_requests
):
    """Scenario:
        - the application is frozen
        - auto-update disabled
        - channel set centralized
        - client_version is set

    This scenario should unlock the auto-update. See NXDRIVE-2047.
    """
    Options.channel = "centralized"
    Options.client_version = "4.4.0"
    Options.is_frozen = True
    Options.update_check_delay = 0

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)

        # The server config has not been fetched yet, no update possible then
        check_attrs(updater, True, False, "")

        # The interval is modified, checks its value
        assert updater._check_interval == 3600

        # The server config has been fetched, the update can be done
        manager.server_config_updater.first_run = False
        check_attrs(updater, True, True, "4.4.0")


@Options.mock()
def test_installer_integrity_failure(manager_factory, monkey_requests):
    """Check installer integrity failure."""
    Options.is_frozen = True
    Options.client_version = "4.5.0"

    with manager_factory(with_engine=False) as manager:
        updater = Updater(manager)

        # The server config has been fetched, the update can be done
        manager.server_config_updater.first_run = False
        check_attrs(updater, True, False, "4.5.0")


@Options.mock()
def test_feature_auto_update(manager_factory, tmp_path):
    """The application is frozen and auto-update enabled, then disabled via the server config."""
    Options.is_frozen = True
    Options.nxdrive_home = tmp_path
    assert Feature.auto_update
    assert Options.feature_auto_update

    def disabled():
        return {"feature": {"auto-update": False}}

    manager, engine = manager_factory()
    with manager:
        updater = Updater(manager)
        server_updater = ServerOptionsUpdater(manager)

        manager.server_config_updater.first_run = False
        with patch.object(engine.remote, "get_server_configuration", new=disabled):
            server_updater._poll()
            assert not Feature.auto_update
            assert not Options.feature_auto_update
            check_attrs(updater, False, False, "")
